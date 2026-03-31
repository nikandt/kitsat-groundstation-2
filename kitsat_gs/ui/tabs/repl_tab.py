"""REPL tab — interactive single-line DSL interpreter with history."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QTextEdit, QPushButton, QLabel,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QKeyEvent

from kitsat_gs.scripting.lexer import LexerError
from kitsat_gs.scripting.parser import ParseError
from kitsat_gs.scripting.interpreter import ScriptWorker
from kitsat_gs.scripting.builtins import help_text
from kitsat_gs.core.events import get_event_bus

_C = {
    "bg_panel":    "#111827",
    "bg_raised":   "#1e2d3d",
    "bg_base":     "#0a0e1a",
    "accent_cyan": "#00d4ff",
    "success":     "#10b981",
    "error":       "#ef4444",
    "text_primary":"#e2e8f0",
    "text_muted":  "#64748b",
    "border":      "#1e2d3d",
}


class _HistoryLineEdit(QLineEdit):
    """QLineEdit with ↑/↓ command history."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: list = []
        self._hist_idx = -1

    def add_to_history(self, cmd: str):
        if cmd.strip():
            self._history.append(cmd)
        self._hist_idx = -1

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Up:
            if self._history:
                self._hist_idx = min(self._hist_idx + 1, len(self._history) - 1)
                self.setText(self._history[-(self._hist_idx + 1)])
        elif event.key() == Qt.Key.Key_Down:
            if self._hist_idx > 0:
                self._hist_idx -= 1
                self.setText(self._history[-(self._hist_idx + 1)])
            elif self._hist_idx == 0:
                self._hist_idx = -1
                self.clear()
        else:
            super().keyPressEvent(event)


class REPLTab(QWidget):
    """Interactive DSL REPL — type one command at a time, see results inline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bus = get_event_bus()
        self._active_worker: ScriptWorker = None
        self._setup_ui()
        self._bus.command_response.connect(self._on_response)
        self._print_welcome()

    def _setup_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(6)

        # Header
        header = QHBoxLayout()
        title = QLabel("Kitsat REPL")
        title.setStyleSheet(
            f"color:{_C['accent_cyan']}; font-size:12pt; font-weight:bold;"
        )
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(70)
        clear_btn.clicked.connect(self._clear)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(clear_btn)
        main.addLayout(header)

        # Output area
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setStyleSheet(
            f"background:{_C['bg_panel']}; color:{_C['text_primary']}; "
            f"font-family:Consolas; font-size:10pt; "
            f"border:1px solid {_C['border']}; border-radius:6px;"
        )
        main.addWidget(self._output, stretch=1)

        # Input row
        input_row = QHBoxLayout()

        prompt_lbl = QLabel("kitsat>")
        prompt_lbl.setStyleSheet(
            f"color:{_C['accent_cyan']}; font-family:Consolas; "
            f"font-size:10pt; font-weight:bold;"
        )
        input_row.addWidget(prompt_lbl)

        self._input = _HistoryLineEdit()
        self._input.setPlaceholderText(
            "Type a DSL command (e.g. SEND PING) and press Enter…"
        )
        self._input.setStyleSheet(
            f"background:{_C['bg_raised']}; color:{_C['text_primary']}; "
            f"font-family:Consolas; font-size:10pt; "
            f"border:1px solid {_C['border']}; border-radius:6px; padding:4px 8px;"
        )
        self._input.returnPressed.connect(self._execute_line)
        input_row.addWidget(self._input)

        run_btn = QPushButton("Run")
        run_btn.setFixedWidth(60)
        run_btn.setStyleSheet(
            f"QPushButton {{ background:{_C['accent_cyan']}; color:{_C['bg_base']}; "
            f"border:none; border-radius:6px; font-weight:bold; }}"
            f"QPushButton:hover {{ background:#33deff; }}"
        )
        run_btn.clicked.connect(self._execute_line)
        input_row.addWidget(run_btn)

        main.addLayout(input_row)

    def _print_welcome(self):
        self._print_html(
            f"<span style='color:{_C['accent_cyan']}'>"
            f"Kitsat DSL REPL — type commands one at a time.<br>"
            f"Try: SEND PING | WAIT 1.0 | GET TELEMETRY battery_percent<br>"
            f"Type HELP for command reference. Type CLEAR to reset."
            f"</span>"
        )

    def _execute_line(self):
        line = self._input.text().strip()
        if not line:
            return

        self._input.add_to_history(line)
        self._print_html(
            f"<span style='color:{_C['text_muted']}'>kitsat&gt;</span> "
            f"<span style='color:{_C['text_primary']}'>{line}</span>"
        )
        self._input.clear()

        if line.upper() == "HELP":
            self._print_plain(help_text())
            return

        if line.upper() == "CLEAR":
            self._clear()
            return

        self._active_worker = ScriptWorker(line)
        self._active_worker.output.connect(self._on_worker_output)
        self._active_worker.finished.connect(self._on_worker_done)
        self._active_worker.start()

    @Slot(str)
    def _on_worker_output(self, line: str):
        if line.startswith("  LOG:"):
            color = _C["success"]
        elif "[ERROR]" in line:
            color = _C["error"]
        else:
            color = _C["text_muted"]
        self._print_html(f"<span style='color:{color}'>{line}</span>")

    @Slot(bool, str)
    def _on_worker_done(self, success: bool, err: str):
        self._active_worker = None

    @Slot(object)
    def _on_response(self, result):
        status_color = _C["success"] if result.success else _C["error"]
        status = "OK" if result.success else "ERR"
        self._print_html(
            f"<span style='color:{status_color}'>[{status}]</span> "
            f"<span style='color:{_C['text_primary']}'>"
            f"{result.command}: {result.response or result.error}</span>"
            f"<span style='color:{_C['text_muted']}'> ({result.latency_ms:.0f}ms)</span>"
        )

    def _print_html(self, html: str):
        self._output.append(html)
        sb = self._output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _print_plain(self, text: str):
        self._output.append(
            f"<span style='color:{_C['text_muted']}'>{text}</span>"
        )
        sb = self._output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear(self):
        self._output.clear()
        self._print_welcome()
