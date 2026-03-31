"""
ScriptWidget — flight script editor and runner, DSL-styled.

Left: plain-text editor for Kitsat scripts.
Right: colour-coded execution log.

The runner executes scripts in a QThread, honouring wait/wait_ms delays
and sending satellite commands via ModemBridge.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QPushButton, QSplitter, QTextEdit, QLabel,
)
from PySide6.QtCore import Qt, Slot, QThread, Signal, QObject
from PySide6.QtGui import QFont
from loguru import logger

from kitsat_gs.core.script_engine import ScriptEngine
from kitsat_gs.core import command_catalog

if TYPE_CHECKING:
    from kitsat_gs.core.modem_bridge import ModemBridge


_C = {
    "bg_base":     "#0a0e1a",
    "bg_panel":    "#111827",
    "bg_raised":   "#1e2d3d",
    "accent_cyan": "#00d4ff",
    "accent_blue": "#3b82f6",
    "success":     "#10b981",
    "warning":     "#f59e0b",
    "error":       "#ef4444",
    "text_primary": "#e2e8f0",
    "text_muted":  "#64748b",
    "border":      "#1e2d3d",
}

_EXAMPLE_SCRIPT = """\
var count = 0
var limit = 3

for count < limit {
    ping
    wait 1
}

beep 2
wait_ms 500
beep 1
"""

_HELP_TEXT = """\
Kitsat Script Reference
=======================

Variables
  var name = value        Declare a variable
  name = value            Assign to an existing variable

Control flow
  for var < limit { }     Loop while var < limit (var auto-incremented)
  loop { }                Infinite loop (use with care)
  if var == val { }       Conditional block
  if var == val { } else { }

Timing
  wait N                  Pause N seconds
  wait_ms N               Pause N milliseconds

Satellite commands
  Any command from the catalog, e.g.:
    ping
    beep 3
    imu_get_all
    gps_get_all

Functions
  Function name(p1, p2) { }   Define a reusable block
  name(arg1, arg2)             Call it

UI commands
  ImageFrame / MapFrame        Request specific UI frames

Example
-------
var count = 0
var limit = 3

for count < limit {
    ping
    wait 1
}

