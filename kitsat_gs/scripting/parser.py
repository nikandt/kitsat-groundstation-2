"""Kitsat DSL Parser — builds an AST from a token list."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union

from .lexer import Lexer, Token, TT


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------

@dataclass
class SendNode:
    command: str
    line: int


@dataclass
class WaitNode:
    seconds: float
    line: int


@dataclass
class GetNode:
    target: str
    field: str
    line: int


@dataclass
class SetNode:
    target: str
    value: str
    line: int


@dataclass
class LogNode:
    message: str
    line: int


@dataclass
class RepeatNode:
    count: int
    body: List
    line: int


@dataclass
class IfNode:
    field: str
    op: str
    value: float
    body: List
    line: int


ASTNode = Union[SendNode, WaitNode, GetNode, SetNode, LogNode, RepeatNode, IfNode]


class ParseError(Exception):
    def __init__(self, message: str, line: int):
        super().__init__(f"Line {line}: {message}")
        self.line = line


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class Parser:
    def __init__(self, tokens: List[Token]):
        cleaned = []
        prev_nl = False
        for t in tokens:
            if t.type == TT.NEWLINE:
                if not prev_nl:
                    cleaned.append(t)
                prev_nl = True
            else:
                prev_nl = False
                cleaned.append(t)
        self._tokens = cleaned
        self._pos = 0

    def parse(self) -> List[ASTNode]:
        stmts = []
        self._skip_newlines()
        while not self._at_eof():
            stmt = self._parse_statement()
            if stmt is not None:
                stmts.append(stmt)
            self._skip_newlines()
        return stmts

    def _peek(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        t = self._tokens[self._pos]
        self._pos += 1
        return t

    def _at_eof(self) -> bool:
        return self._peek().type == TT.EOF

    def _skip_newlines(self):
        while self._peek().type == TT.NEWLINE:
            self._advance()

    def _expect(self, tt: TT, value: Optional[str] = None) -> Token:
        t = self._advance()
        if t.type != tt:
            raise ParseError(
                f"Expected {tt.name}" + (f" '{value}'" if value else "") +
                f", got {t.type.name} '{t.value}'", t.line)
        if value is not None and t.value.upper() != value.upper():
            raise ParseError(f"Expected '{value}', got '{t.value}'", t.line)
        return t

    def _match_keyword(self, *kws: str) -> bool:
        t = self._peek()
        return t.type == TT.KEYWORD and t.value.upper() in kws

    def _parse_statement(self) -> Optional[ASTNode]:
        t = self._peek()
        if t.type == TT.NEWLINE:
            self._advance()
            return None
        if t.type == TT.EOF:
            return None
        if t.type != TT.KEYWORD:
            raise ParseError(f"Expected statement keyword, got '{t.value}'", t.line)

        kw = t.value
        if kw == "SEND":    return self._parse_send()
        if kw == "WAIT":    return self._parse_wait()
        if kw == "GET":     return self._parse_get()
        if kw == "SET":     return self._parse_set()
        if kw == "LOG":     return self._parse_log()
        if kw == "REPEAT":  return self._parse_repeat()
        if kw == "IF":      return self._parse_if()
        raise ParseError(f"Unknown keyword '{kw}'", t.line)

    def _parse_send(self) -> SendNode:
        line = self._peek().line
        self._advance()
        cmd_tok = self._advance()
        return SendNode(command=cmd_tok.value, line=line)

    def _parse_wait(self) -> WaitNode:
        line = self._peek().line
        self._advance()
        num = self._expect(TT.NUMBER)
        return WaitNode(seconds=float(num.value), line=line)

    def _parse_get(self) -> GetNode:
        line = self._peek().line
        self._advance()
        target = self._advance()
        field_tok = self._advance()
        return GetNode(target=target.value, field=field_tok.value, line=line)

    def _parse_set(self) -> SetNode:
        line = self._peek().line
        self._advance()
        target = self._advance()
        value = self._advance()
        return SetNode(target=target.value, value=value.value, line=line)

    def _parse_log(self) -> LogNode:
        line = self._peek().line
        self._advance()
        t = self._advance()
        return LogNode(message=t.value, line=line)

    def _parse_repeat(self) -> RepeatNode:
        line = self._peek().line
        self._advance()
        count_tok = self._expect(TT.NUMBER)
        self._expect(TT.COLON)
        self._skip_newlines()
        body = self._parse_block()
        return RepeatNode(count=int(float(count_tok.value)), body=body, line=line)

    def _parse_if(self) -> IfNode:
        line = self._peek().line
        self._advance()
        field_tok = self._advance()
        op_tok = self._expect(TT.OP)
        val_tok = self._expect(TT.NUMBER)
        self._expect(TT.COLON)
        self._skip_newlines()
        body = self._parse_block()
        return IfNode(
            field=field_tok.value, op=op_tok.value, value=float(val_tok.value),
            body=body, line=line,
        )

    def _parse_block(self) -> List[ASTNode]:
        stmts = []
        while not self._at_eof():
            self._skip_newlines()
            if self._match_keyword("END"):
                self._advance()
                break
            stmt = self._parse_statement()
            if stmt is not None:
                stmts.append(stmt)
        return stmts


def parse_script(source: str) -> List[ASTNode]:
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    return Parser(tokens).parse()
