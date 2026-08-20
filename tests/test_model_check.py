"""SMV emission: structure, properties, scope guards - and nuXmv if present."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from ladder.ir.loader import load_project
from ladder.ir.lower import lower_project
from ladder.ir.model import Project
from ladder.model_check import ModelError, emit_project, emit_smv

EXAMPLE = Path(__file__).parent.parent / "examples" / "vacuum_interlock.yaml"


@pytest.fixture(scope="module")
def smv_texts(tmp_path_factory):
    project = load_project(EXAMPLE)
    out = tmp_path_factory.mktemp("smv")
    files, skipped = emit_project(project, out)
    assert not skipped
    return {f.stem: f.read_text() for f in files}


def test_both_programs_emitted(smv_texts):
    assert set(smv_texts) == {"SafetyPermissives", "PumpDown"}


def test_interlock_failsafe_property(smv_texts):
    text = smv_texts["SafetyPermissives"]
    assert "INVARSPEC (beam_shutter_permit -> (pressure_ok & gate_valve_closed));" in text
    # permit is a latch: state VAR with init FALSE
    assert "beam_shutter_permit : boolean;" in text
    assert "init(beam_shutter_permit) := FALSE;" in text


def test_timer_over_approximation(smv_texts):
    text = smv_texts["SafetyPermissives"]
    assert "IVAR ALM_vacuum_ton_choice : boolean;" in text
    assert "ALM_vacuum_ton_Q : boolean;" in text


def test_state_machine_domain(smv_texts):
    text = smv_texts["PumpDown"]
    assert "pumpdown_state : {0, 1, 2, 99};" in text
    assert "init(pumpdown_state) := 0;" in text


def test_free_inputs_declared(smv_texts):
    text = smv_texts["SafetyPermissives"]
    assert "pressure_ok : boolean;  -- free input" in text


def test_scale_program_is_skipped(tmp_path):
    p = Project.model_validate({
        "name": "P",
        "tags": [{"name": "raw", "type": "INT", "direction": "input"},
                 {"name": "eu", "type": "REAL", "direction": "output"}],
        "programs": [{"name": "M", "logic": [
            {"element": "scale", "id": "S1", "input": "raw", "output": "eu",
             "raw_max": 27648, "eu_max": 100.0}]}],
    })
    files, skipped = emit_project(p, tmp_path)
    assert not files and len(skipped) == 1 and "M" in skipped[0]


def test_raw_st_not_checkable():
    p = Project.model_validate({
        "name": "P", "tags": [{"name": "x", "type": "BOOL"}],
        "programs": [{"name": "M", "logic": [
            {"element": "st", "id": "raw", "code": "x := TRUE;"}]}],
    })
    lp = lower_project(p)["M"]
    with pytest.raises(ModelError, match="escape-hatch"):
        emit_smv(p, lp)


NUXMV = os.environ.get("NUXMV_BIN") or shutil.which("nuxmv") or shutil.which("nuXmv")


@pytest.mark.skipif(not NUXMV, reason="nuXmv not installed")
def test_nuxmv_proves_failsafe_properties(tmp_path):
    project = load_project(EXAMPLE)
    files, _ = emit_project(project, tmp_path)
    for f in files:
        proc = subprocess.run([NUXMV, "-dcx", str(f)],
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
        assert "is false" not in proc.stdout, f"{f.name}:\n{proc.stdout}"
