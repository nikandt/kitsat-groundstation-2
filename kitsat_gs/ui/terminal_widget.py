"""
TerminalWidget — raw modem terminal with REPL-matching aerospace style.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QKeyEvent

if TYPE_CHECKING:
    from kitsat_gs.core.modem_bridge import ModemBridge


_C = {
    "bg_base":     "#0a0e1a",
    "bg_panel":    "#111827",
    "bg_raised":   "#1e2d3d",
    "accent_cyan": "#00d4ff",
    "success":     "#10b981",
    "warning":     "#f59e0b",
    "error":       "#ef4444",
    "text_primary":"#e2e8f0",
    "text_muted":  "#64748b",
    "border":      "#1e2d3d",
}


class _HistoryLineEdit(QLineEdit):
    """QLineEdit that navigates command history with up/down arrows."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._history: list[str] = []
        self._history_idx: int = -1

    def add_to_history(self, cmd: str) -> None:
        if cmd and (not self._history or self._history[-1] != cmd):
            self._history.append(cmd)
        self._history_idx = -1

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Up:
            if self._history:
                self._history_idx = min(self._history_idx + 1, len(self._history) - 1)
                self.setText(self._history[-(self._history_idx + 1)])
        elif event.key() == Qt.Key.Key_Down:
            if self._history_idx > 0:
                self._history_idx -= 1
                self.setText(self._history[-(self._history_idx + 1)])
            elif self._history_idx == 0:
                self._history_idx = -1
                self.clear()
        else:
            super().keyPressEvent(event)


class TerminalWidget(QWidget):
    def __init__(self, bridge: "ModemBridge", parent=None) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._bridge.message_received.connect(self._on_message)
        self._bridge.connected.connect(self._on_connected)
        self._bridge.disconnected.connect(self._on_disconnected)
        self._bridge.error.connect(self._on_error)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("Terminal")
        title.setStyleSheet(
            f"color:{_C['accent_cyan']}; font-size:12pt; font-weight:bold;"
        )
        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setFixedWidth(70)
        self._btn_clear.clicked.connect(self._output.clear if hasattr(self, '_output') else lambda: None)
        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(self._btn_clear)
        layout.addLayout(header_row)

        # Output log
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setStyleSheet(
            f"background:{_C['bg_panel']}; color:{_C['text_primary']}; "
            f"font-family:Consolas; font-size:10pt; "
            f"border:1px solid {_C['border']}; border-radius:6px;"
        )
        self._output.document().setMaximumBlockCount(2000)
        # wire clear button now that _output exists
        self._btn_clear.clicked.disconnect()
        self._btn_clear.clicked.connect(self._output.clear)
        layout.addWidget(self._output, stretch=1)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        prompt = QLabel(">>>")
        prompt.setStyleSheet(
            f"color:{_C['accent_cyan']}; font-family:Consolas; "
            f"font-size:10pt; font-weight:bold;"
        )
        input_row.addWidget(prompt)

        self._input = _HistoryLineEdit()
        self._input.setPlaceholderText("Enter command, e.g.  ping  or  beep 3")
        self._input.setStyleSheet(
            f"background:{_C['bg_raised']}; color:{_C['text_primary']}; "
            f"font-family:Consolas; font-size:10pt; "
            f"border:1px solid {_C['border']}; border-radius:6px; padding:4px 8px;"
        )
        self._input.returnPressed.connect(self._send)
        input_row.addWidget(self._input, stretch=1)

        self._btn_send = QPushButton("Send")
        self._btn_send.setFixedWidth(64)
        self._btn_send.setStyleSheet(
            f"QPushButton {{ background:{_C['accent_cyan']}; color:{_C['bg_base']}; "
            f"border:none; border-radius:6px; font-weight:bold; }}"
            f"QPushButton:hover {{ background:#33deff; }}"
        )
        self._btn_send.clicked.connect(self._send)
        input_row.addWidget(self._btn_send)

        layout.addLayout(input_row)

        self._print_system("Kitsat GS — Terminal ready.")
        self._print_system("Connect to a serial port, then type commands.")

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def _append_html(self, html: str) -> None:
        self._output.append(html)
        sb = self._output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _print_system(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._append_html(
            f"<span style='color:{_C['text_muted']}'>[{ts}] {text}</span>"
        )

    def _print_tx(self, cmd: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._append_html(
            f"<span style='color:{_C['text_muted']}'>[{ts}]</span> "
            f"<span style='color:{_C['accent_cyan']}'>&#8250;&#8250;&#8250; {cmd}</span>"
        )

    def _print_rx(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._append_html(
            f"<span style='color:{_C['text_muted']}'>[{ts}]</span> "
            f"<span style='color:{_C['text_primary']}'>{text}</span>"
        )

    def _print_error(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._append_html(
            f"<span style='color:{_C['text_muted']}'>[{ts}]</span> "
            f"<span style='color:{_C['error']}'>ERROR: {text}</span>"
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot()
    def _send(self) -> None:
        cmd = self._input.text().strip()
        if not cmd:
            return
        self._input.add_to_history(cmd)
        self._input.clear()
        self._print_tx(cmd)
        self._bridge.send_command(cmd)

    @Slot(object)
    def _on_message(self, msg: object) -> None:
        if isinstance(msg, list) and len(msg) >= 5:
            origin, cmd_id, data_len, timestamp, data = msg[0], msg[1], msg[2], msg[3], msg[4]
            self._print_rx(f"[orig={origin} cmd={cmd_id} len={data_len} ts={timestamp}] {data}")
        elif isinstance(msg, str):
            self._print_rx(msg)
        else:
            self._print_rx(str(msg))

    @Slot(str)
    def _on_connected(self, port: str) -> None:
        self._print_system(f"Connected — {port}")

    @Slot()
    def _on_disconnected(self) -> None:
        self._print_system("Disconnected.")

    @Slot(str)
    def _on_error(self, text: str) -> None:
        self._print_error(text)
