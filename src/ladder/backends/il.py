"""IEC 61131-3 Instruction List renderer (ed.2).

Renders the neutral statement AST as standard IL: accumulator loads,
parenthesized deferred operators for nested expressions, conditional
jumps for IF/CASE, and CAL for timer instances. Emitted through the
`iec` backend for programs declaring `language: il`, so matiec proves
the output in CI exactly like the ST path.

IL is deprecated in IEC 61131-3 ed.3 but still shipped by every vendor
and required for some legacy runtimes - which is precisely why a
generator should support it while humans no longer have to write it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ladder.backends.base import BackendError
from ladder.ir import expr as X
from ladder.ir.lower import (
    LoweredProgram,
    SAssign,
    SCase,
    SComment,
    SIf,
    SRaw,
    STimerCall,
    Stmt,
)

_BIN_OPS = {
    "AND": "AND", "OR": "OR", "XOR": "XOR",
    "+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV", "MOD": "MOD",
    "=": "EQ", "<>": "NE", "<": "LT", "<=": "LE", ">": "GT", ">=": "GE",
}
_NEGATABLE = {"AND", "OR", "XOR"}  # ANDN / ORN / XORN exist


def _fmt_lit(lit: X.Lit) -> str:
    if lit.kind == "bool":
        return "TRUE" if lit.value else "FALSE"
    if lit.kind == "time":
        return X.format_time_ms(int(lit.value))
    if lit.kind == "real":
        s = repr(float(lit.value))
        return s if ("." in s or "e" in s) else s + ".0"
    return str(lit.value)


def _operand(e: X.Expr) -> str | None:
    """IL operand text for a simple expression, or None if it needs code."""
    if isinstance(e, X.Lit):
        return _fmt_lit(e)
    if isinstance(e, X.Ref):
        return ".".join(e.path)
    return None


@dataclass
class IlRenderer:
    """One POU body. Collects extra BOOL temporaries (for timer inputs
    that are expressions - CAL arguments must be plain operands)."""

    extra_bools: list[str] = field(default_factory=list)
    _label_n: int = 0

    def _label(self) -> str:
        self._label_n += 1
        return f"L{self._label_n}"

    # ---- expressions -> accumulator ----------------------------------------

    def load(self, e: X.Expr) -> list[str]:
        op = _operand(e)
        if op is not None:
            return [f"LD {op}"]
        if isinstance(e, X.Un):
            if e.op == "NOT":
                inner = _operand(e.x)
                if inner is not None:
                    return [f"LDN {inner}"]
                return [*self.load(e.x), "NOT"]
            # unary minus
            return [*self.load(e.x), "MUL -1"]
        if isinstance(e, X.Bin):
            il_op = _BIN_OPS.get(e.op)
            if il_op is None:
                raise BackendError(f"il: operator {e.op!r} not supported")
            out = self.load(e.left)
            right = _operand(e.right)
            if right is not None:
                out.append(f"{il_op} {right}")
                return out
            if (il_op in _NEGATABLE and isinstance(e.right, X.Un)
                    and e.right.op == "NOT"):
                inner = _operand(e.right.x)
                if inner is not None:
                    out.append(f"{il_op}N {inner}")
                    return out
            out.append(f"{il_op}(")
            out += ["    " + line for line in self.load(e.right)]
            out.append(")")
            return out
        if isinstance(e, X.Conv):
            return [*self.load(e.x), f"{e.frm}_TO_{e.to}"]
        raise BackendError(f"il: cannot render expression {e!r}")

    # ---- statements ---------------------------------------------------------

    def stmt(self, s: Stmt) -> list[str]:
        if isinstance(s, SComment):
            return [f"(* {s.text.replace('*)', '* )')} *)"]
        if isinstance(s, SAssign):
            return [*self.load(s.value), f"ST {'.'.join(s.target.path)}"]
        if isinstance(s, STimerCall):
            arg = _operand(s.input)
            out: list[str] = []
            if arg is None:
                arg = f"{s.instance}_in"
                if arg not in self.extra_bools:
                    self.extra_bools.append(arg)
                out += [*self.load(s.input), f"ST {arg}"]
            preset = X.format_time_ms(s.preset_ms)
            # formal FB call: '(' must end the line, one parameter per line
            out += [f"CAL {s.instance}(",
                    f"    IN := {arg},",
                    f"    PT := {preset}",
                    ")"]
            return out
        if isinstance(s, SIf):
            return self._if(s)
        if isinstance(s, SCase):
            return self._case(s)
        if isinstance(s, SRaw):
            raise BackendError("il: raw st element is not renderable (V11)")
        raise BackendError(f"il: unknown statement {type(s).__name__}")

    def _if(self, s: SIf) -> list[str]:
        out: list[str] = []
        branches = [(s.cond, s.then), *s.elifs]
        end = self._label()
        for i, (cond, body) in enumerate(branches):
            last = i == len(branches) - 1 and not s.orelse
            nxt = end if last else self._label()
            out += self.load(cond)
            out.append(f"JMPCN {nxt}")
            for b in body:
                out += self.stmt(b)
            if not last:
                out.append(f"JMP {end}")
                out.append(f"{nxt}:")
        if s.orelse:
            for b in s.orelse:
                out += self.stmt(b)
        out.append(f"{end}:")
        return out

    def _case(self, s: SCase) -> list[str]:
        sel = ".".join(s.selector.path)
        out: list[str] = []
        end = self._label()
        for code, name, body in s.cases:
            nxt = self._label()
            out.append(f"(* {name} *)")
            out.append(f"LD {sel}")
            out.append(f"EQ {code}")
            out.append(f"JMPCN {nxt}")
            for b in body:
                out += self.stmt(b)
            out.append(f"JMP {end}")
            out.append(f"{nxt}:")
        out.append(f"{end}:")
        return out

    def body(self, lp: LoweredProgram) -> str:
        lines: list[str] = []
        for s in lp.statements:
            lines += self.stmt(s)
        # a label must not be the last line of a POU body
        if lines and lines[-1].rstrip().endswith(":"):
            lines.append("LD TRUE")
        return "\n".join(lines) + "\n"
