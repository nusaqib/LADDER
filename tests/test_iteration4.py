"""Plant models in scenarios, the sim REPL, and semantic diff."""

from pathlib import Path

import pytest

from ladder.cli import main
from ladder.ir.model import Project
from ladder.scenario import run_scenario


def _pid_project() -> Project:
    return Project.model_validate({
        "name": "Heater",
        "tags": [
            {"name": "sp", "type": "REAL", "initial": 60.0},
            {"name": "pv", "type": "REAL", "direction": "input"},
            {"name": "u", "type": "REAL", "direction": "output"},
            {"name": "enable", "type": "BOOL", "direction": "input"},
        ],
        "programs": [{"name": "Trim", "logic": [
            {"element": "pid", "id": "PID_heat", "setpoint": "sp",
             "process_value": "pv", "output": "u", "kp": 2.0,
             "ti": "T#5s", "interval": "T#100ms",
             "out_min": 0.0, "out_max": 100.0, "enable": "enable"},
        ]}],
    })


def test_closed_loop_scenario_with_plant_model():
    """The `model:` step closes the loop: PID drives a first-order plant
    to the setpoint, asserted with expect_near - all in YAML."""
    scenario = {
        "name": "pid_reaches_setpoint",
        "steps": [
            {"model": {"input": "u", "output": "pv",
                       "gain": 1.0, "tau_ms": 2000.0, "ambient": 20.0}},
            {"set": {"enable": True}},
            {"run": {"ms": 60000, "dt_ms": 100}},
            {"expect_near": {"pv": {"value": 60.0, "tol": 3.0}}},
        ],
    }
    res = run_scenario(_pid_project(), scenario)
    assert res.passed, str(res)


def test_expect_near_fails_outside_tolerance():
    scenario = {
        "name": "wrong_setpoint",
        "steps": [
            {"model": {"input": "u", "output": "pv", "gain": 1.0,
                       "tau_ms": 2000.0, "ambient": 20.0}},
            {"run": {"ms": 5000, "dt_ms": 100}},   # PID disabled: pv ~ 20
            {"expect_near": {"pv": {"value": 60.0, "tol": 3.0}}},
        ],
    }
    res = run_scenario(_pid_project(), scenario)
    assert not res.passed and "expected 60" in str(res)


def test_repl_session(tmp_path):
    from ladder.repl import run_repl
    from ladder.scaffold import init_project
    from ladder.ir.loader import load_project
    from ladder.scaffold import load_manifest

    root = tmp_path / "p"
    init_project(root, name="P")
    manifest, _ = load_manifest(root)
    project = load_project(root / manifest.ir)

    script = iter([
        "help", "set estop_ok true", "set overload_ok true",
        "set stop_ok true", "pulse reset_pb",
        "watch motor_run run_permit", "pulse start_pb",
        "get motor_run", "state", "quit",
    ])
    lines: list[str] = []
    rc = run_repl(project, input_fn=lambda _: next(script),
                  print_fn=lines.append)
    assert rc == 0
    text = "\n".join(lines)
    assert "commands:" in text
    assert "motor_run=True" in text          # watch output after start
    assert "motor_run = True" in text        # get + state agree


def test_semantic_diff(tmp_path):
    old = tmp_path / "old.yaml"
    new = tmp_path / "new.yaml"
    old.write_text("""\
ir_version: "0.2"
name: P
tags:
  - {name: a, type: BOOL, direction: input}
  - {name: b, type: BOOL, direction: input}
  - {name: y, type: BOOL, direction: output}
programs:
  - name: M
    logic:
      - {element: interlock, id: IL, permissives: {all: [a, b]},
         output: y, reset: {signal: a}}
""", encoding="utf-8")
    new.write_text("""\
ir_version: "0.2"
name: P
tags:
  - {name: a, type: BOOL, direction: input}
  - {name: c, type: BOOL, direction: input}
  - {name: y, type: BOOL, direction: output}
programs:
  - name: M
    logic:
      - {element: interlock, id: IL, permissives: {all: [a, c]},
         output: y, reset: {signal: a}}
      - {element: assign, id: A2, target: y, value: a}
""", encoding="utf-8")
    from ladder.irdiff import diff_ir

    lines = diff_ir(old, new)
    text = "\n".join(lines)
    assert "- tag b removed" in text
    assert "+ tag c added" in text
    assert "permissives DROPPED b" in text
    assert "permissives gained c" in text
    assert "M/A2 added (assign)" in text
    assert main(["diff", str(old), str(new)]) == 0
