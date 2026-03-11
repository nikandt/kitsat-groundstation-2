"""
FirmwareUpdater — download and flash Kitsat firmware.

Four configuration dimensions:
  band         : "433" | "915"          (RF frequency band)
  pl_version   : "1.2" | "1.3" | "1.4" (Payload board version)
  eps_version  : "1.4"                  (EPS board version)
  update_type  : "nucleo" | "sdcard"    (Update method)

URL strategy:
  The staging server currently (2026-03) only serves a single binary at
  https://staging.kitsat.fi/mbedos5-kitsat.bin (the legacy v1 URL).
  The multi-config URL pattern is not yet live (select.js returns 404).
  We use a configurable URL template so the correct URLs can be set once
  the server publishes them. The user can also paste a direct URL.

  Default template (update when server is ready):
    https://staging.kitsat.fi/{band}/{pl_version}/{eps_version}/{update_type}/kitsat.bin

Nucleo update:
  - File: kitsat.bin
  - Copy to NODE_F401RE mass storage (auto-detected)

SD card update:
  - File: kitsat-update.bin
  - Copy to SD card root (user selects or auto-detected)
"""

from __future__ import annotations

import shutil
import sys
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot
from loguru import logger


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BANDS = ["433", "915"]
PL_VERSIONS = ["1.2", "1.3", "1.4"]
EPS_VERSIONS = ["1.4"]
UPDATE_TYPES = ["nucleo", "sdcard"]

# Legacy single-binary URL (currently the only working one)
LEGACY_URL = "https://staging.kitsat.fi/mbedos5-kitsat.bin"

# Template for when multi-config server is ready.
# Replace with confirmed pattern once staging.kitsat.fi/select.js is live.
URL_TEMPLATE = "https://staging.kitsat.fi/{band}/{pl_version}/{eps_version}/{update_type}/kitsat.bin"

NUCLEO_VOLUME = "NODE_F401RE"


# ---------------------------------------------------------------------------
# Mass storage detection
# ---------------------------------------------------------------------------

def find_nucleo_path() -> Optional[Path]:
    """Find the NODE_F401RE mass storage mount point across platforms."""
    if sys.platform == "win32":
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if bitmask & 1:
                drive = Path(f"{letter}:\\")
                try:
                    vol_buf = ctypes.create_unicode_buffer(261)
                    ctypes.windll.kernel32.GetVolumeInformationW(
                        str(drive), vol_buf, 261, None, None, None, None, 0
                    )
                    if vol_buf.value == NUCLEO_VOLUME:
                        return drive
                except Exception:
                    pass
            bitmask >>= 1

    elif sys.platform == "darwin":
        candidate = Path(f"/Volumes/{NUCLEO_VOLUME}")
        if candidate.exists():
            return candidate

    else:  # Linux
        import getpass
        for base in (
            Path(f"/media/{getpass.getuser()}/{NUCLEO_VOLUME}"),
            Path(f"/run/media/{getpass.getuser()}/{NUCLEO_VOLUME}"),
            Path(f"/mnt/{NUCLEO_VOLUME}"),
        ):
            if base.exists():
                return base

    return None


# ---------------------------------------------------------------------------
# Download worker
# ---------------------------------------------------------------------------

class _DownloadWorker(QThread):
    progress = Signal(int)       # 0-100
    finished = Signal(Path)      # local path of downloaded file
    error = Signal(str)

    def __init__(self, url: str, dest: Path, parent=None) -> None:
        super().__init__(parent)
        self._url = url
        self._dest = dest

    def run(self) -> None:
        try:
            logger.info(f"Downloading firmware from {self._url}")
            self._dest.parent.mkdir(parents=True, exist_ok=True)

            with urllib.request.urlopen(self._url) as response:
                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                chunk_size = 8192

                with open(self._dest, "wb") as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            self.progress.emit(int(downloaded / total * 100))

            self.progress.emit(100)
            logger.info(f"Firmware downloaded to {self._dest}")
            self.finished.emit(self._dest)

        except Exception as exc:
            logger.error(f"Firmware download failed: {exc}")
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# FirmwareUpdater
# ---------------------------------------------------------------------------

class FirmwareUpdater(QObject):
    """
    Signals:
        download_progress(percent)
        download_finished(local_path)
        flash_finished(message)
        error(message)
    """

    download_progress = Signal(int)
    download_finished = Signal(object)   # Path
    flash_finished = Signal(str)
    error = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker: Optional[_DownloadWorker] = None
        self._tmp_dir = Path.home() / "Documents" / "Kitsat" / "firmware"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # URL building
    # ------------------------------------------------------------------

    @staticmethod
    def build_url(
        band: str,
        pl_version: str,
        eps_version: str,
        update_type: str,
        custom_url: str = "",
    ) -> str:
        """
        Build the firmware download URL.
        If custom_url is non-empty, use it directly.
        Falls back to LEGACY_URL until multi-config server is live.
        """
        if custom_url.strip():
            return custom_url.strip()
        # TODO: switch to URL_TEMPLATE once staging.kitsat.fi/select.js is live
        # and the per-config binaries are published.
        logger.warning(
            "Multi-config firmware URLs not yet live on staging server. "
            f"Using legacy URL: {LEGACY_URL}"
        )
        return LEGACY_URL

    @staticmethod
    def filename_for(update_type: str) -> str:
        return "kitsat-update.bin" if update_type == "sdcard" else "kitsat.bin"

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    @Slot(str, str, str, str, str)
    def download(
        self,
        band: str,
        pl_version: str,
        eps_version: str,
        update_type: str,
        custom_url: str = "",
    ) -> None:
        url = self.build_url(band, pl_version, eps_version, update_type, custom_url)
        dest = self._tmp_dir / self.filename_for(update_type)

        self._worker = _DownloadWorker(url, dest, parent=self)
        self._worker.progress.connect(self.download_progress)
        self._worker.finished.connect(self._on_download_finished)
        self._worker.error.connect(self.error)
        self._worker.start()

    @Slot(object)
    def _on_download_finished(self, path: Path) -> None:
        self.download_finished.emit(path)

    # ------------------------------------------------------------------
    # Flash
    # ------------------------------------------------------------------

    @Slot(object, str, object)
    def flash(self, firmware_path: Path, update_type: str, target_path: Optional[Path] = None) -> None:
        """
        Flash the firmware binary.
        For Nucleo: auto-detect NODE_F401RE and copy.
        For SD card: use target_path (user-selected) or raise error.
        """
        try:
            if update_type == "nucleo":
                dest_dir = find_nucleo_path()
                if dest_dir is None:
                    self.error.emit(
                        f"Could not find {NUCLEO_VOLUME} drive. "
                        "Connect the Kitsat via USB and ensure it appears as a mass storage device."
                    )
                    return
                dest = dest_dir / firmware_path.name
                shutil.copy2(firmware_path, dest)
                msg = f"Firmware copied to {dest}. Wait for the LED to stop blinking, then restart."
                logger.info(msg)
                self.flash_finished.emit(msg)

            elif update_type == "sdcard":
                if target_path is None:
                    self.error.emit("SD card path not specified.")
                    return
                dest = Path(target_path) / firmware_path.name
                shutil.copy2(firmware_path, dest)
                msg = (
                    f"Firmware copied to {dest}.\n"
                    "Eject the SD card, reinsert into Kitsat OBC, and power on."
                )
                logger.info(msg)
                self.flash_finished.emit(msg)

        except Exception as exc:
            logger.error(f"Flash failed: {exc}")
            self.error.emit(str(exc))
