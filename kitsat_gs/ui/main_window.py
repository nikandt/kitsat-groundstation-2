"""
MainWindow — application shell.

Phase 1: Terminal
Phase 2: Housekeeping + Command Builder
Phase 3: Map + Orbit
Phase 4: Images
Phase 5: Scripts + Firmware
Phase 6: Settings + About  (geometry/state persistence, theme switching)
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QStackedWidget, QLabel, QStatusBar,
    QComboBox, QApplication,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QCloseEvent
from loguru import logger

from kitsat_gs.config import settings
from kitsat_gs.core.modem_bridge import ModemBridge
from kitsat_gs.core.telemetry_store import TelemetryStore
from kitsat_gs.core.packet_dispatcher import PacketDispatcher
from kitsat_gs.core.image_manager import ImageManager
from kitsat_gs.ui.terminal_widget import TerminalWidget
from kitsat_gs.ui.housekeeping_widget import HousekeepingWidget
from kitsat_gs.ui.command_builder_widget import CommandBuilderWidget
from kitsat_gs.ui.map_widget import MapWidget
from kitsat_gs.ui.orbit_widget import OrbitWidget
from kitsat_gs.ui.image_widget import ImageWidget
from kitsat_gs.ui.script_widget import ScriptWidget
from kitsat_gs.ui.firmware_widget import FirmwareWidget
from kitsat_gs.ui.settings_widget import SettingsWidget
from kitsat_gs.ui.about_widget import AboutWidget


class _SidebarButton(QPushButton):
    def __init__(self, label: str, parent=None) -> None:
        super().__init__(label, parent)
        self.setCheckable(True)
        self.setFixedHeight(44)
        self.setFixedWidth(140)
        self.setCursor(Qt.PointingHandCursor)


class MainWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self._app = app
        self.setWindowTitle("Kitsat GS v2")
        self.resize(1200, 760)

        self._bridge = ModemBridge(parent=self)
        self._bridge.connected.connect(self._on_connected)
        self._bridge.disconnected.connect(self._on_disconnected)
        self._bridge.error.connect(self._on_error)

        self._store = TelemetryStore(parent=self)
        self._dispatcher = PacketDispatcher(self._store, parent=self)
        self._bridge.message_received.connect(self._dispatcher.dispatch)

        self._image_manager = ImageManager(parent=self)

        self._build_ui()
        self._restore_geometry()
        self._refresh_ports()

        # Pre-fill port from settings
        last = settings.last_port()
        if last:
            idx = self._port_combo.findText(last)
            if idx >= 0:
                self._port_combo.setCurrentIndex(idx)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_content())

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Disconnected")

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(148)
        sidebar.setObjectName("sidebar")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(4, 12, 4, 12)
        layout.setSpacing(4)

        title = QLabel("KITSAT GS")
        title.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setBold(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        title.setFont(font)
        title.setObjectName("sidebarTitle")
        layout.addWidget(title)
        layout.addSpacing(16)

        self._nav_buttons: list[_SidebarButton] = []
        self._stack_pages: list[str] = []

        def add_nav(label: str) -> _SidebarButton:
            btn = _SidebarButton(label)
            btn.clicked.connect(lambda checked, l=label: self._navigate(l))
            self._nav_buttons.append(btn)
            self._stack_pages.append(label)
            layout.addWidget(btn)
            return btn

        self._btn_terminal = add_nav("Terminal")
        add_nav("Housekeeping")
        add_nav("Cmd Builder")
        add_nav("Map")
        add_nav("Orbit")
        add_nav("Images")
        add_nav("Scripts")
        add_nav("Firmware")
        add_nav("Settings")
        add_nav("About")

        layout.addStretch()

        version = QLabel("v2.0.0")
        version.setAlignment(Qt.AlignCenter)
        version.setObjectName("versionLabel")
        layout.addWidget(version)

        self._btn_terminal.setChecked(True)
        return sidebar

    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_connection_bar())

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # Phase 1
        self._terminal = TerminalWidget(self._bridge)
        self._stack.addWidget(self._terminal)

        # Phase 2
        self._housekeeping = HousekeepingWidget(self._store)
        self._stack.addWidget(self._housekeeping)
        self._cmd_builder = CommandBuilderWidget(self._bridge)
        self._stack.addWidget(self._cmd_builder)

        # Phase 3
        self._map = MapWidget()
        self._stack.addWidget(self._map)
        self._orbit = OrbitWidget()
        self._stack.addWidget(self._orbit)

        # Phase 4
        self._images = ImageWidget(self._image_manager)
        self._stack.addWidget(self._images)

        # Phase 5
        self._scripts = ScriptWidget(self._bridge)
        self._stack.addWidget(self._scripts)
        self._firmware = FirmwareWidget()
        self._stack.addWidget(self._firmware)

        # Phase 6
        self._settings = SettingsWidget()
        self._settings.theme_changed.connect(self._on_theme_changed)
        self._settings.gs_changed.connect(self._on_gs_changed)
        self._stack.addWidget(self._settings)

        self._about = AboutWidget()
        self._stack.addWidget(self._about)

        return content

    def _build_connection_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("connectionBar")
        bar.setFixedHeight(44)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        self._port_combo = QComboBox()
        self._port_combo.setFixedWidth(160)
        self._port_combo.setToolTip("Select serial port")
        layout.addWidget(self._port_combo)

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setFixedWidth(70)
        self._btn_refresh.clicked.connect(self._refresh_ports)
        layout.addWidget(self._btn_refresh)

        self._btn_connect = QPushButton("Connect")
        self._btn_connect.setFixedWidth(80)
        self._btn_connect.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self._btn_connect)

        self._btn_auto = QPushButton("Auto")
        self._btn_auto.setFixedWidth(60)
        self._btn_auto.setToolTip("Auto-detect satellite or groundstation")
        self._btn_auto.clicked.connect(self._bridge.connect_auto)
        layout.addWidget(self._btn_auto)

        self._btn_disconnect = QPushButton("Disconnect")
        self._btn_disconnect.setFixedWidth(90)
        self._btn_disconnect.setEnabled(False)
        self._btn_disconnect.clicked.connect(self._bridge.disconnect)
        layout.addWidget(self._btn_disconnect)

        self._conn_indicator = QLabel("●")
        self._conn_indicator.setObjectName("connIndicatorOff")
        self._conn_indicator.setToolTip("Connection status")
        layout.addWidget(self._conn_indicator)

        layout.addStretch()
        return bar

    # ------------------------------------------------------------------
    # Geometry persistence
    # ------------------------------------------------------------------

    def _restore_geometry(self) -> None:
        geom = settings.window_geometry()
        state = settings.window_state()
        if geom:
            self.restoreGeometry(geom)
        if state:
            self.restoreState(state)

    def closeEvent(self, event: QCloseEvent) -> None:
        settings.set_window_geometry(bytes(self.saveGeometry()))
        settings.set_window_state(bytes(self.saveState()))
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(str)
    def _navigate(self, label: str) -> None:
        idx = self._stack_pages.index(label)
        self._stack.setCurrentIndex(idx)
        for btn in self._nav_buttons:
            btn.setChecked(btn.text() == label)

    @Slot()
    def _refresh_ports(self) -> None:
        ports = self._bridge.list_ports()
        self._port_combo.clear()
        for p in ports:
            self._port_combo.addItem(p)
        if not ports:
            self._port_combo.addItem("No ports found")

    @Slot()
    def _on_connect_clicked(self) -> None:
        port = self._port_combo.currentText()
        if port and port != "No ports found":
            settings.set_last_port(port)
            self._bridge.connect_port(port)

    @Slot(str)
    def _on_connected(self, port: str) -> None:
        self._status_bar.showMessage(f"Connected — {port}")
        self._conn_indicator.setObjectName("connIndicatorOn")
        self._conn_indicator.style().unpolish(self._conn_indicator)
        self._conn_indicator.style().polish(self._conn_indicator)
        self._btn_connect.setEnabled(False)
        self._btn_auto.setEnabled(False)
        self._btn_disconnect.setEnabled(True)

    @Slot()
    def _on_disconnected(self) -> None:
        self._status_bar.showMessage("Disconnected")
        self._conn_indicator.setObjectName("connIndicatorOff")
        self._conn_indicator.style().unpolish(self._conn_indicator)
        self._conn_indicator.style().polish(self._conn_indicator)
        self._btn_connect.setEnabled(True)
        self._btn_auto.setEnabled(True)
        self._btn_disconnect.setEnabled(False)

    @Slot(str)
    def _on_error(self, text: str) -> None:
        self._status_bar.showMessage(f"Error: {text}", 5000)
        logger.error(text)

    @Slot(str)
    def _on_theme_changed(self, theme: str) -> None:
        from kitsat_gs.app import load_stylesheet
        self._app.setStyleSheet(load_stylesheet(theme))
        logger.info(f"Theme switched to {theme}")

    @Slot()
    def _on_gs_changed(self) -> None:
        from kitsat_gs.core.pass_predictor import GroundStation
        gs = GroundStation(
            lat=settings.gs_lat(),
            lon=settings.gs_lon(),
            alt_m=settings.gs_alt_m(),
        )
        self._map.set_ground_station(gs)
        self._orbit.set_ground_station(gs)
        logger.info(f"Ground station updated: {gs.lat}, {gs.lon}")
