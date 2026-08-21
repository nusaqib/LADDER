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
    AlarmGroupEl,
    AssignEl,
    DualChannelEl,
    SearchChainEl,
    InterlockEl,
    PidEl,
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
    if isinstance(el, AlarmGroupEl):
        return _lower_alarm_group(el, synth)
    if isinstance(el, DualChannelEl):
        return _lower_dual_channel(el, synth)
    if isinstance(el, SearchChainEl):
        return _lower_search_chain(el, synth)
    if isinstance(el, TimerEl):
        return _lower_timer(el, synth)
    if isinstance(el, StateMachineEl):
        return _lower_state_machine(el)
    if isinstance(el, ScaleEl):
        return _lower_scale(el, types)
    if isinstance(el, PidEl):
        return _lower_pid(el, synth, types)
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


def _lower_alarm_group(el: AlarmGroupEl, synth: list[SynthVar]) -> list[Stmt]:
    """Annunciator semantics (ISA 18.1 sequence A, simplified):

    - each member latches on the rising edge of its (delayed) condition
    - a new alarm re-sounds the horn even while older ones stand unacked
    - ack silences the horn and clears latched members whose condition is gone
    - first_out captures the first member to trip after the group was clean
      (1-based list index; 0 = none), and clears when the group clears
    """
    out = _header(el, "alarm_group")
    if el.first_out:
        legend = ", ".join(f"{i}={m.name}" for i, m in enumerate(el.alarms, 1))
        out.append(SComment(f"first_out codes: 0=none, {legend}"))

    trips: list[X.Expr] = []
    lats: list[str] = []
    unks: list[str] = []
    fo = _ref(el.first_out) if el.first_out else None

    for i, m in enumerate(el.alarms, 1):
        raw = compile_cond(m.condition)
        if m.on_delay:
            inst = f"{el.id}_{m.name}_ton"
            synth.append(SynthVar(inst, "timer", "TON",
                                  comment=f"on-delay for {el.id}/{m.name}"))
            out.append(STimerCall(inst, "TON", raw, X.parse_time_literal(m.on_delay)))
            trip: X.Expr = X.Ref((inst, "Q"))
        else:
            trip = raw
        trips.append(trip)
        lat = f"{el.id}_{m.name}_lat"
        mem = f"{el.id}_{m.name}_mem"
        synth.append(SynthVar(lat, "bool", comment=f"latched alarm {m.name}"))
        synth.append(SynthVar(mem, "bool", comment=f"trip edge memory for {m.name}"))
        lats.append(lat)
        body: list[Stmt] = [SAssign(_ref(lat), X.Lit(True, "bool"))]
        if el.unacked:
            unk = f"{el.id}_{m.name}_unk"
            synth.append(SynthVar(unk, "bool", comment=f"unacknowledged {m.name}"))
            unks.append(unk)
            body.append(SAssign(_ref(unk), X.Lit(True, "bool")))
        if fo is not None:
            body.append(SIf(X.Bin("=", fo, X.Lit(0, "int")),
                            [SAssign(fo, X.Lit(i, "int"))]))
        label = f"member {i}: {m.name}"
        if m.description:
            label += f" - {m.description}"
        out.append(SComment(label))
        out.append(SIf(X.Bin("AND", trip, X.Un("NOT", _ref(mem))), body))
        out.append(SAssign(_ref(mem), trip))

    # common acknowledge: silence horn, clear members whose condition is gone
    ack_mem = f"{el.id}_ack_mem"
    synth.append(SynthVar(ack_mem, "bool", comment=f"edge memory for {el.ack}"))
    ack_body: list[Stmt] = []
    for i, m in enumerate(el.alarms):
        if el.unacked:
            ack_body.append(SAssign(_ref(unks[i]), X.Lit(False, "bool")))
        ack_body.append(SIf(X.Un("NOT", trips[i]),
                            [SAssign(_ref(lats[i]), X.Lit(False, "bool"))]))
    out.append(SIf(X.Bin("AND", _ref(el.ack), X.Un("NOT", _ref(ack_mem))), ack_body))
    out.append(SAssign(_ref(ack_mem), _ref(el.ack)))

    # group outputs
    out.append(SAssign(_ref(el.active), X.any_of([_ref(n) for n in lats])))
    if el.unacked:
        out.append(SAssign(_ref(el.unacked), X.any_of([_ref(n) for n in unks])))
    for i, m in enumerate(el.alarms):
        if m.output:
            out.append(SAssign(_ref(m.output), _ref(lats[i])))
    if fo is not None:
        out.append(SIf(X.Un("NOT", _ref(el.active)), [SAssign(fo, X.Lit(0, "int"))]))
    return out


