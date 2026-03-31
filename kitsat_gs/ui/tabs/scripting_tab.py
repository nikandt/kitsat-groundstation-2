"""DSL Scripting tab — syntax-highlighted editor + run/stop + output pane."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QTextEdit, QLabel,
)
from PySide6.QtCore import Qt, Slot

from kitsat_gs.ui.widgets.script_editor import ScriptEditor
from kitsat_gs.scripting.interpreter import ScriptWorker
from kitsat_gs.scripting.builtins import EXAMPLE_SCRIPT, help_text

_C = {
    "bg_panel":    "#111827",
    "accent_cyan": "#00d4ff",
    "accent_blue": "#3b82f6",
    "success":     "#10b981",
    "warning":     "#f59e0b",
    "error":       "#ef4444",
    "text_primary":"#e2e8f0",
    "text_muted":  "#64748b",
    "border":      "#1e2d3d",
    "bg_raised":   "#1e2d3d",
    "bg_base":     "#0a0e1a",
}


class ScriptingTab(QWidget):
    """DSL script editor with run/stop control and colour-coded output."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: ScriptWorker = None
        self._setup_ui()

    def _setup_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()

        self._run_btn = QPushButton("▶  Run")
        self._run_btn.setFixedHeight(32)
        self._run_btn.setStyleSheet(
            f"QPushButton {{ background:{_C['accent_cyan']}; color:{_C['bg_base']}; "
            f"border:none; border-radius:6px; font-weight:bold; padding:0 14px; }}"
            f"QPushButton:hover {{ background:#33deff; }}"
        )
        self._run_btn.clicked.connect(self._run_script)
        toolbar.addWidget(self._run_btn)

        self._stop_btn = QPushButton("■  Stop")
        self._stop_btn.setFixedHeight(32)
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet(
            f"QPushButton {{ background:{_C['error']}; color:white; "
            f"border:none; border-radius:6px; font-weight:bold; padding:0 14px; }}"
            f"QPushButton:disabled {{ background:{_C['bg_raised']}; "
            f"color:{_C['text_muted']}; }}"
            f"QPushButton:hover:enabled {{ background:#f87171; }}"
        )
        self._stop_btn.clicked.connect(self._stop_script)
        toolbar.addWidget(self._stop_btn)

        toolbar.addSpacing(12)

        for label, slot in [("Load Example", self._load_example),
                             ("Help", self._show_help),
                             ("Clear Output", self._clear_output)]:
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.clicked.connect(slot)
            toolbar.addWidget(btn)

        toolbar.addStretch()

        self._status_label = QLabel("Idle")
        self._status_label.setStyleSheet(
            f"color:{_C['text_muted']}; font-size:9pt;"
        )
        toolbar.addWidget(self._status_label)
        main.addLayout(toolbar)

        # Editor / output splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._editor = ScriptEditor()
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

        main.addWidget(splitter, stretch=1)

    def _run_script(self):
        source = self._editor.toPlainText().strip()
        if not source:
            return

        self._output.clear()
        self._output.append(
            f"<span style='color:{_C['text_muted']}'>--- Script started ---</span>"
        )
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status_label.setText("Running…")
        self._status_label.setStyleSheet(
            f"color:{_C['warning']}; font-size:9pt;"
        )

        self._worker = ScriptWorker(source)
        self._worker.output.connect(self._on_output)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _stop_script(self):
        if self._worker and self._worker.isRunning():
            self._worker.stop()

    @Slot(str)
    def _on_output(self, line: str):
        if line.startswith("  LOG:"):
            color = _C["success"]
        elif "[ERROR]" in line:
            color = _C["error"]
        elif "[STOPPED]" in line:
            color = _C["warning"]
        elif "[DONE]" in line:
            color = _C["accent_cyan"]
        elif line.strip().startswith("SEND"):
            color = _C["accent_blue"]
        else:
            color = _C["text_primary"]
        self._output.append(f"<span style='color:{color}'>{line}</span>")
        sb = self._output.verticalScrollBar()
        sb.setValue(sb.maximum())

    @Slot(bool, str)
    def _on_finished(self, success: bool, error_msg: str):
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        if success:
            self._status_label.setText("Completed")
            self._status_label.setStyleSheet(f"color:{_C['success']}; font-size:9pt;")
        else:
            self._status_label.setText(f"Failed: {error_msg[:40]}")
            self._status_label.setStyleSheet(f"color:{_C['error']}; font-size:9pt;")
        self._worker = None

    def _load_example(self):
        self._editor.setPlainText(EXAMPLE_SCRIPT)

    def _show_help(self):
        self._output.clear()
        self._output.setPlainText(help_text())

    def _clear_output(self):
        self._output.clear()
