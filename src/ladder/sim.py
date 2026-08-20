"""Scan-based simulator for the neutral statement AST (M4).

Interprets lowered programs the way a PLC would: read inputs, execute every
program once per scan, advance time. IEC timers (TON/TOF/TP) are modeled
with real elapsed time, so on-delay alarms, debounces, and state-machine
dwell times can be scenario-tested in plain Python - the checks the IR
exists to make possible, with no vendor tool in the loop.

    sim = Simulator(load_project("examples/vacuum_interlock.yaml"))
    sim.set("pressure_ok", True)
    sim.set("gate_valve_closed", True)
    sim.pulse("reset_pb")
    sim.scan()
    assert sim.get("beam_shutter_permit") is True

`st` escape-hatch elements are not interpretable (they are opaque vendor-
neutral text); by default they raise, or pass on_raw="skip" to ignore them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
    lower_project,
)
from ladder.ir.model import Project, Tag

_DEFAULTS = {"BOOL": False, "INT": 0, "DINT": 0, "WORD": 0, "DWORD": 0,
             "REAL": 0.0, "LREAL": 0.0, "TIME": 0, "STRING": ""}


class SimError(RuntimeError):
    pass


@dataclass
class _TimerState:
    kind: str  # TON | TOF | TP
    elapsed: int = 0  # ms
    q: bool = False
    prev_in: bool = False
    pulsing: bool = False

    def step(self, in_: bool, preset: int, dt: int) -> None:
        if self.kind == "TON":
            if in_:
                self.elapsed = min(self.elapsed + dt, preset)
                self.q = self.elapsed >= preset
            else:
                self.elapsed, self.q = 0, False
        elif self.kind == "TOF":
            if in_:
                self.elapsed, self.q = 0, True
            elif self.q:
                self.elapsed = min(self.elapsed + dt, preset)
                if self.elapsed >= preset:
                    self.q = False
        elif self.kind == "TP":
            if self.pulsing:
                self.elapsed = min(self.elapsed + dt, preset)
                if self.elapsed >= preset:
                    self.q, self.pulsing = False, False
            elif in_ and not self.prev_in:
                self.q, self.pulsing, self.elapsed = True, True, 0
            elif not in_:
                self.elapsed = 0
        self.prev_in = in_


def _default(tag: Tag) -> Any:
    if tag.initial is not None:
        return tag.initial
    return _DEFAULTS.get(tag.type.upper(), 0)


@dataclass
class _Scope:
    """Variable environment for one program (locals over globals)."""

    globals_: dict[str, Any]
    locals_: dict[str, Any] = field(default_factory=dict)
    timers: dict[str, _TimerState] = field(default_factory=dict)

    def read(self, ref: X.Ref) -> Any:
        head = ref.root
        if head in self.timers:
            t = self.timers[head]
            member = ref.path[1] if len(ref.path) > 1 else "Q"
            if member == "Q":
                return t.q
            if member == "ET":
                return t.elapsed
            raise SimError(f"unknown timer member {ref}")
        if len(ref.path) > 1:
            raise SimError(f"member access not simulated: {ref}")
        if head in self.locals_:
            return self.locals_[head]
        if head in self.globals_:
            return self.globals_[head]
        raise SimError(f"unknown reference {ref}")

    def write(self, ref: X.Ref, value: Any) -> None:
        head = ref.root
        if len(ref.path) > 1:
            raise SimError(f"member write not simulated: {ref}")
        if head in self.locals_:
            self.locals_[head] = value
        elif head in self.globals_:
            self.globals_[head] = value
        else:
            raise SimError(f"unknown target {ref}")


def _eval(e: X.Expr, scope: _Scope) -> Any:
    if isinstance(e, X.Lit):
        return e.value
    if isinstance(e, X.Ref):
        return scope.read(e)
    if isinstance(e, X.Conv):
        v = _eval(e.x, scope)
        return float(v) if e.to in ("REAL", "LREAL") else int(v)
    if isinstance(e, X.Un):
        v = _eval(e.x, scope)
        return (not v) if e.op == "NOT" else -v
    if isinstance(e, X.Bin):
        left = _eval(e.left, scope)
        if e.op == "AND":
            return bool(left) and bool(_eval(e.right, scope))
        if e.op == "OR":
            return bool(left) or bool(_eval(e.right, scope))
        right = _eval(e.right, scope)
        return {
            "XOR": lambda: bool(left) != bool(right),
            "=": lambda: left == right, "<>": lambda: left != right,
            "<": lambda: left < right, "<=": lambda: left <= right,
            ">": lambda: left > right, ">=": lambda: left >= right,
            "+": lambda: left + right, "-": lambda: left - right,
            "*": lambda: left * right, "/": lambda: left / right,
            "MOD": lambda: left % right,
        }[e.op]()
    raise SimError(f"cannot evaluate {e!r}")


class Simulator:
    def __init__(self, project: Project, on_raw: str = "error"):
        assert on_raw in ("error", "skip")
        self.project = project
        self.on_raw = on_raw
        self.lowered: dict[str, LoweredProgram] = lower_project(project)
        self.globals: dict[str, Any] = {t.name: _default(t) for t in project.tags}
        self.time_ms = 0
        self.scan_count = 0
        self._scopes: dict[str, _Scope] = {}
        for name, lp in self.lowered.items():
            scope = _Scope(self.globals)
            for t in lp.program.variables:
                scope.locals_[t.name] = _default(t)
            for v in lp.synth:
                if v.kind == "timer":
                    scope.timers[v.name] = _TimerState(v.timer_kind)
                else:
                    scope.locals_[v.name] = False
            self._scopes[name] = scope

    # ------------------------------------------------------------- controls

    def set(self, tag: str, value: Any) -> None:
        if tag not in self.globals:
            raise SimError(f"unknown global tag {tag!r}")
        self.globals[tag] = value

    def get(self, tag: str) -> Any:
        if tag in self.globals:
            return self.globals[tag]
        for scope in self._scopes.values():
            if tag in scope.locals_:
                return scope.locals_[tag]
        raise SimError(f"unknown tag {tag!r}")

    def pulse(self, tag: str, dt_ms: int = 10) -> None:
        """One scan with the tag TRUE, one with it FALSE (a button press)."""
        self.set(tag, True)
        self.scan(dt_ms)
        self.set(tag, False)
        self.scan(dt_ms)

    def scan(self, dt_ms: int = 10, n: int = 1) -> None:
        for _ in range(n):
            self.time_ms += dt_ms
            self.scan_count += 1
            for name, lp in self.lowered.items():
                self._exec_block(lp.statements, self._scopes[name], dt_ms)

    def run(self, ms: int, dt_ms: int = 10) -> None:
        """Advance simulated time by ms, scanning every dt_ms."""
        self.scan(dt_ms, n=max(1, ms // dt_ms))

    # ------------------------------------------------------------ execution

    def _exec_block(self, stmts: list[Stmt], scope: _Scope, dt: int) -> None:
        for s in stmts:
            self._exec(s, scope, dt)

    def _exec(self, s: Stmt, scope: _Scope, dt: int) -> None:
        if isinstance(s, SComment):
            return
        if isinstance(s, SAssign):
            scope.write(s.target, _eval(s.value, scope))
        elif isinstance(s, STimerCall):
            scope.timers[s.instance].step(bool(_eval(s.input, scope)), s.preset_ms, dt)
        elif isinstance(s, SIf):
            if _eval(s.cond, scope):
                self._exec_block(s.then, scope, dt)
                return
            for cond, body in s.elifs:
                if _eval(cond, scope):
                    self._exec_block(body, scope, dt)
                    return
            self._exec_block(s.orelse, scope, dt)
        elif isinstance(s, SCase):
            sel = scope.read(s.selector)
            for code, _name, body in s.cases:
                if sel == code:
                    self._exec_block(body, scope, dt)
                    return
        elif isinstance(s, SRaw):
            if self.on_raw == "error":
                raise SimError("st escape-hatch element cannot be simulated "
                               "(construct Simulator with on_raw='skip' to ignore)")
        else:
            raise SimError(f"unknown statement {s!r}")
