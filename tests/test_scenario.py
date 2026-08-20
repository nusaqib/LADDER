"""Scenario runner: step semantics and failure reporting."""

from pathlib import Path

import pytest
import yaml

from ladder.ir.loader import load_project
from ladder.scenario import ScenarioError, ScenarioSuite, run_scenario, run_suite

EXAMPLE = Path(__file__).parent.parent / "examples" / "vacuum_interlock.yaml"


def _suite(tmp_path, text):
    p = tmp_path / "s.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_passing_scenario(tmp_path):
    path = _suite(tmp_path, """
scenarios:
  - name: permit
    steps:
      - set: {pressure_ok: true, gate_valve_closed: true}
      - scan: {}
      - expect: {beam_shutter_permit: false}
      - pulse: reset_pb
      - expect: {beam_shutter_permit: true}
""")
    results = run_suite(load_project(EXAMPLE), path)
    assert all(r.passed for r in results)


def test_expect_failure_reports_step_and_time(tmp_path):
    path = _suite(tmp_path, """
scenarios:
  - name: wrong
    steps:
      - set: {pressure_ok: true, gate_valve_closed: true}
      - scan: {}
      - expect: {beam_shutter_permit: true}
""")
    r = run_suite(load_project(EXAMPLE), path)[0]
    assert not r.passed
    assert r.failure.index == 2
    assert "beam_shutter_permit is False, expected True" in r.failure.message
    assert "t=" in r.failure.message


def test_unknown_tag_is_error_not_crash(tmp_path):
    path = _suite(tmp_path, """
scenarios:
  - name: bad
    steps:
      - set: {no_such_tag: true}
""")
    r = run_suite(load_project(EXAMPLE), path)[0]
    assert not r.passed and "no_such_tag" in r.error


def test_malformed_suite(tmp_path):
    with pytest.raises(ScenarioError):
        ScenarioSuite.load(_suite(tmp_path, "scenarios: {oops: 1}"))
    with pytest.raises(ScenarioError):
        ScenarioSuite.load(_suite(tmp_path, "scenarios:\n  - steps: []"))


def test_unknown_step_kind(tmp_path):
    project = load_project(EXAMPLE)
    sc = yaml.safe_load("""
name: bad
steps:
  - frobnicate: {x: 1}
""")
    with pytest.raises(ScenarioError, match="unknown step"):
        run_scenario(project, sc)