def _lower_pid(el: PidEl, synth: list[SynthVar],
               types: dict[str, str]) -> list[Stmt]:
    """Discrete positional PID with clamping anti-windup: the integrator
    advances only in the unsaturated branch, and the whole controller
    freezes (bumplessly) while `enable` is FALSE."""
    out = _header(el, "pid")
    dt = X.parse_time_literal(el.interval) / 1000.0

    def real_ref(name: str) -> X.Expr:
        src: X.Expr = _ref(name)
        t = types.get(name, "REAL")
        return src if t in ("REAL", "LREAL") else X.Conv(t, "REAL", src)

    e = _ref(f"{el.id}_e")
    synth.append(SynthVar(f"{el.id}_e", "real", comment=f"error for pid {el.id}"))
    u = _ref(f"{el.id}_u")
    synth.append(SynthVar(f"{el.id}_u", "real", comment=f"unsaturated output for pid {el.id}"))
    body: list[Stmt] = [SAssign(e, X.Bin("-", real_ref(el.setpoint),
                                         real_ref(el.process_value)))]
    terms: X.Expr = X.Bin("*", X.Lit(el.kp, "real"), e)
    i_ref = None
    if el.ti:
        i_ref = _ref(f"{el.id}_i")
        synth.append(SynthVar(f"{el.id}_i", "real", comment=f"integrator for pid {el.id}"))
        terms = X.Bin("+", terms, i_ref)
    if el.td:
        ep = _ref(f"{el.id}_ep")
        synth.append(SynthVar(f"{el.id}_ep", "real", comment=f"previous error for pid {el.id}"))
        kd = el.kp * (X.parse_time_literal(el.td) / 1000.0) / dt
        terms = X.Bin("+", terms, X.Bin("*", X.Lit(kd, "real"),
                                        X.Bin("-", e, ep)))
    body.append(SAssign(u, terms))
    cv = _ref(el.output)
    unsat: list[Stmt] = [SAssign(cv, u)]
    if i_ref is not None:
        ki = el.kp * dt / (X.parse_time_literal(el.ti) / 1000.0)
        # clamping anti-windup: integrate only while unsaturated
        unsat.append(SAssign(i_ref, X.Bin("+", i_ref,
                                          X.Bin("*", X.Lit(ki, "real"), e))))
    body.append(SIf(
        X.Bin(">", u, X.Lit(el.out_max, "real")),
        [SAssign(cv, X.Lit(el.out_max, "real"))],
        elifs=[(X.Bin("<", u, X.Lit(el.out_min, "real")),
                [SAssign(cv, X.Lit(el.out_min, "real"))])],
        orelse=unsat,
    ))
    if el.td:
        body.append(SAssign(_ref(f"{el.id}_ep"), e))
    if el.enable is not None:
        out.append(SIf(compile_cond(el.enable), body))
    else:
        out.extend(body)
    return out


def _lower_dual_channel(el: DualChannelEl, synth: list[SynthVar]) -> list[Stmt]:
    """1oo2 evaluation. Without discrepancy monitoring the output is the
    plain series evaluation; with it, a disagreement outlasting the window
    latches a fault that forces the output FALSE until acknowledged with
    the channels back in agreement."""
    out = _header(el, "dual_channel (1oo2)")
    a, b = _ref(el.channel_a), _ref(el.channel_b)
    output = _ref(el.output)
    if not el.discrepancy_time:
        out.append(SAssign(output, X.Bin("AND", a, b)))
        return out
    inst = f"{el.id}_disc"
    synth.append(SynthVar(inst, "timer", "TON",
                          comment=f"discrepancy window for {el.id}"))
    out.append(STimerCall(inst, "TON", X.Bin("<>", a, b),
                          X.parse_time_literal(el.discrepancy_time)))
    fault = _ref(el.fault) if el.fault else _ref(f"{el.id}_flt")
    if not el.fault:
        synth.append(SynthVar(f"{el.id}_flt", "bool",
                              comment=f"latched discrepancy fault for {el.id}"))
    out.append(SIf(X.Ref((inst, "Q")), [SAssign(fault, X.Lit(True, "bool"))]))
    assert el.ack is not None  # enforced by validation V05
    mem = f"{el.id}_ack_mem"
    ack_edge = _rising_edge(el.ack, mem, synth)
    agree = X.Bin("=", a, b)
    out.append(SIf(X.Bin("AND", ack_edge, agree),
                   [SAssign(fault, X.Lit(False, "bool"))]))
    out.append(SAssign(_ref(mem), _ref(el.ack)))
    out.append(SAssign(output, X.all_of([a, b, X.Un("NOT", fault)])))
    if el.ack_required:
        out.append(SAssign(_ref(el.ack_required), X.Bin("AND", fault, agree)))
    return out


def _lower_search_chain(el: SearchChainEl, synth: list[SynthVar]) -> list[Stmt]:
    """Sequential search chain. Station i sets on the rising edge of its
    key while its predecessor holds (station 1: while the precondition
    holds) and clears the scan the predecessor is lost, so a breach
    cascades down the walk order within one scan. Key edge memories update
    in trailing statements, after every station has run, so a key held
    early cannot ride the chain."""
    out = _header(el, "search_chain")
    out.append(SComment("walk order: " + " -> ".join(s.name for s in el.stations)))
    lats: list[X.Ref] = []
    for st in el.stations:
        if st.latched:
            lats.append(_ref(st.latched))
        else:
            name = f"{el.id}_{st.name}_lat"
            synth.append(SynthVar(name, "bool", comment=f"search latch {st.name}"))
            lats.append(_ref(name))
    prevs: list[str] = []
    for st in el.stations:
        prev = f"{el.id}_{st.name}_prev"
        synth.append(SynthVar(prev, "bool",
                              comment=f"previous-scan key for {st.name}"))
        prevs.append(prev)
    for i, st in enumerate(el.stations):
        pred: X.Expr = compile_cond(el.precondition) if i == 0 else lats[i - 1]
        label = f"station {i + 1}: {st.name}"
        if st.description:
            label += f" - {st.description}"
        out.append(SComment(label))
        # clear the moment the predecessor is lost (breach cascade)
        out.append(SIf(X.Un("NOT", pred), [SAssign(lats[i], X.Lit(False, "bool"))]))
        # set only on the key's rising edge while the predecessor holds
        out.append(SIf(
            X.all_of([pred, _ref(st.key), X.Un("NOT", _ref(prevs[i]))]),
            [SAssign(lats[i], X.Lit(True, "bool"))]))
    out.append(SComment("trailing key edge memories (after every station has run)"))
    for st, prev in zip(el.stations, prevs):
        out.append(SAssign(_ref(prev), _ref(st.key)))
    out.append(SAssign(_ref(el.complete), lats[-1]))
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
