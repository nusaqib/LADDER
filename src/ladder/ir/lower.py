"""Deterministic lowering: IR logic elements -> neutral statement AST.

Backends never see IR elements directly; they render this small statement
AST in their own ST dialect. Lowering also synthesizes the support
variables the elements imply (timer instances, edge memories) so every
backend declares exactly the same state.

Semantics locked here (not in the backends):

  interlock (latching):   trip the scan permissives go false; re-permit only
                          on reset edge while permissives are healthy.
  alarm (on-delay):       condition feeds a TON; the TON's done bit is the
                          alarm condition. Latching alarms clear on ack only
                          once the (delayed) condition is gone.
  state machine:          CASE on the state tag; 'do' actions run every scan
                          in the state, then transitions are evaluated in
                          order (first match wins).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from ladder.ir import expr as X
from ladder.ir.model import (
    AlarmEl,
    AssignEl,
    InterlockEl,
    Program,
    Project,
    RawStEl,
    ScaleEl,
    StateMachineEl,
    TimerEl,
    compile_cond,
)

# ------------------------------------------------------------- statements


@dataclass
class SComment:
    text: str


@dataclass
class SAssign:
    target: X.Ref
    value: X.Expr


@dataclass
class SIf:
    cond: X.Expr
    then: list["Stmt"]
    orelse: list["Stmt"] = field(default_factory=list)
    #: chained (cond, body) pairs rendered as ELSIF
    elifs: list[tuple[X.Expr, list["Stmt"]]] = field(default_factory=list)


@dataclass
class SCase:
    selector: X.Ref
    #: (code, state name for the comment, body)
    cases: list[tuple[int, str, list["Stmt"]]]


@dataclass
class STimerCall:
    """Invoke an IEC timer instance. Backends own the call syntax."""

    instance: str  # synthesized local variable name
    kind: str  # TON | TOF | TP
    input: X.Expr
    preset_ms: int


@dataclass
class SRaw:
    """Neutral ST passed through; backends apply reference decoration only."""

    code: str


Stmt = Union[SComment, SAssign, SIf, SCase, STimerCall, SRaw]


@dataclass
class SynthVar:
    """Variable synthesized by lowering (timer instance / edge memory)."""

    name: str
    kind: str  # 'timer' | 'bool'
    timer_kind: str = "TON"  # meaningful when kind == 'timer'
    comment: str = ""


@dataclass
class LoweredProgram:
    program: Program
    statements: list[Stmt]
    synth: list[SynthVar]


# --------------------------------------------------------------- lowering


def _ref(name: str) -> X.Ref:
    return X.Ref(tuple(name.split(".")))


def _rising_edge(signal: str, mem_name: str, synth: list[SynthVar]) -> X.Expr:
    """signal AND NOT mem; caller must append 'mem := signal' afterwards."""
    synth.append(SynthVar(mem_name, "bool", comment=f"edge memory for {signal}"))
    return X.Bin("AND", _ref(signal), X.Un("NOT", _ref(mem_name)))


def lower_program(project: Project, prog: Program) -> LoweredProgram:
    stmts: list[Stmt] = []
    synth: list[SynthVar] = []
    types = {t.name: t.type.upper() for t in project.tags}
    types.update({t.name: t.type.upper() for t in prog.variables})
    for el in prog.logic:
        stmts.extend(_lower_element(el, synth, types))
    return LoweredProgram(prog, stmts, synth)


def lower_project(project: Project) -> dict[str, LoweredProgram]:
    return {p.name: lower_program(project, p) for p in project.programs}


def _header(el, kind: str) -> list[Stmt]:
    el_id = getattr(el, "id", None)
    label = f"{kind} {el_id}" if el_id else kind
    if el.description:
        label += f": {el.description}"
    return [SComment(label)]


def _lower_element(el, synth: list[SynthVar], types: dict[str, str]) -> list[Stmt]:
    if isinstance(el, AssignEl):
        out = _header(el, "assign") if el.description else []
        out.append(SAssign(_ref(el.target), compile_cond(el.value)))
        return out
    if isinstance(el, InterlockEl):
        return _lower_interlock(el, synth)
    if isinstance(el, AlarmEl):
        return _lower_alarm(el, synth)
    if isinstance(el, TimerEl):
        return _lower_timer(el, synth)
    if isinstance(el, StateMachineEl):
        return _lower_state_machine(el)
    if isinstance(el, ScaleEl):
        return _lower_scale(el, types)
    if isinstance(el, RawStEl):
        return [*_header(el, "st"), SRaw(el.code)]
    raise TypeError(f"unknown element: {el!r} (patterns must be expanded first)")


def _lower_scale(el: ScaleEl, types: dict[str, str]) -> list[Stmt]:
    out = _header(el, "scale")
    k = (el.eu_max - el.eu_min) / (el.raw_max - el.raw_min)
    b = el.eu_min - el.raw_min * k
    src: X.Expr = _ref(el.input)
    src_type = types.get(el.input, "INT")
    if src_type not in ("REAL", "LREAL"):
        src = X.Conv(src_type, "REAL", src)
    expr: X.Expr = X.Bin("*", src, X.Lit(k, "real"))
    if b != 0.0:
        expr = X.Bin("+", expr, X.Lit(b, "real"))
    output = _ref(el.output)
    out.append(SAssign(output, expr))
    if el.clamp:
        lo, hi = sorted((el.eu_min, el.eu_max))
        out.append(SIf(
            X.Bin(">", output, X.Lit(hi, "real")),
            [SAssign(output, X.Lit(hi, "real"))],
            elifs=[(X.Bin("<", output, X.Lit(lo, "real")),
                    [SAssign(output, X.Lit(lo, "real"))])],
        ))
    return out


def _lower_interlock(el: InterlockEl, synth: list[SynthVar]) -> list[Stmt]:
    out = _header(el, "interlock")
    perm = compile_cond(el.permissives)
    output = _ref(el.output)
    if not el.latching:
        out.append(SAssign(output, perm))
        return out
    # trip immediately when any permissive is lost
    out.append(SIf(X.Un("NOT", perm), [SAssign(output, X.Lit(False, "bool"))]))
    # re-permit on reset (edge by default) only while healthy
    assert el.reset is not None  # enforced by validation V05
    if el.reset.edge == "rising":
        mem = f"{el.id}_rst_mem"
        reset_expr = _rising_edge(el.reset.signal, mem, synth)
        out.append(SIf(X.Bin("AND", reset_expr, perm),
                       [SAssign(output, X.Lit(True, "bool"))]))
        out.append(SAssign(_ref(mem), _ref(el.reset.signal)))
    else:
        out.append(SIf(X.Bin("AND", _ref(el.reset.signal), perm),
                       [SAssign(output, X.Lit(True, "bool"))]))
    return out


def _lower_alarm(el: AlarmEl, synth: list[SynthVar]) -> list[Stmt]:
    out = _header(el, f"alarm [{el.severity}]")
    raw = compile_cond(el.condition)
    if el.on_delay:
        inst = f"{el.id}_ton"
        synth.append(SynthVar(inst, "timer", "TON", comment=f"on-delay for alarm {el.id}"))
        out.append(STimerCall(inst, "TON", raw, X.parse_time_literal(el.on_delay)))
        trip: X.Expr = X.Ref((inst, "Q"))
    else:
        trip = raw
    output = _ref(el.output)
    if not el.latching:
        out.append(SAssign(output, trip))
        return out
    out.append(SIf(trip, [SAssign(output, X.Lit(True, "bool"))]))
    assert el.ack is not None  # enforced by validation V05
    mem = f"{el.id}_ack_mem"
    ack_edge = _rising_edge(el.ack, mem, synth)
    out.append(SIf(X.Bin("AND", ack_edge, X.Un("NOT", trip)),
                   [SAssign(output, X.Lit(False, "bool"))]))
    out.append(SAssign(_ref(mem), _ref(el.ack)))
    return out


def _lower_timer(el: TimerEl, synth: list[SynthVar]) -> list[Stmt]:
    out = _header(el, f"timer {el.kind}")
    inst = f"{el.id}_t"
    synth.append(SynthVar(inst, "timer", el.kind, comment=f"instance for timer {el.id}"))
    out.append(STimerCall(inst, el.kind, compile_cond(el.input),
                          X.parse_time_literal(el.preset)))
    if el.done:
        out.append(SAssign(_ref(el.done), X.Ref((inst, "Q"))))
    if el.elapsed:
        out.append(SAssign(_ref(el.elapsed), X.Ref((inst, "ET"))))
    return out


def state_codes(el: StateMachineEl) -> dict[str, int]:
    """Stable name -> numeric code mapping (explicit codes win, then order)."""
    used = {s.code for s in el.states if s.code is not None}
    codes: dict[str, int] = {}
    auto = 0
    for s in el.states:
        if s.code is not None:
            codes[s.name] = s.code
        else:
            while auto in used:
                auto += 1
            codes[s.name] = auto
            used.add(auto)
    return codes


def _lower_state_machine(el: StateMachineEl) -> list[Stmt]:
    out = _header(el, "state_machine")
    codes = state_codes(el)
    sel = _ref(el.state_tag)
    cases: list[tuple[int, str, list[Stmt]]] = []
    for st in el.states:
        body: list[Stmt] = []
        for act in st.do:
            body.append(SAssign(_ref(act.target), compile_cond(act.value)))
        # transitions: first match wins -> IF/ELSIF chain
        if st.transitions:
            first, *rest = st.transitions
            body.append(SIf(
                compile_cond(first.when),
                [SAssign(sel, X.Lit(codes[first.goto], "int"))],
                elifs=[(compile_cond(tr.when),
                        [SAssign(sel, X.Lit(codes[tr.goto], "int"))]) for tr in rest],
            ))
        cases.append((codes[st.name], st.name, body))
    out.append(SCase(sel, cases))
    return out
