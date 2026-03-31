"""QPlainTextEdit with Kitsat DSL syntax highlighting and auto-indent."""
from __future__ import annotations

from PySide6.QtWidgets import QPlainTextEdit
from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor,
    QFont, QKeyEvent, QTextCursor,
)


_C = {
    "accent_cyan": "#00d4ff",
    "accent_blue": "#3b82f6",
    "success":     "#10b981",
    "warning":     "#f59e0b",
    "text_primary":"#e2e8f0",
    "text_muted":  "#64748b",
}


class DSLHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for the Kitsat DSL."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rules = []

        def fmt(color: str, bold: bool = False, italic: bool = False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            if italic:
                f.setFontItalic(True)
            return f

        for kw in ["SEND", "WAIT", "GET", "SET", "LOG", "REPEAT",
                   "IF", "END", "TELEMETRY", "MODE"]:
            self._rules.append((
                QRegularExpression(rf"\b{kw}\b"),
                fmt(_C["accent_cyan"], bold=True)
            ))

        for cmd in ["PING", "REBOOT", "CAPTURE_IMAGE", "BEACON", "DEPLOY_ANTENNA",
                    "SET_MODE", "GET_STATUS", "CALIBRATE_ATTITUDE", "GET_TELEMETRY",
                    "RESET_FAULT", "ENABLE_PAYLOAD", "DISABLE_PAYLOAD",
                    "START_LOGGING", "STOP_LOGGING", "DOWNLOAD_LOG", "SET_TX_POWER",
                    "SET_BEACON_INTERVAL", "EMERGENCY_STOP", "RUN_SELF_TEST",
                    "SET_ATTITUDE"]:
            self._rules.append((
                QRegularExpression(rf"\b{cmd}\b"),
                fmt(_C["accent_blue"])
            ))

        self._rules.append((QRegularExpression(r'"[^"]*"'), fmt(_C["success"])))
        self._rules.append((QRegularExpression(r"'[^']*'"), fmt(_C["success"])))
        self._rules.append((QRegularExpression(r"\b\d+(\.\d+)?\b"), fmt(_C["warning"])))
        self._rules.append((QRegularExpression(r"[><=!]+"), fmt(_C["text_primary"])))
        self._rules.append((QRegularExpression(r"#[^\n]*"), fmt(_C["text_muted"], italic=True)))

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


class ScriptEditor(QPlainTextEdit):
    """Code editor with DSL syntax highlighting and auto-indent on Enter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._highlighter = DSLHighlighter(self.document())
        self.setTabStopDistance(28)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setPlaceholderText(
            "# Write your Kitsat DSL script here…\n"
            "# SEND PING\n"
            "# WAIT 2.0\n"
            "# REPEAT 3:\n"
            "#     SEND BEACON\n"
            "#     WAIT 5.0\n"
            "# END"
        )

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Return:
            cursor = self.textCursor()
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            line = cursor.selectedText()
            indent = ""
            for ch in line:
                if ch in (" ", "\t"):
                    indent += ch
                else:
                    break
            super().keyPressEvent(event)
            self.insertPlainText(indent)
            return
        super().keyPressEvent(event)
