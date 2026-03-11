"""
AboutWidget — version info, dependency list, and update check.

Checks PyPI for the latest kitsat-gs version using urllib (no extra dep).
"""

from __future__ import annotations

import json
import urllib.request
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QGroupBox,
)
from PySide6.QtCore import Qt, Slot, QThread, Signal
from PySide6.QtGui import QFont
from loguru import logger

import kitsat_gs


_PYPI_URL = "https://pypi.org/pypi/kitsat-gs/json"

_LICENSES = """\
kitsat-gs — MIT License
Copyright (c) 2026 Arctic Astronautics Ltd.

Third-party dependencies:
  PySide6          — LGPL v3  (Qt for Python)
  kitsat           — see kitsat PyPI page
  sgp4             — MIT
  pyqtgraph        — MIT
  folium           — MIT
  loguru           — MIT
  pyserial         — BSD
"""


class _UpdateChecker(QThread):
    result = Signal(str)   # latest version string or error message

    def run(self) -> None:
        try:
            with urllib.request.urlopen(_PYPI_URL, timeout=5) as r:
                data = json.loads(r.read())
            latest = data["info"]["version"]
            self.result.emit(latest)
        except Exception as exc:
            self.result.emit(f"error: {exc}")


class AboutWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._checker: Optional[_UpdateChecker] = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        title = QLabel("Kitsat Ground Station")
        title_font = QFont()
        title_font.setPointSize(20)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setObjectName("sidebarTitle")
        layout.addWidget(title)

        subtitle = QLabel("Cross-platform satellite ground station software")
        subtitle.setObjectName("versionLabel")
        layout.addWidget(subtitle)

        # Version box
        ver_box = QGroupBox("Version")
        ver_layout = QVBoxLayout(ver_box)

        current = kitsat_gs.__version__
        self._lbl_current = QLabel(f"Installed:  <b>{current}</b>")
        ver_layout.addWidget(self._lbl_current)

        self._lbl_latest = QLabel("Latest:  (not checked)")
        self._lbl_latest.setObjectName("versionLabel")
        ver_layout.addWidget(self._lbl_latest)

        update_row = QHBoxLayout()
        self._btn_check = QPushButton("Check for Updates")
        self._btn_check.setFixedWidth(160)
        self._btn_check.clicked.connect(self._check_update)
        update_row.addWidget(self._btn_check)

        self._lbl_update_status = QLabel("")
        self._lbl_update_status.setObjectName("versionLabel")
        update_row.addWidget(self._lbl_update_status)
        update_row.addStretch()
        ver_layout.addLayout(update_row)

        self._lbl_upgrade_cmd = QLabel("")
        self._lbl_upgrade_cmd.setObjectName("versionLabel")
        self._lbl_upgrade_cmd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ver_layout.addWidget(self._lbl_upgrade_cmd)

        layout.addWidget(ver_box)

        # Links
        links_box = QGroupBox("Links")
        links_layout = QVBoxLayout(links_box)
        for text, url in [
            ("GitHub Repository", "https://github.com/nikandt/kitsat-groundstation-GUI-2"),
            ("Kitsat Website", "https://kitsat.fi"),
            ("Report an Issue", "https://github.com/nikandt/kitsat-groundstation-GUI-2/issues"),
            ("PyPI Package", "https://pypi.org/project/kitsat-gs/"),
        ]:
            lbl = QLabel(f'<a href="{url}">{text}</a>')
            lbl.setOpenExternalLinks(True)
            lbl.setObjectName("versionLabel")
            links_layout.addWidget(lbl)
        layout.addWidget(links_box)

        # Licenses
        lic_box = QGroupBox("Licenses")
        lic_layout = QVBoxLayout(lic_box)
        lic_text = QPlainTextEdit(_LICENSES)
        lic_text.setReadOnly(True)
        lic_text.setObjectName("terminalOutput")
        lic_text.setFixedHeight(140)
        lic_layout.addWidget(lic_text)
        layout.addWidget(lic_box)

        layout.addStretch()

    @Slot()
    def _check_update(self) -> None:
        self._btn_check.setEnabled(False)
        self._lbl_update_status.setText("Checking…")
        self._checker = _UpdateChecker(self)
        self._checker.result.connect(self._on_update_result)
        self._checker.start()

    @Slot(str)
    def _on_update_result(self, latest: str) -> None:
        self._btn_check.setEnabled(True)
        current = kitsat_gs.__version__

        if latest.startswith("error:"):
            self._lbl_update_status.setText(f"Could not reach PyPI: {latest[7:]}")
            return

        self._lbl_latest.setText(f"Latest:  <b>{latest}</b>")

        if latest == current:
            self._lbl_update_status.setText("✓ You are up to date")
            self._lbl_update_status.setStyleSheet("color: #00da96;")
            self._lbl_upgrade_cmd.setText("")
        else:
            self._lbl_update_status.setText(f"Update available: {current} → {latest}")
            self._lbl_update_status.setStyleSheet("color: #ffaa00;")
            self._lbl_upgrade_cmd.setText(
                "To upgrade, run:  pip install --upgrade kitsat-gs"
            )
        logger.info(f"Update check: current={current} latest={latest}")
