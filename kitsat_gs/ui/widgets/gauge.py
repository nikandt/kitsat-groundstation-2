"""Circular arc gauge widget (QPainter-based)."""
from __future__ import annotations

import math

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics

# Color palette (matches aerospace theme)
_C = {
    "bg_raised":    "#1e2d3d",
    "success":      "#10b981",
    "warning":      "#f59e0b",
    "error":        "#ef4444",
    "text_primary": "#e2e8f0",
    "text_muted":   "#64748b",
}


class CircularGauge(QWidget):
    """240° arc gauge with color-coded thresholds.

    Arc sweeps from lower-left (-220°) to lower-right (+40°) in Qt coordinates.
    """

    ARC_START = -220
    ARC_SWEEP = 240

    def __init__(self, label: str = "", unit: str = "",
                 min_val: float = 0.0, max_val: float = 100.0,
                 warn_val: float = None, error_val: float = None,
                 size: int = 120, parent=None):
        super().__init__(parent)
        self._label = label
        self._unit = unit
        self._min = min_val
        self._max = max_val
        self._warn = warn_val
        self._error = error_val
        self._value = min_val
        self._size = size
        self.setFixedSize(size, size)

    def set_value(self, value: float) -> None:
        self._value = max(self._min, min(self._max, value))
        self.update()

    @property
    def value(self) -> float:
        return self._value

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        margin = 10
        r = min(w, h) / 2 - margin
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)

        # Background arc track
        track_pen = QPen(QColor(_C["bg_raised"]))
        track_pen.setWidth(8)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(rect,
                        int((90 - self.ARC_START) * 16),
                        int(-self.ARC_SWEEP * 16))

        # Value arc
        fraction = (self._value - self._min) / max(1e-9, self._max - self._min)
        sweep = fraction * self.ARC_SWEEP

        arc_color = _C["success"]
        if self._error is not None and self._value >= self._error:
            arc_color = _C["error"]
        elif self._warn is not None and self._value >= self._warn:
            arc_color = _C["warning"]

        val_pen = QPen(QColor(arc_color))
        val_pen.setWidth(8)
        val_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(val_pen)
        painter.drawArc(rect,
                        int((90 - self.ARC_START) * 16),
                        int(-sweep * 16))

        # Value text (center)
        painter.setPen(QColor(_C["text_primary"]))
        val_font = QFont("Consolas", max(8, self._size // 8), QFont.Weight.Bold)
        painter.setFont(val_font)
        val_str = f"{self._value:.1f}"
        fm = QFontMetrics(val_font)
        tw = fm.horizontalAdvance(val_str)
        th = fm.height()
        painter.drawText(QPointF(cx - tw / 2, cy + th / 4), val_str)

        # Unit text
        unit_font = QFont("Consolas", max(6, self._size // 14))
        painter.setFont(unit_font)
        painter.setPen(QColor(_C["text_muted"]))
        ufm = QFontMetrics(unit_font)
        utw = ufm.horizontalAdvance(self._unit)
        painter.drawText(QPointF(cx - utw / 2, cy + th * 1.1), self._unit)

        # Label text (bottom)
        label_font = QFont("Segoe UI", max(7, self._size // 13))
        painter.setFont(label_font)
        painter.setPen(QColor(_C["text_muted"]))
        lfm = QFontMetrics(label_font)
        ltw = lfm.horizontalAdvance(self._label)
        painter.drawText(QPointF(cx - ltw / 2, cy + r - 2), self._label)

        painter.end()
