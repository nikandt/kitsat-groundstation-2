"""
ScriptEngine — port of Kitsat_script.cs / Codeblock.cs from v1.

Supports:
  var name = value          variable declaration + assignment
  name = value              assignment
  loop { ... }              infinite loop (use with care)
  for var < limit { ... }   counted for-loop
  if var == val { ... }     conditional (with optional }else { ... })
  Function name(p1, p2) {}  function definition and call
  wait N                    backend: sleep N seconds
  wait_ms N                 backend: sleep N milliseconds
  <satellite command>       any command in the catalog (e.g. ping, beep 3)
  ImageFrame / MapFrame     UI commands

Usage:
    engine = ScriptEngine(code, command_names=["ping", "beep", ...])
    for cmd in engine:
        if cmd.kind == "satellite":
            modem.send(cmd.line)
        elif cmd.kind == "wait":
            time.sleep(cmd.value_s)
        ...

The engine is a Python iterator — each call to next() returns one
ScriptCommand, or raises StopIteration when the script is done.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ScriptCommand:
    kind: str       # "satellite" | "wait" | "wait_ms" | "ui" | "assignment"
    line: str       # original (whitespace-normalised) line
    value_s: float = 0.0    # for wait / wait_ms (converted to seconds)
    parameter: str = ""     # for UI commands


class ScriptError(Exception):
    def __init__(self, message: str, line_no: int = -1):
        super().__init__(message)
        self.line_no = line_no


# ---------------------------------------------------------------------------
# Preprocessing helpers
# ---------------------------------------------------------------------------

def _add_spaces(s: str) -> str:
    """Ensure spaces around =, +, - (mirrors C# AddWhiteSpace)."""
    for ch in "=+-":
        new_s = ""
        for i, c in enumerate(s):
            if c == ch and i > 0:
                if s[i - 1] != " ":
                    new_s += " "
                new_s += c
                if i + 1 < len(s) and s[i + 1] != " ":
                    new_s += " "
            else:
                new_s += c
        s = new_s
    return s


def _preprocess(code: str) -> list[str]:
    """
    1. Strip whitespace, remove blank lines.
    2. Split lines ending in { or } so the brace is on its own line.
    3. Add spaces around operators.
    """
    lines = [l.strip() for l in code.split("\n")]
    lines = [l for l in lines if l]

    result: list[str] = []
    for line in lines:
        if line and line[-1] in "{}":
            body = line[:-1].strip()
            brace = line[-1]
            if body:
                result.append(body)
            result.append(brace)
        else:
            result.append(line)

    result = [l for l in result if l]
    result = [_add_spaces(l) for l in result]
    return result


def _find_block_end(lines: list[str], start: int) -> int:
    """Find the index of the closing } that matches the { at or after start."""
    depth = 0
    for i in range(start, len(lines)):
        depth += lines[i].count("{")
        depth -= lines[i].count("}")
        if depth <= 0:
            return i
    raise ScriptError(f"Unmatched '{{' starting near line {start}")


def _find_block_start(lines: list[str], start: int) -> int:
    for i in range(start, len(lines)):
        if "{" in lines[i]:
            return i
    raise ScriptError(f"Expected '{{' after line {start}")


# ---------------------------------------------------------------------------
# ScriptEngine
# ---------------------------------------------------------------------------

_RE_FUNCTION = re.compile(r"Function\s+(.+?)\((.*?)\)")
_RE_STRING = re.compile(r'"(.*?)"')


class ScriptEngine:
    """
    Stateful script iterator. Use in a for-loop or call next() manually.

    Not thread-safe — run from a single thread (e.g. a QThread worker).
    """

    def __init__(self, code: str, command_names: list[str]) -> None:
        self._lines = _preprocess(code)
        self._command_names = set(command_names)
        self._variables: dict[str, str] = {}
        self._functions: dict[str, tuple[int, int, list[str]]] = {}
            # name → (body_start, body_end, param_names)

        # Execution stack: list of (pc, end_line)
        # pc = next line to execute; end_line = exclusive end of this frame
        self._call_stack: list[tuple[int, int]] = [(0, len(self._lines))]

        self._scan_functions()

    # ------------------------------------------------------------------
    # Iterator protocol
    # ------------------------------------------------------------------

    def __iter__(self):
        return self

    def __next__(self) -> ScriptCommand:
        cmd = self._step()
        if cmd is None:
            raise StopIteration
        return cmd

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def set_variable(self, name: str, value: str) -> None:
        self._variables[name] = value

    def get_variable(self, name: str) -> Optional[str]:
        return self._variables.get(name)

    # ------------------------------------------------------------------
    # Internal: function scanning
    # ------------------------------------------------------------------

    def _scan_functions(self) -> None:
        for i, line in enumerate(self._lines):
            m = _RE_FUNCTION.match(line)
            if m:
                fname = m.group(1).strip()
                params = [p.strip() for p in m.group(2).split(",") if p.strip()]
                body_start = _find_block_start(self._lines, i + 1)
                body_end = _find_block_end(self._lines, body_start)
                # Store inner body (between braces)
                self._functions[fname] = (body_start + 1, body_end, params)

    # ------------------------------------------------------------------
    # Internal: execution
    # ------------------------------------------------------------------

    def _step(self) -> Optional[ScriptCommand]:
        """Advance the engine by one meaningful command. Returns None when done."""
        while self._call_stack:
            pc, end = self._call_stack[-1]

            # Frame exhausted — pop it
            if pc >= end:
                self._call_stack.pop()
                continue

            line = self._lines[pc]
            words = line.split()
            self._call_stack[-1] = (pc + 1, end)

            # Skip bare braces
            if line in ("{", "}"):
                continue

            # Skip function definitions (already scanned)
            if words[0] == "Function":
                body_start = _find_block_start(self._lines, pc + 1)
                body_end = _find_block_end(self._lines, body_start)
                self._call_stack[-1] = (body_end + 1, end)
                continue

            # Variable declaration: var name = value
            if words[0] == "var":
                name = words[1]
                if "=" in words:
                    eq_idx = words.index("=")
                    val = self._resolve(" ".join(words[eq_idx + 1:]))
                else:
                    val = ""
                self._variables[name] = val
                continue

            # Assignment: name = value
            if len(words) >= 3 and words[1] == "=":
                name = words[0]
                val = self._resolve(" ".join(words[2:]))
                self._variables[name] = val
                return ScriptCommand(kind="assignment", line=line)

            # loop { ... }
            if words[0] == "loop":
                body_start = _find_block_start(self._lines, pc)
                body_end = _find_block_end(self._lines, body_start)
                # Push infinite loop frame — resets to body_start+1 each iteration
                self._call_stack[-1] = (pc, end)      # stay on 'loop' line
                self._call_stack.append((body_start + 1, body_end))
                continue

            # for var < limit { ... }
            if words[0] == "for" and len(words) >= 4:
                iter_name = words[1]
                limit_str = words[3]
                body_start = _find_block_start(self._lines, pc)
                body_end = _find_block_end(self._lines, body_start)

                val = int(self._variables.get(iter_name, "0"))
                limit = int(self._variables.get(limit_str, limit_str))

                if val >= limit:
                    self._call_stack[-1] = (body_end + 1, end)
                    continue

                self._variables[iter_name] = str(val + 1)
                self._call_stack[-1] = (pc, end)      # stay on 'for' line
                self._call_stack.append((body_start + 1, body_end))
                continue

            # if var == val { ... } (optional }else { ... })
            if words[0] == "if" and len(words) >= 4:
                var_val = self._variables.get(words[1], words[1])
                cmp_val = self._resolve(words[3])
                body_start = _find_block_start(self._lines, pc)
                body_end = _find_block_end(self._lines, body_start)

                has_else = (body_end + 1 < len(self._lines) and
                            self._lines[body_end + 1].strip() in ("}else", "} else"))

                if var_val == cmp_val:
                    after = body_end + 2 if has_else else body_end + 1
                    if has_else:
                        else_end = _find_block_end(self._lines, body_end + 2)
                        after = else_end + 1
                    self._call_stack[-1] = (after, end)
                    self._call_stack.append((body_start + 1, body_end))
                else:
                    if has_else:
                        else_start = body_end + 2
                        else_end = _find_block_end(self._lines, else_start)
                        self._call_stack[-1] = (else_end + 1, end)
                        self._call_stack.append((else_start, else_end))
                    else:
                        self._call_stack[-1] = (body_end + 1, end)
                continue

            # Function call
            func_name = words[0].rstrip("()")
            if func_name in self._functions:
                body_start, body_end, params = self._functions[func_name]
                # Bind parameters if provided
                if len(words) > 1:
                    call_args = " ".join(words[1:])
                    arg_vals = [a.strip().strip('"()') for a in call_args.split(",")]
                    for pname, pval in zip(params, arg_vals):
                        self._variables[pname] = self._resolve(pval)
                self._call_stack.append((body_start, body_end))
                continue

            # Backend: wait / wait_ms
            if words[0] == "wait_ms" and len(words) >= 2:
                ms = float(self._resolve(words[1]))
                return ScriptCommand(kind="wait_ms", line=line, value_s=ms / 1000.0)
            if words[0] == "wait" and len(words) >= 2:
                s = float(self._resolve(words[1]))
                return ScriptCommand(kind="wait", line=line, value_s=s)

            # UI commands
            if words[0] in ("ImageFrame", "MapFrame"):
                param = " ".join(words[1:]) if len(words) > 1 else ""
                return ScriptCommand(kind="ui", line=line,
                                     parameter=self._resolve(param))

            # Satellite command
            if words[0] in self._command_names:
                # Resolve any variable references in the arguments
                resolved_words = [words[0]] + [self._resolve(w) for w in words[1:]]
                return ScriptCommand(kind="satellite",
                                     line=" ".join(resolved_words))

            # Unknown / skip
            continue

        return None   # script finished

    def _resolve(self, token: str) -> str:
        """Resolve a token: string literal, integer literal, or variable."""
        token = token.strip()
        m = _RE_STRING.fullmatch(token)
        if m:
            return m.group(1)
        try:
            int(token)
            return token
        except ValueError:
            pass
        try:
            float(token)
            return token
        except ValueError:
            pass
        return self._variables.get(token, token)
