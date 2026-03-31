"""Enhanced command tab — searchable list of 20 commands + param form + response log."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QLineEdit, QTextEdit,
    QListWidget, QListWidgetItem, QFrame,
    QFormLayout, QDoubleSpinBox, QSpinBox,
    QComboBox, QGroupBox,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor

from kitsat_gs.core.command_registry import CommandRegistry
from kitsat_gs.core.models import CommandDef, CommandParam, CommandResult
from kitsat_gs.core.events import get_event_bus

_C = {
    "bg_base":     "#0a0e1a",
    "bg_panel":    "#111827",
    "bg_raised":   "#1e2d3d",
    "accent_cyan": "#00d4ff",
    "accent_blue": "#3b82f6",
    "success":     "#10b981",
    "warning":     "#f59e0b",
    "error":       "#ef4444",
    "text_primary":"#e2e8f0",
    "text_muted":  "#64748b",
    "border":      "#1e2d3d",
}


class CommandTab(QWidget):
    """Searchable command builder with parameter forms and response log.

    Requires a provider reference to actually dispatch commands; pass None
    to operate in EventBus-only mode (e.g. with MockProvider).
    """

    def __init__(self, provider=None, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._registry = CommandRegistry()
        self._bus = get_event_bus()
        self._param_widgets: dict = {}
        self._current_cmd: CommandDef = None

        self._setup_ui()
        self._bus.command_response.connect(self._on_response)
        self._populate_list()

    def set_provider(self, provider) -> None:
        self._provider = provider

    def _setup_ui(self):
        main = QHBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: command list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search commands…")
        self._search_box.textChanged.connect(self._filter_list)
        left_layout.addWidget(self._search_box)

        self._cmd_list = QListWidget()
        self._cmd_list.setAlternatingRowColors(True)
        self._cmd_list.currentItemChanged.connect(self._on_cmd_selected)
        left_layout.addWidget(self._cmd_list)
        left.setFixedWidth(220)

        # ── Center: parameter form
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)

        self._cmd_title = QLabel("Select a command")
        self._cmd_title.setStyleSheet(
            f"color:{_C['accent_cyan']}; font-size:13pt; font-weight:bold;"
        )
        center_layout.addWidget(self._cmd_title)

        self._cmd_desc = QLabel("")
        self._cmd_desc.setStyleSheet(f"color:{_C['text_muted']}; font-size:9pt;")
        self._cmd_desc.setWordWrap(True)
        center_layout.addWidget(self._cmd_desc)

        self._danger_label = QLabel("⚠ This command is marked DANGEROUS")
        self._danger_label.setStyleSheet(
            f"color:{_C['error']}; font-weight:bold; font-size:9pt;"
        )
        self._danger_label.hide()
        center_layout.addWidget(self._danger_label)

        self._param_group = QGroupBox("Parameters")
        self._param_group.setStyleSheet(
            f"QGroupBox {{ background:{_C['bg_panel']}; "
            f"border:1px solid {_C['border']}; border-radius:6px; "
            f"margin-top:1.5em; color:{_C['text_muted']}; }} "
            f"QGroupBox::title {{ color:{_C['accent_cyan']}; "
            f"subcontrol-origin:margin; padding:0 6px; }}"
        )
        self._param_form = QFormLayout(self._param_group)
        self._param_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        center_layout.addWidget(self._param_group)
        center_layout.addStretch()

        self._send_btn = QPushButton("Send Command")
        self._send_btn.setEnabled(False)
        self._send_btn.clicked.connect(self._send_command)
        self._send_btn.setFixedHeight(36)
        self._send_btn.setStyleSheet(
            f"QPushButton {{ background:{_C['accent_cyan']}; color:{_C['bg_base']}; "
            f"border:none; border-radius:6px; font-weight:bold; }}"
            f"QPushButton:disabled {{ background:{_C['bg_raised']}; "
            f"color:{_C['text_muted']}; }}"
            f"QPushButton:hover {{ background:#33deff; }}"
        )
        center_layout.addWidget(self._send_btn)

        # ── Right: response log
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        log_header = QHBoxLayout()
        log_title = QLabel("Response Log")
        log_title.setStyleSheet(
            f"color:{_C['accent_cyan']}; font-size:10pt; font-weight:bold;"
        )
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(60)
        clear_btn.clicked.connect(lambda: self._log.clear())
        log_header.addWidget(log_title)
        log_header.addStretch()
        log_header.addWidget(clear_btn)
        right_layout.addLayout(log_header)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(
            f"background:{_C['bg_panel']}; color:{_C['text_primary']}; "
            f"font-family:Consolas; font-size:10pt; "
            f"border:1px solid {_C['border']}; border-radius:6px;"
        )
        right_layout.addWidget(self._log)

        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(right)
        splitter.setSizes([220, 300, 500])
        main.addWidget(splitter)

    def _populate_list(self):
        self._cmd_list.clear()
        for name, cmd in sorted(self._registry.all().items()):
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setForeground(QColor(_C["error"]) if cmd.dangerous
                               else QColor(_C["text_primary"]))
            self._cmd_list.addItem(item)

    def _filter_list(self, text: str):
        for i in range(self._cmd_list.count()):
            item = self._cmd_list.item(i)
            item.setHidden(text.upper() not in item.text())

    def _on_cmd_selected(self, item: QListWidgetItem, _prev):
        if item is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
        cmd = self._registry.get(name)
        if not cmd:
            return
        self._current_cmd = cmd
        self._cmd_title.setText(cmd.name)
        self._cmd_desc.setText(f"[{cmd.category.upper()}]  {cmd.description}")
        self._danger_label.setVisible(cmd.dangerous)
        self._send_btn.setEnabled(True)
        if cmd.dangerous:
            self._send_btn.setStyleSheet(
                f"QPushButton {{ background:{_C['error']}; color:white; "
                f"border:none; border-radius:6px; font-weight:bold; }}"
                f"QPushButton:hover {{ background:#f87171; }}"
            )
        else:
            self._send_btn.setStyleSheet(
                f"QPushButton {{ background:{_C['accent_cyan']}; color:{_C['bg_base']}; "
                f"border:none; border-radius:6px; font-weight:bold; }}"
                f"QPushButton:hover {{ background:#33deff; }}"
            )
        self._build_param_form(cmd)

    def _build_param_form(self, cmd: CommandDef):
        while self._param_form.rowCount() > 0:
            self._param_form.removeRow(0)
        self._param_widgets.clear()

        if not cmd.params:
            self._param_group.setVisible(False)
            return

        self._param_group.setVisible(True)
        for param in cmd.params:
            widget = self._make_param_widget(param)
            lbl = QLabel(f"{param.name}:")
            lbl.setStyleSheet(f"color:{_C['text_muted']}; font-size:9pt;")
            if param.description:
                widget.setToolTip(param.description)
            self._param_form.addRow(lbl, widget)
            self._param_widgets[param.name] = (param, widget)

    def _make_param_widget(self, param: CommandParam) -> QWidget:
        if param.type == "enum" and param.choices:
            cb = QComboBox()
            cb.addItems(param.choices)
            if param.default in param.choices:
                cb.setCurrentText(str(param.default))
            return cb
        elif param.type == "int":
            sb = QSpinBox()
            sb.setRange(
                int(param.min_val) if param.min_val is not None else -99999,
                int(param.max_val) if param.max_val is not None else 99999,
            )
            sb.setValue(int(param.default) if param.default is not None else 0)
            return sb
        elif param.type == "float":
            sb = QDoubleSpinBox()
            sb.setRange(
                param.min_val if param.min_val is not None else -9999.0,
                param.max_val if param.max_val is not None else 9999.0,
            )
            sb.setValue(float(param.default) if param.default is not None else 0.0)
            sb.setDecimals(2)
            return sb
        else:
            le = QLineEdit()
            if param.default is not None:
                le.setText(str(param.default))
            return le

    def _send_command(self):
        if not self._current_cmd:
            return
        params = {}
        for name, (param, widget) in self._param_widgets.items():
            if isinstance(widget, QComboBox):
                params[name] = widget.currentText()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                params[name] = widget.value()
            elif isinstance(widget, QLineEdit):
                params[name] = widget.text()

        ts = datetime.utcnow().strftime("%H:%M:%S")
        self._append_log(
            f"<span style='color:{_C['text_muted']}'>[{ts}]</span> "
            f"<span style='color:{_C['accent_cyan']}'>→ {self._current_cmd.name}</span>"
            + (f" {params}" if params else "")
        )
        self._bus.command_sent.emit(self._current_cmd.name, params)
        if self._provider is not None:
            self._provider.send_command(self._current_cmd.name, params)

    @Slot(object)
    def _on_response(self, result: CommandResult):
        ts = result.timestamp.strftime("%H:%M:%S")
        status_color = _C["success"] if result.success else _C["error"]
        status = "OK" if result.success else "ERR"
        self._append_log(
            f"<span style='color:{_C['text_muted']}'>[{ts}]</span> "
            f"<span style='color:{status_color}'>[{status}]</span> "
            f"<span style='color:{_C['text_primary']}'>{result.command}</span>: "
            f"<span style='color:{_C['text_primary']}'>{result.response or result.error}</span>"
            f"<span style='color:{_C['text_muted']}'> ({result.latency_ms:.0f} ms)</span>"
        )

    def _append_log(self, html: str):
        self._log.append(html)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())