beep 2
"""


# ---------------------------------------------------------------------------
# Runner thread
# ---------------------------------------------------------------------------

class _ScriptRunner(QObject):
    log = Signal(str, str)   # (message, level)  level: info|tx|error|system
    finished = Signal()
    send_command = Signal(str)

    def __init__(self, engine: ScriptEngine, parent=None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._stop = False

    @Slot()
    def run(self) -> None:
        try:
            for cmd in self._engine:
                if self._stop:
                    self.log.emit("Script stopped by user.", "system")
                    break

                if cmd.kind == "satellite":
                    self.log.emit(f"TX › {cmd.line}", "tx")

                elif cmd.kind in ("wait", "wait_ms"):
                    self.log.emit(f"wait {cmd.value_s:.3f}s", "info")
                    deadline = time.monotonic() + cmd.value_s
                    while time.monotonic() < deadline:
                        if self._stop:
                            break
                        time.sleep(min(0.05, deadline - time.monotonic()))

                elif cmd.kind == "ui":
                    self.log.emit(f"UI › {cmd.line}", "info")

                elif cmd.kind == "assignment":
                    self.log.emit(f"  {cmd.line}", "info")

            else:
                self.log.emit("Script finished.", "system")
        except Exception as exc:
            self.log.emit(f"Script error: {exc}", "error")
            logger.error(f"ScriptRunner: {exc}")
        finally:
            self.finished.emit()

    def stop(self) -> None:
        self._stop = True


class _RunnerThread(QThread):
    def __init__(self, runner: _ScriptRunner, parent=None):
        super().__init__(parent)
        self._runner = runner
        self._runner.moveToThread(self)
        self.started.connect(self._runner.run)


# ---------------------------------------------------------------------------
# ScriptWidget
# ---------------------------------------------------------------------------

class ScriptWidget(QWidget):
    send_command = Signal(str)

    def __init__(self, bridge: "ModemBridge", parent=None) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._thread: _RunnerThread | None = None
        self._runner: _ScriptRunner | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()

        self._btn_run = QPushButton("▶  Run")
        self._btn_run.setFixedHeight(32)
        self._btn_run.setStyleSheet(
            f"QPushButton {{ background:{_C['accent_cyan']}; color:{_C['bg_base']}; "
            f"border:none; border-radius:6px; font-weight:bold; padding:0 14px; }}"
            f"QPushButton:hover {{ background:#33deff; }}"
        )
        self._btn_run.clicked.connect(self._on_run)
        toolbar.addWidget(self._btn_run)

        self._btn_stop = QPushButton("■  Stop")
        self._btn_stop.setFixedHeight(32)
        self._btn_stop.setEnabled(False)
        self._btn_stop.setStyleSheet(
            f"QPushButton {{ background:{_C['error']}; color:white; "
            f"border:none; border-radius:6px; font-weight:bold; padding:0 14px; }}"
            f"QPushButton:disabled {{ background:{_C['bg_raised']}; "
            f"color:{_C['text_muted']}; }}"
            f"QPushButton:hover:enabled {{ background:#f87171; }}"
        )
        self._btn_stop.clicked.connect(self._on_stop)
        toolbar.addWidget(self._btn_stop)

        toolbar.addSpacing(12)

        for label, slot in [
            ("Load Example", self._load_example),
            ("Help",         self._show_help),
            ("Clear Output", self._clear_output),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.setStyleSheet(
                f"QPushButton {{ background:{_C['bg_raised']}; color:{_C['text_primary']}; "
                f"border:1px solid {_C['border']}; border-radius:6px; padding:0 10px; }}"
                f"QPushButton:hover {{ background:#2a3f55; }}"
            )
            btn.clicked.connect(slot)
            toolbar.addWidget(btn)

        toolbar.addStretch()

        self._status_label = QLabel("Idle")
        self._status_label.setStyleSheet(f"color:{_C['text_muted']}; font-size:9pt;")
        toolbar.addWidget(self._status_label)
        layout.addLayout(toolbar)

        # Editor / output splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._editor = QPlainTextEdit(_EXAMPLE_SCRIPT)
        self._editor.setStyleSheet(
            f"background:{_C['bg_panel']}; color:{_C['text_primary']}; "
            f"font-family:Consolas; font-size:10pt; "
            f"border:1px solid {_C['border']}; border-radius:6px;"
        )
        self._editor.setFont(QFont("Consolas", 10))
        self._editor.setMinimumWidth(300)
        splitter.addWidget(self._editor)

        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setStyleSheet(
            f"background:{_C['bg_panel']}; color:{_C['text_primary']}; "
            f"font-family:Consolas; font-size:10pt; "
            f"border:1px solid {_C['border']}; border-radius:6px;"
        )
        splitter.addWidget(self._output)
        splitter.setSizes([500, 400])

        layout.addWidget(splitter, stretch=1)

    # ------------------------------------------------------------------
    # Toolbar actions
    # ------------------------------------------------------------------

    def _load_example(self) -> None:
        self._editor.setPlainText(_EXAMPLE_SCRIPT)

    def _show_help(self) -> None:
        self._output.clear()
        self._output.setPlainText(_HELP_TEXT)

    def _clear_output(self) -> None:
        self._output.clear()

    # ------------------------------------------------------------------
    # Run / Stop
    # ------------------------------------------------------------------

    @Slot()
    def _on_run(self) -> None:
        code = self._editor.toPlainText()
        if not code.strip():
            return

        cmd_names = command_catalog.all_names()
        try:
            engine = ScriptEngine(code, cmd_names)
        except Exception as exc:
            self._append_log(f"Parse error: {exc}", "error")
            return

        self._output.clear()
        col = _C['text_muted']
        self._output.append(f"<span style='color:{col}'>--- Script started ---</span>")

        self._runner = _ScriptRunner(engine)
        self._runner.log.connect(self._append_log)
        self._runner.finished.connect(self._on_finished)
        self._runner.log.connect(self._maybe_send)

        self._thread = _RunnerThread(self._runner)
        self._thread.start()

        self._btn_run.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._status_label.setText("Running…")
        self._status_label.setStyleSheet(f"color:{_C['warning']}; font-size:9pt;")

    @Slot()
    def _on_stop(self) -> None:
        if self._runner:
            self._runner.stop()

    @Slot()
    def _on_finished(self) -> None:
        self._btn_run.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._status_label.setText("Completed")
        self._status_label.setStyleSheet(f"color:{_C['success']}; font-size:9pt;")
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
        self._runner = None

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    @Slot(str, str)
    def _append_log(self, message: str, level: str) -> None:
        colors = {
            "tx":     _C["success"],
            "error":  _C["error"],
            "system": _C["text_muted"],
            "info":   _C["text_primary"],
        }
        color = colors.get(level, _C["text_primary"])
        self._output.append(f"<span style='color:{color}'>{message}</span>")
        sb = self._output.verticalScrollBar()
        sb.setValue(sb.maximum())

    @Slot(str, str)
    def _maybe_send(self, message: str, level: str) -> None:
        if level == "tx" and message.startswith("TX › "):
            self._bridge.send_command(message[5:])
