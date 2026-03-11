"""
MapWidget — interactive map showing satellite ground track and ground station.

Uses folium to generate an OpenStreetMap HTML page, loaded into a
QWebEngineView. Refreshes whenever a new ground track is computed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

import folium
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QGroupBox, QGridLayout,
    QPlainTextEdit,
)
from PySide6.QtCore import Qt, Slot, QUrl
from loguru import logger

from kitsat_gs.core.pass_predictor import PassPredictor, GroundStation
from kitsat_gs.core.tle_parser import from_string, Tle


_DEFAULT_TLE = """\
ISS (ZARYA)
1 25544U 98067A   24001.50000000  .00001764  00000-0  40000-4 0  9993
2 25544  51.6416 247.4627 0006703 130.5360 325.0288 15.50377579432900"""


class MapWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tle: Optional[Tle] = None
        self._gs = GroundStation(lat=60.17, lon=24.94, alt_m=10)  # Helsinki default
        self._tmp_html = Path(tempfile.mktemp(suffix=".html"))
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel("Map")
        header.setObjectName("panelHeader")
        layout.addWidget(header)

        # Controls row
        controls = QHBoxLayout()
        controls.setSpacing(8)

        # Ground station box
        gs_box = QGroupBox("Ground Station")
        gs_grid = QGridLayout(gs_box)
        gs_grid.setSpacing(4)
        gs_grid.addWidget(QLabel("Lat:"), 0, 0)
        self._gs_lat = QLineEdit(str(self._gs.lat))
        self._gs_lat.setFixedWidth(80)
        gs_grid.addWidget(self._gs_lat, 0, 1)
        gs_grid.addWidget(QLabel("Lon:"), 0, 2)
        self._gs_lon = QLineEdit(str(self._gs.lon))
        self._gs_lon.setFixedWidth(80)
        gs_grid.addWidget(self._gs_lon, 0, 3)
        controls.addWidget(gs_box)

        # TLE box
        tle_box = QGroupBox("TLE")
        tle_layout = QVBoxLayout(tle_box)
        self._tle_input = QPlainTextEdit(_DEFAULT_TLE)
        self._tle_input.setFixedHeight(70)
        self._tle_input.setObjectName("terminalOutput")
        tle_layout.addWidget(self._tle_input)
        controls.addWidget(tle_box, stretch=1)

        # Update button
        self._btn_update = QPushButton("Update Map")
        self._btn_update.setFixedWidth(100)
        self._btn_update.clicked.connect(self._on_update)
        controls.addWidget(self._btn_update, alignment=Qt.AlignBottom)

        layout.addLayout(controls)

        # Map view
        self._webview = QWebEngineView()
        layout.addWidget(self._webview, stretch=1)

        # Trigger initial render
        self._on_update()

    @Slot()
    def _on_update(self) -> None:
        try:
            self._gs = GroundStation(
                lat=float(self._gs_lat.text()),
                lon=float(self._gs_lon.text()),
            )
        except ValueError:
            logger.warning("MapWidget: invalid ground station coordinates")

        tle_text = self._tle_input.toPlainText()
        self._tle = from_string(tle_text)
        if self._tle is None:
            logger.warning("MapWidget: invalid TLE, rendering map without track")

        self._render_map()

    def _render_map(self) -> None:
        m = folium.Map(
            location=[self._gs.lat, self._gs.lon],
            zoom_start=3,
            tiles="OpenStreetMap",
        )

        # Ground station marker
        folium.Marker(
            location=[self._gs.lat, self._gs.lon],
            popup="Ground Station",
            tooltip="Ground Station",
            icon=folium.Icon(color="green", icon="antenna", prefix="fa"),
        ).add_to(m)

        # Ground track
        if self._tle is not None:
            try:
                predictor = PassPredictor(self._tle, self._gs)
                track = predictor.ground_track(minutes=100, step_s=30)
                if track:
                    # Split track at antimeridian crossings to avoid wrap-around lines
                    segments: list[list] = []
                    current: list = [list(track[0])]
                    for prev, curr in zip(track, track[1:]):
                        if abs(curr[1] - prev[1]) > 180:
                            segments.append(current)
                            current = [list(curr)]
                        else:
                            current.append(list(curr))
                    segments.append(current)

                    for seg in segments:
                        if len(seg) > 1:
                            folium.PolyLine(
                                seg, color="#00da96", weight=2, opacity=0.8
                            ).add_to(m)

                    # Current position
                    pos = predictor.current_position()
                    if pos:
                        folium.CircleMarker(
                            location=[pos.lat, pos.lon],
                            radius=6,
                            color="#00da96",
                            fill=True,
                            fill_color="#00da96",
                            popup=f"{self._tle.name}<br>Alt: {pos.alt_km:.1f} km",
                            tooltip=self._tle.name,
                        ).add_to(m)

                    # Upcoming passes
                    passes = predictor.find_passes(days=1)
                    for p in passes[:3]:
                        if p.sky_points:
                            apex = max(p.sky_points, key=lambda pt: pt.elevation)
                            folium.CircleMarker(
                                location=[apex.lat, apex.lon],
                                radius=4,
                                color="#ffaa00",
                                fill=True,
                                fill_color="#ffaa00",
                                popup=(
                                    f"Pass<br>"
                                    f"AOS: {p.aos.strftime('%H:%M:%S UTC')}<br>"
                                    f"Max El: {p.max_elevation:.1f}°<br>"
                                    f"Duration: {p.duration_s:.0f}s"
                                ),
                            ).add_to(m)
            except Exception as exc:
                logger.warning(f"MapWidget: propagation error: {exc}")

        m.save(str(self._tmp_html))
        self._webview.load(QUrl.fromLocalFile(str(self._tmp_html)))

    def set_tle(self, tle: Tle) -> None:
        """Update TLE from external source (e.g. settings widget)."""
        self._tle = tle
        self._tle_input.setPlainText(f"{tle.name}\n{tle.line1}\n{tle.line2}")
        self._render_map()

    def set_ground_station(self, gs: GroundStation) -> None:
        self._gs = gs
        self._gs_lat.setText(str(gs.lat))
        self._gs_lon.setText(str(gs.lon))
        self._render_map()
