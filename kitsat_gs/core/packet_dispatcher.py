"""
PacketDispatcher — receives raw parsed packets from ModemBridge and routes
them to the TelemetryStore after applying housekeeping unit conversions.

Also works around known bugs in kitsat's packet_parser:
  - EPS (origin=8) binary parse is broken upstream; we handle it here
  - GPS "nofix" case missing return is handled defensively
"""

from __future__ import annotations

import struct
import time
from typing import Optional

from PySide6.QtCore import QObject, Slot
from loguru import logger

from kitsat_gs.core import housekeeping_catalog
from kitsat_gs.core.telemetry_store import TelemetryStore


class PacketDispatcher(QObject):
    def __init__(self, store: TelemetryStore, parent=None) -> None:
        super().__init__(parent)
        self._store = store

    @Slot(object)
    def dispatch(self, msg: object) -> None:
        """
        Called for every message emitted by ModemBridge.message_received.
        msg is either a list [origin, cmd_id, data_len, timestamp, data, fnv]
        or a plain string (non-packet output).
        """
        if not isinstance(msg, list) or len(msg) < 5:
            return

        origin: int = msg[0]
        cmd_id: int = msg[1]
        data_len: int = msg[2]
        sat_timestamp: int = msg[3]
        data = msg[4]   # str or bytes depending on kitsat version

        hk = housekeeping_catalog.by_command(origin, cmd_id)
        if hk is None:
            return  # Not a housekeeping measurement we track

        ts = time.time()

        try:
            raw_values = self._parse_data(origin, cmd_id, data, data_len)
        except Exception as exc:
            logger.warning(f"PacketDispatcher: parse error origin={origin} cmd={cmd_id}: {exc}")
            return

        if raw_values is None:
            return

        converted = hk.convert(raw_values)
        self._store.record_packet(
            hk.type, hk.subtype, hk.subvalues, converted, timestamp=ts
        )

    # ------------------------------------------------------------------
    # Per-subsystem binary parsers
    # ------------------------------------------------------------------

    def _parse_data(
        self, origin: int, cmd_id: int, data, data_len: int
    ) -> Optional[list[float]]:
        """Return a list of raw floats, or None to skip."""

        # IMU — 9 floats (mag x/y/z, gyr x/y/z, acc x/y/z)
        if origin == 5 and cmd_id == 14:
            return self._unpack_floats(data, 9)

        # IMU sub-commands — 3 floats each
        if origin == 5 and cmd_id in (1, 5, 9):
            return self._unpack_floats(data, 3)

        # GPS location — lat, lon (2 floats from full gps_get_all payload)
        if origin == 3 and cmd_id == 2:
            vals = self._unpack_floats(data, 2)
            return vals

        # GPS velocity
        if origin == 3 and cmd_id == 3:
            vals = self._unpack_floats(data, 1)
            return vals

        # GPS altitude
        if origin == 3 and cmd_id == 4:
            vals = self._unpack_floats(data, 1)
            return vals

        # Environment — single float
        if origin == 4 and cmd_id in (1, 2):
            vals = self._unpack_floats(data, 1)
            return vals

        # EPS battery voltage (origin=8, cmd_id=1) — single float
        # Upstream kitsat EPS parser is broken; we handle it here directly.
        if origin == 8 and cmd_id == 1:
            return self._unpack_floats(data, 1)

        # EPS solar panel voltage (origin=8, cmd_id=2) — 4 floats
        if origin == 8 and cmd_id == 2:
            return self._unpack_floats(data, 4)

        # EPS solar panel current (origin=8, cmd_id=3) — 2 floats
        if origin == 8 and cmd_id == 3:
            return self._unpack_floats(data, 2)

        return None

    @staticmethod
    def _unpack_floats(data, count: int) -> list[float]:
        raw = data if isinstance(data, (bytes, bytearray)) else data.encode("latin-1")
        needed = count * 4
        if len(raw) < needed:
            raise ValueError(f"Expected {needed} bytes for {count} floats, got {len(raw)}")
        return list(struct.unpack_from(f"<{count}f", raw))
