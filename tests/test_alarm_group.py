"""alarm_group element: validation, annunciator semantics, backends."""

from pathlib import Path

import pytest

from ladder.backends import get_backend
from ladder.ir.loader import load_project
from ladder.ir.lower import lower_project
from ladder.ir.model import Project
from ladder.ir.validate import lint_project, validate_project
from ladder.scenario import run_suite

EXAMPLE = Path(__file__).parent.parent / "examples" / "annunciator.yaml"
SCENARIOS = Path(__file__).parent.parent / "examples" / "annunciator.scenarios.yaml"


@pytest.fixture(scope="module")
def project():
    return load_project(EXAMPLE)


def test_example_validates_and_lints_clean(project):
    assert validate_project(project).ok
    assert lint_project(project) == []


def test_scenarios_pass(project):
    results = run_suite(project, SCENARIOS)
    assert len(results) == 5
    failed = [str(r) for r in results if not r.passed]
    assert not failed, "\n".join(failed)


# ------------------------------------------------------------- validation


def _mutated(mutate):
    import yaml

    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    mutate(data)
    return Project.model_validate(data)


def _codes(p):
    return {i.code for i in validate_project(p).issues}


def _group(d):
    return d["programs"][0]["logic"][0]


def test_duplicate_member_name_v02():
    p = _mutated(lambda d: _group(d)["alarms"].append(
        {"name": "overtemp", "condition": "TRUE"}))
    assert "V02" in _codes(p)


def test_unknown_condition_ref_v03():
    p = _mutated(lambda d: _group(d)["alarms"].append(
        {"name": "ghost", "condition": "nonexistent_tag"}))
    assert "V03" in _codes(p)


def test_first_out_must_be_int_v06():
    def mutate(d):
        _group(d)["first_out"] = "horn"
    assert "V06" in _codes(_mutated(mutate))


def test_active_must_be_bool_v06():
    def mutate(d):
        _group(d)["active"] = "first_out_code"
    assert "V06" in _codes(_mutated(mutate))


def test_write_to_input_v04():
    def mutate(d):
        _group(d)["active"] = "flow_ok"
    assert "V04" in _codes(_mutated(mutate))


def test_bad_on_delay_rejected():
    with pytest.raises(ValueError):
        _mutated(lambda d: _group(d)["alarms"][0].update({"on_delay": "2 seconds"}))


# --------------------------------------------------------------- backends


def test_backends_emit(project, tmp_path):
    lowered = lower_project(project)
    for name in ("siemens", "rockwell", "plcopen", "beckhoff", "iec"):
        get_backend(name).emit(project, lowered, tmp_path)
    scl = (tmp_path / "siemens" / "FB_AlarmPanel.scl").read_text()
    assert "GRP_panel_no_flow_ton" in scl          # delayed member timer
    assert "first_out codes: 0=none, 1=no_flow" in scl
    st = (tmp_path / "iec" / "Annunciator.st").read_text()
    assert "GRP_panel_overtemp_lat" in st


def test_lowering_is_deterministic(project):
    a = lower_project(project)["AlarmPanel"]
    b = lower_project(project)["AlarmPanel"]
    assert [s.name for s in a.synth] == [s.name for s in b.synth]
    assert len(a.statements) == len(b.statements)
