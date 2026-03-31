"""
MainWindow — application shell.

Phase 1:  Terminal
Phase 2:  Housekeeping + Command Builder
Phase 3:  Map + Orbit
Phase 4:  Images
Phase 5:  Scripts + Firmware
Phase 6:  Settings + About  (geometry/state persistence, theme switching)
New:      Dashboard + Commands + DSL Scripts + REPL  (KitsatOperations import)
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QStackedWidget, QLabel, QStatusBar,
    QComboBox, QApplication,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QCloseEvent, QKeySequence, QShortcut
from loguru import logger

from kitsat_gs.config import settings
from kitsat_gs.core.modem_bridge import ModemBridge
from kitsat_gs.core.telemetry_store import TelemetryStore
from kitsat_gs.core.packet_dispatcher import PacketDispatcher
from kitsat_gs.core.image_manager import ImageManager
from kitsat_gs.core.events import get_event_bus
from kitsat_gs.core.models import TelemetryFrame
from kitsat_gs.providers.mock import MockProvider
from kitsat_gs.orbit.simulator import OrbitSimulator
from kitsat_gs.orbit.ground_station import GroundStation

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

# New tabs from KitsatOperations import
from kitsat_gs.ui.tabs.dashboard_tab import DashboardTab
from kitsat_gs.ui.tabs.command_tab import CommandTab
from kitsat_gs.ui.tabs.scripting_tab import ScriptingTab
from kitsat_gs.ui.tabs.repl_tab import REPLTab


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
        self.resize(1280, 800)

        # ── Hardware bridge (existing)
        self._bridge = ModemBridge(parent=self)
        self._bridge.connected.connect(self._on_connected)
        self._bridge.disconnected.connect(self._on_disconnected)
        self._bridge.error.connect(self._on_error)

        self._store = TelemetryStore(parent=self)
        self._dispatcher = PacketDispatcher(self._store, parent=self)
        self._bridge.message_received.connect(self._dispatcher.dispatch)

        self._image_manager = ImageManager(parent=self)

        # ── Event bus + new providers
        self._bus = get_event_bus()
        self._mock_provider = MockProvider(parent=self)
        self._hw_packet_count = 0
        self._store.updated.connect(self._on_store_updated)
        self._mock_active = False

        # ── Orbit simulator (feeds EventBus orbit_updated)
        self._orbit_sim = OrbitSimulator(parent=self)
        self._orbit_sim.state_updated.connect(self._on_orbit_state)
        self._orbit_sim.start()

        self._build_ui()
        self._restore_geometry()
        self._refresh_ports()
        self._setup_shortcuts()

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
        self._status_bar.showMessage("Disconnected  |  Mock: OFF")

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(148)
        sidebar.setObjectName("sidebar")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(4, 12, 4, 12)
        layout.setSpacing(4)

        title = QLabel("KITSAT GS")
        title.setAlignment(Qt.AlignCenter)
        font = QFont("Segoe UI", 9)
        font.setBold(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        title.setFont(font)
        title.setObjectName("sidebarTitle")
        layout.addWidget(title)
        layout.addSpacing(8)

        self._nav_buttons: list[_SidebarButton] = []
        self._stack_pages: list[str] = []

        def add_nav(label: str) -> _SidebarButton:
            btn = _SidebarButton(label)
            btn.clicked.connect(lambda checked, l=label: self._navigate(l))
            self._nav_buttons.append(btn)
            self._stack_pages.append(label)
            layout.addWidget(btn)
            return btn

        # Original tabs
        self._btn_terminal = add_nav("Terminal")
        add_nav("Housekeeping")
        add_nav("Cmd Builder")
        add_nav("Map")
        add_nav("Orbit")
        add_nav("Images")
        add_nav("Scripts")
        add_nav("Firmware")

        # Separator label
        sep = QLabel("── New ──")
        sep.setAlignment(Qt.AlignCenter)
        sep.setStyleSheet("color: #64748b; font-size: 9pt;")
        layout.addWidget(sep)

        # New tabs from KitsatOperations
        add_nav("Dashboard")
        add_nav("Commands")
        add_nav("DSL Scripts")
        add_nav("REPL")

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

        # ── Original tabs
        self._terminal = TerminalWidget(self._bridge)
        self._stack.addWidget(self._terminal)

        self._housekeeping = HousekeepingWidget(self._store)
        self._stack.addWidget(self._housekeeping)

        self._cmd_builder = CommandBuilderWidget(self._bridge)
        self._stack.addWidget(self._cmd_builder)

        self._map = MapWidget()
        self._stack.addWidget(self._map)

        self._orbit = OrbitWidget()
        self._stack.addWidget(self._orbit)

        self._images = ImageWidget(self._image_manager)
        self._stack.addWidget(self._images)

        self._scripts = ScriptWidget(self._bridge)
        self._stack.addWidget(self._scripts)

        self._firmware = FirmwareWidget()
        self._stack.addWidget(self._firmware)

        # ── New tabs (KitsatOperations import)
        self._dashboard = DashboardTab()
        self._stack.addWidget(self._dashboard)

        self._commands = CommandTab(provider=self._mock_provider)
        self._stack.addWidget(self._commands)

        self._dsl_scripts = ScriptingTab()
        self._stack.addWidget(self._dsl_scripts)

        self._repl = REPLTab()
        self._stack.addWidget(self._repl)

        # ── Settings + About
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
        self._conn_indicator.setToolTip("Hardware connection status")
        layout.addWidget(self._conn_indicator)

        # Mock mode toggle (new)
        layout.addSpacing(16)
        self._btn_mock = QPushButton("Mock: OFF")
        self._btn_mock.setFixedWidth(100)
        self._btn_mock.setCheckable(True)
        self._btn_mock.setToolTip(
            "Start/stop the mock satellite provider (generates simulated telemetry)"
        )
        self._btn_mock.clicked.connect(self._toggle_mock)
        layout.addWidget(self._btn_mock)

        # Orbit speed combo (new)
        self._speed_combo = QComboBox()
        self._speed_combo.setFixedWidth(75)
        self._speed_combo.setToolTip("Orbit simulation speed")
        for speed, label in OrbitSimulator.SPEEDS.items():
            self._speed_combo.addItem(label, speed)
        self._speed_combo.currentIndexChanged.connect(self._on_speed_changed)
        layout.addWidget(self._speed_combo)

        layout.addStretch()
        return bar

    def _setup_shortcuts(self) -> None:
        """Alt+1…Alt+N jump to sidebar pages."""
        shortcuts = [
            "Terminal", "Dashboard", "Commands", "DSL Scripts", "REPL",
            "Housekeeping", "Map", "Orbit", "Images",
        ]
        for i, page in enumerate(shortcuts, start=1):
            if i > 9:
                break
            sc = QShortcut(QKeySequence(f"Alt+{i}"), self)
            sc.activated.connect(lambda p=page: self._navigate(p))

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
        if self._mock_active:
            self._mock_provider.stop()
        self._orbit_sim.stop()
        settings.set_window_geometry(bytes(self.saveGeometry()))
        settings.set_window_state(bytes(self.saveState()))
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Slots — navigation
    # ------------------------------------------------------------------

    @Slot(str)
    def _navigate(self, label: str) -> None:
        if label not in self._stack_pages:
            return
        idx = self._stack_pages.index(label)
        self._stack.setCurrentIndex(idx)
        for btn in self._nav_buttons:
            btn.setChecked(btn.text() == label)

    # ------------------------------------------------------------------
    # Slots — hardware connection
    # ------------------------------------------------------------------

    @Slot()
    def _refresh_ports(self) -> None:
        current = self._port_combo.currentText()
        ports = self._bridge.list_ports()
        self._port_combo.clear()
        for p in ports:
            self._port_combo.addItem(p)
        if not ports:
            self._port_combo.addItem("No ports found")
        idx = self._port_combo.findText(current)
        if idx >= 0:
            self._port_combo.setCurrentIndex(idx)

    @Slot()
    def _on_connect_clicked(self) -> None:
        port = self._port_combo.currentText()
        if port and port != "No ports found":
            settings.set_last_port(port)
            self._bridge.connect_port(port)

    @Slot(str)
    def _on_connected(self, port: str) -> None:
        self._status_bar.showMessage(
            f"Connected — {port}  |  Mock: {'ON' if self._mock_active else 'OFF'}"
        )
        self._conn_indicator.setObjectName("connIndicatorOn")
        self._conn_indicator.style().unpolish(self._conn_indicator)
        self._conn_indicator.style().polish(self._conn_indicator)
        self._btn_connect.setEnabled(False)
        self._btn_auto.setEnabled(False)
        self._btn_disconnect.setEnabled(True)
        self._hw_packet_count = 0
        self._bus.telemetry_request.connect(self._bridge.send_command)
        self._bus.connection_changed.emit("CONNECTED")

    @Slot()
    def _on_disconnected(self) -> None:
        self._status_bar.showMessage(
            f"Disconnected  |  Mock: {'ON' if self._mock_active else 'OFF'}"
        )
        self._conn_indicator.setObjectName("connIndicatorOff")
        self._conn_indicator.style().unpolish(self._conn_indicator)
        self._conn_indicator.style().polish(self._conn_indicator)
        self._btn_connect.setEnabled(True)
        self._btn_auto.setEnabled(True)
        self._btn_disconnect.setEnabled(False)
        try:
            self._bus.telemetry_request.disconnect(self._bridge.send_command)
        except RuntimeError:
            pass
        self._bus.connection_changed.emit("DISCONNECTED")

    @Slot(str)
    def _on_error(self, text: str) -> None:
        self._status_bar.showMessage(f"Error: {text}", 5000)
        logger.error(text)

    # ------------------------------------------------------------------
    # Slots — mock provider
    # ------------------------------------------------------------------

    @Slot()
    def _toggle_mock(self) -> None:
        if not self._mock_active:
            self._mock_provider.start()
            self._mock_active = True
            self._btn_mock.setText("Mock: ON")
            self._btn_mock.setStyleSheet(
                "QPushButton { background: #10b981; color: #0a0e1a; "
                "border: none; border-radius: 6px; font-weight: bold; }"
            )
            self._status_bar.showMessage("Mock mode active — simulated telemetry running")
            logger.info("Mock provider started")
        else:
            self._mock_provider.stop()
            self._mock_active = False
            self._btn_mock.setText("Mock: OFF")
            self._btn_mock.setStyleSheet("")
            self._status_bar.showMessage("Mock mode stopped")
            logger.info("Mock provider stopped")

    # ------------------------------------------------------------------
    # Slots — hardware telemetry → EventBus bridge
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_store_updated(self, key: str) -> None:
        """Bridge TelemetryStore → TelemetryFrame → EventBus for Dashboard."""
        if self._mock_active:
            return  # mock provider owns the bus when active

        self._hw_packet_count += 1

        def _get(k: str) -> float | None:
            s = self._store.latest(k)
            return s.value if s is not None else None

        def _get_or(k: str, default: float) -> float:
            v = _get(k)
            return v if v is not None else default

        # Voltage → battery percent (2S LiPo: 6.0 V = 0 %, 8.4 V = 100 %)
        batt_v = _get_or("Power/Battery Voltage", 0.0)
        batt_pct = max(0.0, min(100.0, (batt_v - 6.0) / 2.4 * 100.0)) if batt_v else 0.0

        solar_x = _get_or("Power/Solar Panel Current/X", 0.0)
        solar_y = _get_or("Power/Solar Panel Current/Y", 0.0)
        solar_ma = solar_x + solar_y

        sol_vxp = _get_or("Power/Solar Panel Voltage/X+", 0.0)
        sol_vxm = _get_or("Power/Solar Panel Voltage/X-", 0.0)
        sol_vym = _get_or("Power/Solar Panel Voltage/Y-", 0.0)
        sol_vyp = _get_or("Power/Solar Panel Voltage/Y+", 0.0)
        avg_sol_v = (sol_vxp + sol_vxm + sol_vym + sol_vyp) / 4.0
        power_mw = avg_sol_v * solar_ma

        alt_m = _get_or("GPS/Altitude", 0.0)

        frame = TelemetryFrame(
            temp_obc=_get_or("Environment/Temperature", 25.0),
            temp_battery=_get_or("Environment/Temperature", 22.0),
            battery_percent=batt_pct,
            battery_voltage=batt_v,
            solar_current_ma=solar_ma,
            power_consumption_mw=power_mw,
            gyro_x=_get_or("Attitude/Gyroscope/x", 0.0),
            gyro_y=_get_or("Attitude/Gyroscope/y", 0.0),
            gyro_z=_get_or("Attitude/Gyroscope/z", 0.0),
            latitude=_get_or("GPS/Coordinates/Lat", 0.0),
            longitude=_get_or("GPS/Coordinates/Lon", 0.0),
            altitude_km=alt_m / 1000.0,
            packet_count=self._hw_packet_count,
        )
        self._bus.telemetry_updated.emit(frame)

    # ------------------------------------------------------------------
    # Slots — orbit simulator
    # ------------------------------------------------------------------

    @Slot(object)
    def _on_orbit_state(self, state) -> None:
        """Forward orbit state to MockProvider (updates satellite position)."""
        if self._mock_active:
            self._mock_provider.update_orbit_position(
                state.latitude, state.longitude, state.altitude_km
            )
        # Emit orbit_updated on the EventBus for any tabs that subscribe
        self._bus.orbit_updated.emit({
            "lat": state.latitude,
            "lon": state.longitude,
            "alt_km": state.altitude_km,
            "velocity_km_s": state.velocity_km_s,
            "timestamp": state.timestamp.isoformat(),
        })

    @Slot()
    def _on_speed_changed(self) -> None:
        speed = self._speed_combo.currentData()
        if speed is not None:
            self._orbit_sim.set_speed(int(speed))
            logger.debug(f"Orbit simulation speed: {speed}×")

    # ------------------------------------------------------------------
    # Slots — settings
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_theme_changed(self, theme: str) -> None:
        from kitsat_gs.app import load_stylesheet
        self._app.setStyleSheet(load_stylesheet(theme))
        logger.info(f"Theme switched to {theme}")

    @Slot()
    def _on_gs_changed(self) -> None:
        from kitsat_gs.core.pass_predictor import GroundStation as LegacyGS
        gs = LegacyGS(
            lat=settings.gs_lat(),
            lon=settings.gs_lon(),
            alt_m=settings.gs_alt_m(),
        )
        self._map.set_ground_station(gs)
        self._orbit.set_ground_station(gs)
        # Update the new orbit simulator too
        self._orbit_sim.update_ground_station(
            lat=settings.gs_lat(),
            lon=settings.gs_lon(),
            alt_m=settings.gs_alt_m(),
        )
        logger.info(f"Ground station updated: {settings.gs_lat()}, {settings.gs_lon()}")
