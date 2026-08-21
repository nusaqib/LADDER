"""Formal model emission: lowered programs -> SMV for nuXmv (M4).

`ladder model` symbolically executes a program's statement AST into a
synchronous SMV transition system:

  - every tag the program writes (plus synthesized locals) is a state VAR;
  - tags only read are free VARs (unconstrained evolution = any input);
  - timers are over-approximated: while enabled, the done bit may rise on
    any scan (an IVAR choice); disabled resets it. This covers EVERY real
    timing, so safety properties proved here hold for all presets/scan rates;
  - the scan's statement order is folded into one TRANS per variable.

Auto-generated properties: for every interlock, the fail-safe theorem

    INVARSPEC output -> permissives

i.e. the permit is never TRUE in any reachable state where a permissive is
down - proved exhaustively, which no amount of scenario testing can do.

Scope (v0.1): BOOL logic and INT state tags with literal assignments.
REAL math (scale), raw `st`, and timer ET reads raise ModelError; programs
using them are skipped with a warning by the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

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
from ladder.ir.model import (
    AlarmGroupEl,
    DualChannelEl,
    InterlockEl,
    Project,
    SearchChainEl,
    compile_cond,
)


class ModelError(ValueError):
    """Program uses something outside the model-checkable subset."""


def _var(path: tuple[str, ...]) -> str:
    if any("[" in seg for seg in path):
        raise ModelError("array indexing is not model-checkable yet")
    return "_".join(path)


@dataclass
class _Ctx:
    state_vars: set[str]  # written this program (current-state reference)
    env: dict[str, str] = field(default_factory=dict)  # var -> SMV next-expr
    choices: list[str] = field(default_factory=list)  # IVAR names

    def read(self, name: str) -> str:
        if name in self.env:
            return self.env[name]
        if name in self.state_vars:
            return name  # pre-scan value of a state variable
        return f"next({name})"  # free input: the value driving this scan


class _PropCtx(_Ctx):
    """Property context: every reference reads the current state."""

    def __init__(self) -> None:
        super().__init__(state_vars=set())

    def read(self, name: str) -> str:
        return name


def _smv_expr(e: X.Expr, ctx: _Ctx) -> str:
    if isinstance(e, X.Lit):
        if e.kind == "bool":
            return "TRUE" if e.value else "FALSE"
        if e.kind == "int":
            return str(e.value)
        raise ModelError(f"literal kind {e.kind} not model-checkable")
    if isinstance(e, X.Ref):
        name = _var(e.path)
        if len(e.path) > 1 and e.path[-1] == "ET":
            raise ModelError("timer ET reads are not model-checkable")
        return ctx.read(name)
    if isinstance(e, X.Un):
        inner = _smv_expr(e.x, ctx)
        return f"(!{inner})" if e.op == "NOT" else f"(-{inner})"
    if isinstance(e, X.Bin):
        op = {"AND": "&", "OR": "|", "XOR": "xor", "=": "=", "<>": "!=",
              "<": "<", "<=": "<=", ">": ">", ">=": ">=", "+": "+",
              "-": "-", "*": "*", "MOD": "mod"}.get(e.op)
        if op is None or e.op == "/":
            raise ModelError(f"operator {e.op} not model-checkable")
        return f"({_smv_expr(e.left, ctx)} {op} {_smv_expr(e.right, ctx)})"
    raise ModelError(f"{type(e).__name__} not model-checkable (REAL math?)")


def _ite(cond: str, then: str, other: str) -> str:
    if then == other:
        return then
    return f"(case {cond} : {then}; TRUE : {other}; esac)"


def _exec_block(stmts: list[Stmt], ctx: _Ctx) -> None:
    for s in stmts:
        _exec(s, ctx)


def _exec(s: Stmt, ctx: _Ctx) -> None:
    if isinstance(s, SComment):
        return
    if isinstance(s, SAssign):
        ctx.env[_var(s.target.path)] = _smv_expr(s.value, ctx)
    elif isinstance(s, STimerCall):
        # over-approximation: done may rise on any scan while enabled
        in_expr = _smv_expr(s.input, ctx)
        q = f"{s.instance}_Q"
        choice = f"{s.instance}_choice"
        ctx.choices.append(choice)
        if s.kind == "TON":
            ctx.env[q] = _ite(in_expr, f"({ctx.read(q)} | {choice})", "FALSE")
        elif s.kind == "TOF":
            ctx.env[q] = _ite(in_expr, "TRUE", f"({ctx.read(q)} & {choice})")
        else:  # TP: fully nondeterministic pulse
            ctx.env[q] = choice
    elif isinstance(s, SIf):
        branches: list[tuple[str, dict[str, str]]] = []
        base = dict(ctx.env)
        for cond, body in [(s.cond, s.then), *s.elifs]:
            cond_smv = _smv_expr(cond, ctx)  # conditions see pre-branch env
            sub = _Ctx(ctx.state_vars, dict(base), ctx.choices)
            _exec_block(body, sub)
            branches.append((cond_smv, sub.env))
        sub = _Ctx(ctx.state_vars, dict(base), ctx.choices)
        _exec_block(s.orelse, sub)
        else_env = sub.env
        touched = set().union(else_env, *(env for _, env in branches))
        for v in touched:
            expr = else_env.get(v, base.get(v, ctx.read(v)))
            for cond_smv, env in reversed(branches):
                expr = _ite(cond_smv, env.get(v, base.get(v, ctx.read(v))), expr)
            ctx.env[v] = expr
    elif isinstance(s, SCase):
        sel = _smv_expr(X.Ref(s.selector.path), ctx)
        base = dict(ctx.env)
        branches = []
        for code, _name, body in s.cases:
            sub = _Ctx(ctx.state_vars, dict(base), ctx.choices)
            _exec_block(body, sub)
            branches.append((f"({sel} = {code})", sub.env))
        touched = set().union(*(env for _, env in branches)) if branches else set()
        for v in touched:
            expr = base.get(v, ctx.read(v))  # no case matched: hold
            for cond_smv, env in reversed(branches):
                expr = _ite(cond_smv, env.get(v, base.get(v, ctx.read(v))), expr)
            ctx.env[v] = expr
    elif isinstance(s, SRaw):
        raise ModelError("st escape-hatch element is not model-checkable")
    else:
        raise ModelError(f"unknown statement {type(s).__name__}")


# ------------------------------------------------------------ module emit


def _all_refs(stmts: list[Stmt]) -> list[X.Ref]:
    out: list[X.Ref] = []
    for s in stmts:
        if isinstance(s, SAssign):
            out.append(s.target)
            out.extend(X.refs(s.value))
        elif isinstance(s, STimerCall):
            out.extend(X.refs(s.input))
        elif isinstance(s, SIf):
            out.extend(X.refs(s.cond))
            for c, b in s.elifs:
                out.extend(X.refs(c))
                out.extend(_all_refs(b))
            out.extend(_all_refs([*s.then, *s.orelse]))
        elif isinstance(s, SCase):
            out.append(s.selector)
            for _, _, body in s.cases:
                out.extend(_all_refs(body))
    return out


def _written_vars(stmts: list[Stmt]) -> set[str]:
    out: set[str] = set()
    for s in stmts:
        if isinstance(s, SAssign):
            out.add(_var(s.target.path))
        elif isinstance(s, STimerCall):
            out.add(f"{s.instance}_Q")
        elif isinstance(s, SIf):
            for _, body in [(None, s.then), (None, s.orelse), *((c, b) for c, b in s.elifs)]:
                out |= _written_vars(body)
        elif isinstance(s, SCase):
            for _, _, body in s.cases:
                out |= _written_vars(body)
    return out


def _read_roots(stmts: list[Stmt]) -> set[str]:
    out: set[str] = set()

    def expr_roots(e: X.Expr) -> None:
        for r in X.refs(e):
            out.add(_var(r.path))

    for s in stmts:
        if isinstance(s, SAssign):
            expr_roots(s.value)
        elif isinstance(s, STimerCall):
            expr_roots(s.input)
        elif isinstance(s, SIf):
            expr_roots(s.cond)
            for c, b in s.elifs:
                expr_roots(c)
                _ = [out.update(_read_roots([x])) for x in b]
            for b in (*s.then, *s.orelse):
                out |= _read_roots([b])
        elif isinstance(s, SCase):
            out.add(_var(s.selector.path))
            for _, _, body in s.cases:
                out |= _read_roots(body)
    return out


def _int_domain(name: str, stmts: list[Stmt], initial: int) -> str:
    """Enumerate literal codes assigned to an INT var, or fail."""
    codes = {initial}

    def walk(body: list[Stmt]) -> None:
        for s in body:
            if isinstance(s, SAssign) and _var(s.target.path) == name:
                if isinstance(s.value, X.Lit) and s.value.kind == "int":
                    codes.add(int(s.value.value))
                else:
                    raise ModelError(
                        f"non-literal INT assignment to {name}; cannot bound domain")
            elif isinstance(s, SIf):
                walk(s.then)
                walk(s.orelse)
                for _, b in s.elifs:
                    walk(b)
            elif isinstance(s, SCase):
                for _, _, b in s.cases:
                    walk(b)

    walk(stmts)
    return "{" + ", ".join(str(c) for c in sorted(codes)) + "}"


def emit_smv(project: Project, lp: LoweredProgram) -> str:
    prog = lp.program
    all_tags = {t.name: t for t in (*project.tags, *prog.variables)}
    types_map = {t.name: t for t in project.types}
    synth_timers = {v.name for v in lp.synth if v.kind == "timer"}

    def flat_type(r: X.Ref) -> str:
        """Type of a (possibly UDT-member) reference; arrays are rejected."""
        from ladder.ir.validate import resolve_path

        if len(r.path) > 1 and r.path[0] in synth_timers:
            return "BOOL"  # timer .Q
        tag = all_tags.get(r.path[0])
        if tag is None:
            return "BOOL"  # synthesized edge memory / latch
        if tag.array is not None:
            raise ModelError("array tags are not model-checkable yet")
        if len(r.path) == 1:
            return tag.type.upper()
        final, err = resolve_path(types_map, tag, tuple(r.path))
        if err:
            raise ModelError(err)
        return final

    ref_types: dict[str, str] = {}
    for r in _all_refs(lp.statements):
        ref_types[_var(r.path)] = flat_type(r)
    initials = {t.name: t.initial for t in (*project.tags, *prog.variables)}

    written = _written_vars(lp.statements)
    read = _read_roots(lp.statements)
    inputs = sorted(r for r in read - written if not r.endswith("_Q"))

    ctx = _Ctx(state_vars=set(written))
    _exec_block(lp.statements, ctx)

    lines = [f"-- {project.name}/{prog.name} - generated by LADDER",
             "-- timers over-approximated: proofs hold for every preset/scan rate",
             "MODULE main", "VAR"]
    for name in inputs:
        t = ref_types.get(name, "BOOL")
        if t not in ("BOOL",):
            raise ModelError(f"free input {name} has type {t}; only BOOL inputs supported")
        lines.append(f"  {name} : boolean;  -- free input")
    int_inits: dict[str, int] = {}
    for name in sorted(written):
        t = "BOOL" if name.endswith("_Q") else ref_types.get(name, "BOOL")
        if t == "BOOL":
            lines.append(f"  {name} : boolean;")
        elif t in ("INT", "DINT"):
            init = int(initials.get(name) or 0)
            int_inits[name] = init
            lines.append(f"  {name} : {_int_domain(name, lp.statements, init)};")
        else:
            raise ModelError(f"state variable {name} has type {t}; not supported")
    for choice in ctx.choices:
        lines.append(f"IVAR {choice} : boolean;  -- timer nondeterminism")

    lines.append("ASSIGN")
    for name in sorted(written):
        if name in int_inits:
            lines.append(f"  init({name}) := {int_inits[name]};")
        else:
            init = initials.get(name)
            lines.append(f"  init({name}) := {'TRUE' if init in (True, 1) else 'FALSE'};")
    lines.append("TRANS")
    parts = [f"next({name}) = {ctx.env.get(name, name)}" for name in sorted(written)]
    lines.append("  " + " &\n  ".join(parts) + ";")

    # fail-safe theorems: interlock output -> permissives, in every reachable state
    for el in prog.logic:
        if isinstance(el, InterlockEl):
            perm = _smv_expr(compile_cond(el.permissives), _PropCtx())
            lines.append(f"-- {el.id}: permit never TRUE while a permissive is down")
            lines.append(f"INVARSPEC ({el.output} -> {perm});")
        elif isinstance(el, AlarmGroupEl):
            active = _var(tuple(el.active.split(".")))
            if el.unacked:
                unacked = _var(tuple(el.unacked.split(".")))
                lines.append(f"-- {el.id}: horn never sounds without the group lamp")
                lines.append(f"INVARSPEC ({unacked} -> {active});")
            if el.first_out:
                fo = _var(tuple(el.first_out.split(".")))
                lines.append(f"-- {el.id}: first-out is nonzero exactly while the group is active")
                lines.append(f"INVARSPEC ({active} <-> ({fo} != 0));")
        elif isinstance(el, DualChannelEl):
            a = _var(tuple(el.channel_a.split(".")))
            b = _var(tuple(el.channel_b.split(".")))
            o = _var(tuple(el.output.split(".")))
            lines.append(f"-- {el.id}: never evaluates OK with a channel down")
            lines.append(f"INVARSPEC ({o} -> ({a} & {b}));")
        elif isinstance(el, SearchChainEl):
            lats = [_var(tuple(st.latched.split("."))) if st.latched
                    else f"{el.id}_{st.name}_lat" for st in el.stations]
            comp = _var(tuple(el.complete.split(".")))
            pre = _smv_expr(compile_cond(el.precondition), _PropCtx())
            lines.append(f"-- {el.id}: search never complete while the precondition is down")
            lines.append(f"INVARSPEC ({comp} -> {pre});")
            lines.append(f"-- {el.id}: stations latch strictly in walk order")
            for i in range(1, len(lats)):
                lines.append(f"INVARSPEC ({lats[i]} -> {lats[i - 1]});")
    return "\n".join(lines) + "\n"


def emit_project(project: Project, outdir: Path) -> tuple[list[Path], list[str]]:
    """Emit one .smv per model-checkable program; return (files, skip notes)."""
    outdir.mkdir(parents=True, exist_ok=True)
    files, skipped = [], []
    for name, lp in lower_project(project).items():
        try:
            text = emit_smv(project, lp)
        except ModelError as e:
            skipped.append(f"{name}: {e}")
            continue
        path = outdir / f"{name}.smv"
        path.write_text(text, encoding="ascii")
        files.append(path)
    return files, skipped
