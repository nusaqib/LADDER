"""Rockwell reverse adoption: L5X -> IR, proved by behavioral round-trip."""

from pathlib import Path

import pytest
import yaml

from ladder.adopt import adopt_rockwell_l5x
from ladder.backends import get_backend
from ladder.ir.lower import lower_project
from ladder.ir.model import Project
from ladder.ir.validate import validate_project
from ladder.scenario import run_scenario

_IR = {
    "ir_version": "0.2",
    "name": "MotorRT",
    "tags": [
        {"name": "estop_ok", "type": "BOOL", "direction": "input"},
        {"name": "overload_ok", "type": "BOOL", "direction": "input"},
        {"name": "stop_ok", "type": "BOOL", "direction": "input"},
        {"name": "start_pb", "type": "BOOL", "direction": "input"},
        {"name": "reset_pb", "type": "BOOL", "direction": "input"},
        {"name": "ack_pb", "type": "BOOL", "direction": "input"},
        {"name": "run_permit", "type": "BOOL", "direction": "output"},
        {"name": "motor_run", "type": "BOOL", "direction": "output"},
        {"name": "overload_alarm", "type": "BOOL", "direction": "output"},
    ],
    "programs": [{
        "name": "MotorStation", "language": "ladder",
        "logic": [
            {"element": "interlock", "id": "IL_motor",
             "permissives": {"all": ["estop_ok", "overload_ok"]},
             "output": "run_permit", "reset": {"signal": "reset_pb"}},
            {"element": "assign", "target": "motor_run",
             "value": {"all": ["run_permit", "stop_ok",
                               {"any": ["start_pb", "motor_run"]}]}},
            {"element": "alarm", "id": "ALM_overload",
             "condition": {"not": "overload_ok"}, "on_delay": "T#1s",
             "latching": True, "ack": "ack_pb", "output": "overload_alarm"},
        ],
    }],
}

_SCENARIOS = yaml.safe_load("""
scenarios:
  - name: start_seal_stop
    steps:
      - set: {estop_ok: true, overload_ok: true, stop_ok: true}
      - pulse: reset_pb
      - expect: {run_permit: true}
      - pulse: start_pb
      - expect: {motor_run: true}
      - set: {stop_ok: false}
      - scan: {}
      - expect: {motor_run: false}
  - name: trip_needs_manual_reset
    steps:
      - set: {estop_ok: true, overload_ok: true, stop_ok: true}
      - pulse: reset_pb
      - set: {estop_ok: false}
      - scan: {}
      - expect: {run_permit: false}
      - set: {estop_ok: true}
      - scan: {}
      - expect: {run_permit: false}
      - pulse: reset_pb
      - expect: {run_permit: true}
  - name: overload_debounce_latch_ack
    steps:
      - set: {estop_ok: true, overload_ok: true, stop_ok: true}
      - scan: {}
      - set: {overload_ok: false}
      - run: {ms: 800, dt_ms: 100}
      - expect: {overload_alarm: false}
      - run: {ms: 400, dt_ms: 100}
      - expect: {overload_alarm: true}
      - set: {overload_ok: true}
      - scan: {}
      - expect: {overload_alarm: true}
      - pulse: ack_pb
      - expect: {overload_alarm: false}
""")["scenarios"]


def test_l5x_round_trip_preserves_behavior(tmp_path):
    """emit L5X -> adopt back -> the identical scenario suite passes on
    the adopted project. Behavior, not syntax, is the fidelity proof."""
    original = Project.model_validate(_IR)
    assert validate_project(original).ok
    for sc in _SCENARIOS:  # baseline: original passes
        assert run_scenario(original, sc).passed, sc["name"]

    files = get_backend("rockwell").emit(original, lower_project(original),
                                         tmp_path)
    l5x = next(f for f in files if str(f).endswith(".L5X"))

    result = adopt_rockwell_l5x(l5x)
    adopted = result.project
    assert not result.unsupported, result.unsupported
    assert validate_project(adopted).ok

    for sc in _SCENARIOS:
        res = run_scenario(adopted, sc)
        assert res.passed, f"{sc['name']}: {res}"


def test_adopted_shape(tmp_path):
    original = Project.model_validate(_IR)
    files = get_backend("rockwell").emit(original, lower_project(original),
                                         tmp_path)
    l5x = next(f for f in files if str(f).endswith(".L5X"))
    adopted = adopt_rockwell_l5x(l5x).project
    names = {t.name for t in adopted.tags}
    assert {"estop_ok", "run_permit", "motor_run"} <= names
    kinds = [el.element for el in adopted.programs[0].logic]
    assert "timer" in kinds and "assign" in kinds
    # the TON preset survived the trip
    timer = next(el for el in adopted.programs[0].logic
                 if el.element == "timer")
    assert timer.preset == "T#1000ms"
