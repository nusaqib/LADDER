"""Pattern invocation: expansion, validation, and simulated behavior."""

from pathlib import Path

import pytest

from ladder.ir.loader import load_project
from ladder.ir.model import PatternEl, Project
from ladder.ir.validate import validate_project
from ladder.patterns import PatternError, expand_project
from ladder.sim import Simulator

EXAMPLE = Path(__file__).parent.parent / "examples" / "pump_skid.yaml"


def test_expansion_replaces_pattern_elements():
    project = load_project(EXAMPLE)  # expands by default
    els = project.programs[0].logic
    assert not any(isinstance(e, PatternEl) for e in els)
    assert {e.element for e in els} == {"assign", "alarm"}
    assert validate_project(project).ok


def test_unexpanded_pattern_fails_v09():
    project = load_project(EXAMPLE, expand=False)
    codes = {i.code for i in validate_project(project).issues}
    assert "V09" in codes


def _one_pattern_project(ref: str, params: dict) -> Project:
    return Project.model_validate({
        "name": "P",
        "tags": [{"name": "x", "type": "BOOL", "direction": "input"},
                 {"name": "y", "type": "BOOL", "direction": "output"}],
        "programs": [{"name": "Main", "logic": [
            {"element": "pattern", "id": "p1", "ref": ref, "params": params}]}],
    })


def test_unknown_pattern():
    with pytest.raises(PatternError, match="unknown pattern"):
        expand_project(_one_pattern_project("no_such_pattern", {}))


def test_bad_params():
    with pytest.raises(PatternError, match="bad params"):
        expand_project(_one_pattern_project("motor_starter", {"start": "x"}))


# ------------------------------------------------------- simulated behavior


@pytest.fixture
def sim():
    s = Simulator(load_project(EXAMPLE))
    s.set("stop_ok", True)
    s.set("motor_fault_ok", True)
    s.set("valve_closed_fb", True)
    s.scan()
    return s


def test_seal_in_starter(sim):
    assert sim.get("pump_run") is False
    sim.pulse("start_pb")  # momentary press
    assert sim.get("pump_run") is True  # sealed in
    sim.set("stop_ok", False)
    sim.scan()
    assert sim.get("pump_run") is False


def test_valve_mismatch_alarm(sim):
    sim.pulse("start_pb")
    assert sim.get("valve_open_cmd") is True
    # valve never reaches open limit -> mismatch after travel time (3 s)
    sim.set("valve_closed_fb", False)
    sim.run(2800, dt_ms=100)
    assert sim.get("valve_alarm") is False
    sim.run(400, dt_ms=100)
    assert sim.get("valve_alarm") is True
    # valve finally opens; latched alarm clears on ack only
    sim.set("valve_open_fb", True)
    sim.run(300, dt_ms=100)
    assert sim.get("valve_alarm") is True
    sim.pulse("ack_pb")
    assert sim.get("valve_alarm") is False


def test_pattern_example_builds_everywhere(tmp_path):
    from ladder.backends import get_backend, registry
    from ladder.ir.lower import lower_project

    project = load_project(EXAMPLE)
    lowered = lower_project(project)
    for name in sorted(registry):
        files = get_backend(name).emit(project, lowered, tmp_path)
        assert files
