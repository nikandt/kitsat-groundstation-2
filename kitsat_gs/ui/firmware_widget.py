"""
FirmwareWidget — firmware download and flash panel.

Configuration selectors:
  - RF Band:        433 MHz / 915 MHz
  - PL version:     1.2 / 1.3 / 1.4
  - EPS version:    1.4 (expandable)
  - Update type:    Nucleo (NODE_F401RE) / SD card

Note on multi-config URLs:
  The staging server (staging.kitsat.fi) currently only serves the legacy
  single binary. The per-configuration URL pattern will be enabled once
  staging.kitsat.fi/select.js is live. Until then, all downloads use the
  legacy URL regardless of band/version selection. A warning is shown.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QPushButton, QProgressBar,
    QGroupBox, QLineEdit, QFileDialog, QPlainTextEdit,
)
from PySide6.QtCore import Qt, Slot
from loguru import logger

from kitsat_gs.core.firmware_updater import (
    FirmwareUpdater, BANDS, PL_VERSIONS, EPS_VERSIONS,
    find_nucleo_path, NUCLEO_VOLUME, LEGACY_URL,
)


class FirmwareWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._updater = FirmwareUpdater(parent=self)
        self._updater.download_progress.connect(self._on_progress)
        self._updater.download_finished.connect(self._on_download_finished)
        self._updater.flash_finished.connect(self._on_flash_finished)
        self._updater.error.connect(self._on_error)
        self._firmware_path: Optional[Path] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QLabel("Firmware Update")
        header.setObjectName("panelHeader")
        layout.addWidget(header)

        # Server notice
        notice = QLabel(
            "⚠  Multi-config firmware URLs are not yet live on the staging server. "
            "All downloads currently use the legacy binary regardless of version selection. "
            "This will be resolved once staging.kitsat.fi/select.js is deployed."
        )
        notice.setWordWrap(True)
        notice.setObjectName("versionLabel")
        notice.setStyleSheet("color: #ffaa00; padding: 6px; "
                             "background: #2a2000; border-radius: 4px;")
        layout.addWidget(notice)

        # Configuration
        config_box = QGroupBox("Hardware Configuration")
        grid = QGridLayout(config_box)
        grid.setSpacing(8)

        grid.addWidget(QLabel("RF Band:"), 0, 0)
        self._band = QComboBox()
        for b in BANDS:
            self._band.addItem(f"{b} MHz", b)
        grid.addWidget(self._band, 0, 1)

        grid.addWidget(QLabel("Payload (PL) version:"), 1, 0)
        self._pl = QComboBox()
        for v in PL_VERSIONS:
            self._pl.addItem(v, v)
        self._pl.setCurrentIndex(len(PL_VERSIONS) - 1)   # default to latest
        grid.addWidget(self._pl, 1, 1)

        grid.addWidget(QLabel("EPS version:"), 2, 0)
        self._eps = QComboBox()
        for v in EPS_VERSIONS:
            self._eps.addItem(v, v)
        grid.addWidget(self._eps, 2, 1)

        grid.addWidget(QLabel("Update type:"), 3, 0)
        self._update_type = QComboBox()
        self._update_type.addItem("Nucleo (NODE_F401RE via USB)", "nucleo")
        self._update_type.addItem("SD card", "sdcard")
        self._update_type.currentIndexChanged.connect(self._on_type_changed)
        grid.addWidget(self._update_type, 3, 1)

        grid.addWidget(QLabel("Custom URL (optional):"), 4, 0)
        self._custom_url = QLineEdit()
        self._custom_url.setPlaceholderText(f"Leave empty to use default  ({LEGACY_URL})")
        grid.addWidget(self._custom_url, 4, 1)

        layout.addWidget(config_box)

        # Target path (SD card only)
        self._sdcard_box = QGroupBox("SD Card Path")
        sd_layout = QHBoxLayout(self._sdcard_box)
        self._sd_path = QLineEdit()
        self._sd_path.setPlaceholderText("Select SD card root directory…")
        sd_layout.addWidget(self._sd_path)
        self._btn_browse = QPushButton("Browse…")
        self._btn_browse.setFixedWidth(80)
        self._btn_browse.clicked.connect(self._on_browse_sd)
        sd_layout.addWidget(self._btn_browse)
        self._sdcard_box.setVisible(False)
        layout.addWidget(self._sdcard_box)

        # Nucleo auto-detect status
        self._nucleo_box = QGroupBox("Nucleo Detection")
        nucleo_layout = QHBoxLayout(self._nucleo_box)
        self._lbl_nucleo = QLabel("Not detected")
        self._lbl_nucleo.setObjectName("versionLabel")
        nucleo_layout.addWidget(self._lbl_nucleo)
        self._btn_detect = QPushButton("Detect Now")
        self._btn_detect.setFixedWidth(100)
        self._btn_detect.clicked.connect(self._detect_nucleo)
        nucleo_layout.addWidget(self._btn_detect)
        layout.addWidget(self._nucleo_box)

        # Action buttons + progress
        action_row = QHBoxLayout()
        self._btn_download = QPushButton("⬇  Download Firmware")
        self._btn_download.clicked.connect(self._on_download)
        action_row.addWidget(self._btn_download)

        self._btn_flash = QPushButton("⚡  Flash")
        self._btn_flash.setEnabled(False)
        self._btn_flash.clicked.connect(self._on_flash)
        action_row.addWidget(self._btn_flash)

        self._btn_download_flash = QPushButton("⬇⚡  Download & Flash")
        self._btn_download_flash.clicked.connect(self._on_download_and_flash)
        action_row.addWidget(self._btn_download_flash)

        layout.addLayout(action_row)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Status log
        log_box = QGroupBox("Status")
        log_layout = QVBoxLayout(log_box)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setObjectName("terminalOutput")
        self._log.setFixedHeight(160)
        log_layout.addWidget(self._log)
        layout.addWidget(log_box)

        # Instructions
        self._instructions = QGroupBox("Instructions")
        inst_layout = QVBoxLayout(self._instructions)
        self._lbl_instructions = QLabel()
        self._lbl_instructions.setWordWrap(True)
        self._lbl_instructions.setObjectName("versionLabel")
        inst_layout.addWidget(self._lbl_instructions)
        layout.addWidget(self._instructions)

        layout.addStretch()
        self._on_type_changed()
        self._detect_nucleo()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(int)
    def _on_type_changed(self, _=None) -> None:
        update_type = self._update_type.currentData()
        is_nucleo = (update_type == "nucleo")
        self._sdcard_box.setVisible(not is_nucleo)
        self._nucleo_box.setVisible(is_nucleo)
        self._update_instructions(update_type)

    def _update_instructions(self, update_type: str) -> None:
        if update_type == "nucleo":
            self._lbl_instructions.setText(
                "1. Power on Kitsat and connect via USB.\n"
                "2. Kitsat should appear as a mass storage drive named NODE_F401RE.\n"
                "3. Click Download & Flash — the binary will be copied automatically.\n"
                "4. Wait for the Kitsat LED to stop blinking, then unplug USB."
            )
        else:
            self._lbl_instructions.setText(
                "1. Power off Kitsat.\n"
                "2. Remove the micro SD card from the OBC board.\n"
                "3. Insert the SD card into your PC.\n"
                "4. Click Browse… and select the SD card root directory.\n"
                "5. Click Download & Flash — kitsat-update.bin will be copied to the SD card.\n"
                "6. Eject the SD card, reinsert into OBC, and power on Kitsat."
            )

    @Slot()
    def _detect_nucleo(self) -> None:
        path = find_nucleo_path()
        if path:
            self._lbl_nucleo.setText(f"✓ Found: {path}")
            self._lbl_nucleo.setStyleSheet("color: #00da96;")
        else:
            self._lbl_nucleo.setText(f"✗ {NUCLEO_VOLUME} not found — connect Kitsat via USB")
            self._lbl_nucleo.setStyleSheet("color: #ff5555;")

    @Slot()
    def _on_browse_sd(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select SD card root directory")
        if path:
            self._sd_path.setText(path)

    @Slot()
    def _on_download(self) -> None:
        self._start_download(flash_after=False)

    @Slot()
    def _on_flash(self) -> None:
        if self._firmware_path:
            update_type = self._update_type.currentData()
            sd_path = Path(self._sd_path.text()) if self._sd_path.text() else None
            self._updater.flash(self._firmware_path, update_type, sd_path)

    @Slot()
    def _on_download_and_flash(self) -> None:
        self._start_download(flash_after=True)

    def _start_download(self, flash_after: bool) -> None:
        self._flash_after = flash_after
        self._btn_download.setEnabled(False)
        self._btn_download_flash.setEnabled(False)
        self._btn_flash.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)

        band = self._band.currentData()
        pl = self._pl.currentData()
        eps = self._eps.currentData()
        update_type = self._update_type.currentData()
        custom_url = self._custom_url.text()

        self._log_msg(f"Downloading: band={band}MHz PL={pl} EPS={eps} type={update_type}")
        self._updater.download(band, pl, eps, update_type, custom_url)

    @Slot(int)
    def _on_progress(self, pct: int) -> None:
        self._progress.setValue(pct)

    @Slot(object)
    def _on_download_finished(self, path: Path) -> None:
        self._firmware_path = path
        self._log_msg(f"Downloaded: {path}")
        self._btn_flash.setEnabled(True)
        self._btn_download.setEnabled(True)
        self._btn_download_flash.setEnabled(True)

        if self._flash_after:
            update_type = self._update_type.currentData()
            sd_path = Path(self._sd_path.text()) if self._sd_path.text() else None
            self._updater.flash(path, update_type, sd_path)

    @Slot(str)
    def _on_flash_finished(self, message: str) -> None:
        self._log_msg(f"✓ {message}")
        self._progress.setValue(100)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._log_msg(f"✗ Error: {message}", error=True)
        self._btn_download.setEnabled(True)
        self._btn_download_flash.setEnabled(True)
        self._progress.setVisible(False)

    def _log_msg(self, text: str, error: bool = False) -> None:
        color = "#ff5555" if error else "#e0e0e0"
        self._log.appendHtml(f'<span style="color:{color}">{text}</span>')
        self._log.ensureCursorVisible()
