import pytest
from kitsat_gs.core.tle_parser import parse, from_string, _tle_checksum

ISS_L1 = "1 25544U 98067A   24001.50000000  .00001764  00000-0  40000-4 0  9993"
ISS_L2 = "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.50377579432900"
ISS_NAME = "ISS (ZARYA)"


def test_parse_valid_tle():
    tle = parse(ISS_L1, ISS_L2, ISS_NAME)
    assert tle.name == ISS_NAME
    assert tle.catalog_number == 25544
    assert tle.classification == "U"
    assert abs(tle.inclination - 51.6416) < 0.001
    assert abs(tle.mean_motion - 15.50377579) < 0.0001


def test_parse_eccentricity():
    tle = parse(ISS_L1, ISS_L2)
    assert abs(tle.eccentricity - 0.0006703) < 1e-7


def test_bad_checksum_raises():
    bad_l1 = ISS_L1[:-1] + "0"  # flip last digit
    with pytest.raises(ValueError, match="checksum"):
        parse(bad_l1, ISS_L2)


def test_from_string_three_lines():
    text = f"{ISS_NAME}\n{ISS_L1}\n{ISS_L2}"
    tle = from_string(text)
    assert tle is not None
    assert tle.name == ISS_NAME


def test_from_string_two_lines():
    text = f"{ISS_L1}\n{ISS_L2}"
    tle = from_string(text)
    assert tle is not None


def test_from_string_invalid_returns_none():
    assert from_string("not a tle") is None


def test_tle_checksum_known():
    assert _tle_checksum(ISS_L1) == int(ISS_L1[-1])
    assert _tle_checksum(ISS_L2) == int(ISS_L2[-1])
