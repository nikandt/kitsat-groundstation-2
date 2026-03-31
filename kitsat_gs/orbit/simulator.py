"""QTimer-driven orbit simulation clock with speed multiplier."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QObject, QTimer, Signal

from .propagator import OrbitPropagator, OrbitState
from .ground_station import GroundStation, PassInfo


class OrbitSimulator(QObject):
    """Tick the propagator at a configurable wall-clock rate and emit
    orbit data via Qt signals (also forwarded to the EventBus).

    Speeds: 1× / 10× / 60× / 600×
    """

    state_updated = Signal(object)   # OrbitState
    pass_updated = Signal(object)    # PassInfo

    SPEEDS = {1: "1×", 10: "10×", 60: "60×", 600: "600×"}

    def __init__(self, propagator: OrbitPropagator = None,
                 ground_station: GroundStation = None,
                 parent=None):
        super().__init__(parent)
        self._propagator = propagator or OrbitPropagator()
        self._gs = ground_station or GroundStation()
        self._speed = 1
        self._tick_ms = 1000
        self._sim_step_s = 1.0
        self._sim_time = datetime.now(timezone.utc)
        self._running = False
        self._pass_info = PassInfo(aos=None, los=None)
        self._pass_refresh_counter = 0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._sim_time = datetime.now(timezone.utc)
        self._running = True
        self._timer.start(self._tick_ms)

    def stop(self) -> None:
        self._running = False
        self._timer.stop()

    def set_speed(self, multiplier: int) -> None:
        self._speed = multiplier
        self._tick_ms = max(200, 1000 // max(1, multiplier // 10))
        self._sim_step_s = multiplier * (self._tick_ms / 1000.0)
        if self._running:
            self._timer.start(self._tick_ms)

    def update_tle(self, line1: str, line2: str) -> None:
        self._propagator.update_tle(line1, line2)

    def update_ground_station(self, lat: float, lon: float, alt_m: float) -> None:
        self._gs = GroundStation(lat=lat, lon=lon, alt_m=alt_m)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def sim_time(self) -> datetime:
        return self._sim_time

    @property
    def speed(self) -> int:
        return self._speed

    @property
    def ground_station(self) -> GroundStation:
        return self._gs

    @property
    def propagator(self) -> OrbitPropagator:
        return self._propagator

    def get_ground_track(self, points: int = 90) -> list:
        return self._propagator.get_ground_track(
            self._sim_time, points=points, step_s=60.0
        )

    def get_current_state(self) -> OrbitState:
        return self._propagator.propagate(self._sim_time)

    def get_current_elevation(self) -> float:
        state = self.get_current_state()
        return self._gs.elevation_to(state)

    def get_pass_info(self) -> PassInfo:
        return self._pass_info

    def force_pass_refresh(self) -> PassInfo:
        self._refresh_pass()
        return self._pass_info

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        self._sim_time += timedelta(seconds=self._sim_step_s)
        state = self._propagator.propagate(self._sim_time)
        self.state_updated.emit(state)

        self._pass_refresh_counter += 1
        if self._pass_refresh_counter >= 30:
            self._pass_refresh_counter = 0
            self._refresh_pass()
            self.pass_updated.emit(self._pass_info)

    def _refresh_pass(self) -> None:
        self._pass_info = self._gs.find_next_pass(
            self._propagator, self._sim_time,
            search_window_h=6.0, step_s=30.0
        )
