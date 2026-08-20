"""Neutral expression language for the LADDER IR.

Expressions are written in a small, vendor-neutral subset of IEC 61131-3
Structured Text syntax:

    pressure_ok AND gate_valve_closed
    NOT (pump_speed > 100.0) OR bypass
    T#5s            (TIME literal, normalized to milliseconds internally)
    fill_level >= setpoint - 2.5

They are parsed once into a small AST; every vendor backend renders the AST
in its own dialect. The LLM (or a human) never writes vendor syntax.

Grammar (lowest to highest precedence):

    or_expr   := xor_expr  ( OR  xor_expr )*
    xor_expr  := and_expr  ( XOR and_expr )*
    and_expr  := cmp_expr  ( AND cmp_expr )*
    cmp_expr  := add_expr  ( ( = | <> | < | <= | > | >= ) add_expr )?
    add_expr  := mul_expr  ( ( + | - ) mul_expr )*
    mul_expr  := unary     ( ( * | / | MOD ) unary )*
    unary     := ( NOT | - ) unary | primary
    primary   := literal | reference | '(' or_expr ')'
    reference := SEGMENT ( '.' SEGMENT )*    e.g. motor.running, T1.Q
    SEGMENT   := IDENT ( '[' INT ']' )?      e.g. temps[3], axes[2].pos

Array indices are literal integers (v0.2); a segment keeps its index in
the path string ('temps[3]') - use split_segment() to take it apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, Union

# ---------------------------------------------------------------- AST nodes


@dataclass(frozen=True)
class Lit:
    """Literal: bool, int, float, or TIME (kind='time', value in ms)."""

    value: Union[bool, int, float]
    kind: str  # 'bool' | 'int' | 'real' | 'time'


_SEGMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?$")


def split_segment(seg: str) -> tuple[str, Union[int, None]]:
    """'temps[3]' -> ('temps', 3); 'motor' -> ('motor', None)."""
    m = _SEGMENT_RE.match(seg)
    if not m:
        raise ExprError(f"invalid reference segment {seg!r}")
    return m.group(1), int(m.group(2)) if m.group(2) is not None else None


@dataclass(frozen=True)
class Ref:
    """Reference to a tag or a member path, e.g. ('motor', 'running').
    Segments may carry a literal array index: ('temps[3]',)."""

    path: tuple[str, ...]

    @property
    def root(self) -> str:
        return split_segment(self.path[0])[0]

    def __str__(self) -> str:
        return ".".join(self.path)


@dataclass(frozen=True)
class Un:
    op: str  # 'NOT' | '-'
    x: "Expr"


@dataclass(frozen=True)
class Bin:
    op: str  # AND OR XOR = <> < <= > >= + - * / MOD
    left: "Expr"
    right: "Expr"


@dataclass(frozen=True)
class Conv:
    """Explicit type conversion, e.g. INT_TO_REAL. Produced by lowering
    (never by the parser); dialects that convert implicitly may drop it."""

    frm: str  # source type, e.g. 'INT'
    to: str  # target type, e.g. 'REAL'
    x: "Expr"


Expr = Union[Lit, Ref, Un, Bin, Conv]

BOOL_OPS = {"AND", "OR", "XOR"}
CMP_OPS = {"=", "<>", "<", "<=", ">", ">="}


class ExprError(ValueError):
    """Raised on a syntax error in an IR expression."""


# ---------------------------------------------------------------- tokenizer

_TIME_RE = re.compile(r"(?:TIME|T)#([0-9][0-9a-zA-Z_.]*)", re.IGNORECASE)
_TOKEN_RE = re.compile(
    r"""
    \s*(?:
        (?P<time>(?:TIME|T)\#[0-9][0-9a-zA-Z_.]*)
      | (?P<num>\d+\.\d+|\d+)
      | (?P<ident>[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\d+\])?)*)
      | (?P<op><>|<=|>=|[=<>+\-*/()])
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

_TIME_UNITS_MS = {"d": 86_400_000, "h": 3_600_000, "m": 60_000, "s": 1_000, "ms": 1}
_TIME_PART_RE = re.compile(r"(\d+(?:\.\d+)?)(ms|d|h|m|s)", re.IGNORECASE)


def parse_time_literal(text: str) -> int:
    """T#1m30s / T#500ms / TIME#2.5s -> milliseconds. Raises ExprError."""
    m = _TIME_RE.fullmatch(text.strip())
    if not m:
        raise ExprError(f"invalid TIME literal: {text!r}")
    body = m.group(1).replace("_", "")
    pos, total = 0, 0.0
    for part in _TIME_PART_RE.finditer(body):
        if part.start() != pos:
            raise ExprError(f"invalid TIME literal: {text!r}")
        total += float(part.group(1)) * _TIME_UNITS_MS[part.group(2).lower()]
        pos = part.end()
    if pos != len(body) or pos == 0:
        raise ExprError(f"invalid TIME literal: {text!r}")
    return int(round(total))


