"""
CommandBuilderWidget — manual packet builder with Commands-tab-matching style.

Lets the user pick a command from the catalog, fill in parameters,
preview the hex packet with FNV checksum, and send it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QLineEdit, QPushButton,
    QTextEdit, QGroupBox, QSplitter, QFrame,
)
from PySide6.QtCore import Qt, Slot

from kitsat_gs.core import command_catalog
from kitsat_gs.core.command_catalog import CommandDefinition

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
    "text_primary":"#e2e8f0",
    "text_muted":  "#64748b",
    "border":      "#1e2d3d",
}

_GROUP_STYLE = (
    f"QGroupBox {{ background:{_C['bg_panel']}; "
    f"border:1px solid {_C['border']}; border-radius:6px; "
    f"margin-top:1.5em; color:{_C['text_muted']}; }} "
    f"QGroupBox::title {{ color:{_C['accent_cyan']}; "
    f"subcontrol-origin:margin; padding:0 6px; }}"
)


def _fnv1a_32(data: bytes) -> int:
    hval = 0x811C9DC5
    for byte in data:
        hval ^= byte
        hval = (hval * 0x01000193) & 0xFFFFFFFF
    return hval


def _build_packet(cmd: CommandDefinition, params_str: str) -> bytes | None:
    try:
        if cmd.param_type == "int":
            payload = str(int(params_str.strip())).encode()
        elif cmd.param_type == "int|int":
            parts = params_str.strip().split()
            payload = b" ".join(str(int(p)).encode() for p in parts)
        elif cmd.param_type == "str":
            payload = params_str.strip().encode()
        else:
            payload = b""
    except (ValueError, AttributeError):
        return None

    header = bytes([cmd.target_id, cmd.command_id, len(payload)]) + payload
    checksum = _fnv1a_32(header).to_bytes(4, "little")
    return header + checksum


class CommandBuilderWidget(QWidget):
    def __init__(self, bridge: "ModemBridge", parent=None) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._build_ui()
        self._populate_commands()

    def _build_ui(self) -> None:
        main = QHBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: command selector + params + preview
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        title = QLabel("Command Builder")
        title.setStyleSheet(
            f"color:{_C['accent_cyan']}; font-size:13pt; font-weight:bold;"
        )
        left_layout.addWidget(title)

        # Command selector group
        selector_box = QGroupBox("Command")
        selector_box.setStyleSheet(_GROUP_STYLE)
        sel_layout = QGridLayout(selector_box)
        sel_layout.setSpacing(6)

        def _muted(text):
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color:{_C['text_muted']}; font-size:9pt;")
            return lbl

        sel_layout.addWidget(_muted("Command:"), 0, 0)
        self._cmd_combo = QComboBox()
        self._cmd_combo.setMinimumWidth(200)
        self._cmd_combo.setStyleSheet(
            f"QComboBox {{ background:{_C['bg_raised']}; color:{_C['text_primary']}; "
            f"border:1px solid {_C['border']}; border-radius:4px; padding:2px 6px; }} "
            f"QComboBox QAbstractItemView {{ background:{_C['bg_panel']}; "
            f"color:{_C['text_primary']}; selection-background-color:{_C['bg_raised']}; }}"
        )
        self._cmd_combo.currentIndexChanged.connect(self._on_command_changed)
        sel_layout.addWidget(self._cmd_combo, 0, 1, 1, 2)

        sel_layout.addWidget(_muted("Target ID:"), 1, 0)
        self._lbl_target = QLabel("—")
        self._lbl_target.setStyleSheet(
            f"color:{_C['text_primary']}; font-family:Consolas; font-size:10pt;"
        )
        sel_layout.addWidget(self._lbl_target, 1, 1)

        sel_layout.addWidget(_muted("Command ID:"), 2, 0)
        self._lbl_cmd_id = QLabel("—")
        self._lbl_cmd_id.setStyleSheet(
            f"color:{_C['text_primary']}; font-family:Consolas; font-size:10pt;"
        )
        sel_layout.addWidget(self._lbl_cmd_id, 2, 1)

        sel_layout.addWidget(_muted("Parameters:"), 3, 0)
        self._lbl_param_type = QLabel("—")
        self._lbl_param_type.setStyleSheet(
            f"color:{_C['text_primary']}; font-family:Consolas; font-size:10pt;"
        )
        sel_layout.addWidget(self._lbl_param_type, 3, 1)

        sel_layout.addWidget(_muted("Description:"), 4, 0)
        self._lbl_explanation = QLabel("—")
        self._lbl_explanation.setStyleSheet(f"color:{_C['text_muted']}; font-size:9pt;")
        self._lbl_explanation.setWordWrap(True)
        sel_layout.addWidget(self._lbl_explanation, 4, 1, 1, 2)
        left_layout.addWidget(selector_box)

        # Parameter input group
        param_box = QGroupBox("Parameters")
        param_box.setStyleSheet(_GROUP_STYLE)
        param_layout = QHBoxLayout(param_box)
        self._param_input = QLineEdit()
        self._param_input.setPlaceholderText("Enter parameter value(s)")
        self._param_input.setStyleSheet(
            f"background:{_C['bg_raised']}; color:{_C['text_primary']}; "
            f"border:1px solid {_C['border']}; border-radius:4px; padding:4px 8px;"
        )
        self._param_input.textChanged.connect(self._update_preview)
        param_layout.addWidget(self._param_input)
        left_layout.addWidget(param_box)

        left_layout.addStretch()

        self._btn_send = QPushButton("Send Command")
        self._btn_send.setFixedHeight(36)
        self._btn_send.setStyleSheet(
            f"QPushButton {{ background:{_C['accent_cyan']}; color:{_C['bg_base']}; "
            f"border:none; border-radius:6px; font-weight:bold; }}"
            f"QPushButton:hover {{ background:#33deff; }}"
        )
        self._btn_send.clicked.connect(self._on_send)
        left_layout.addWidget(self._btn_send)

        # ── Right: packet preview log
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        log_header = QHBoxLayout()
        log_title = QLabel("Packet Preview")
        log_title.setStyleSheet(
            f"color:{_C['accent_cyan']}; font-size:10pt; font-weight:bold;"
        )
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(60)
        clear_btn.clicked.connect(lambda: self._preview.clear())
        log_header.addWidget(log_title)
        log_header.addStretch()
        log_header.addWidget(clear_btn)
        right_layout.addLayout(log_header)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setStyleSheet(
            f"background:{_C['bg_panel']}; color:{_C['text_primary']}; "
            f"font-family:Consolas; font-size:10pt; "
            f"border:1px solid {_C['border']}; border-radius:6px;"
        )
        right_layout.addWidget(self._preview)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([420, 380])
        main.addWidget(splitter)

    def _populate_commands(self) -> None:
        self._cmd_combo.clear()
        for name in command_catalog.all_names():
            self._cmd_combo.addItem(name)

    @Slot(int)
    def _on_command_changed(self, _index: int) -> None:
        name = self._cmd_combo.currentText()
        cmd = command_catalog.get(name)
        if cmd:
            self._lbl_target.setText(str(cmd.target_id))
            self._lbl_cmd_id.setText(str(cmd.command_id))
            self._lbl_param_type.setText(cmd.param_type or "none")
            self._lbl_explanation.setText(
                cmd.explanation + (f" — {cmd.param_explanation}" if cmd.param_explanation else "")
            )
            self._param_input.setEnabled(bool(cmd.param_type))
            self._param_input.clear()
        self._update_preview()

    @Slot()
    def _update_preview(self) -> None:
        name = self._cmd_combo.currentText()
        cmd = command_catalog.get(name)
        if not cmd:
            return

        params = self._param_input.text()
        packet = _build_packet(cmd, params)

        if packet is None:
            self._preview.append(
                f"<span style='color:{_C['warning']}'>(invalid parameters)</span>"
            )
            return

        hex_str = " ".join(f"{b:02X}" for b in packet)
        fnv = int.from_bytes(packet[-4:], "little")
        col_muted = _C['text_muted']
        col_cyan = _C['accent_cyan']
        col_primary = _C['text_primary']
        col_success = _C['success']
        param_part = (' ' + params.strip()) if params.strip() else ''
        self._preview.append(
            f"<span style='color:{col_muted}'>"
            f"<b style='color:{col_cyan}'>{name}</b>"
            f"{param_part}<br>"
            f"Bytes ({len(packet)}): </span>"
            f"<span style='color:{col_primary}'>{hex_str}</span><br>"
            f"<span style='color:{col_muted}'>FNV-1a: </span>"
            f"<span style='color:{col_success}'>0x{fnv:08X}</span>"
        )
        sb = self._preview.verticalScrollBar()
        sb.setValue(sb.maximum())

    @Slot()
    def _on_send(self) -> None:
        name = self._cmd_combo.currentText()
        params = self._param_input.text().strip()
        cmd_str = f"{name} {params}".strip() if params else name
        self._bridge.send_command(cmd_str)
        self._update_preview()
