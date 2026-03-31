"""Kitsat DSL Lexer — tokenises a script into a flat token list."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import List


class TT(Enum):
    KEYWORD = auto()
    IDENT   = auto()
    STRING  = auto()
    NUMBER  = auto()
    OP      = auto()
    COLON   = auto()
    NEWLINE = auto()
    COMMENT = auto()
    EOF     = auto()


KEYWORDS = {
    "SEND", "WAIT", "GET", "SET", "LOG", "REPEAT",
    "IF", "END", "TELEMETRY", "MODE",
}

OPERATORS = {"==", "!=", ">=", "<=", ">", "<"}


@dataclass
class Token:
    type: TT
    value: str
    line: int

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, L{self.line})"


class LexerError(Exception):
    def __init__(self, message: str, line: int):
        super().__init__(f"Line {line}: {message}")
        self.line = line


class Lexer:
    def __init__(self, source: str):
        self._source = source
        self._pos = 0
        self._line = 1
        self._tokens: List[Token] = []

    def tokenize(self) -> List[Token]:
        self._tokens = []
        while self._pos < len(self._source):
            self._scan_token()
        self._tokens.append(Token(TT.EOF, "", self._line))
        return [t for t in self._tokens if t.type != TT.COMMENT]

    def _scan_token(self):
        c = self._source[self._pos]

        if c in " \t\r":
            self._pos += 1
            return

        if c == "\n":
            self._tokens.append(Token(TT.NEWLINE, "\\n", self._line))
            self._line += 1
            self._pos += 1
            return

        if c == "#":
            end = self._source.find("\n", self._pos)
            if end == -1:
                end = len(self._source)
            text = self._source[self._pos:end]
            self._tokens.append(Token(TT.COMMENT, text, self._line))
            self._pos = end
            return

        if c == ":":
            self._tokens.append(Token(TT.COLON, ":", self._line))
            self._pos += 1
            return

        two = self._source[self._pos:self._pos + 2]
        if two in OPERATORS:
            self._tokens.append(Token(TT.OP, two, self._line))
            self._pos += 2
            return

        if c in "><!=":
            self._tokens.append(Token(TT.OP, c, self._line))
            self._pos += 1
            return

        if c in ('"', "'"):
            self._pos += 1
            start = self._pos
            while self._pos < len(self._source) and self._source[self._pos] != c:
                if self._source[self._pos] == "\n":
                    raise LexerError("Unterminated string", self._line)
                self._pos += 1
            text = self._source[start:self._pos]
            self._pos += 1
            self._tokens.append(Token(TT.STRING, text, self._line))
            return

        if c.isdigit() or (c == "-" and self._pos + 1 < len(self._source)
                           and self._source[self._pos + 1].isdigit()):
            start = self._pos
            if c == "-":
                self._pos += 1
            while self._pos < len(self._source) and (
                    self._source[self._pos].isdigit() or self._source[self._pos] == "."):
                self._pos += 1
            text = self._source[start:self._pos]
            self._tokens.append(Token(TT.NUMBER, text, self._line))
            return

        if c.isalpha() or c == "_":
            start = self._pos
            while self._pos < len(self._source) and (
                    self._source[self._pos].isalnum() or self._source[self._pos] == "_"):
                self._pos += 1
            text = self._source[start:self._pos]
            tt = TT.KEYWORD if text.upper() in KEYWORDS else TT.IDENT
            self._tokens.append(Token(
                tt, text.upper() if tt == TT.KEYWORD else text, self._line
            ))
            return

        raise LexerError(f"Unexpected character: {c!r}", self._line)
