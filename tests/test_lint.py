"""Non-fatal lint (W01-W05) and the prompt bundle."""

from pathlib import Path

from ladder.ir.loader import load_project
from ladder.ir.model import Project
from ladder.ir.validate import lint_project

EXAMPLES = Path(__file__).parent.parent / "examples"


def _codes(project):
    return {w.code for w in lint_project(project)}


def test_examples_are_lint_clean():
    assert _codes(load_project(EXAMPLES / "vacuum_interlock.yaml")) == set()
    assert _codes(load_project(EXAMPLES / "pump_skid.yaml")) == set()


def _base(**over):
    d = {
        "name": "P",
        "tags": [
            {"name": "sensor", "type": "BOOL", "direction": "input"},
            {"name": "permit", "type": "BOOL", "direction": "output"},
            {"name": "rst", "type": "BOOL", "direction": "input"},
        ],
        "programs": [{"name": "Main", "logic": [{
            "element": "interlock", "id": "IL1", "permissives": "sensor",
            "output": "permit", "reset": {"signal": "rst"}}]}],
    }
    d.update(over)
    return Project.model_validate(d)


def test_unwritten_output_w01():
    p = _base()
    p.tags.append(p.tags[1].model_copy(update={"name": "orphan_out"}))
    assert "W01" in _codes(p)


def test_multi_writer_w02():
    p = _base()
    p.programs.append(p.programs[0].model_copy(update={"name": "Second"}))
    assert "W02" in _codes(p)


def test_unread_input_w03():
    p = _base()
    p.tags.append(p.tags[0].model_copy(update={"name": "orphan_in"}))
    assert "W03" in _codes(p)


def test_raw_st_suppresses_usage_lint():
    p = _base()
    p.tags.append(p.tags[1].model_copy(update={"name": "orphan_out"}))
    p.programs[0].logic.append(Project.model_validate({
        "name": "T", "tags": [],
        "programs": [{"name": "M", "logic": [
            {"element": "st", "id": "raw", "code": "orphan_out := TRUE;"}]}],
    }).programs[0].logic[0])
    codes = _codes(p)
    assert "W01" not in codes and "W03" not in codes


def test_state_machine_w04_w05():
    p = Project.model_validate({
        "name": "P",
        "tags": [{"name": "st", "type": "INT"},
                 {"name": "go", "type": "BOOL", "direction": "input"}],
        "programs": [{"name": "Main", "logic": [{
            "element": "state_machine", "id": "SM1", "state_tag": "st",
            "initial": "A",
            "states": [
                {"name": "A", "transitions": [{"when": "go", "goto": "B"}]},
                {"name": "B"},                      # trap: no outgoing
                {"name": "C", "transitions": [{"when": "go", "goto": "A"}]},  # unreachable
            ]}]}],
    })
    codes = _codes(p)
    assert "W04" in codes and "W05" in codes


def test_prompt_bundle():
    from ladder.promptgen import build_prompt

    text = build_prompt("A conveyor with a jam alarm.")
    assert "JSON Schema" in text and '"ir_version"' in text
    assert "motor_starter" in text and "valve_with_feedback" in text
    assert "A conveyor with a jam alarm." in text
    assert "1 = OK / healthy / closed" in text
