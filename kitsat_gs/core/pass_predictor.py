"""
PassPredictor — predict satellite passes over a ground station using sgp4.

Coordinate conversions:
  TEME (sgp4 output) → ECEF → geodetic (lat/lon/alt)
  Ground station elevation angle calculation

Usage:
    from kitsat_gs.core.pass_predictor import PassPredictor, GroundStation
    gs = GroundStation(lat=60.17, lon=24.94, alt_m=10)
    predictor = PassPredictor(tle, gs)
    passes = predictor.find_passes(days=3)
    track = predictor.ground_track(minutes=100)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sgp4.api import Satrec, jday
from loguru import logger

from kitsat_gs.core.tle_parser import Tle

# Earth constants (WGS84)
_RE = 6378.137      # km
_F = 1 / 298.257223563
_E2 = 2 * _F - _F ** 2


@dataclass
class GroundStation:
    lat: float          # degrees
    lon: float          # degrees
    alt_m: float = 0.0  # metres above sea level


@dataclass
class SkyPoint:
    """Azimuth/elevation at a specific moment."""
    time: datetime
    azimuth: float      # degrees, 0=N, 90=E
    elevation: float    # degrees above horizon
    range_km: float
    lat: float          # satellite geodetic latitude
    lon: float          # satellite geodetic longitude
    alt_km: float       # satellite altitude


@dataclass
class PassInfo:
    aos: datetime                    # Acquisition of Signal
    los: datetime                    # Loss of Signal
    max_el_time: datetime
    max_elevation: float             # degrees
    sky_points: list[SkyPoint] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return (self.los - self.aos).total_seconds()


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def _gmst(jd: float, fr: float) -> float:
    """Greenwich Mean Sidereal Time in radians."""
    tut1 = (jd + fr - 2451545.0) / 36525.0
    gmst = (67310.54841
            + tut1 * (876600 * 3600 + 8640184.812866)
            + tut1 ** 2 * 0.093104
            - tut1 ** 3 * 6.2e-6)
    return math.radians(gmst % 86400 / 240.0)


def _teme_to_ecef(r_teme: tuple, jd: float, fr: float) -> tuple[float, float, float]:
    theta = _gmst(jd, fr)
    c, s = math.cos(theta), math.sin(theta)
    x = c * r_teme[0] + s * r_teme[1]
    y = -s * r_teme[0] + c * r_teme[1]
    z = r_teme[2]
    return x, y, z


def _ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float, float, float]:
    """Returns (lat_deg, lon_deg, alt_km)."""
    lon = math.degrees(math.atan2(y, x))
    p = math.sqrt(x ** 2 + y ** 2)
    lat = math.atan2(z, p * (1 - _E2))
    for _ in range(10):
        sin_lat = math.sin(lat)
        N = _RE / math.sqrt(1 - _E2 * sin_lat ** 2)
        lat = math.atan2(z + _E2 * N * sin_lat, p)
    sin_lat = math.sin(lat)
    N = _RE / math.sqrt(1 - _E2 * sin_lat ** 2)
    alt = p / math.cos(lat) - N if abs(math.degrees(lat)) < 89 else z / sin_lat - N * (1 - _E2)
    return math.degrees(lat), lon, alt


def _elevation_azimuth(
    sat_ecef: tuple[float, float, float],
    gs: GroundStation,
) -> tuple[float, float, float]:
    """Return (elevation_deg, azimuth_deg, range_km) from ground station to satellite."""
    lat_r = math.radians(gs.lat)
    lon_r = math.radians(gs.lon)
    alt_km = gs.alt_m / 1000.0

    sin_lat, cos_lat = math.sin(lat_r), math.cos(lat_r)
    sin_lon, cos_lon = math.sin(lon_r), math.cos(lon_r)

    N = _RE / math.sqrt(1 - _E2 * sin_lat ** 2)
    gx = (N + alt_km) * cos_lat * cos_lon
    gy = (N + alt_km) * cos_lat * sin_lon
    gz = (N * (1 - _E2) + alt_km) * sin_lat

    dx, dy, dz = sat_ecef[0] - gx, sat_ecef[1] - gy, sat_ecef[2] - gz
    range_km = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)

    # SEZ (South-East-Zenith) frame
    s = sin_lat * cos_lon * dx + sin_lat * sin_lon * dy - cos_lat * dz
    e = -sin_lon * dx + cos_lon * dy
    z_comp = cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz

    elevation = math.degrees(math.asin(z_comp / range_km))
    azimuth = math.degrees(math.atan2(e, -s)) % 360.0

    return elevation, azimuth, range_km


# ---------------------------------------------------------------------------
# PassPredictor
# ---------------------------------------------------------------------------

class PassPredictor:
    def __init__(self, tle: Tle, ground_station: GroundStation) -> None:
        self._sat = Satrec.twoline2rv(tle.line1, tle.line2)
        self._gs = ground_station

    def _propagate(self, dt: datetime) -> Optional[SkyPoint]:
        jd, fr = jday(dt.year, dt.month, dt.day, dt.hour, dt.minute,
                      dt.second + dt.microsecond / 1e6)
        err, r, _ = self._sat.sgp4(jd, fr)
        if err != 0:
            return None
        ecef = _teme_to_ecef(r, jd, fr)
        el, az, rng = _elevation_azimuth(ecef, self._gs)
        lat, lon, alt = _ecef_to_geodetic(*ecef)
        return SkyPoint(time=dt, azimuth=az, elevation=el, range_km=rng,
                        lat=lat, lon=lon, alt_km=alt)

    def find_passes(
        self,
        start: Optional[datetime] = None,
        days: float = 3.0,
        min_elevation: float = 0.0,
        step_coarse_s: int = 30,
        step_fine_s: int = 5,
    ) -> list[PassInfo]:
        """Find all passes above min_elevation within the given time window."""
        if start is None:
            start = datetime.now(timezone.utc)

        end = start + timedelta(days=days)
        passes: list[PassInfo] = []
        in_pass = False
        aos_time: Optional[datetime] = None
        pass_points: list[SkyPoint] = []

        t = start
        while t < end:
            pt = self._propagate(t)
            if pt is None:
                t += timedelta(seconds=step_coarse_s)
                continue

            if pt.elevation >= min_elevation and not in_pass:
                # Refine AOS with fine steps
                in_pass = True
                aos_time = t
                pass_points = []
                step = step_fine_s
            elif pt.elevation < min_elevation and in_pass:
                # Refine LOS and close the pass
                in_pass = False
                if pass_points:
                    max_pt = max(pass_points, key=lambda p: p.elevation)
                    passes.append(PassInfo(
                        aos=aos_time,
                        los=t,
                        max_el_time=max_pt.time,
                        max_elevation=max_pt.elevation,
                        sky_points=pass_points,
                    ))
                step = step_coarse_s
            else:
                step = step_fine_s if in_pass else step_coarse_s

            if in_pass:
                pass_points.append(pt)

            t += timedelta(seconds=step)

        logger.debug(f"Found {len(passes)} passes over {days:.1f} days")
        return passes

    def ground_track(
        self,
        start: Optional[datetime] = None,
        minutes: float = 100.0,
        step_s: int = 30,
    ) -> list[tuple[float, float]]:
        """Return a list of (lat, lon) for the satellite ground track."""
        if start is None:
            start = datetime.now(timezone.utc)
        points: list[tuple[float, float]] = []
        end = start + timedelta(minutes=minutes)
        t = start
        while t < end:
            jd, fr = jday(t.year, t.month, t.day, t.hour, t.minute,
                          t.second + t.microsecond / 1e6)
            err, r, _ = self._sat.sgp4(jd, fr)
            if err == 0:
                ecef = _teme_to_ecef(r, jd, fr)
                lat, lon, _ = _ecef_to_geodetic(*ecef)
                points.append((lat, lon))
            t += timedelta(seconds=step_s)
        return points

    def current_position(self) -> Optional[SkyPoint]:
        return self._propagate(datetime.now(timezone.utc))
