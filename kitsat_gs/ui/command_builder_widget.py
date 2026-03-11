"""
CommandBuilderWidget — manual packet builder.

Lets the user pick a command from the catalog, fill in parameters,
preview the hex packet with FNV checksum, and send it.
Port of command_window.xaml / command_window.xaml.cs from v1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QLineEdit, QPushButton,
    QPlainTextEdit, QGroupBox,
)
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont

from kitsat_gs.core import command_catalog
from kitsat_gs.core.command_catalog import CommandDefinition

if TYPE_CHECKING:
    from kitsat_gs.core.modem_bridge import ModemBridge


def _fnv1a_32(data: bytes) -> int:
    hval = 0x811C9DC5
    for byte in data:
        hval ^= byte
        hval = (hval * 0x01000193) & 0xFFFFFFFF
    return hval


def _build_packet(cmd: CommandDefinition, params_str: str) -> bytes | None:
    """Replicate kitsat cmd_parser logic to preview the outgoing packet."""
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QLabel("Command Builder")
        header.setObjectName("panelHeader")
        layout.addWidget(header)

        # Command selector
        selector_box = QGroupBox("Command")
        sel_layout = QGridLayout(selector_box)
        sel_layout.setSpacing(6)

        sel_layout.addWidget(QLabel("Command:"), 0, 0)
        self._cmd_combo = QComboBox()
        self._cmd_combo.setMinimumWidth(220)
        self._cmd_combo.currentIndexChanged.connect(self._on_command_changed)
        sel_layout.addWidget(self._cmd_combo, 0, 1, 1, 2)

        sel_layout.addWidget(QLabel("Target ID:"), 1, 0)
        self._lbl_target = QLabel("—")
        sel_layout.addWidget(self._lbl_target, 1, 1)

        sel_layout.addWidget(QLabel("Command ID:"), 2, 0)
        self._lbl_cmd_id = QLabel("—")
        sel_layout.addWidget(self._lbl_cmd_id, 2, 1)

        sel_layout.addWidget(QLabel("Parameters:"), 3, 0)
        self._lbl_param_type = QLabel("—")
        sel_layout.addWidget(self._lbl_param_type, 3, 1)

        sel_layout.addWidget(QLabel("Explanation:"), 4, 0)
        self._lbl_explanation = QLabel("—")
        self._lbl_explanation.setWordWrap(True)
        sel_layout.addWidget(self._lbl_explanation, 4, 1, 1, 2)

        layout.addWidget(selector_box)

        # Parameter input
        param_box = QGroupBox("Parameters")
        param_layout = QHBoxLayout(param_box)
        param_layout.setSpacing(6)
        self._param_input = QLineEdit()
        self._param_input.setPlaceholderText("Enter parameter value(s)")
        self._param_input.textChanged.connect(self._update_preview)
        param_layout.addWidget(self._param_input)
        layout.addWidget(param_box)

        # Packet preview
        preview_box = QGroupBox("Packet preview (hex)")
        preview_layout = QVBoxLayout(preview_box)
        self._preview = QPlainTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setFixedHeight(80)
        mono = QFont("Courier New", 10)
        self._preview.setFont(mono)
        self._preview.setObjectName("terminalOutput")
        preview_layout.addWidget(self._preview)
        layout.addWidget(preview_box)

        # Send button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_send = QPushButton("Send Command")
        self._btn_send.setFixedWidth(130)
        self._btn_send.clicked.connect(self._on_send)
        btn_row.addWidget(self._btn_send)
        layout.addLayout(btn_row)

        layout.addStretch()

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
            self._preview.setPlainText("")
            return

        params = self._param_input.text()
        packet = _build_packet(cmd, params)
        if packet is None:
            self._preview.setPlainText("(invalid parameters)")
            return

        hex_str = " ".join(f"{b:02X}" for b in packet)
        self._preview.setPlainText(
            f"Bytes ({len(packet)}):  {hex_str}\n"
            f"FNV-1a checksum: 0x{int.from_bytes(packet[-4:], 'little'):08X}"
        )

    @Slot()
    def _on_send(self) -> None:
        name = self._cmd_combo.currentText()
        params = self._param_input.text().strip()
        cmd_str = f"{name} {params}".strip() if params else name
        self._bridge.send_command(cmd_str)
