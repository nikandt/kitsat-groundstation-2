"""
Tests for PassPredictor — no hardware required.
Uses a known ISS TLE and Helsinki ground station.
"""

from datetime import datetime, timezone
from kitsat_gs.core.tle_parser import parse
from kitsat_gs.core.pass_predictor import (
    PassPredictor, GroundStation,
    _teme_to_ecef, _ecef_to_geodetic, _elevation_azimuth,
)

ISS_L1 = "1 25544U 98067A   24001.50000000  .00001764  00000-0  40000-4 0  9993"
ISS_L2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.50377579432900"

_GS = GroundStation(lat=60.17, lon=24.94, alt_m=10)
_TLE = parse(ISS_L1, ISS_L2, "ISS")


def test_ground_track_returns_points():
    p = PassPredictor(_TLE, _GS)
    track = p.ground_track(minutes=95, step_s=60)
    assert len(track) > 0
    for lat, lon in track:
        assert -90 <= lat <= 90
        assert -180 <= lon <= 180


def test_ground_track_length():
    p = PassPredictor(_TLE, _GS)
    # ISS period ~92 min, 60s steps → ~92 points per orbit
    track = p.ground_track(minutes=95, step_s=60)
    assert 90 <= len(track) <= 100


def test_find_passes_returns_list():
    p = PassPredictor(_TLE, _GS)
    passes = p.find_passes(days=3)
    assert isinstance(passes, list)


def test_passes_have_valid_elevations():
    p = PassPredictor(_TLE, _GS)
    passes = p.find_passes(days=3)
    for pas in passes:
        assert pas.max_elevation >= 0
        assert pas.aos < pas.los


def test_ecef_to_geodetic_roundtrip():
    import math
    lat, lon = 60.17, 24.94
    lat_r, lon_r = math.radians(lat), math.radians(lon)
    R = 6378.137
    x = R * math.cos(lat_r) * math.cos(lon_r)
    y = R * math.cos(lat_r) * math.sin(lon_r)
    z = R * math.sin(lat_r)
    lat2, lon2, alt = _ecef_to_geodetic(x, y, z)
    assert abs(lat2 - lat) < 0.1
    assert abs(lon2 - lon) < 0.1


def test_sky_point_elevation_range():
    p = PassPredictor(_TLE, _GS)
    pos = p.current_position()
    assert pos is not None
    assert -90 <= pos.elevation <= 90
    assert 0 <= pos.azimuth < 360
    assert pos.range_km > 0
