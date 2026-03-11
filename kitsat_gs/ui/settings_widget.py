"""
SettingsWidget — persistent application preferences panel.

Sections:
  - Connection (last port, serial timeout)
  - Ground Station (name, lat, lon, alt)
  - Orbital (default TLE)
  - Firmware defaults (band, PL/EPS version, update type, custom URL)
  - Appearance (theme toggle)

Changes are saved immediately on Apply or when the user leaves the field.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QComboBox, QPushButton,
    QHBoxLayout, QPlainTextEdit, QScrollArea,
)
from PySide6.QtCore import Qt, Slot, Signal
from loguru import logger

from kitsat_gs.config import settings
from kitsat_gs.core.firmware_updater import BANDS, PL_VERSIONS, EPS_VERSIONS


class SettingsWidget(QWidget):
    """Emits theme_changed("dark"|"light") when the user toggles the theme."""
    theme_changed = Signal(str)
    gs_changed = Signal()   # ground station coords updated

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        inner = QWidget()
        main_layout = QVBoxLayout(inner)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        scroll.setWidget(inner)

        header = QLabel("Settings")
        header.setObjectName("panelHeader")
        main_layout.addWidget(header)

        # ---- Connection ----
        conn_box = QGroupBox("Connection")
        conn_form = QFormLayout(conn_box)
        self._last_port = QLineEdit()
        self._last_port.setPlaceholderText("e.g. COM3 or /dev/ttyUSB0")
        conn_form.addRow("Default port:", self._last_port)
        self._timeout = QLineEdit()
        self._timeout.setPlaceholderText("seconds, e.g. 1.0")
        conn_form.addRow("Serial timeout (s):", self._timeout)
        main_layout.addWidget(conn_box)

        # ---- Ground Station ----
        gs_box = QGroupBox("Ground Station")
        gs_form = QFormLayout(gs_box)
        self._gs_name = QLineEdit()
        gs_form.addRow("Name:", self._gs_name)
        self._gs_lat = QLineEdit()
        gs_form.addRow("Latitude (°):", self._gs_lat)
        self._gs_lon = QLineEdit()
        gs_form.addRow("Longitude (°):", self._gs_lon)
        self._gs_alt = QLineEdit()
        gs_form.addRow("Altitude (m):", self._gs_alt)
        main_layout.addWidget(gs_box)

        # ---- Orbital ----
        tle_box = QGroupBox("Default TLE")
        tle_layout = QVBoxLayout(tle_box)
        tle_layout.addWidget(QLabel("Paste a 2- or 3-line TLE set:"))
        self._tle = QPlainTextEdit()
        self._tle.setFixedHeight(80)
        self._tle.setObjectName("terminalOutput")
        tle_layout.addWidget(self._tle)
        main_layout.addWidget(tle_box)

        # ---- Firmware defaults ----
        fw_box = QGroupBox("Firmware Defaults")
        fw_form = QFormLayout(fw_box)

        self._fw_band = QComboBox()
        for b in BANDS:
            self._fw_band.addItem(f"{b} MHz", b)
        fw_form.addRow("RF Band:", self._fw_band)

        self._fw_pl = QComboBox()
        for v in PL_VERSIONS:
            self._fw_pl.addItem(v, v)
        fw_form.addRow("PL version:", self._fw_pl)

        self._fw_eps = QComboBox()
        for v in EPS_VERSIONS:
            self._fw_eps.addItem(v, v)
        fw_form.addRow("EPS version:", self._fw_eps)

        self._fw_type = QComboBox()
        self._fw_type.addItem("Nucleo", "nucleo")
        self._fw_type.addItem("SD card", "sdcard")
        fw_form.addRow("Update type:", self._fw_type)

        self._fw_url = QLineEdit()
        self._fw_url.setPlaceholderText("Leave empty to use default URL")
        fw_form.addRow("Custom URL:", self._fw_url)
        main_layout.addWidget(fw_box)

        # ---- Appearance ----
        ap_box = QGroupBox("Appearance")
        ap_layout = QFormLayout(ap_box)
        self._theme = QComboBox()
        self._theme.addItem("Dark", "dark")
        self._theme.addItem("Light", "light")
        ap_layout.addRow("Theme:", self._theme)
        main_layout.addWidget(ap_box)

        # ---- Buttons ----
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_apply = QPushButton("Apply")
        self._btn_apply.setFixedWidth(80)
        self._btn_apply.clicked.connect(self._apply)
        btn_row.addWidget(self._btn_apply)

        self._btn_reset = QPushButton("Reset to Defaults")
        self._btn_reset.setFixedWidth(130)
        self._btn_reset.clicked.connect(self._reset)
        btn_row.addWidget(self._btn_reset)
        main_layout.addLayout(btn_row)

        main_layout.addStretch()

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _load(self) -> None:
        self._last_port.setText(settings.last_port())
        self._timeout.setText(str(settings.serial_timeout()))
        self._gs_name.setText(settings.gs_name())
        self._gs_lat.setText(str(settings.gs_lat()))
        self._gs_lon.setText(str(settings.gs_lon()))
        self._gs_alt.setText(str(settings.gs_alt_m()))
        self._tle.setPlainText(settings.last_tle())

        band = settings.fw_band()
        for i in range(self._fw_band.count()):
            if self._fw_band.itemData(i) == band:
                self._fw_band.setCurrentIndex(i)
                break

        pl = settings.fw_pl_version()
        for i in range(self._fw_pl.count()):
            if self._fw_pl.itemData(i) == pl:
                self._fw_pl.setCurrentIndex(i)
                break

        eps = settings.fw_eps_version()
        for i in range(self._fw_eps.count()):
            if self._fw_eps.itemData(i) == eps:
                self._fw_eps.setCurrentIndex(i)
                break

        ut = settings.fw_update_type()
        for i in range(self._fw_type.count()):
            if self._fw_type.itemData(i) == ut:
                self._fw_type.setCurrentIndex(i)
                break

        self._fw_url.setText(settings.fw_custom_url())

        theme = settings.theme()
        for i in range(self._theme.count()):
            if self._theme.itemData(i) == theme:
                self._theme.setCurrentIndex(i)
                break

    @Slot()
    def _apply(self) -> None:
        settings.set_last_port(self._last_port.text().strip())
        try:
            settings.set_serial_timeout(float(self._timeout.text()))
        except ValueError:
            pass

        settings.set_gs_name(self._gs_name.text().strip())
        try:
            settings.set_gs_lat(float(self._gs_lat.text()))
            settings.set_gs_lon(float(self._gs_lon.text()))
            settings.set_gs_alt_m(float(self._gs_alt.text()))
            self.gs_changed.emit()
        except ValueError:
            pass

        settings.set_last_tle(self._tle.toPlainText().strip())
        settings.set_fw_band(self._fw_band.currentData())
        settings.set_fw_pl_version(self._fw_pl.currentData())
        settings.set_fw_eps_version(self._fw_eps.currentData())
        settings.set_fw_update_type(self._fw_type.currentData())
        settings.set_fw_custom_url(self._fw_url.text().strip())

        new_theme = self._theme.currentData()
        if new_theme != settings.theme():
            settings.set_theme(new_theme)
            self.theme_changed.emit(new_theme)

        logger.info("Settings saved")

    @Slot()
    def _reset(self) -> None:
        from PySide6.QtCore import QSettings
        QSettings("Arctic Astronautics", "Kitsat GS").clear()
        self._load()
        logger.info("Settings reset to defaults")
