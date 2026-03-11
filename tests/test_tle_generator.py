"""
Tests for TleGenerator — verify Keplerian → TLE roundtrip produces valid TLE.
"""

import pytest
from kitsat_gs.core.tle_generator import from_keplerian, from_elements
from kitsat_gs.core.tle_parser import _tle_checksum


def test_from_keplerian_produces_valid_tle():
    tle = from_keplerian(
        apogee_km=550, perigee_km=530,
        inclination_deg=97.6,
        raan_deg=45.0,
        arg_of_periapsis_deg=0.0,
        mean_anomaly_deg=0.0,
    )
    assert tle is not None
    assert len(tle.line1) == 69
    assert len(tle.line2) == 69


def test_generated_tle_checksums_valid():
    tle = from_keplerian(550, 530, 97.6, 45.0, 0.0, 0.0)
    assert _tle_checksum(tle.line1) == int(tle.line1[-1])
    assert _tle_checksum(tle.line2) == int(tle.line2[-1])


def test_mean_motion_sensible_for_leo():
    tle = from_keplerian(550, 530, 97.6, 0.0, 0.0, 0.0)
    # LEO satellites orbit ~14-16 times per day
    assert 13.0 < tle.mean_motion < 17.0


def test_eccentricity_sensible():
    tle = from_keplerian(550, 530, 97.6, 0.0, 0.0, 0.0)
    assert 0.0 <= tle.eccentricity < 0.01   # nearly circular


def test_tle_name_preserved():
    tle = from_keplerian(550, 530, 97.6, 0.0, 0.0, 0.0, name="KITSAT-1")
    assert tle.name == "KITSAT-1"


def test_sgp4_accepts_generated_tle():
    """Generated TLE must be accepted by sgp4 without errors."""
    from sgp4.api import Satrec, jday
    from datetime import datetime, timezone
    tle = from_keplerian(550, 530, 97.6, 0.0, 0.0, 0.0)
    sat = Satrec.twoline2rv(tle.line1, tle.line2)
    now = datetime.now(timezone.utc)
    jd, fr = jday(now.year, now.month, now.day, now.hour, now.minute, now.second)
    err, r, v = sat.sgp4(jd, fr)
    assert err == 0
    assert len(r) == 3
    assert all(isinstance(x, float) for x in r)
