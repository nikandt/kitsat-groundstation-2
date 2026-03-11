"""
Settings — persistent application preferences via QSettings.

Storage locations (managed automatically by Qt):
  Windows : HKCU\\Software\\Arctic Astronautics\\Kitsat GS
  macOS   : ~/Library/Preferences/com.arctic-astronautics.kitsat-gs.plist
  Linux   : ~/.config/Arctic Astronautics/Kitsat GS.ini

All keys have typed accessors so callers never deal with raw QSettings.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

_ORG = "Arctic Astronautics"
_APP = "Kitsat GS"


def _s() -> QSettings:
    return QSettings(_ORG, _APP)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def last_port() -> str:
    return _s().value("connection/last_port", "")

def set_last_port(port: str) -> None:
    _s().setValue("connection/last_port", port)

def serial_timeout() -> float:
    return float(_s().value("connection/timeout", 1.0))

def set_serial_timeout(t: float) -> None:
    _s().setValue("connection/timeout", t)


# ---------------------------------------------------------------------------
# Ground station
# ---------------------------------------------------------------------------

def gs_lat() -> float:
    return float(_s().value("groundstation/lat", 60.17))

def set_gs_lat(v: float) -> None:
    _s().setValue("groundstation/lat", v)

def gs_lon() -> float:
    return float(_s().value("groundstation/lon", 24.94))

def set_gs_lon(v: float) -> None:
    _s().setValue("groundstation/lon", v)

def gs_alt_m() -> float:
    return float(_s().value("groundstation/alt_m", 10.0))

def set_gs_alt_m(v: float) -> None:
    _s().setValue("groundstation/alt_m", v)

def gs_name() -> str:
    return _s().value("groundstation/name", "My Ground Station")

def set_gs_name(v: str) -> None:
    _s().setValue("groundstation/name", v)


# ---------------------------------------------------------------------------
# TLE
# ---------------------------------------------------------------------------

def last_tle() -> str:
    default = (
        "ISS (ZARYA)\n"
        "1 25544U 98067A   24001.50000000  .00001764  00000-0  40000-4 0  9993\n"
        "2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.50377579432900"
    )
    return _s().value("orbital/last_tle", default)

def set_last_tle(tle_text: str) -> None:
    _s().setValue("orbital/last_tle", tle_text)


# ---------------------------------------------------------------------------
# Appearance
# ---------------------------------------------------------------------------

def theme() -> str:
    """Returns "dark" or "light"."""
    return _s().value("appearance/theme", "dark")

def set_theme(t: str) -> None:
    _s().setValue("appearance/theme", t)


# ---------------------------------------------------------------------------
# Firmware
# ---------------------------------------------------------------------------

def fw_band() -> str:
    return _s().value("firmware/band", "433")

def set_fw_band(v: str) -> None:
    _s().setValue("firmware/band", v)

def fw_pl_version() -> str:
    return _s().value("firmware/pl_version", "1.4")

def set_fw_pl_version(v: str) -> None:
    _s().setValue("firmware/pl_version", v)

def fw_eps_version() -> str:
    return _s().value("firmware/eps_version", "1.4")

def set_fw_eps_version(v: str) -> None:
    _s().setValue("firmware/eps_version", v)

def fw_update_type() -> str:
    return _s().value("firmware/update_type", "nucleo")

def set_fw_update_type(v: str) -> None:
    _s().setValue("firmware/update_type", v)

def fw_custom_url() -> str:
    return _s().value("firmware/custom_url", "")

def set_fw_custom_url(v: str) -> None:
    _s().setValue("firmware/custom_url", v)


# ---------------------------------------------------------------------------
# Window geometry
# ---------------------------------------------------------------------------

def window_geometry() -> bytes | None:
    v = _s().value("window/geometry")
    return bytes(v) if v else None

def set_window_geometry(data: bytes) -> None:
    _s().setValue("window/geometry", data)

def window_state() -> bytes | None:
    v = _s().value("window/state")
    return bytes(v) if v else None

def set_window_state(data: bytes) -> None:
    _s().setValue("window/state", data)
