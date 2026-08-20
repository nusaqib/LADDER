"""Per-program language preference: V11 expressibility + IL rendering."""

from pathlib import Path

import pytest

from ladder.backends import get_backend
from ladder.ir.loader import load_project
from ladder.ir.lower import lower_project
from ladder.ir.model import Project
from ladder.ir.validate import lint_project, validate_project
from ladder.sim import Simulator

EXAMPLE = Path(__file__).parent.parent / "examples" / "languages_demo.yaml"


@pytest.fixture(scope="module")
def project():
    return load_project(EXAMPLE)


def test_example_validates_and_lints_clean(project):
    assert validate_project(project).ok
    assert lint_project(project) == []


def test_language_is_rendering_only_sim_unaffected(project):
    sim = Simulator(project)
    sim.set("estop_ok", True)
    sim.set("guard_closed", True)
    sim.set("motion_ok", True)
    sim.pulse("reset_pb")
    assert sim.get("run_permit") is True
    sim.set("start_pb", True)
    sim.scan()
    assert sim.get("motor_run") is True
    sim.set("start_pb", False)
    sim.run(3200, dt_ms=100)
    assert sim.get("warmed_up") is True          # IL program
    assert sim.get("fill_valve") is True         # SFC program reached filling


# ------------------------------------------------------------------- V11


def _codes(p):
    return {i.code for i in validate_project(p).issues}


def _demo(mutate):
    import yaml

    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    mutate(data)
    return Project.model_validate(data)


def test_state_machine_in_ladder_v11():
    def mutate(d):
        d["programs"][2]["language"] = "ladder"   # Sequence is a state machine
    assert "V11" in _codes(_demo(mutate))


def test_sfc_requires_single_state_machine_v11():
    def mutate(d):
        d["programs"][3]["language"] = "sfc"      # Runtime has assign+timer
    assert "V11" in _codes(_demo(mutate))


def test_raw_st_in_il_v11():
    def mutate(d):
        d["programs"][3]["logic"].append(
            {"element": "st", "id": "raw", "code": "motor_run := 0;"})
    assert "V11" in _codes(_demo(mutate))


def test_non_bool_assign_in_ladder_v11():
    def mutate(d):
        d["programs"][0]["logic"].append(
            {"element": "assign", "target": "seq_state", "value": "3"})
    assert "V11" in _codes(_demo(mutate))


def test_timer_elapsed_in_fbd_v11():
    def mutate(d):
        d["programs"][1]["logic"].append(
            {"element": "timer", "id": "T_x", "input": "motor_run",
             "preset": "T#1s", "elapsed": "seq_state"})
        d["programs"][1]["language"] = "fbd"
    assert "V11" in _codes(_demo(mutate))


# -------------------------------------------------------------------- IL


def test_iec_backend_renders_il(project, tmp_path):
    lowered = lower_project(project)
    get_backend("iec").emit(project, lowered, tmp_path)
    st = (tmp_path / "iec" / "LangDemo.st").read_text()
    # the IL program body: accumulator loads, no ST-syntax assignment
    runtime = st.split("PROGRAM Runtime")[1].split("END_PROGRAM")[0]
    assert "LD run_permit" in runtime
    assert "OR(" in runtime or "OR " in runtime
    assert "ST motor_run" in runtime
    assert ":= " not in runtime.split("CAL")[0]   # no ST assignments before the call
    assert "CAL T_warmup_t(IN := T_warmup_t_in, PT := T#3s)" in runtime
    assert "T_warmup_t_in : BOOL;" in runtime     # synthesized IL temporary
    # ladder/fbd/sfc programs fall back to ST in the textual backend, with a note
    assert "language 'ladder' has no IEC textual form" in st


def test_il_if_and_case_jumps():
    p = Project.model_validate({
        "name": "JumpDemo",
        "tags": [{"name": "sel", "type": "INT"},
                 {"name": "go", "type": "BOOL", "direction": "input"},
                 {"name": "out_a", "type": "BOOL", "direction": "output"},
                 {"name": "out_b", "type": "BOOL", "direction": "output"}],
        "programs": [{"name": "Main", "language": "il", "logic": [
            {"element": "interlock", "id": "IL1", "permissives": "go",
             "output": "out_a", "reset": {"signal": "go"}},
            {"element": "state_machine", "id": "SM1", "state_tag": "sel",
             "initial": "a",
             "states": [
                 {"name": "a", "do": [{"target": "out_b", "value": "TRUE"}],
                  "transitions": [{"when": "go", "goto": "b"}]},
                 {"name": "b", "transitions": [{"when": {"not": "go"}, "goto": "a"}]},
             ]}]}],
    })
    from ladder.backends.il import IlRenderer

    body = IlRenderer().body(lower_project(p)["Main"])
    assert "JMPCN" in body and "JMP " in body
    assert "EQ 0" in body and "EQ 1" in body      # CASE arms
    assert body.rstrip().splitlines()[-1].endswith(("TRUE", ":")) is True


def test_all_backends_emit_language_project(project, tmp_path):
    lowered = lower_project(project)
    for name in ("siemens", "rockwell", "plcopen", "beckhoff", "iec"):
        get_backend(name).emit(project, lowered, tmp_path)
