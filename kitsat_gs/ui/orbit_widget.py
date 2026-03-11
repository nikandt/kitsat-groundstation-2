"""
OrbitWidget — polar sky plot showing satellite passes.

Uses pyqtgraph to draw a polar plot:
  - Centre = zenith (90° elevation)
  - Edge = horizon (0° elevation)
  - Angle = azimuth (0=N, 90=E, 180=S, 270=W)
  - Current pass arc rendered in accent green
  - Upcoming passes in dimmed yellow
  - Cardinal directions labelled
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter,
)
from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QFont
from loguru import logger

from kitsat_gs.core.pass_predictor import PassPredictor, GroundStation, PassInfo, SkyPoint
from kitsat_gs.core.tle_parser import Tle, from_string


_DEFAULT_TLE = """\
ISS (ZARYA)
1 25544U 98067A   24001.50000000  .00001764  00000-0  40000-4 0  9993
2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.50377579432900"""

_ACCENT = (0, 218, 150)       # #00da96
_PASS_DIM = (255, 170, 0, 120)
_HORIZON = (80, 80, 80)
_GRID_COLOR = (50, 50, 50)


def _sky_to_xy(azimuth_deg: float, elevation_deg: float) -> tuple[float, float]:
    """Convert az/el to Cartesian for polar plot (radius = 1 at horizon, 0 at zenith)."""
    r = 1.0 - elevation_deg / 90.0
    az_r = math.radians(azimuth_deg)
    x = r * math.sin(az_r)
    y = r * math.cos(az_r)
    return x, y


class _PolarPlot(pg.PlotWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setBackground("#141414")
        self.setAspectLocked(True)
        self.hideAxis("left")
        self.hideAxis("bottom")
        self.setRange(xRange=(-1.15, 1.15), yRange=(-1.15, 1.15))
        self.setMouseEnabled(x=False, y=False)
        self._draw_grid()
        self._draw_cardinals()

    def _draw_grid(self) -> None:
        """Draw horizon, elevation rings (30°, 60°) and azimuth spokes."""
        pen_horizon = pg.mkPen(color=_HORIZON, width=1.5)
        pen_grid = pg.mkPen(color=_GRID_COLOR, width=1, style=Qt.DashLine)

        # Elevation circles: 0° (horizon), 30°, 60°
        for el in (0, 30, 60):
            r = 1.0 - el / 90.0
            circle = pg.QtWidgets.QGraphicsEllipseItem(-r, -r, 2 * r, 2 * r)
            pen = pen_horizon if el == 0 else pen_grid
            circle.setPen(QtGui.QPen(pen.color(), pen.width()))
            circle.setBrush(QtGui.QBrush(QtCore.Qt.NoBrush))
            self.addItem(circle)

            if el > 0:
                label = pg.TextItem(f"{el}°", anchor=(0.5, 0.5), color="#555555")
                label.setPos(0, -r)
                self.addItem(label)

        # Azimuth spokes every 45°
        for az in range(0, 360, 45):
            az_r = math.radians(az)
            x, y = math.sin(az_r), math.cos(az_r)
            self.plot([0, x], [0, y], pen=pen_grid)

    def _draw_cardinals(self) -> None:
        for label, az in [("N", 0), ("E", 90), ("S", 180), ("W", 270)]:
            az_r = math.radians(az)
            x = 1.1 * math.sin(az_r)
            y = 1.1 * math.cos(az_r)
            t = pg.TextItem(label, anchor=(0.5, 0.5), color="#888888")
            f = QFont()
            f.setBold(True)
            t.setFont(f)
            t.setPos(x, y)
            self.addItem(t)

    def plot_pass(self, sky_points: list[SkyPoint], color=_ACCENT, width: int = 2) -> None:
        if not sky_points:
            return
        xs, ys = zip(*[_sky_to_xy(p.azimuth, p.elevation) for p in sky_points])
        self.plot(list(xs), list(ys),
                  pen=pg.mkPen(color=color, width=width),
                  symbol="o", symbolSize=3,
                  symbolPen=pg.mkPen(None),
                  symbolBrush=pg.mkBrush(color=color))

    def plot_current(self, pt: SkyPoint) -> None:
        x, y = _sky_to_xy(pt.azimuth, pt.elevation)
        self.plot([x], [y],
                  symbol="o", symbolSize=10,
                  symbolPen=pg.mkPen(color=_ACCENT, width=2),
                  symbolBrush=pg.mkBrush(color=(*_ACCENT, 200)))


class OrbitWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tle: Optional[Tle] = from_string(_DEFAULT_TLE)
        self._gs = GroundStation(lat=60.17, lon=24.94)
        self._passes: list[PassInfo] = []
        self._build_ui()
        self._refresh()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_current_pos)
        self._timer.start(5000)   # update current position every 5s

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel("Orbit / Sky View")
        header.setObjectName("panelHeader")
        layout.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)

        # Left: polar plot
        self._polar = _PolarPlot()
        splitter.addWidget(self._polar)

        # Right: pass table
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._pass_table = QTableWidget(0, 4)
        self._pass_table.setHorizontalHeaderLabels(["AOS (UTC)", "LOS (UTC)", "Max El", "Duration"])
        self._pass_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._pass_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._pass_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._pass_table.verticalHeader().setVisible(False)
        self._pass_table.itemSelectionChanged.connect(self._on_pass_selected)
        right_layout.addWidget(self._pass_table)

        self._btn_refresh = QPushButton("Recalculate Passes")
        self._btn_refresh.clicked.connect(self._refresh)
        right_layout.addWidget(self._btn_refresh)

        splitter.addWidget(right)
        splitter.setSizes([500, 300])
        layout.addWidget(splitter, stretch=1)

    @Slot()
    def _refresh(self) -> None:
        if self._tle is None:
            return
        try:
            predictor = PassPredictor(self._tle, self._gs)
            self._passes = predictor.find_passes(days=2)
            self._populate_table()
            self._draw_passes()
            self._update_current_pos()
        except Exception as exc:
            logger.warning(f"OrbitWidget: {exc}")

    def _populate_table(self) -> None:
        self._pass_table.setRowCount(0)
        for p in self._passes:
            row = self._pass_table.rowCount()
            self._pass_table.insertRow(row)
            self._pass_table.setItem(row, 0, QTableWidgetItem(p.aos.strftime("%m-%d %H:%M:%S")))
            self._pass_table.setItem(row, 1, QTableWidgetItem(p.los.strftime("%m-%d %H:%M:%S")))
            el_item = QTableWidgetItem(f"{p.max_elevation:.1f}°")
            el_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._pass_table.setItem(row, 2, el_item)
            dur = QTableWidgetItem(f"{p.duration_s:.0f}s")
            dur.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._pass_table.setItem(row, 3, dur)

    def _draw_passes(self) -> None:
        self._polar.clear()
        self._polar._draw_grid()
        self._polar._draw_cardinals()
        for p in self._passes[:5]:
            self._polar.plot_pass(p.sky_points, color=_PASS_DIM, width=1)

    @Slot()
    def _on_pass_selected(self) -> None:
        rows = self._pass_table.selectedItems()
        if not rows:
            return
        row = self._pass_table.currentRow()
        if 0 <= row < len(self._passes):
            self._draw_passes()
            self._polar.plot_pass(self._passes[row].sky_points, color=_ACCENT, width=2)

    @Slot()
    def _update_current_pos(self) -> None:
        if self._tle is None:
            return
        try:
            predictor = PassPredictor(self._tle, self._gs)
            pos = predictor.current_position()
            if pos and pos.elevation > 0:
                self._polar.plot_current(pos)
        except Exception:
            pass

    def set_tle(self, tle: Tle) -> None:
        self._tle = tle
        self._refresh()

    def set_ground_station(self, gs: GroundStation) -> None:
        self._gs = gs
        self._refresh()
