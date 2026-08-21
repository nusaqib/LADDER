"""Declarative acceptance scenarios, executed by the simulator (M5).

A scenarios file is YAML:

    scenarios:
      - name: permit_requires_reset
        description: optional
        steps:
          - set: {pressure_ok: true, gate_valve_closed: true}
          - scan: {}                    # one scan; or {n: 5, dt_ms: 100}
          - expect: {beam_shutter_permit: false}
          - pulse: reset_pb             # one scan TRUE, one scan FALSE
          - run: {ms: 2000, dt_ms: 100} # advance simulated time
          - expect: {beam_shutter_permit: true}

Scenarios are how generated IR is *accepted*: `ladder generate` runs them
after validation, and benchmark tasks ship them as the ground truth. They
run in pure Python - no vendor tool, no PLC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ladder.ir.model import Project
from ladder.sim import SimError, Simulator


class ScenarioError(ValueError):
    """Malformed scenarios file."""


@dataclass
class StepFailure:
    index: int
    step: dict
    message: str

    def __str__(self) -> str:
        return f"step {self.index + 1} {self.step}: {self.message}"


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    failure: StepFailure | None = None
    error: str | None = None  # simulator/setup error rather than an expect miss

    def __str__(self) -> str:
        if self.passed:
            return f"PASS {self.name}"
        detail = self.error or str(self.failure)
        return f"FAIL {self.name} - {detail}"


@dataclass
class ScenarioSuite:
    scenarios: list[dict] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "ScenarioSuite":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("scenarios"), list):
            raise ScenarioError(f"{path}: expected a top-level 'scenarios' list")
        for sc in data["scenarios"]:
            if "name" not in sc or not isinstance(sc.get("steps"), list):
                raise ScenarioError(f"{path}: every scenario needs 'name' and 'steps'")
        return cls(data["scenarios"])


_STEP_KINDS = {"set", "pulse", "scan", "run", "expect", "model",
               "expect_near"}


def _step_kind(step: dict) -> tuple[str, Any]:
    if not isinstance(step, dict) or len(step) != 1:
        raise ScenarioError(f"step must be a single-key mapping, got {step!r}")
    kind, arg = next(iter(step.items()))
    if kind not in _STEP_KINDS:
        raise ScenarioError(f"unknown step {kind!r}; expected one of {sorted(_STEP_KINDS)}")
    return kind, arg


def run_scenario(project: Project, scenario: dict, on_raw: str = "error") -> ScenarioResult:
    name = scenario["name"]
    try:
        sim = Simulator(project, on_raw=on_raw)
    except SimError as e:
        return ScenarioResult(name, False, error=str(e))
    for i, step in enumerate(scenario["steps"]):
        kind, arg = _step_kind(step)
        try:
            if kind == "set":
                for tag, value in arg.items():
                    sim.set(tag, value)
            elif kind == "pulse":
                sim.pulse(arg)
            elif kind == "scan":
                sim.scan(dt_ms=(arg or {}).get("dt_ms", 10), n=(arg or {}).get("n", 1))
            elif kind == "run":
                sim.run(arg["ms"], dt_ms=arg.get("dt_ms", 10))
            elif kind == "model":
                from ladder.sim import FirstOrderProcess

                sim.attach_model(FirstOrderProcess(**arg))
            elif kind == "expect_near":
                for tag, spec in arg.items():
                    want = float(spec["value"])
                    tol = float(spec.get("tol", abs(want) * 0.05 or 0.1))
                    got = float(sim.get(tag))
                    if abs(got - want) > tol:
                        return ScenarioResult(name, False, StepFailure(
                            i, step, f"{tag} is {got:.4g}, expected "
                            f"{want:.4g} +/- {tol:.4g} (t={sim.time_ms}ms)"))
            elif kind == "expect":
                for tag, want in arg.items():
                    got = sim.get(tag)
                    if got != want:
                        return ScenarioResult(name, False, StepFailure(
                            i, step, f"{tag} is {got!r}, expected {want!r} "
                            f"(t={sim.time_ms}ms, scan {sim.scan_count})"))
        except (SimError, KeyError, TypeError) as e:
            return ScenarioResult(name, False, error=f"step {i + 1} {step}: {e}")
    return ScenarioResult(name, True)


def run_suite(project: Project, path: str | Path,
              on_raw: str = "error") -> list[ScenarioResult]:
    suite = ScenarioSuite.load(path)
    return [run_scenario(project, sc, on_raw=on_raw) for sc in suite.scenarios]


def junit_xml(results: list[ScenarioResult], suite_name: str) -> str:
    """Render scenario results as JUnit/xUnit XML so CI systems display
    each acceptance scenario as a test case (TcUnit's good idea)."""
    from xml.sax.saxutils import escape, quoteattr

    failures = sum(1 for r in results if not r.passed)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             f'<testsuite name={quoteattr(suite_name)} '
             f'tests="{len(results)}" failures="{failures}" errors="0">']
    for r in results:
        if r.passed:
            lines.append(f"  <testcase name={quoteattr(r.name)}/>")
        else:
            detail = r.error or str(r.failure)
            lines.append(f"  <testcase name={quoteattr(r.name)}>")
            lines.append(f"    <failure message={quoteattr(detail)}>"
                         f"{escape(detail)}</failure>")
            lines.append("  </testcase>")
    lines.append("</testsuite>")
    return "\n".join(lines) + "\n"
