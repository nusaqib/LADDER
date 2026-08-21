"""Counterexample replay: nuXmv traces -> runnable failing scenarios.

When `ladder verify -t smv` finds a violated theorem, the raw nuXmv
trace is expert-hostile. This module converts it into a scenario file
for our own simulator: each trace transition becomes `set` (the free
inputs) + `scan`, and the final state's property variables become an
`expect`. **The replay scenario PASSES when the violation reproduces
concretely** - it pins the counterexample as an executable artifact you
can step through, show a reviewer, and keep as a regression once the
design is fixed (inverting the expectation).

Caveat (stated in the generated file): the model over-approximates
timers, so a counterexample that rides on a timer edge may not
reproduce under the simulator's real presets - such a replay failing is
informative, not a bug.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ladder.ir.lower import LoweredProgram
from ladder.ir.model import Project
from ladder.model_check import _all_refs, _read_roots, _var, _written_vars

_STATE = re.compile(r"->\s*State:\s*\d+\.(\d+)\s*<-")
_ASSIGN = re.compile(r"^\s*([A-Za-z_][\w]*)\s*=\s*(\S+)\s*$")
_FALSE_SPEC = re.compile(r"--\s*invariant\s+(.*?)\s+is false")
_IDENT = re.compile(r"[A-Za-z_]\w*")


@dataclass
class Trace:
    spec: str
    states: list[dict[str, object]] = field(default_factory=list)


def _value(tok: str):
    if tok == "TRUE":
        return True
    if tok == "FALSE":
        return False
    try:
        return int(tok)
    except ValueError:
        return tok


def parse_nuxmv_output(text: str) -> list[Trace]:
    """Extract every falsified invariant and its (cumulative) state trace."""
    traces: list[Trace] = []
    current: Trace | None = None
    state: dict[str, object] | None = None
    in_input = False
    for line in text.splitlines():
        m = _FALSE_SPEC.search(line)
        if m:
            current = Trace(spec=m.group(1))
            traces.append(current)
            state = None
            continue
        if current is None:
            continue
        if _STATE.search(line):
            # nuXmv prints only CHANGED values after the first state
            state = dict(current.states[-1]) if current.states else {}
            current.states.append(state)
            in_input = False
            continue
        if "-> Input:" in line:
            in_input = True  # IVAR choices (timer nondeterminism) - ignored
            continue
        m = _ASSIGN.match(line)
        if m and state is not None and not in_input:
            state[m.group(1)] = _value(m.group(2))
    return [t for t in traces if t.states]


def _flat_to_dotted(lp: LoweredProgram) -> dict[str, str]:
    return {_var(r.path): ".".join(r.path) for r in _all_refs(lp.statements)}


def trace_to_scenario(project: Project, lp: LoweredProgram, trace: Trace,
                      name: str) -> dict:
    """One nuXmv trace -> one scenario dict (our scenario schema)."""
    written = _written_vars(lp.statements)
    inputs = sorted(r for r in _read_roots(lp.statements) - written
                    if not r.endswith("_Q"))
    dotted = _flat_to_dotted(lp)

    steps: list[dict] = []
    prev_inputs: dict[str, object] = {}
    for k, state in enumerate(trace.states):
        if k == 0:
            continue  # initial state: inputs there don't drive a transition
        setting = {dotted.get(v, v): state[v] for v in inputs
                   if v in state and state[v] != prev_inputs.get(v)}
        prev_inputs.update({v: state[v] for v in inputs if v in state})
        if setting:
            steps.append({"set": setting})
        steps.append({"scan": {}})

    final = trace.states[-1]
    spec_vars = [v for v in _IDENT.findall(trace.spec)
                 if v in written and v in final]
    expect = {dotted.get(v, v): final[v] for v in sorted(set(spec_vars))}
    if expect:
        steps.append({"expect": expect})
    return {"name": name, "steps": steps}


def replay_suite(project: Project, lp: LoweredProgram,
                 traces: list[Trace]) -> str:
    """Render the replay scenario YAML (with the honest header)."""
    import yaml

    scenarios = [trace_to_scenario(project, lp, t, f"replay_violation_{i + 1}")
                 for i, t in enumerate(traces)]
    header = (
        "# GENERATED counterexample replay - ladder verify -t smv.\n"
        "# Each scenario re-drives a nuXmv counterexample through the\n"
        "# scan-accurate simulator. A PASS here means the violation is\n"
        "# CONCRETE - step through it, fix the design, then invert the\n"
        "# final expect to keep it as a regression. A FAIL usually means\n"
        "# the counterexample rides on the timer over-approximation\n"
        "# (a timing the real presets don't produce).\n")
    for i, t in enumerate(traces):
        header += f"# violation {i + 1}: {t.spec}\n"
    return header + yaml.safe_dump({"scenarios": scenarios}, sort_keys=False)
