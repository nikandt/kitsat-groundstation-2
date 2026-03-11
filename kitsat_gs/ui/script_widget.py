"""
ScriptWidget — flight script editor and runner.

Left: plain-text editor for Kitsat scripts.
Right: execution log showing each command as it runs.

The runner executes scripts in a QThread, honouring wait/wait_ms delays
and sending satellite commands via ModemBridge.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QSplitter, QGroupBox,
)
from PySide6.QtCore import Qt, Slot, QThread, Signal, QObject
from PySide6.QtGui import QFont
from loguru import logger

from kitsat_gs.core.script_engine import ScriptEngine, ScriptCommand
from kitsat_gs.core import command_catalog

if TYPE_CHECKING:
    from kitsat_gs.core.modem_bridge import ModemBridge


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


# ---------------------------------------------------------------------------
# Runner thread
# ---------------------------------------------------------------------------

class _ScriptRunner(QObject):
    """
    Runs in a QThread. Iterates ScriptEngine and emits signals for each step.
    Supports stop().
    """

    log = Signal(str, str)      # (message, level)  level: "info"|"tx"|"error"|"system"
    finished = Signal()

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
                    # Actual send happens via bridge signal — see ScriptWidget

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

    # Signal emitted for each satellite command so the widget can forward it
    send_command = Signal(str)


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
    # Forward satellite commands to the modem bridge
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

        header = QLabel("Scripts")
        header.setObjectName("panelHeader")
        layout.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)

        # Left: editor
        editor_box = QGroupBox("Script editor")
        editor_layout = QVBoxLayout(editor_box)
        self._editor = QPlainTextEdit(_EXAMPLE_SCRIPT)
        self._editor.setObjectName("terminalOutput")
        mono = QFont("Courier New", 11)
        self._editor.setFont(mono)
        editor_layout.addWidget(self._editor)

        btn_row = QHBoxLayout()
        self._btn_run = QPushButton("▶  Run")
        self._btn_run.clicked.connect(self._on_run)
        btn_row.addWidget(self._btn_run)

        self._btn_stop = QPushButton("■  Stop")
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._on_stop)
        btn_row.addWidget(self._btn_stop)

        self._btn_clear_editor = QPushButton("Clear")
        self._btn_clear_editor.setFixedWidth(60)
        self._btn_clear_editor.clicked.connect(self._editor.clear)
        btn_row.addWidget(self._btn_clear_editor)
        editor_layout.addLayout(btn_row)

        splitter.addWidget(editor_box)

        # Right: execution log
        log_box = QGroupBox("Execution log")
        log_layout = QVBoxLayout(log_box)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setObjectName("terminalOutput")
        self._log.setFont(mono)
        self._log.setMaximumBlockCount(1000)
        log_layout.addWidget(self._log)

        self._btn_clear_log = QPushButton("Clear log")
        self._btn_clear_log.setFixedWidth(80)
        self._btn_clear_log.clicked.connect(self._log.clear)
        log_layout.addWidget(self._btn_clear_log, alignment=Qt.AlignRight)

        splitter.addWidget(log_box)
        splitter.setSizes([500, 400])
        layout.addWidget(splitter, stretch=1)

    # ------------------------------------------------------------------
    # Slots
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

        self._runner = _ScriptRunner(engine)
        self._runner.log.connect(self._append_log)
        self._runner.finished.connect(self._on_finished)

        # Forward satellite commands to the bridge
        self._runner.log.connect(self._maybe_send)

        self._thread = _RunnerThread(self._runner)
        self._thread.start()

        self._btn_run.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._append_log("Script started.", "system")

    @Slot()
    def _on_stop(self) -> None:
        if self._runner:
            self._runner.stop()

    @Slot()
    def _on_finished(self) -> None:
        self._btn_run.setEnabled(True)
        self._btn_stop.setEnabled(False)
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)

    @Slot(str, str)
    def _append_log(self, message: str, level: str) -> None:
        colors = {
            "tx":     "#00da96",
            "error":  "#ff5555",
            "system": "#888888",
            "info":   "#e0e0e0",
        }
        color = colors.get(level, "#e0e0e0")
        self._log.appendHtml(f'<span style="color:{color}">{message}</span>')
        self._log.ensureCursorVisible()

    @Slot(str, str)
    def _maybe_send(self, message: str, level: str) -> None:
        """If the log message is a TX command, forward it to the bridge."""
        if level == "tx" and message.startswith("TX › "):
            cmd = message[5:]
            self._bridge.send_command(cmd)
