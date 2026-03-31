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

        ts = time.time()

        # Combined commands return data for multiple HK channels in one packet.
        # Handle them before the single-channel catalog lookup.
        if self._dispatch_combined(origin, cmd_id, data, ts):
            return

        hk = housekeeping_catalog.by_command(origin, cmd_id)
        if hk is None:
            logger.debug(f"PacketDispatcher: no HK entry for origin={origin} cmd_id={cmd_id} — dropped")
            return  # Not a housekeeping measurement we track

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

    # ------------------------------------------------------------------
    # Combined-packet splitter
    # ------------------------------------------------------------------

    def _dispatch_combined(self, origin: int, cmd_id: int, data, ts: float) -> bool:
        """
        Split combined multi-sensor packets into individual HK records.
        Returns True if the packet was handled (caller should not process further).
        """

        # imu_get_all (5, 14): 9 floats — mag[0:3], gyr[3:6], acc[6:9]
        if origin == 5 and cmd_id == 14:
            try:
                floats = self._decode_imu_all(data)
            except Exception as exc:
                logger.warning(f"PacketDispatcher: imu_get_all decode error: {exc}")
                return True
            for sub_cmd, vals in [(1, floats[0:3]), (5, floats[3:6]), (9, floats[6:9])]:
                hk = housekeeping_catalog.by_command(5, sub_cmd)
                if hk:
                    self._store.record_packet(
                        hk.type, hk.subtype, hk.subvalues, hk.convert(list(vals)), ts
                    )
            return True

        # gps_get_all (3, 6): ASCII CSV — lat, lon, alt_m, vel, time_hhmmss
        # The satellite sends a pre-formatted ASCII string (UTF-8 decode succeeds),
        # so binary unpack would give garbage. Parse as CSV directly.
        if origin == 3 and cmd_id == 6:
            try:
                if isinstance(data, str):
                    parts = [float(x.strip()) for x in data.split(",")]
                else:
                    parts = self._unpack_floats(data, 5)
                if len(parts) < 4:
                    raise ValueError(f"Expected ≥4 GPS values, got {len(parts)}")
            except Exception as exc:
                logger.warning(f"PacketDispatcher: gps_get_all decode error: {exc}")
                return True
            lat, lon = parts[0], parts[1]
            if lat == -1.0 or lon == -1.0 or (lat == 0.0 and lon == 0.0):
                logger.debug("PacketDispatcher: GPS no fix")
                return True
            for sub_cmd, vals in [
                (2, [lat, lon]),       # lat/lon (deg)
                (4, [parts[2]]),       # altitude (m)
                (3, [parts[3]]),       # velocity (knots → m/s via catalog multiplier)
            ]:
                hk = housekeeping_catalog.by_command(3, sub_cmd)
                if hk:
                    self._store.record_packet(
                        hk.type, hk.subtype, hk.subvalues, hk.convert(vals), ts
                    )
            return True

        # eps_measure (8, 4): ASCII CSV — curr_x, curr_y, v_xm, v_xp, v_ym, v_yp, v_batt, ...
        if origin == 8 and cmd_id == 4:
            try:
                raw_str = data if isinstance(data, str) else data.decode("ascii", errors="replace")
                parts = [float(x.strip()) for x in raw_str.split(",")]
                if len(parts) < 7:
                    raise ValueError(f"Expected ≥7 CSV values, got {len(parts)}")
            except Exception as exc:
                logger.warning(f"PacketDispatcher: eps_measure decode error: {exc}")
                return True
            # Currents X, Y → (8, 3)
            hk = housekeeping_catalog.by_command(8, 3)
            if hk:
                self._store.record_packet(
                    hk.type, hk.subtype, hk.subvalues, hk.convert([parts[0], parts[1]]), ts
                )
            # Solar panel voltages: CSV = xm, xp, ym, yp; catalog subvalues = X+|X-|Y-|Y+
            hk = housekeeping_catalog.by_command(8, 2)
            if hk:
                xm, xp = max(0.0, parts[2]), max(0.0, parts[3])
                ym, yp = max(0.0, parts[4]), max(0.0, parts[5])
                self._store.record_packet(
                    hk.type, hk.subtype, hk.subvalues, hk.convert([xp, xm, ym, yp]), ts
                )
            # Battery voltage → (8, 1)
            hk = housekeeping_catalog.by_command(8, 1)
            if hk:
                self._store.record_packet(
                    hk.type, hk.subtype, hk.subvalues, hk.convert([parts[6]]), ts
                )
            return True

        return False

    def _decode_imu_all(self, data) -> list[float]:
        """
        Decode imu_get_all payload as 9 floats.

        packet_parser.parse_bytedata may have already processed the bytes in one
        of two ways:
          1. UTF-8 decode succeeded → data is a raw-escaped string; re-encode with
             latin-1 to recover the original bytes, then struct-unpack.
          2. UnicodeDecodeError occurred and parse_imu() was called → data is a
             formatted string like "mag x,y,z; gyr x,y,z; acc x,y,z"; parse directly.
        """
        import re
        if isinstance(data, str) and data.startswith("mag "):
            nums = [float(x) for x in re.findall(r"[-+]?\d*\.?\d+", data)]
            if len(nums) < 9:
                raise ValueError(f"Only {len(nums)} numbers in pre-formatted IMU string")
            return nums[:9]
        return self._unpack_floats(data, 9)
