"""
HousekeepingWidget — live telemetry display panel.

Shows all housekeeping channels in a table that updates in real-time
as packets arrive. Each row: channel name | latest value | unit | timestamp.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QPushButton,
    QHeaderView, QFileDialog,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont

from kitsat_gs.core.telemetry_store import TelemetryStore
from kitsat_gs.core import housekeeping_catalog, telemetry_exporter


class HousekeepingWidget(QWidget):
    def __init__(self, store: TelemetryStore, parent=None) -> None:
        super().__init__(parent)
        self._store = store
        self._store.updated.connect(self._on_updated)
        self._row_map: dict[str, int] = {}   # key → table row index
        self._build_ui()
        self._populate_rows()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QLabel("Housekeeping")
        header.setObjectName("panelHeader")
        layout.addWidget(header)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Channel", "Value", "Unit", "Updated"])
        self._table.setObjectName("housekeepingTable")
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        mono = QFont("Courier New", 10)
        self._table.setFont(mono)
        layout.addWidget(self._table, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setFixedWidth(70)
        self._btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(self._btn_clear)

        self._btn_export = QPushButton("Export CSV")
        self._btn_export.setFixedWidth(90)
        self._btn_export.clicked.connect(self._on_export)
        btn_row.addWidget(self._btn_export)

        layout.addLayout(btn_row)

    def _populate_rows(self) -> None:
        """Pre-populate one row per housekeeping channel."""
        for hk in housekeeping_catalog.load():
            if hk.subvalues:
                for sv in hk.subvalues:
                    self._add_row(f"{hk.type}/{hk.subtype}/{sv}", hk.units)
            else:
                self._add_row(f"{hk.type}/{hk.subtype}", hk.units)

    def _add_row(self, key: str, units: str) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(key))
        val_item = QTableWidgetItem("—")
        val_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._table.setItem(row, 1, val_item)
        self._table.setItem(row, 2, QTableWidgetItem(units))
        self._table.setItem(row, 3, QTableWidgetItem("—"))
        self._row_map[key] = row

    @Slot(str)
    def _on_updated(self, key: str) -> None:
        sample = self._store.latest(key)
        if sample is None:
            return
        row = self._row_map.get(key)
        if row is None:
            return
        val_item = self._table.item(row, 1)
        ts_item = self._table.item(row, 3)
        if val_item:
            val_item.setText(f"{sample.value:.4f}")
        if ts_item:
            ts_item.setText(datetime.fromtimestamp(sample.timestamp).strftime("%H:%M:%S"))

    @Slot()
    def _on_clear(self) -> None:
        self._store.clear()
        for row in range(self._table.rowCount()):
            val_item = self._table.item(row, 1)
            ts_item = self._table.item(row, 3)
            if val_item:
                val_item.setText("—")
            if ts_item:
                ts_item.setText("—")

    @Slot()
    def _on_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Telemetry CSV", "", "CSV files (*.csv)"
        )
        if path:
            telemetry_exporter.export(self._store, path=__import__("pathlib").Path(path))
