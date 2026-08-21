"""Neutral rung/network model: statement AST -> ladder-shaped networks.

The graphic IEC languages (LD, FBD) cannot express arbitrary statements,
but everything our lowering produces for the V11-checked element subset
(assign/interlock/alarm/alarm_group/timer) maps onto a short list of
network shapes:

    SAssign(bool, expr)            -> conditional coil        (OTE)
    SIf(cond){x := TRUE}           -> set/latch coil          (OTL / S)
    SIf(cond){x := FALSE}          -> reset/unlatch coil      (OTU / R)
    SIf(cond){int := literal}      -> enabled move            (MOV / MOVE)
    nested SIf                     -> AND of the conditions
    STimerCall                     -> timer instruction/block

`to_rungs` performs that conversion or raises RungError - the same
condition V11 guards at validation time, so a backend hitting RungError
on a `language: ladder` program is a bug, not a user error.

Correctness note on flattening: one IF with N body actions becomes N
rungs sharing the condition. Rung order preserves statement order, and
re-evaluating a pure condition per rung is only observable if a body
action writes a variable the condition reads - that case is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from ladder.backends.base import BackendError
from ladder.ir import expr as X
from ladder.ir.lower import (
    LoweredProgram,
    SAssign,
    SComment,
    SIf,
    STimerCall,
    Stmt,
)


class RungError(BackendError):
    """Statement shape a ladder/FBD network cannot express."""


@dataclass
class CoilAction:
    target: X.Ref
    mode: str  # 'out' (OTE) | 'set' (OTL) | 'reset' (OTU)


@dataclass
class MoveAction:
    target: X.Ref
    value: X.Expr  # literal or plain reference


@dataclass
class TimerAction:
    instance: str
    kind: str  # TON | TOF | TP
    preset_ms: int


Action = Union[CoilAction, MoveAction, TimerAction]


@dataclass
class Rung:
    cond: X.Expr | None  # None = unconditional (direct to the action)
    action: Action
    comment: str = ""


def _and(a: X.Expr | None, b: X.Expr) -> X.Expr:
    return b if a is None else X.Bin("AND", a, b)


def _writes(s: Stmt) -> set[str]:
    """Full dotted paths written (members of one UDT are distinct)."""
    if isinstance(s, SAssign):
        return {".".join(s.target.path)}
    if isinstance(s, SIf):
        out: set[str] = set()
        for b in (*s.then, *s.orelse):
            out |= _writes(b)
        for _, body in s.elifs:
            for b in body:
                out |= _writes(b)
        return out
    return set()


def _cond_reads(e: X.Expr) -> set[str]:
    return {".".join(r.path) for r in X.refs(e)}


def to_rungs(lp: LoweredProgram, bool_roots: set[str]) -> list[Rung]:
    """Convert a lowered program to rungs. `bool_roots` are the tag/synth
    roots of BOOL type (used to distinguish coils from moves)."""
    rungs: list[Rung] = []
    comment = ""

    def emit(cond: X.Expr | None, action: Action) -> None:
        nonlocal comment
        rungs.append(Rung(cond, action, comment))
        comment = ""

    def is_bool_target(ref: X.Ref) -> bool:
        # members (timer .Q, UDT BOOL members) only occur on BOOL positions
        # in the V11-checked subset; roots decide the rest
        return len(ref.path) > 1 or ref.root in bool_roots

    def body_stmt(s: Stmt, cond: X.Expr | None) -> None:
        if isinstance(s, SComment):
            return
        if isinstance(s, SAssign):
            if isinstance(s.value, X.Lit) and s.value.kind == "bool":
                mode = "set" if s.value.value else "reset"
                if cond is None:
                    # unconditional literal: an always-on/off coil
                    emit(None, CoilAction(s.target, mode))
                else:
                    emit(cond, CoilAction(s.target, mode))
                return
            if not is_bool_target(s.target):
                if isinstance(s.value, (X.Lit, X.Ref)):
                    emit(cond, MoveAction(s.target, s.value))
                    return
                raise RungError(
                    f"non-scalar move value for {'.'.join(s.target.path)}")
            if cond is not None:
                raise RungError(
                    f"conditional non-literal assign to {'.'.join(s.target.path)} "
                    "has no ladder equivalent (IF c THEN x := e keeps x on else)")
            emit(s.value, CoilAction(s.target, "out"))
            return
        if isinstance(s, SIf):
            if s.elifs or s.orelse:
                raise RungError("ELSIF/ELSE has no ladder equivalent")
            inner = _and(cond, s.cond)
            guard = _cond_reads(inner)
            for b in s.then:
                if _writes(b) & guard:
                    raise RungError(
                        "IF body writes a variable its condition reads; "
                        "flattening to rungs would change semantics")
                body_stmt(b, inner)
            return
        if isinstance(s, STimerCall):
            if cond is not None:
                raise RungError("timer call inside IF is not rung-shaped")
            emit(None if isinstance(s.input, X.Lit) else s.input,
                 TimerAction(s.instance, s.kind, s.preset_ms))
            return
        raise RungError(f"{type(s).__name__} has no ladder equivalent")

    for s in lp.statements:
        if isinstance(s, SComment):
            comment = (comment + "\n" + s.text).strip()
            continue
        body_stmt(s, None)
    return rungs


def bool_roots_for(lp: LoweredProgram, project) -> set[str]:
    """BOOL-typed roots visible to a program (globals, locals, synth)."""
    roots = {t.name for t in project.tags if t.type.upper() == "BOOL"}
    roots |= {t.name for t in lp.program.variables if t.type.upper() == "BOOL"}
    roots |= {v.name for v in lp.synth if v.kind == "bool"}
    return roots


# ---------------------------------------------------------- normalization


_INVERT = {"=": "<>", "<>": "=", "<": ">=", "<=": ">", ">": "<=", ">=": "<"}


def push_not_down(e: X.Expr) -> X.Expr:
    """De Morgan normalization: NOT only on leaves (refs), so renderers
    map leaves to normally-closed contacts and never need a NOT gate."""
    if isinstance(e, X.Un) and e.op == "NOT":
        x = e.x
        if isinstance(x, X.Un) and x.op == "NOT":
            return push_not_down(x.x)
        if isinstance(x, X.Bin):
            if x.op == "AND":
                return X.Bin("OR", push_not_down(X.Un("NOT", x.left)),
                             push_not_down(X.Un("NOT", x.right)))
            if x.op == "OR":
                return X.Bin("AND", push_not_down(X.Un("NOT", x.left)),
                             push_not_down(X.Un("NOT", x.right)))
            if x.op in _INVERT:
                return X.Bin(_INVERT[x.op], push_not_down(x.left),
                             push_not_down(x.right))
        if isinstance(x, X.Lit) and x.kind == "bool":
            return X.Lit(not x.value, "bool")
        return X.Un("NOT", push_not_down(x))
    if isinstance(e, X.Bin):
        return X.Bin(e.op, push_not_down(e.left), push_not_down(e.right))
    return e
