"""
TleGenerator — generate a TLE set from Keplerian orbital elements.

Port of TLE.cs GenerateTLEKeplerian() and GenerateTLE() from v1.

Constants:
    EARTH_RADIUS = 6371 km
    EARTH_MU     = 398600.44 km³/s²
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from kitsat_gs.core.tle_parser import Tle, _tle_checksum

EARTH_RADIUS = 6371.0       # km
EARTH_MU = 398600.44        # km³/s²


def _checksum(line68: str) -> str:
    """Compute checksum digit and return the complete 69-char line."""
    return line68 + str(_tle_checksum(line68))


def _epoch_day_str(day: float) -> str:
    return f"{day:012.8f}"


def _first_deriv_str(value: float) -> str:
    s = f"{value:+.8f}"    # e.g. +.00001234
    return s.replace("+0.", ".").replace("-0.", "-.").ljust(10)


def _exp_notation_str(value: float, width: int = 8) -> str:
    """Format a value in TLE scientific notation: ±NNNNN±N (no decimal point)."""
    if value == 0.0:
        return " 00000-0"
    sign = "-" if value < 0 else " "
    value = abs(value)
    exp = math.floor(math.log10(value)) + 1
    mantissa = value / (10 ** exp)
    mantissa_str = f"{mantissa:.5f}".replace("0.", "").replace(".", "")[:5]
    exp_sign = "-" if exp < 0 else "+"
    return f"{sign}{mantissa_str}{exp_sign}{abs(exp)}"


def _deg_str(value: float) -> str:
    return f"{value:8.4f}"


def _ecc_str(value: float) -> str:
    value = min(value, 0.99999)
    return f"{value:.7f}".replace("0.", "").replace(".", "")[:7]


def _mean_motion_str(value: float) -> str:
    return f"{value:11.8f}"


def from_keplerian(
    apogee_km: float,
    perigee_km: float,
    inclination_deg: float,
    raan_deg: float,
    arg_of_periapsis_deg: float,
    mean_anomaly_deg: float,
    name: str = "KITSAT",
) -> Tle:
    """
    Generate a TLE from Keplerian elements.

    apogee_km / perigee_km are altitudes above Earth's surface in km.
    Matches the logic of TLE.cs GenerateTLEKeplerian().
    """
    # Ensure apogee >= perigee
    hi = max(apogee_km, perigee_km)
    lo = min(apogee_km, perigee_km)
    r_apogee = EARTH_RADIUS + hi
    r_perigee = EARTH_RADIUS + lo

    semi_major = (r_apogee + r_perigee) / 2.0
    semi_minor = math.sqrt(r_apogee * r_perigee)
    eccentricity = math.sqrt(1.0 - (semi_minor ** 2 / semi_major ** 2))

    orbital_period_s = 2 * math.pi * semi_major * math.sqrt(semi_major / EARTH_MU)
    mean_motion = 86400.0 / orbital_period_s   # revs/day

    return from_elements(
        inclination_deg, raan_deg, eccentricity,
        arg_of_periapsis_deg, mean_anomaly_deg, mean_motion, name=name,
    )


def from_elements(
    inclination_deg: float,
    raan_deg: float,
    eccentricity: float,
    arg_of_perigee_deg: float,
    mean_anomaly_deg: float,
    mean_motion: float,
    name: str = "KITSAT",
    catalog_number: int = 99999,
) -> Tle:
    """Generate a TLE directly from orbital elements."""
    now = datetime.now(timezone.utc)
    epoch_year = now.year % 100
    day_of_year = now.timetuple().tm_yday
    seconds_today = now.hour * 3600 + now.minute * 60 + now.second + now.microsecond / 1e6
    epoch_day = day_of_year + seconds_today / 86400.0

    intl_year = str(now.year % 100).zfill(2)
    cat = str(catalog_number).rjust(5)

    # Line 1 (68 chars before checksum)
    l1_68 = (
        f"1 {cat}U {intl_year}001A   "
        f"{epoch_year:02d}{_epoch_day_str(epoch_day)} "
        f"{_first_deriv_str(0.0)} "
        f"{_exp_notation_str(0.0)} "
        f"{_exp_notation_str(0.0)} "
        f"0 "
        f"{'1':>4}"
    )
    # Pad/truncate to exactly 68 chars
    l1_68 = l1_68[:68].ljust(68)
    line1 = _checksum(l1_68)

    # Line 2 (68 chars before checksum)
    l2_68 = (
        f"2 {cat} "
        f"{_deg_str(inclination_deg)} "
        f"{_deg_str(raan_deg)} "
        f"{_ecc_str(eccentricity)} "
        f"{_deg_str(arg_of_perigee_deg)} "
        f"{_deg_str(mean_anomaly_deg)}"
        f"{_mean_motion_str(mean_motion)}"
        f"{'0':>5}"
    )
    l2_68 = l2_68[:68].ljust(68)
    line2 = _checksum(l2_68)

    from kitsat_gs.core.tle_parser import parse
    return parse(line1, line2, name=name)
