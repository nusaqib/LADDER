"""IEC 61131-3 backend: strict ed.2 output for vendor-free verification."""

from pathlib import Path

import pytest

from ladder.backends import get_backend
from ladder.ir.loader import load_project
from ladder.ir.lower import lower_project

EXAMPLE = Path(__file__).parent.parent / "examples" / "vacuum_interlock.yaml"


@pytest.fixture(scope="module")
def st_text(tmp_path_factory):
    project = load_project(EXAMPLE)
    out = tmp_path_factory.mktemp("iec")
    files = get_backend("iec").emit(project, lower_project(project), out)
    return files[0].read_text()


def test_pous_and_configuration(st_text):
    assert "PROGRAM SafetyPermissives" in st_text
    assert "PROGRAM PumpDown" in st_text
    assert "CONFIGURATION Config" in st_text
    assert "TASK MainTask(INTERVAL := T#20ms, PRIORITY := 1);" in st_text
    assert "PROGRAM inst_PumpDown WITH MainTask : PumpDown;" in st_text


def test_var_external_declared(st_text):
    # globals referenced by the POU must be VAR_EXTERNAL (strict IEC / matiec)
    body = st_text.split("PROGRAM SafetyPermissives", 1)[1].split("END_PROGRAM")[0]
    assert "VAR_EXTERNAL" in body
    assert "pressure_ok : BOOL;" in body
    # tag not referenced by this program is not declared external here
    assert "at_vacuum" not in body


def test_globals_in_resource(st_text):
    cfg = st_text.split("CONFIGURATION", 1)[1]
    assert "VAR_GLOBAL" in cfg and "pumpdown_state : INT;" in cfg


def test_strict_comments_only(st_text):
    # matiec is edition-2 strict: // comments are a syntax error
    for line in st_text.splitlines():
        assert not line.strip().startswith("//"), line
    assert "(* interlock IL_shutter" in st_text


def test_ascii_only(st_text):
    st_text.encode("ascii")
