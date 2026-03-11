"""
Tests for FirmwareUpdater — no network or hardware required.
"""

import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from kitsat_gs.core.firmware_updater import (
    FirmwareUpdater, find_nucleo_path,
    LEGACY_URL, NUCLEO_VOLUME, BANDS, PL_VERSIONS, EPS_VERSIONS,
)


def test_build_url_returns_legacy_when_no_custom():
    url = FirmwareUpdater.build_url("433", "1.4", "1.4", "nucleo")
    assert url == LEGACY_URL


def test_build_url_uses_custom_when_provided():
    custom = "https://example.com/firmware.bin"
    url = FirmwareUpdater.build_url("433", "1.4", "1.4", "nucleo", custom_url=custom)
    assert url == custom


def test_filename_nucleo():
    assert FirmwareUpdater.filename_for("nucleo") == "kitsat.bin"


def test_filename_sdcard():
    assert FirmwareUpdater.filename_for("sdcard") == "kitsat-update.bin"


def test_bands_include_433_and_915():
    assert "433" in BANDS
    assert "915" in BANDS


def test_pl_versions():
    assert "1.2" in PL_VERSIONS
    assert "1.3" in PL_VERSIONS
    assert "1.4" in PL_VERSIONS


def test_eps_versions():
    assert "1.4" in EPS_VERSIONS


def test_flash_nucleo_success(qapp, tmp_path):
    firmware = tmp_path / "kitsat.bin"
    firmware.write_bytes(b"\x00" * 64)
    nucleo_dir = tmp_path / "nucleo_drive"
    nucleo_dir.mkdir()

    updater = FirmwareUpdater()
    results = []
    updater.flash_finished.connect(lambda msg: results.append(msg))

    with patch("kitsat_gs.core.firmware_updater.find_nucleo_path", return_value=nucleo_dir):
        updater.flash(firmware, "nucleo")

    assert len(results) == 1
    assert (nucleo_dir / "kitsat.bin").exists()


def test_flash_nucleo_not_found(qapp):
    updater = FirmwareUpdater()
    errors = []
    updater.error.connect(lambda e: errors.append(e))

    with patch("kitsat_gs.core.firmware_updater.find_nucleo_path", return_value=None):
        updater.flash(Path("/tmp/kitsat.bin"), "nucleo")

    assert len(errors) == 1
    assert NUCLEO_VOLUME in errors[0]


def test_flash_sdcard_success(qapp, tmp_path):
    firmware = tmp_path / "kitsat-update.bin"
    firmware.write_bytes(b"\x00" * 64)
    sd_dir = tmp_path / "sdcard"
    sd_dir.mkdir()

    updater = FirmwareUpdater()
    results = []
    updater.flash_finished.connect(lambda msg: results.append(msg))
    updater.flash(firmware, "sdcard", target_path=sd_dir)

    assert len(results) == 1
    assert (sd_dir / "kitsat-update.bin").exists()


def test_flash_sdcard_no_path(qapp):
    updater = FirmwareUpdater()
    errors = []
    updater.error.connect(lambda e: errors.append(e))
    updater.flash(Path("/tmp/kitsat-update.bin"), "sdcard", target_path=None)
    assert len(errors) == 1
