"""Dashboard tab — 6 circular gauges + live strip charts + status panels."""
from __future__ import annotations

from collections import deque

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QScrollArea, QPushButton,
)
from PySide6.QtCore import Qt, Slot, QTimer

try:
    import pyqtgraph as pg
    PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False

from kitsat_gs.core.events import get_event_bus
from kitsat_gs.core.models import TelemetryFrame
from kitsat_gs.ui.widgets.gauge import CircularGauge
from kitsat_gs.ui.widgets.status_led import StatusLED

_C = {
    "bg_base":     "#0a0e1a",
    "bg_panel":    "#111827",
    "bg_raised":   "#1e2d3d",
    "accent_cyan": "#00d4ff",
    "accent_blue": "#3b82f6",
    "success":     "#10b981",
    "warning":     "#f59e0b",
    "error":       "#ef4444",
    "text_primary":"#e2e8f0",
    "text_muted":  "#64748b",
    "border":      "#1e2d3d",
}


def _panel(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setStyleSheet(
        f"QFrame {{ background:{_C['bg_panel']}; "
        f"border:1px solid {_C['border']}; border-radius:6px; padding:6px; }}"
    )
    return f


def _header(text: str, parent=None) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setStyleSheet(
        f"color:{_C['accent_cyan']}; font-size:10pt; font-weight:bold; "
        f"letter-spacing:0.08em;"
    )
    return lbl


class MiniChart(QWidget):
    """Rolling 120-point strip chart (pyqtgraph)."""
    MAX_POINTS = 120

    def __init__(self, title: str, unit: str, color: str,
                 y_min: float = None, y_max: float = None, parent=None):
        super().__init__(parent)
        self._data: deque = deque(maxlen=self.MAX_POINTS)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not PG_AVAILABLE:
            lbl = QLabel(f"{title}: pyqtgraph not available")
            lbl.setStyleSheet(f"color:{_C['text_muted']}; font-size:9pt;")
            layout.addWidget(lbl)
            return

        pg.setConfigOptions(antialias=True, background=_C["bg_panel"],
                            foreground=_C["text_muted"])
        self._plot = pg.PlotWidget()
        self._plot.setTitle(title, color=_C["text_muted"], size="9pt")
        self._plot.setLabel("left", unit, color=_C["text_muted"])
        self._plot.showGrid(x=True, y=True, alpha=0.15)
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.getAxis("bottom").hide()
        if y_min is not None and y_max is not None:
            self._plot.setYRange(y_min, y_max)
        self._plot.setMinimumHeight(100)
        self._curve = self._plot.plot(pen=pg.mkPen(color=color, width=1.5))
        layout.addWidget(self._plot)

    def push(self, value: float):
        self._data.append(value)
        if PG_AVAILABLE and hasattr(self, "_curve"):
            self._curve.setData(list(self._data))


class DashboardTab(QWidget):
    """Main telemetry dashboard with gauges, charts, attitude, and GNSS."""

    _POLL_COMMANDS = ["imu_get_all", "gps_get_all", "eps_measure", "env_get_temp"]
    _POLL_INTERVAL_MS = 5000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bus = get_event_bus()
        self._poll_active = False
        self._connected = False

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._on_poll_tick)

        self._setup_ui()
        self._bus.telemetry_updated.connect(self._on_telemetry)
        self._bus.connection_changed.connect(self._on_connection)

    def _setup_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        main = QVBoxLayout(content)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(12)

        # Hint bar — hidden once first telemetry arrives
        self._hint = QLabel(
            "Waiting for telemetry — send housekeeping commands "
            "(e.g. imu_get_all, eps_get_batt_volt, gps_get_lat_lon) "
            "or enable Mock mode to see live data."
        )
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(
            f"color:{_C['warning']}; font-size:9pt; "
            f"background:{_C['bg_raised']}; border-radius:4px; padding:6px;"
        )
        main.addWidget(self._hint)

        # Poll controls bar
        poll_bar = QHBoxLayout()
        self._btn_poll = QPushButton("Auto-poll: OFF")
        self._btn_poll.setCheckable(True)
        self._btn_poll.setMinimumWidth(110)
        self._btn_poll.setEnabled(False)
        self._btn_poll.clicked.connect(self._toggle_poll)
        poll_bar.addWidget(self._btn_poll)

        self._btn_poll_now = QPushButton("Poll Now")
        self._btn_poll_now.setMinimumWidth(80)
        self._btn_poll_now.setEnabled(False)
        self._btn_poll_now.clicked.connect(self._on_poll_tick)
        poll_bar.addWidget(self._btn_poll_now)

        self._lbl_last_poll = QLabel("Last poll: —")
        self._lbl_last_poll.setStyleSheet(
            f"color:{_C['text_muted']}; font-size:9pt;"
        )
        poll_bar.addWidget(self._lbl_last_poll)
        poll_bar.addStretch()
        main.addLayout(poll_bar)

        # Row 1: status + attitude + GNSS
        row1 = QHBoxLayout()
        row1.addWidget(self._build_status_panel())
        row1.addWidget(self._build_attitude_panel())
        row1.addWidget(self._build_gnss_panel())
        main.addLayout(row1)

        # Row 2: gauges
        main.addWidget(self._build_gauges_panel())

        # Row 3: charts
        charts_row = QHBoxLayout()
        self._battery_chart = MiniChart("Battery", "%", _C["accent_cyan"],
                                        y_min=0, y_max=100)
        self._temp_obc_chart = MiniChart("OBC Temp", "°C", _C["warning"],
                                         y_min=-20, y_max=80)
        self._solar_chart = MiniChart("Solar Current", "mA", _C["success"],
                                      y_min=0, y_max=600)
        self._power_chart = MiniChart("Power Consumption", "mW", _C["error"],
                                      y_min=0, y_max=1500)
        for chart in [self._battery_chart, self._temp_obc_chart,
                      self._solar_chart, self._power_chart]:
            charts_row.addWidget(chart)
        main.addLayout(charts_row)
        main.addStretch()

    def _build_status_panel(self) -> QFrame:
        panel = _panel()
        layout = QVBoxLayout(panel)
        layout.addWidget(_header("Satellite Status"))

        grid = QGridLayout()
        grid.setSpacing(8)

        def row(label, r):
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{_C['text_muted']}; font-size:9pt;")
            val = QLabel("—")
            val.setStyleSheet(
                f"color:{_C['text_primary']}; font-family:Consolas; font-size:10pt;"
            )
            grid.addWidget(lbl, r, 0)
            grid.addWidget(val, r, 1)
            return val

        self._lbl_mode    = row("Mode", 0)
        self._lbl_uptime  = row("Uptime", 1)
        self._lbl_packets = row("Packets", 2)
        self._lbl_rssi    = row("RSSI", 3)
        layout.addLayout(grid)

        led_row = QHBoxLayout()
        self._status_led = StatusLED("red", 14)
        self._conn_text = QLabel("DISCONNECTED")
        self._conn_text.setStyleSheet(
            f"color:{_C['error']}; font-weight:bold; font-size:9pt;"
        )
        led_row.addWidget(self._status_led)
        led_row.addWidget(self._conn_text)
        led_row.addStretch()
        layout.addLayout(led_row)
        layout.addStretch()
        return panel

    def _build_attitude_panel(self) -> QFrame:
        panel = _panel()
        layout = QVBoxLayout(panel)
        layout.addWidget(_header("Attitude / IMU"))

        grid = QGridLayout()
        grid.setSpacing(6)

        def row(label, r):
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{_C['text_muted']}; font-size:9pt;")
            val = QLabel("—")
            val.setStyleSheet(
                f"color:{_C['text_primary']}; font-family:Consolas; font-size:10pt;"
            )
            grid.addWidget(lbl, r, 0)
            grid.addWidget(val, r, 1)
            return val

        self._lbl_mx = row("Mag X (Gs)", 0)
        self._lbl_my = row("Mag Y (Gs)", 1)
        self._lbl_mz = row("Mag Z (Gs)", 2)
        self._lbl_gx = row("ω_x (°/s)", 3)
        self._lbl_gy = row("ω_y (°/s)", 4)
        self._lbl_gz = row("ω_z (°/s)", 5)

        layout.addLayout(grid)
        layout.addStretch()
        return panel

    def _build_gnss_panel(self) -> QFrame:
        panel = _panel()
        layout = QVBoxLayout(panel)
        layout.addWidget(_header("GNSS / Position"))

        grid = QGridLayout()
        grid.setSpacing(6)

        def row(label, r):
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{_C['text_muted']}; font-size:9pt;")
            val = QLabel("—")
            val.setStyleSheet(
                f"color:{_C['text_primary']}; font-family:Consolas; font-size:10pt;"
            )
            grid.addWidget(lbl, r, 0)
            grid.addWidget(val, r, 1)
            return val

        self._lbl_lat = row("Latitude", 0)
        self._lbl_lon = row("Longitude", 1)
        self._lbl_alt = row("Altitude", 2)
        self._lbl_ts  = row("Timestamp", 3)

        layout.addLayout(grid)

        self._lbl_nofix = QLabel("No GPS fix — send gps_get_all and ensure open sky view")
        self._lbl_nofix.setWordWrap(True)
        self._lbl_nofix.setStyleSheet(
            f"color:{_C['warning']}; font-size:8pt; padding-top:4px;"
        )
        layout.addWidget(self._lbl_nofix)
        layout.addStretch()
        return panel

    def _build_gauges_panel(self) -> QFrame:
        panel = _panel()
        layout = QVBoxLayout(panel)
        layout.addWidget(_header("Sensors"))

        gauge_row = QHBoxLayout()
        gauge_row.setSpacing(16)

        self._gauge_battery   = CircularGauge("Battery", "%", 0, 100,
                                               warn_val=30, error_val=15, size=110)
        self._gauge_temp_obc  = CircularGauge("OBC Temp", "°C", -30, 80,
                                               warn_val=55, error_val=70, size=110)
        self._gauge_temp_batt = CircularGauge("Batt Temp", "°C", -20, 60,
                                               warn_val=45, error_val=55, size=110)
        self._gauge_temp_px   = CircularGauge("+X Panel", "°C", -40, 100,
                                               warn_val=70, error_val=85, size=110)
        self._gauge_solar     = CircularGauge("Solar", "mA", 0, 600,
                                               warn_val=None, error_val=None, size=110)
        self._gauge_power     = CircularGauge("Power", "mW", 0, 1500,
                                               warn_val=1200, error_val=1400, size=110)

        for g in [self._gauge_battery, self._gauge_temp_obc, self._gauge_temp_batt,
                  self._gauge_temp_px, self._gauge_solar, self._gauge_power]:
            gauge_row.addWidget(g, alignment=Qt.AlignmentFlag.AlignCenter)
        gauge_row.addStretch()
        layout.addLayout(gauge_row)
        return panel

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(object)
    def _on_telemetry(self, frame: TelemetryFrame) -> None:
        self._hint.setVisible(False)
        # Status panel
        mode_color = _C["error"] if frame.mode == "fault" else _C["success"]
        self._lbl_mode.setText(frame.mode.upper())
        self._lbl_mode.setStyleSheet(
            f"color:{mode_color}; font-family:Consolas; font-size:10pt; font-weight:bold;"
        )
        h, rem = divmod(frame.uptime_s, 3600)
        m, s = divmod(rem, 60)
        self._lbl_uptime.setText(f"{h:02d}:{m:02d}:{s:02d}")
        self._lbl_packets.setText(str(frame.packet_count))
        rssi_color = _C["success"] if frame.rssi_dbm > -90 else _C["warning"]
        self._lbl_rssi.setText(f"{frame.rssi_dbm:.1f} dBm")
        self._lbl_rssi.setStyleSheet(
            f"color:{rssi_color}; font-family:Consolas; font-size:10pt;"
        )

        # Attitude / IMU
        self._lbl_mx.setText(f"{frame.mag_x:+.2f}")
        self._lbl_my.setText(f"{frame.mag_y:+.2f}")
        self._lbl_mz.setText(f"{frame.mag_z:+.2f}")
        self._lbl_gx.setText(f"{frame.gyro_x:+.3f}")
        self._lbl_gy.setText(f"{frame.gyro_y:+.3f}")
        self._lbl_gz.setText(f"{frame.gyro_z:+.3f}")

        # GNSS
        gps_fix = not (frame.latitude == 0.0 and frame.longitude == 0.0)
        self._lbl_nofix.setVisible(not gps_fix)
        if gps_fix:
            self._lbl_lat.setText(f"{frame.latitude:.5f}°")
            self._lbl_lon.setText(f"{frame.longitude:.5f}°")
            self._lbl_alt.setText(f"{frame.altitude_km * 1000:.1f} m")
        else:
            self._lbl_lat.setText("No fix")
            self._lbl_lon.setText("—")
            self._lbl_alt.setText("—")
        self._lbl_ts.setText(frame.timestamp.strftime("%H:%M:%S"))

        # Gauges
        self._gauge_battery.set_value(frame.battery_percent)
        self._gauge_temp_obc.set_value(frame.temp_obc)
        self._gauge_temp_batt.set_value(frame.temp_battery)
        self._gauge_temp_px.set_value(frame.temp_panel_x)
        self._gauge_solar.set_value(frame.solar_current_ma)
        self._gauge_power.set_value(frame.power_consumption_mw)

        # Charts
        self._battery_chart.push(frame.battery_percent)
        self._temp_obc_chart.push(frame.temp_obc)
        self._solar_chart.push(frame.solar_current_ma)
        self._power_chart.push(frame.power_consumption_mw)

    @Slot(str)
    def _on_connection(self, state: str) -> None:
        self._connected = (state == "CONNECTED")
        self._status_led.set_state(state)
        colors = {
            "CONNECTED":    (_C["success"], "CONNECTED"),
            "SEARCHING":    (_C["warning"], "SEARCHING…"),
            "DISCONNECTED": (_C["error"],   "DISCONNECTED"),
        }
        color, text = colors.get(state, (_C["error"], state))
        self._conn_text.setText(text)
        self._conn_text.setStyleSheet(
            f"color:{color}; font-weight:bold; font-size:9pt;"
        )
        self._btn_poll.setEnabled(self._connected)
        self._btn_poll_now.setEnabled(self._connected)
        if not self._connected and self._poll_active:
            self._stop_poll()

    @Slot()
    def _toggle_poll(self) -> None:
        if self._poll_active:
            self._stop_poll()
        else:
            self._start_poll()

    def _start_poll(self) -> None:
        self._poll_active = True
        self._btn_poll.setText("Auto-poll: ON")
        self._btn_poll.setStyleSheet(
            "QPushButton { background:#10b981; color:#0a0e1a; "
            "border:none; border-radius:4px; font-weight:bold; }"
        )
        self._poll_timer.start()
        self._on_poll_tick()   # fire immediately

    def _stop_poll(self) -> None:
        self._poll_active = False
        self._poll_timer.stop()
        self._btn_poll.setChecked(False)
        self._btn_poll.setText("Auto-poll: OFF")
        self._btn_poll.setStyleSheet("")

    @Slot()
    def _on_poll_tick(self) -> None:
        if not self._connected:
            return
        for cmd in self._POLL_COMMANDS:
            self._bus.telemetry_request.emit(cmd)
        self._lbl_last_poll.setText(
            f"Last poll: {datetime.now().strftime('%H:%M:%S')}"
        )
