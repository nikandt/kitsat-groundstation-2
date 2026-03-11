"""Tests for kitsat_gs.config.settings — typed QSettings accessors."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Redirect QSettings to a temp INI file so tests don't touch the real registry."""
    from PySide6.QtCore import QSettings
    ini = str(tmp_path / "test_settings.ini")
    monkeypatch.setattr(
        "kitsat_gs.config.settings._qs",
        QSettings(ini, QSettings.Format.IniFormat),
    )
    yield


def _s():
    from kitsat_gs.config import settings
    return settings


# ------------------------------------------------------------------
# last_port
# ------------------------------------------------------------------

def test_last_port_default():
    s = _s()
    assert s.last_port() == ""


def test_last_port_roundtrip():
    s = _s()
    s.set_last_port("COM3")
    assert s.last_port() == "COM3"


# ------------------------------------------------------------------
# serial_timeout
# ------------------------------------------------------------------

def test_serial_timeout_default():
    s = _s()
    assert s.serial_timeout() == 0.1


def test_serial_timeout_roundtrip():
    s = _s()
    s.set_serial_timeout(0.5)
    assert s.serial_timeout() == pytest.approx(0.5)


# ------------------------------------------------------------------
# Ground station
# ------------------------------------------------------------------

def test_gs_lat_default():
    s = _s()
    assert s.gs_lat() == pytest.approx(65.0)


def test_gs_lon_default():
    s = _s()
    assert s.gs_lon() == pytest.approx(25.47)


def test_gs_alt_default():
    s = _s()
    assert s.gs_alt_m() == pytest.approx(15.0)


def test_gs_name_default():
    s = _s()
    assert s.gs_name() == "Oulu"


def test_gs_roundtrip():
    s = _s()
    s.set_gs_lat(60.169)
    s.set_gs_lon(24.935)
    s.set_gs_alt_m(5.0)
    s.set_gs_name("Helsinki")
    assert s.gs_lat() == pytest.approx(60.169)
    assert s.gs_lon() == pytest.approx(24.935)
    assert s.gs_alt_m() == pytest.approx(5.0)
    assert s.gs_name() == "Helsinki"


# ------------------------------------------------------------------
# TLE
# ------------------------------------------------------------------

def test_last_tle_default():
    s = _s()
    assert s.last_tle() == ""


def test_last_tle_roundtrip():
    s = _s()
    tle = "1 25544U 98067A   24001.00000000  .00000000  00000-0  00000-0 0  9999\n2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.50000000000000"
    s.set_last_tle(tle)
    assert s.last_tle() == tle


# ------------------------------------------------------------------
# Theme
# ------------------------------------------------------------------

def test_theme_default():
    s = _s()
    assert s.theme() == "dark"


def test_theme_roundtrip():
    s = _s()
    s.set_theme("light")
    assert s.theme() == "light"
    s.set_theme("dark")
    assert s.theme() == "dark"


# ------------------------------------------------------------------
# Firmware
# ------------------------------------------------------------------

def test_fw_band_default():
    s = _s()
    assert s.fw_band() == "433"


def test_fw_pl_version_default():
    s = _s()
    assert s.fw_pl_version() == "1.4"


def test_fw_eps_version_default():
    s = _s()
    assert s.fw_eps_version() == "1.4"


def test_fw_update_type_default():
    s = _s()
    assert s.fw_update_type() == "nucleo"


def test_fw_custom_url_default():
    s = _s()
    assert s.fw_custom_url() == ""


def test_fw_roundtrip():
    s = _s()
    s.set_fw_band("915")
    s.set_fw_pl_version("1.2")
    s.set_fw_eps_version("1.4")
    s.set_fw_update_type("sdcard")
    s.set_fw_custom_url("https://example.com/fw.bin")
    assert s.fw_band() == "915"
    assert s.fw_pl_version() == "1.2"
    assert s.fw_eps_version() == "1.4"
    assert s.fw_update_type() == "sdcard"
    assert s.fw_custom_url() == "https://example.com/fw.bin"


# ------------------------------------------------------------------
# Window geometry (bytes blobs)
# ------------------------------------------------------------------

def test_window_geometry_default():
    s = _s()
    assert s.window_geometry() is None or s.window_geometry() == b""


def test_window_geometry_roundtrip():
    s = _s()
    blob = b"\x01\x02\x03\x04"
    s.set_window_geometry(blob)
    assert s.window_geometry() == blob


def test_window_state_roundtrip():
    s = _s()
    blob = b"\xde\xad\xbe\xef"
    s.set_window_state(blob)
    assert s.window_state() == blob
