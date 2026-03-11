"""
TelemetryStore — thread-safe time-series ring buffer for charting and display.

Each measurement is stored as a (unix_timestamp, value) pair per channel key.
Keys follow the pattern  "Type/Subtype/subvalue"  e.g. "Attitude/Magnetometer/x".
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque

from PySide6.QtCore import QObject, Signal

DEFAULT_MAX_SAMPLES = 500


@dataclass
class Sample:
    timestamp: float   # Unix time
    value: float


class TelemetryStore(QObject):
    """
    Stores telemetry samples and emits updated() whenever new data arrives.
    Safe to write from any thread; reads are also thread-safe.
    """

    updated = Signal(str)   # emits the key that was updated

    def __init__(self, max_samples: int = DEFAULT_MAX_SAMPLES, parent=None) -> None:
        super().__init__(parent)
        self._max = max_samples
        self._lock = threading.Lock()
        self._data: dict[str, Deque[Sample]] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, key: str, value: float, timestamp: float | None = None) -> None:
        """Record a single scalar value for the given key."""
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            if key not in self._data:
                self._data[key] = deque(maxlen=self._max)
            self._data[key].append(Sample(ts, value))
        self.updated.emit(key)

    def record_packet(
        self,
        type_: str,
        subtype: str,
        subvalues: list[str],
        converted: list[float],
        timestamp: float | None = None,
    ) -> None:
        """Record a multi-channel packet (e.g. IMU x/y/z)."""
        ts = timestamp if timestamp is not None else time.time()
        if subvalues:
            for sv, val in zip(subvalues, converted):
                self.record(f"{type_}/{subtype}/{sv}", val, ts)
        else:
            self.record(f"{type_}/{subtype}", converted[0] if converted else 0.0, ts)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def latest(self, key: str) -> Sample | None:
        with self._lock:
            buf = self._data.get(key)
            return buf[-1] if buf else None

    def series(self, key: str) -> list[Sample]:
        """Return a snapshot of all samples for the given key."""
        with self._lock:
            buf = self._data.get(key)
            return list(buf) if buf else []

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._data.keys())

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
