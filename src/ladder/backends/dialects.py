"""Structured Text dialect renderers.

One neutral statement AST in, vendor-specific ST text out. The differences
between vendors are concentrated here:

  Siemens SCL   locals #name, globals "name", IEC TON instances, T# literals
  IEC 61131-3   plain identifiers, standard TON/TOF/TP, T# literals
                (CODESYS, Beckhoff TwinCAT, PLCopen XML bodies)
  Rockwell ST   plain identifiers, FBD_TIMER + TONR/TOFR instructions,
                presets as DINT milliseconds, .DN/.ACC members
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
    SynthVar,
)

_PREC = {
    "OR": 1, "XOR": 2, "AND": 3,
    "=": 4, "<>": 4, "<": 4, "<=": 4, ">": 4, ">=": 4,
    "+": 5, "-": 5,
    "*": 6, "/": 6, "MOD": 6,
}
_UNARY_PREC = 7


@dataclass
class RenderContext:
    """Which names are local to the POU being rendered (locals get the
    dialect's local decoration; everything else is a global tag)."""

    local_names: set[str] = field(default_factory=set)

    @classmethod
    def for_program(cls, lp: LoweredProgram) -> "RenderContext":
        names = {t.name for t in lp.program.variables}
        names.update(v.name for v in lp.synth)
        return cls(names)


class STDialect:
    """Base renderer: IEC 61131-3 flavored, no decoration."""

    name = "iec"
    indent = "    "
    #: neutral timer member -> dialect member
    timer_members = {"Q": "Q", "ET": "ET"}
    #: timer instance declaration type per kind
    timer_types = {"TON": "TON", "TOF": "TOF", "TP": "TP"}

    # ---- identifiers -----------------------------------------------------

    def fmt_local(self, name: str) -> str:
        return name

    def fmt_global(self, name: str) -> str:
        return name

    def fmt_ref(self, ref: X.Ref, ctx: RenderContext) -> str:
        head, *rest = ref.path
        is_local = head in ctx.local_names
        # member access on a timer instance: map neutral Q/ET
        if rest and is_local:
            rest = [self.timer_members.get(m, m) for m in rest]
        base = self.fmt_local(head) if is_local else self.fmt_global(head)
        return ".".join([base, *rest])

    # ---- literals --------------------------------------------------------

    def fmt_time(self, ms: int) -> str:
        return X.format_time_ms(ms)

    def fmt_lit(self, lit: X.Lit) -> str:
        if lit.kind == "bool":
            return "TRUE" if lit.value else "FALSE"
        if lit.kind == "time":
            return self.fmt_time(int(lit.value))
        if lit.kind == "real":
            s = repr(float(lit.value))
            return s if ("." in s or "e" in s) else s + ".0"
        return str(lit.value)

    # ---- expressions -----------------------------------------------------

    def expr(self, e: X.Expr, ctx: RenderContext, parent_prec: int = 0) -> str:
        if isinstance(e, X.Lit):
            return self.fmt_lit(e)
        if isinstance(e, X.Ref):
            return self.fmt_ref(e, ctx)
        if isinstance(e, X.Un):
            inner = self.expr(e.x, ctx, _UNARY_PREC)
            s = f"NOT {inner}" if e.op == "NOT" else f"-{inner}"
            return f"({s})" if parent_prec >= _UNARY_PREC else s
        if isinstance(e, X.Bin):
            prec = _PREC[e.op]
            s = (f"{self.expr(e.left, ctx, prec)} {e.op} "
                 f"{self.expr(e.right, ctx, prec + 1)}")
            return f"({s})" if parent_prec > prec else s
        if isinstance(e, X.Conv):
            return self.convert(e, ctx)
        raise TypeError(f"unknown expression node: {e!r}")

    def convert(self, e: X.Conv, ctx: RenderContext) -> str:
        """Explicit IEC conversion function, e.g. INT_TO_REAL(x)."""
        return f"{e.frm}_TO_{e.to}({self.expr(e.x, ctx)})"

    # ---- statements --------------------------------------------------------

    def comment(self, text: str) -> list[str]:
        return [f"// {text}"]

    def timer_call(self, s: STimerCall, ctx: RenderContext) -> list[str]:
        if s.kind not in self.timer_types:
            raise BackendError(f"{self.name}: timer kind {s.kind} unsupported")
        inst = self.fmt_local(s.instance)
        return [f"{inst}(IN := {self.expr(s.input, ctx)}, PT := {self.fmt_time(s.preset_ms)});"]

    def stmt(self, s: Stmt, ctx: RenderContext) -> list[str]:
        if isinstance(s, SComment):
            return self.comment(s.text)
        if isinstance(s, SAssign):
            return [f"{self.fmt_ref(s.target, ctx)} := {self.expr(s.value, ctx)};"]
        if isinstance(s, STimerCall):
            return self.timer_call(s, ctx)
        if isinstance(s, SRaw):
            return s.code.rstrip().splitlines()
        if isinstance(s, SIf):
            out = [f"IF {self.expr(s.cond, ctx)} THEN"]
            out += self._block(s.then, ctx)
            for cond, body in s.elifs:
                out.append(f"ELSIF {self.expr(cond, ctx)} THEN")
                out += self._block(body, ctx)
            if s.orelse:
                out.append("ELSE")
                out += self._block(s.orelse, ctx)
            out.append("END_IF;")
            return out
        if isinstance(s, SCase):
            out = [f"CASE {self.fmt_ref(s.selector, ctx)} OF"]
            for code, name, body in s.cases:
                out.append(f"{self.indent}{code}:  {self.comment_inline(name)}")
                for b in body:
                    out += [self.indent * 2 + line for line in self.stmt(b, ctx)]
            out.append("END_CASE;")
            return out
        raise TypeError(f"unknown statement: {s!r}")

    def comment_inline(self, text: str) -> str:
        return f"(* {text} *)"

    def _block(self, body: list[Stmt], ctx: RenderContext) -> list[str]:
        out: list[str] = []
        for s in body:
            out += [self.indent + line for line in self.stmt(s, ctx)]
        return out

    def body(self, lp: LoweredProgram) -> str:
        ctx = RenderContext.for_program(lp)
        lines: list[str] = []
        for s in lp.statements:
            lines += self.stmt(s, ctx)
        return "\n".join(lines) + "\n"

    # ---- declarations ------------------------------------------------------

    def timer_decl_type(self, v: SynthVar) -> str:
        if v.timer_kind not in self.timer_types:
            raise BackendError(
                f"{self.name}: timer kind {v.timer_kind} unsupported "
                f"(instance {v.name!r})")
        return self.timer_types[v.timer_kind]


class Iec61131Dialect(STDialect):
    """CODESYS / Beckhoff TwinCAT / PLCopen XML bodies."""

    name = "iec61131"


class SiemensSclDialect(STDialect):
    """Siemens SCL (TIA Portal, S7-1500). Locals are #name, globals "name"."""

    name = "siemens-scl"

    def fmt_local(self, name: str) -> str:
        return f"#{name}"

    def fmt_global(self, name: str) -> str:
        return f'"{name}"'


class RockwellStDialect(STDialect):
    """Studio 5000 Logix Designer Structured Text.

    Timers are FBD_TIMER tags driven by the TONR/TOFR instructions; presets
    and accumulators are DINT milliseconds; done bit is .DN.
    """

    name = "rockwell-st"
    timer_members = {"Q": "DN", "ET": "ACC"}
    timer_types = {"TON": "FBD_TIMER", "TOF": "FBD_TIMER"}
    _instructions = {"TON": "TONR", "TOF": "TOFR"}

    def fmt_time(self, ms: int) -> str:
        return str(ms)  # DINT milliseconds

    def timer_call(self, s: STimerCall, ctx: RenderContext) -> list[str]:
        if s.kind not in self._instructions:
            raise BackendError(
                "rockwell: TP (pulse) timers have no ST instruction in Logix; "
                f"rework timer instance {s.instance!r} (e.g. TON + logic)")
        return [
            f"{s.instance}.TimerEnable := {self.expr(s.input, ctx)};",
            f"{s.instance}.PRE := {s.preset_ms};",
            f"{self._instructions[s.kind]}({s.instance});",
        ]

    def fmt_lit(self, lit: X.Lit) -> str:
        if lit.kind == "bool":
            return "1" if lit.value else "0"  # Logix ST has no TRUE/FALSE literals pre-v32; 1/0 is always safe
        return super().fmt_lit(lit)

    def convert(self, e: X.Conv, ctx: RenderContext) -> str:
        # Logix ST converts numeric types implicitly in expressions
        return f"({self.expr(e.x, ctx)})"
