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
class FirstOrderProcess:
    """First-order-lag plant model for closed-loop scenarios:

        pv -> ambient + gain * u   with time constant tau_ms.

    Attach with `sim.attach_model(...)` or the scenario `model:` step -
    turns PID/heater/flow acceptance tests into pure YAML."""

    input: str            # the actuator tag the logic writes (u)
    output: str           # the process-value tag the logic reads (pv)
    gain: float = 1.0
    tau_ms: float = 1000.0
    ambient: float = 0.0

    def __call__(self, sim: "Simulator", dt_ms: int) -> None:
        u = float(sim.get(self.input) or 0.0)
        pv = float(sim.get(self.output) or 0.0)
        target = self.ambient + self.gain * u
        alpha = dt_ms / max(self.tau_ms, float(dt_ms))
        sim.set(self.output, pv + (target - pv) * alpha)


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


def _default(tag: Tag, types: dict | None = None) -> Any:
    types = types or {}
    if tag.array is not None:
        return [_scalar_or_struct(tag.type, None, types) for _ in range(tag.array)]
    return _scalar_or_struct(tag.type, tag.initial, types)


def _scalar_or_struct(type_: str, initial: Any, types: dict) -> Any:
    t = type_.upper()
    if t in _DEFAULTS:
        return initial if initial is not None else _DEFAULTS[t]
    udt = types.get(type_)
    if udt is not None:
        return {m.name: _scalar_or_struct(m.type, m.initial, types)
                for m in udt.members}
    return 0  # opaque instance types


def _step_into(value: Any, seg: str) -> Any:
    name, idx = X.split_segment(seg)
    if isinstance(value, dict):
        if name not in value:
            raise SimError(f"no member {name!r}")
        value = value[name]
    if idx is not None:
        if not isinstance(value, list) or not (0 <= idx < len(value)):
            raise SimError(f"bad index in {seg!r}")
        value = value[idx]
    return value


@dataclass
class _Scope:
    """Variable environment for one program (locals over globals)."""

    globals_: dict[str, Any]
    locals_: dict[str, Any] = field(default_factory=dict)
    timers: dict[str, _TimerState] = field(default_factory=dict)

    def _container(self, root: str) -> dict[str, Any]:
        if root in self.locals_:
            return self.locals_
        if root in self.globals_:
            return self.globals_
        raise SimError(f"unknown reference root {root!r}")

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
        try:
            container = self._container(head)
            value = _step_into({head: container[head]}, ref.path[0])
            for seg in ref.path[1:]:
                value = _step_into(value, seg)
        except SimError as e:
            raise SimError(f"{ref}: {e}") from None
        if isinstance(value, (dict, list)):
            raise SimError(f"{ref}: UDT/array used without member/index")
        return value

    def write(self, ref: X.Ref, value: Any) -> None:
        head = ref.root
        try:
            container = self._container(head)
            base, idx = X.split_segment(ref.path[0])
            if len(ref.path) == 1 and idx is None:
                if isinstance(container[base], (dict, list)):
                    raise SimError("cannot assign a whole UDT/array")
                container[base] = value
                return
            # navigate to the parent of the final scalar
            parent: Any = container[base]
            steps: list = ([idx] if idx is not None else [])
            for seg in ref.path[1:]:
                name, seg_idx = X.split_segment(seg)
                steps.append(name)
                if seg_idx is not None:
                    steps.append(seg_idx)
            for step in steps[:-1]:
                parent = parent[step]
            if isinstance(parent, dict) and steps[-1] not in parent:
                raise SimError(f"no member {steps[-1]!r}")
            if not isinstance(parent, (dict, list)):
                raise SimError("not a UDT/array")
            parent[steps[-1]] = value
        except (KeyError, IndexError, TypeError) as e:
            raise SimError(f"{ref}: {e}") from None
        except SimError as e:
            raise SimError(f"{ref}: {e}") from None


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
        self._types = {t.name: t for t in project.types}
        self.globals: dict[str, Any] = {t.name: _default(t, self._types)
                                        for t in project.tags}
        self.time_ms = 0
        self.scan_count = 0
        self._models: list = []
        self._scopes: dict[str, _Scope] = {}
        for name, lp in self.lowered.items():
            scope = _Scope(self.globals)
            for t in lp.program.variables:
                scope.locals_[t.name] = _default(t, self._types)
            for v in lp.synth:
                if v.kind == "timer":
                    scope.timers[v.name] = _TimerState(v.timer_kind)
                elif v.kind == "real":
                    scope.locals_[v.name] = 0.0
                else:
                    scope.locals_[v.name] = False
            self._scopes[name] = scope

    # ------------------------------------------------------------- controls

    def set(self, tag: str, value: Any) -> None:
        """Write a global tag; dotted/indexed paths reach members
        (e.g. set('pump1.run_cmd', True), set('temps[3]', 42.0))."""
        path = tuple(tag.split("."))
        root = X.split_segment(path[0])[0]
        if root not in self.globals:
            raise SimError(f"unknown global tag {root!r}")
        _Scope(self.globals).write(X.Ref(path), value)

    def get(self, tag: str) -> Any:
        path = tuple(tag.split("."))
        root = X.split_segment(path[0])[0]
        for scope in self._scopes.values():
            if root in scope.locals_ or root in scope.timers:
                return scope.read(X.Ref(path))
        return _Scope(self.globals).read(X.Ref(path))

    def pulse(self, tag: str, dt_ms: int = 10) -> None:
        """One scan with the tag TRUE, one with it FALSE (a button press)."""
        self.set(tag, True)
        self.scan(dt_ms)
        self.set(tag, False)
        self.scan(dt_ms)

    def attach_model(self, model) -> None:
        """Attach a plant model: a callable(sim, dt_ms) run at the start
        of every scan (before program execution), closing the loop by
        writing process-value tags from the previous scan's outputs."""
        self._models.append(model)

    def scan(self, dt_ms: int = 10, n: int = 1) -> None:
        for _ in range(n):
            self.time_ms += dt_ms
            self.scan_count += 1
            for model in self._models:
                model(self, dt_ms)
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
