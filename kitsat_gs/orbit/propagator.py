"""SGP4-based orbit propagator with circular fallback."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Tuple, List

try:
    from sgp4.api import Satrec, jday
    SGP4_AVAILABLE = True
except ImportError:
    SGP4_AVAILABLE = False


@dataclass
class OrbitState:
    timestamp: datetime
    latitude: float     # degrees
    longitude: float    # degrees
    altitude_km: float
    velocity_km_s: float
    # ECI components (km, km/s)
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0


# Synthetic SSO TLE — ~550 km, 97.6° inclination
_SSO_TLE_LINE1 = (
    "1 99999U 24001A   24001.00000000  .00000000  00000-0  00000-0 0  9990"
)
_SSO_TLE_LINE2 = (
    "2 99999  97.6000   0.0000 0001000  90.0000 270.0000 15.19000000    10"
)


def _eci_to_geodetic(x: float, y: float, z: float,
                     jd: float, jdf: float) -> Tuple[float, float, float]:
    """Convert ECI (km) to geodetic lat/lon/alt using oblate spheroid."""
    theta_gmst = _gmst(jd + jdf)
    cos_t = math.cos(theta_gmst)
    sin_t = math.sin(theta_gmst)
    x_ecef = x * cos_t + y * sin_t
    y_ecef = -x * sin_t + y * cos_t
    z_ecef = z

    a = 6378.137
    f = 1 / 298.257223563
    e2 = 2 * f - f * f

    lon = math.degrees(math.atan2(y_ecef, x_ecef))
    p = math.sqrt(x_ecef**2 + y_ecef**2)
    lat = math.degrees(math.atan2(z_ecef, p * (1 - e2)))
    for _ in range(5):
        lat_r = math.radians(lat)
        N = a / math.sqrt(1 - e2 * math.sin(lat_r)**2)
        lat = math.degrees(math.atan2(z_ecef + e2 * N * math.sin(lat_r), p))

    lat_r = math.radians(lat)
    N = a / math.sqrt(1 - e2 * math.sin(lat_r)**2)
    alt = p / math.cos(lat_r) - N if abs(lat) < 89.9 else z_ecef / math.sin(lat_r) - N * (1 - e2)
    return lat, lon, alt


def _gmst(jd_ut1: float) -> float:
    T = (jd_ut1 - 2451545.0) / 36525.0
    theta = (67310.54841 + (876600 * 3600 + 8640184.812866) * T
             + 0.093104 * T**2 - 6.2e-6 * T**3)
    return math.radians(theta % 86400 / 240.0)


class OrbitPropagator:
    """SGP4-based propagator. Falls back to simple circular orbit if sgp4
    is unavailable or the TLE parse fails."""

    def __init__(self, tle_line1: str = _SSO_TLE_LINE1,
                 tle_line2: str = _SSO_TLE_LINE2):
        self._tle1 = tle_line1
        self._tle2 = tle_line2
        self._sat = None
        self._use_sgp4 = False

        if SGP4_AVAILABLE:
            try:
                self._sat = Satrec.twoline2rv(tle_line1, tle_line2)
                self._use_sgp4 = True
            except Exception:
                pass

        self._period_s = 5580.0
        self._inc_rad = math.radians(97.6)

    def update_tle(self, line1: str, line2: str) -> None:
        self._tle1, self._tle2 = line1, line2
        self._use_sgp4 = False
        if SGP4_AVAILABLE:
            try:
                self._sat = Satrec.twoline2rv(line1, line2)
                self._use_sgp4 = True
            except Exception:
                pass

    def propagate(self, t: datetime) -> OrbitState:
        if self._use_sgp4 and self._sat is not None:
            return self._propagate_sgp4(t)
        return self._propagate_circular(t)

    def _propagate_sgp4(self, t: datetime) -> OrbitState:
        jd, jdf = jday(t.year, t.month, t.day,
                       t.hour, t.minute, t.second + t.microsecond / 1e6)
        e, r, v = self._sat.sgp4(jd, jdf)
        if e != 0:
            return self._propagate_circular(t)
        x, y, z = r
        vx, vy, vz = v
        lat, lon, alt = _eci_to_geodetic(x, y, z, jd, jdf)
        velocity = math.sqrt(vx**2 + vy**2 + vz**2)
        return OrbitState(
            timestamp=t, latitude=lat, longitude=lon,
            altitude_km=alt, velocity_km_s=velocity,
            x=x, y=y, z=z, vx=vx, vy=vy, vz=vz,
        )

    def _propagate_circular(self, t: datetime) -> OrbitState:
        epoch = datetime(2024, 1, 1, tzinfo=timezone.utc)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        elapsed = (t - epoch).total_seconds()

        alt_km = 550.0
        R = 6378.137 + alt_km
        mu = 398600.4418
        n = math.sqrt(mu / R**3)
        omega = n * elapsed

        inc = self._inc_rad
        x = R * math.cos(omega)
        y = R * math.sin(omega) * math.cos(inc)
        z = R * math.sin(omega) * math.sin(inc)

        speed = math.sqrt(mu / R)
        vx = -speed * math.sin(omega)
        vy = speed * math.cos(omega) * math.cos(inc)
        vz = speed * math.cos(omega) * math.sin(inc)

        lon = math.degrees(math.atan2(y, x)) % 360
        if lon > 180:
            lon -= 360
        lat = math.degrees(math.asin(z / R))

        return OrbitState(
            timestamp=t, latitude=lat, longitude=lon,
            altitude_km=alt_km, velocity_km_s=speed,
            x=x, y=y, z=z, vx=vx, vy=vy, vz=vz,
        )

    def get_ground_track(self, t: datetime, points: int = 90,
                         step_s: float = 60.0) -> List[Tuple[float, float]]:
        """Return list of (lat, lon) for the next `points` steps."""
        from datetime import timedelta
        track = []
        for i in range(points):
            dt = t + timedelta(seconds=i * step_s)
            state = self.propagate(dt)
            track.append((state.latitude, state.longitude))
        return track
