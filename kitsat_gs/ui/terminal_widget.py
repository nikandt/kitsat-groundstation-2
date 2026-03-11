"""
TerminalWidget — command input and raw packet output log.

- Top area: scrollable output log (read-only)
- Bottom area: command input with send button
- Supports command history (up/down arrow keys)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QLineEdit, QPushButton, QLabel,
)
from PySide6.QtCore import Qt, Slot, QStringListModel
from PySide6.QtGui import QFont, QKeyEvent, QTextCursor, QColor

if TYPE_CHECKING:
    from kitsat_gs.core.modem_bridge import ModemBridge


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
        if event.key() == Qt.Key_Up:
            if self._history:
                self._history_idx = min(self._history_idx + 1, len(self._history) - 1)
                self.setText(self._history[-(self._history_idx + 1)])
        elif event.key() == Qt.Key_Down:
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

        # Header label
        header = QLabel("Terminal")
        header.setObjectName("panelHeader")
        layout.addWidget(header)

        # Output log
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setObjectName("terminalOutput")
        mono = QFont("Courier New", 10)
        mono.setStyleHint(QFont.Monospace)
        self._output.setFont(mono)
        self._output.setMaximumBlockCount(2000)
        layout.addWidget(self._output, stretch=1)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self._prompt = QLabel(">>>")
        self._prompt.setObjectName("terminalPrompt")
        input_row.addWidget(self._prompt)

        self._input = _HistoryLineEdit()
        self._input.setObjectName("terminalInput")
        self._input.setPlaceholderText("Enter command, e.g.  ping  or  beep 3")
        self._input.returnPressed.connect(self._send)
        input_row.addWidget(self._input, stretch=1)

        self._btn_send = QPushButton("Send")
        self._btn_send.setFixedWidth(64)
        self._btn_send.clicked.connect(self._send)
        input_row.addWidget(self._btn_send)

        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setFixedWidth(60)
        self._btn_clear.clicked.connect(self._output.clear)
        input_row.addWidget(self._btn_clear)

        layout.addLayout(input_row)

        self._print_system("Kitsat GS v2 — Terminal ready.")
        self._print_system("Connect to a serial port above, then type commands.")

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def _append(self, text: str, color: str | None = None) -> None:
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._output.setTextCursor(cursor)
        if color:
            self._output.appendHtml(f'<span style="color:{color}">{text}</span>')
        else:
            self._output.appendPlainText(text)
        self._output.ensureCursorVisible()

    def _print_system(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._append(f"[{ts}] {text}", color="#888888")

    def _print_tx(self, cmd: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._append(f"[{ts}] &gt;&gt;&gt; {cmd}", color="#00da96")

    def _print_rx(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._append(f"[{ts}] {text}", color="#e0e0e0")

    def _print_error(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._append(f"[{ts}] ERROR: {text}", color="#ff5555")

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
