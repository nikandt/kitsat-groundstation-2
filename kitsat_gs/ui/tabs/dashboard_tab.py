"""Dashboard tab — 6 circular gauges + live strip charts + status panels."""
from __future__ import annotations

from collections import deque

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QScrollArea,
)
from PySide6.QtCore import Qt, Slot

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bus = get_event_bus()
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

        self._lbl_qw = row("Q_w", 0)
        self._lbl_qx = row("Q_x", 1)
        self._lbl_qy = row("Q_y", 2)
        self._lbl_qz = row("Q_z", 3)
        self._lbl_gx = row("ω_x (°/s)", 4)
        self._lbl_gy = row("ω_y (°/s)", 5)
        self._lbl_gz = row("ω_z (°/s)", 6)

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

        # Attitude
        self._lbl_qw.setText(f"{frame.attitude_w:.4f}")
        self._lbl_qx.setText(f"{frame.attitude_x:.4f}")
        self._lbl_qy.setText(f"{frame.attitude_y:.4f}")
        self._lbl_qz.setText(f"{frame.attitude_z:.4f}")
        self._lbl_gx.setText(f"{frame.gyro_x:+.3f}")
        self._lbl_gy.setText(f"{frame.gyro_y:+.3f}")
        self._lbl_gz.setText(f"{frame.gyro_z:+.3f}")

        # GNSS
        self._lbl_lat.setText(f"{frame.latitude:.4f}°")
        self._lbl_lon.setText(f"{frame.longitude:.4f}°")
        self._lbl_alt.setText(f"{frame.altitude_km:.1f} km")
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
