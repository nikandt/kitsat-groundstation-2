"""Ground station visibility and pass prediction."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional

from .propagator import OrbitPropagator, OrbitState


@dataclass
class PassInfo:
    aos: Optional[datetime]     # Acquisition of Signal
    los: Optional[datetime]     # Loss of Signal
    max_elevation: float = 0.0
    max_el_time: Optional[datetime] = None


def _elevation_angle(gs_lat: float, gs_lon: float,
                     sat_lat: float, sat_lon: float,
                     sat_alt_km: float) -> float:
    Re = 6371.0
    gs_lat_r = math.radians(gs_lat)
    gs_lon_r = math.radians(gs_lon)
    sat_lat_r = math.radians(sat_lat)
    sat_lon_r = math.radians(sat_lon)

    cos_rho = (math.sin(gs_lat_r) * math.sin(sat_lat_r)
               + math.cos(gs_lat_r) * math.cos(sat_lat_r)
               * math.cos(sat_lon_r - gs_lon_r))
    rho = math.acos(max(-1.0, min(1.0, cos_rho)))

    R_sat = Re + sat_alt_km
    elevation_r = math.atan2(
        math.cos(rho) - Re / R_sat,
        math.sin(rho)
    )
    return math.degrees(elevation_r)


class GroundStation:
    """Ground station: elevation angle calculation and pass prediction."""

    DEFAULT_LAT = 60.185
    DEFAULT_LON = 24.833
    DEFAULT_ALT_M = 10.0

    def __init__(self, name: str = "Otaniemi GS",
                 lat: float = DEFAULT_LAT,
                 lon: float = DEFAULT_LON,
                 alt_m: float = DEFAULT_ALT_M,
                 min_elevation: float = 5.0):
        self.name = name
        self.lat = lat
        self.lon = lon
        self.alt_m = alt_m
        self.min_elevation = min_elevation

    def elevation_to(self, state: OrbitState) -> float:
        return _elevation_angle(self.lat, self.lon,
                                state.latitude, state.longitude,
                                state.altitude_km)

    def is_visible(self, state: OrbitState) -> bool:
        return self.elevation_to(state) >= self.min_elevation

    def find_next_pass(self, propagator: OrbitPropagator,
                       start: datetime,
                       search_window_h: float = 24.0,
                       step_s: float = 30.0) -> PassInfo:
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

        t = start
        end = start + timedelta(hours=search_window_h)
        step = timedelta(seconds=step_s)

        aos: Optional[datetime] = None
        los: Optional[datetime] = None
        max_el = 0.0
        max_el_time: Optional[datetime] = None
        in_pass = False

        while t < end:
            state = propagator.propagate(t)
            el = self.elevation_to(state)

            if not in_pass and el >= self.min_elevation:
                aos = self._refine_crossing(propagator, t - step, t, True)
                in_pass = True
                max_el = el
                max_el_time = t
            elif in_pass:
                if el > max_el:
                    max_el = el
                    max_el_time = t
                if el < self.min_elevation:
                    los = self._refine_crossing(propagator, t - step, t, False)
                    return PassInfo(aos=aos, los=los,
                                   max_elevation=max_el, max_el_time=max_el_time)
            t += step

        if in_pass:
            return PassInfo(aos=aos, los=end,
                           max_elevation=max_el, max_el_time=max_el_time)
        return PassInfo(aos=None, los=None)

    def _refine_crossing(self, propagator: OrbitPropagator,
                         t1: datetime, t2: datetime,
                         find_aos: bool, iterations: int = 8) -> datetime:
        for _ in range(iterations):
            tm = t1 + (t2 - t1) / 2
            state = propagator.propagate(tm)
            el = self.elevation_to(state)
            above = el >= self.min_elevation
            if find_aos:
                if above:
                    t2 = tm
                else:
                    t1 = tm
            else:
                if above:
                    t1 = tm
                else:
                    t2 = tm
        return t1 + (t2 - t1) / 2

    def format_pass_info(self, info: PassInfo, now: datetime) -> str:
        if info.aos is None:
            return "No pass in next 24 h"
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        aos_str = info.aos.strftime("%H:%M:%S UTC") if info.aos else "—"
        los_str = info.los.strftime("%H:%M:%S UTC") if info.los else "—"
        dur = (info.los - info.aos).seconds if info.aos and info.los else 0
        mins, secs = divmod(dur, 60)
        return (f"AOS: {aos_str}  |  LOS: {los_str}  |  "
                f"Duration: {mins}m {secs:02d}s  |  "
                f"Max El: {info.max_elevation:.1f}°")
