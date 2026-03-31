"""Kitsat DSL Interpreter — tree-walker that executes AST nodes in a QThread."""
from __future__ import annotations

import time
import threading
from typing import List

from PySide6.QtCore import QThread, Signal

from .parser import (
    ASTNode, SendNode, WaitNode, GetNode, SetNode,
    LogNode, RepeatNode, IfNode, parse_script, ParseError,
)
from .lexer import LexerError
from kitsat_gs.core.events import get_event_bus


class InterpreterError(Exception):
    pass


class ScriptWorker(QThread):
    """Runs a DSL script in a worker thread; emits output lines."""

    output = Signal(str)
    finished = Signal(bool, str)   # (success, error_msg)

    def __init__(self, source: str, parent=None):
        super().__init__(parent)
        self._source = source
        self._stop_event = threading.Event()
        self._last_telemetry: dict = {}

        bus = get_event_bus()
        bus.telemetry_updated.connect(self._cache_telemetry)

    def stop(self):
        self._stop_event.set()

    def _cache_telemetry(self, frame):
        self._last_telemetry = frame.to_dict()

    def run(self):
        try:
            ast = parse_script(self._source)
        except (LexerError, ParseError) as e:
            self.output.emit(f"[ERROR] Parse error: {e}")
            self.finished.emit(False, str(e))
            return

        try:
            self._execute_block(ast)
            self.output.emit("[DONE] Script completed.")
            self.finished.emit(True, "")
        except InterpreterError as e:
            self.output.emit(f"[ERROR] {e}")
            self.finished.emit(False, str(e))
        except Exception as e:
            self.output.emit(f"[ERROR] Runtime error: {e}")
            self.finished.emit(False, str(e))

    def _execute_block(self, stmts: List[ASTNode]):
        for stmt in stmts:
            if self._stop_event.is_set():
                self.output.emit("[STOPPED] Script halted by user.")
                raise InterpreterError("Script stopped")
            self._execute(stmt)

    def _execute(self, node: ASTNode):
        if isinstance(node, SendNode):        self._exec_send(node)
        elif isinstance(node, WaitNode):      self._exec_wait(node)
        elif isinstance(node, GetNode):       self._exec_get(node)
        elif isinstance(node, SetNode):       self._exec_set(node)
        elif isinstance(node, LogNode):       self._exec_log(node)
        elif isinstance(node, RepeatNode):    self._exec_repeat(node)
        elif isinstance(node, IfNode):        self._exec_if(node)
        else:
            raise InterpreterError(f"Unknown node type: {type(node).__name__}")

    def _exec_send(self, node: SendNode):
        self.output.emit(f"  SEND {node.command}")
        get_event_bus().command_sent.emit(node.command, {})

    def _exec_wait(self, node: WaitNode):
        self.output.emit(f"  WAIT {node.seconds}s")
        elapsed = 0.0
        step = 0.1
        while elapsed < node.seconds:
            if self._stop_event.is_set():
                raise InterpreterError("Script stopped during WAIT")
            time.sleep(step)
            elapsed += step

    def _exec_get(self, node: GetNode):
        if node.target == "TELEMETRY":
            val = self._last_telemetry.get(node.field, "N/A")
            self.output.emit(f"  GET TELEMETRY {node.field} = {val}")
        else:
            self.output.emit(f"  GET {node.target} {node.field} = ?")

    def _exec_set(self, node: SetNode):
        self.output.emit(f"  SET {node.target} {node.value}")
        if node.target == "MODE":
            get_event_bus().command_sent.emit("SET_MODE", {"mode": node.value})

    def _exec_log(self, node: LogNode):
        self.output.emit(f"  LOG: {node.message}")

    def _exec_repeat(self, node: RepeatNode):
        self.output.emit(f"  REPEAT {node.count}")
        for i in range(node.count):
            if self._stop_event.is_set():
                raise InterpreterError("Script stopped in REPEAT")
            self.output.emit(f"    [iteration {i + 1}/{node.count}]")
            self._execute_block(node.body)

    def _exec_if(self, node: IfNode):
        val = self._last_telemetry.get(node.field)
        try:
            num_val = float(val) if val is not None else 0.0
        except (TypeError, ValueError):
            num_val = 0.0

        ops = {
            ">":  lambda a, b: a > b,
            "<":  lambda a, b: a < b,
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        condition = ops.get(node.op, lambda a, b: False)(num_val, node.value)
        self.output.emit(
            f"  IF {node.field} {node.op} {node.value} "
            f"→ {num_val} {'TRUE' if condition else 'FALSE'}"
        )
        if condition:
            self._execute_block(node.body)