def format_time_ms(ms: int) -> str:
    """Milliseconds -> canonical IEC TIME literal, e.g. 90000 -> 'T#1m30s'."""
    if ms == 0:
        return "T#0ms"
    out, rest = [], ms
    for unit, factor in (("d", 86_400_000), ("h", 3_600_000), ("m", 60_000), ("s", 1_000), ("ms", 1)):
        n, rest = divmod(rest, factor)
        if n:
            out.append(f"{n}{unit}")
    return "T#" + "".join(out)


def _tokens(text: str) -> Iterator[tuple[str, str]]:
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m or m.end() == pos:
            if text[pos:].strip():
                raise ExprError(f"unexpected character {text[pos:].strip()[0]!r} in {text!r}")
            break
        pos = m.end()
        kind = m.lastgroup
        yield kind, m.group(kind)  # type: ignore[arg-type]
    yield "eof", ""


_KEYWORD_OPS = {"AND", "OR", "XOR", "NOT", "MOD"}


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.toks = list(_tokens(text))
        self.i = 0

    def peek(self) -> tuple[str, str]:
        return self.toks[self.i]

    def next(self) -> tuple[str, str]:
        t = self.toks[self.i]
        self.i += 1
        return t

    def _is_kw(self, word: str) -> bool:
        kind, val = self.peek()
        return kind == "ident" and val.upper() == word

    def parse(self) -> Expr:
        e = self.or_expr()
        kind, val = self.peek()
        if kind != "eof":
            raise ExprError(f"unexpected {val!r} in {self.text!r}")
        return e

    def _binop_chain(self, sub, words: tuple[str, ...]) -> Expr:
        e = sub()
        while True:
            for w in words:
                if self._is_kw(w):
                    self.next()
                    e = Bin(w, e, sub())
                    break
            else:
                return e

    def or_expr(self) -> Expr:
        return self._binop_chain(self.xor_expr, ("OR",))

    def xor_expr(self) -> Expr:
        return self._binop_chain(self.and_expr, ("XOR",))

    def and_expr(self) -> Expr:
        return self._binop_chain(self.cmp_expr, ("AND",))

    def cmp_expr(self) -> Expr:
        e = self.add_expr()
        kind, val = self.peek()
        if kind == "op" and val in CMP_OPS:
            self.next()
            e = Bin(val, e, self.add_expr())
        return e

    def add_expr(self) -> Expr:
        e = self.mul_expr()
        while True:
            kind, val = self.peek()
            if kind == "op" and val in ("+", "-"):
                self.next()
                e = Bin(val, e, self.mul_expr())
            else:
                return e

    def mul_expr(self) -> Expr:
        e = self.unary()
        while True:
            kind, val = self.peek()
            if kind == "op" and val in ("*", "/"):
                self.next()
                e = Bin(val, e, self.unary())
            elif self._is_kw("MOD"):
                self.next()
                e = Bin("MOD", e, self.unary())
            else:
                return e

    def unary(self) -> Expr:
        if self._is_kw("NOT"):
            self.next()
            return Un("NOT", self.unary())
        kind, val = self.peek()
        if kind == "op" and val == "-":
            self.next()
            return Un("-", self.unary())
        return self.primary()

    def primary(self) -> Expr:
        kind, val = self.next()
        if kind == "time":
            return Lit(parse_time_literal(val), "time")
        if kind == "num":
            return Lit(float(val), "real") if "." in val else Lit(int(val), "int")
        if kind == "ident":
            upper = val.upper()
            if upper == "TRUE":
                return Lit(True, "bool")
            if upper == "FALSE":
                return Lit(False, "bool")
            if upper in _KEYWORD_OPS:
                raise ExprError(f"misplaced keyword {val!r} in {self.text!r}")
            return Ref(tuple(val.split(".")))
        if kind == "op" and val == "(":
            e = self.or_expr()
            k2, v2 = self.next()
            if (k2, v2) != ("op", ")"):
                raise ExprError(f"expected ')' in {self.text!r}")
            return e
        raise ExprError(f"unexpected {val or 'end of input'!r} in {self.text!r}")


def parse_expr(text: str) -> Expr:
    """Parse a neutral ST expression string into an AST."""
    if not isinstance(text, str) or not text.strip():
        raise ExprError("empty expression")
    return _Parser(text).parse()


# ---------------------------------------------------------------- utilities


def refs(e: Expr) -> Iterator[Ref]:
    """Yield every Ref in an expression tree."""
    if isinstance(e, Ref):
        yield e
    elif isinstance(e, (Un, Conv)):
        yield from refs(e.x)
    elif isinstance(e, Bin):
        yield from refs(e.left)
        yield from refs(e.right)


def all_of(exprs: list[Expr]) -> Expr:
    """AND-join a list of expressions."""
    out = exprs[0]
    for e in exprs[1:]:
        out = Bin("AND", out, e)
    return out


def any_of(exprs: list[Expr]) -> Expr:
    """OR-join a list of expressions."""
    out = exprs[0]
    for e in exprs[1:]:
        out = Bin("OR", out, e)
    return out
