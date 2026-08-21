"""`ladder mutate` - do your scenarios actually catch broken logic?

Injects single realistic faults into the IR (dropped permissive,
defeated 1oo2 channel, removed debounce, flipped sense, dropped
station, removed transition) and runs the scenario suite against each
mutant. A mutant the suite kills is evidence; a SURVIVOR is a hole -
a fault your acceptance tests would wave through.

Score = killed / valid mutants. Survivors print with exactly what to
add. (STMutants-style evaluation, applied at the IR level where the
mutations are semantic, not syntactic.)
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Mutant:
    description: str
    data: dict
    killed: bool | None = None
    detail: str = ""


def _elements(data: dict):
    for pi, prog in enumerate(data.get("programs", [])):
        for ei, el in enumerate(prog.get("logic", [])):
            yield pi, ei, el


def generate_mutants(data: dict) -> list[Mutant]:
    """Single-fault mutants of a raw IR mapping."""
    out: list[Mutant] = []

    def spawn(desc: str, mutate) -> None:
        clone = copy.deepcopy(data)
        try:
            mutate(clone)
        except (KeyError, IndexError, TypeError):
            return
        out.append(Mutant(desc, clone))

    for pi, ei, el in _elements(data):
        kind = el.get("element")
        where = f"{data['programs'][pi]['name']}/{el.get('id', f'#{ei}')}"

        if kind == "interlock":
            perms = el.get("permissives", {})
            if isinstance(perms, dict) and isinstance(perms.get("all"), list) \
                    and len(perms["all"]) > 1:
                for i, perm in enumerate(perms["all"]):
                    spawn(f"{where}: permissive {perm!r} dropped",
                          lambda d, pi=pi, ei=ei, i=i:
                          d["programs"][pi]["logic"][ei]["permissives"]["all"]
                          .pop(i))

        elif kind == "alarm":
            if el.get("latching"):
                spawn(f"{where}: latching removed (alarm self-clears)",
                      lambda d, pi=pi, ei=ei:
                      d["programs"][pi]["logic"][ei].update(latching=False))
            if el.get("on_delay"):
                spawn(f"{where}: debounce removed",
                      lambda d, pi=pi, ei=ei:
                      d["programs"][pi]["logic"][ei].pop("on_delay"))
            spawn(f"{where}: alarm condition inverted",
                  lambda d, pi=pi, ei=ei:
                  d["programs"][pi]["logic"][ei].update(
                      condition={"not": d["programs"][pi]["logic"][ei]
                                 ["condition"]}))

        elif kind == "dual_channel":
            spawn(f"{where}: 1oo2 defeated (channel_b wired to channel_a)",
                  lambda d, pi=pi, ei=ei:
                  d["programs"][pi]["logic"][ei].update(
                      channel_b=d["programs"][pi]["logic"][ei]["channel_a"]))

        elif kind == "search_chain":
            if len(el.get("stations", [])) > 1:
                spawn(f"{where}: last station dropped from the walk",
                      lambda d, pi=pi, ei=ei:
                      d["programs"][pi]["logic"][ei]["stations"].pop())

        elif kind == "state_machine":
            for si, st in enumerate(el.get("states", [])):
                if len(st.get("transitions", [])) > 1:
                    spawn(f"{where}: transition dropped from state "
                          f"{st.get('name')}",
                          lambda d, pi=pi, ei=ei, si=si:
                          d["programs"][pi]["logic"][ei]["states"][si]
                          ["transitions"].pop())
                    break  # one per machine keeps the mutant count sane

        elif kind == "assign":
            spawn(f"{where}: assigned value inverted",
                  lambda d, pi=pi, ei=ei:
                  d["programs"][pi]["logic"][ei].update(
                      value={"not": d["programs"][pi]["logic"][ei]["value"]}))
    return out


def run_mutation(ir_path: str | Path, scenarios_path: str | Path,
                 ) -> tuple[list[Mutant], int]:
    """Returns (evaluated mutants, invalid_count)."""
    from ladder.ir.loader import load_ir_data
    from ladder.ir.model import Project
    from ladder.ir.validate import validate_project
    from ladder.patterns import expand_project
    from ladder.scenario import run_suite

    data = load_ir_data(ir_path)
    mutants = generate_mutants(data)
    invalid = 0
    for m in mutants:
        try:
            project = expand_project(Project.model_validate(m.data))
            res = validate_project(project)
            if not res.ok:
                raise ValueError(str(res.issues[0]))
        except Exception:  # noqa: BLE001 - not a valid program: not a mutant
            m.killed = None
            invalid += 1
            continue
        try:
            results = run_suite(project, scenarios_path)
            bad = [r for r in results if not r.passed]
            m.killed = bool(bad)
            m.detail = str(bad[0]) if bad else ""
        except Exception as e:  # noqa: BLE001 - a crash also kills
            m.killed = True
            m.detail = f"suite error: {e}"
    return mutants, invalid


def format_mutation(mutants: list[Mutant], invalid: int) -> str:
    valid = [m for m in mutants if m.killed is not None]
    killed = [m for m in valid if m.killed]
    survivors = [m for m in valid if not m.killed]
    lines = [f"mutation score: {len(killed)}/{len(valid)} mutants killed"
             + (f" ({invalid} invalid mutant(s) discarded)" if invalid else "")]
    for m in killed:
        lines.append(f"  [killed  ] {m.description}")
    for m in survivors:
        lines.append(f"  [SURVIVED] {m.description}")
        lines.append("             -> no scenario notices this fault; add one "
                     "that exercises it")
    if not survivors:
        lines.append("every injected fault was caught - the suite earns its "
                     "'definition of done' title")
    return "\n".join(lines)
