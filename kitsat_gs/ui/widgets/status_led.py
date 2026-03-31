"""Animated LED indicator widget."""
from __future__ import annotations

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QPainter, QColor, QRadialGradient

_STATE_COLORS = {
    "green": ("#10b981", "#d1fae5"),
    "amber": ("#f59e0b", "#fef3c7"),
    "red":   ("#ef4444", "#fee2e2"),
    "blue":  ("#00d4ff", "#cffafe"),
    "off":   ("#64748b", "#1e2d3d"),
}


class StatusLED(QWidget):
    """A small circular LED that pulses when in SEARCHING state."""

    def __init__(self, color: str = "green", size: int = 14, parent=None):
        super().__init__(parent)
        self._color_key = color
        self._size = size
        self._alpha = 255
        self._alpha_dir = -8
        self._pulsing = False
        self.setFixedSize(size, size)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_step)

    def set_color(self, color: str) -> None:
        self._color_key = color
        self.update()

    def set_state(self, state: str) -> None:
        """Map CONNECTED/SEARCHING/DISCONNECTED to a color and pulse."""
        mapping = {
            "CONNECTED":    "green",
            "SEARCHING":    "amber",
            "DISCONNECTED": "red",
        }
        self.set_color(mapping.get(state, "red"))
        if state == "SEARCHING":
            self.start_pulse()
        else:
            self.stop_pulse()

    def start_pulse(self) -> None:
        self._pulsing = True
        self._pulse_timer.start(40)

    def stop_pulse(self) -> None:
        self._pulsing = False
        self._pulse_timer.stop()
        self._alpha = 255
        self.update()

    def _pulse_step(self) -> None:
        self._alpha += self._alpha_dir
        if self._alpha <= 60:
            self._alpha_dir = 8
        elif self._alpha >= 255:
            self._alpha_dir = -8
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        outer, inner = _STATE_COLORS.get(self._color_key, _STATE_COLORS["off"])
        outer_c = QColor(outer)
        outer_c.setAlpha(self._alpha)

        cx = self._size / 2
        cy = self._size / 2
        r = self._size / 2 - 1

        grad = QRadialGradient(cx * 0.7, cy * 0.6, r * 0.4, cx, cy, r)
        inner_c = QColor(inner)
        inner_c.setAlpha(self._alpha)
        grad.setColorAt(0, inner_c)
        grad.setColorAt(1, outer_c)

        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(1, 1, self._size - 2, self._size - 2))
        painter.end()
