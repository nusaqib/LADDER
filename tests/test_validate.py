import pytest

from ladder.ir.model import Project
from ladder.ir.validate import validate_project


def _project(**overrides):
    base = {
        "name": "P",
        "tags": [
            {"name": "sensor_a", "type": "BOOL", "direction": "input"},
            {"name": "permit", "type": "BOOL", "direction": "output"},
            {"name": "rst", "type": "BOOL", "direction": "input"},
        ],
        "programs": [{
            "name": "Main",
            "logic": [{
                "element": "interlock", "id": "IL1",
                "permissives": "sensor_a", "output": "permit",
                "reset": {"signal": "rst"},
            }],
        }],
    }
    base.update(overrides)
    return Project.model_validate(base)


def _codes(project):
    return {i.code for i in validate_project(project).issues}


def test_good_project_passes():
    assert validate_project(_project()).ok


def test_unknown_reference_v03():
    p = _project()
    p.programs[0].logic[0].permissives = "sensor_a AND ghost"
    assert "V03" in _codes(p)


def test_write_to_input_v04():
    p = _project()
    p.programs[0].logic[0].output = "sensor_a"
    assert "V04" in _codes(p)


def test_latching_needs_reset_v05():
    p = _project()
    p.programs[0].logic[0].reset = None
    assert "V05" in _codes(p)


def test_bad_identifier_v01():
    p = _project(tags=[
        {"name": "bad__name", "type": "BOOL", "direction": "input"},
        {"name": "permit", "type": "BOOL", "direction": "output"},
        {"name": "rst", "type": "BOOL", "direction": "input"},
        {"name": "sensor_a", "type": "BOOL", "direction": "input"},
    ])
    assert "V01" in _codes(p)


def test_reserved_word_v01():
    p = _project()
    p.tags[0].name = "CASE"
    assert "V01" in _codes(p)


def test_duplicate_names_v02():
    p = _project()
    p.tags.append(p.tags[0].model_copy())
    assert "V02" in _codes(p)


def test_state_machine_v07():
    p = Project.model_validate({
        "name": "P",
        "tags": [{"name": "st", "type": "INT"},
                 {"name": "go", "type": "BOOL", "direction": "input"}],
        "programs": [{
            "name": "Main",
            "logic": [{
                "element": "state_machine", "id": "SM1",
                "state_tag": "st", "initial": "NOWHERE",
                "states": [{"name": "IDLE",
                            "transitions": [{"when": "go", "goto": "MISSING"}]}],
            }],
        }],
    })
    assert "V07" in _codes(p)


def test_non_bool_interlock_output_v06():
    p = _project()
    p.tags[1].type = "INT"
    assert "V06" in _codes(p)
