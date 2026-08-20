"""Reverse adoption: real Export-TiaToSpec output (fixture exported from a
TIA V19 scratch project that was itself built from LADDER artifacts - a full
IR -> SCL -> TIA -> SimaticML -> IR round trip)."""

from pathlib import Path

import pytest

from ladder.adopt import adopt_siemens_spec
from ladder.ir.validate import validate_project

SPEC = Path(__file__).parent / "fixtures" / "siemens-spec"


@pytest.fixture(scope="module")
def adopted():
    return adopt_siemens_spec(SPEC)


def test_tags_adopted_with_direction(adopted):
    tags = {t.name: t for t in adopted.project.tags}
    assert len(tags) == 12
    assert tags["pressure_ok"].direction == "input"
    assert tags["pressure_ok"].address == "%I0.0"
    assert tags["beam_shutter_permit"].direction == "output"
    assert tags["pumpdown_state"].type == "INT"
    assert tags["at_vacuum"].direction == "memory"


def test_scl_blocks_lifted(adopted):
    names = {p.name for p in adopted.project.programs}
    assert {"SafetyPermissives", "PumpDown"} <= names
    lifted = {b.name: b.lifted for b in adopted.blocks}
    assert lifted["FB_SafetyPermissives"] and lifted["FB_PumpDown"]
    assert lifted.get("Main") is False  # LAD OB: inventoried, not lifted


def test_locals_from_interface(adopted):
    pump = next(p for p in adopted.project.programs if p.name == "PumpDown")
    locals_ = {t.name: t.type for t in pump.variables}
    assert locals_["stable_ok"] == "BOOL"
    assert locals_["T_stable_t"] == "TON_TIME"  # TIA's instance type, verbatim


def test_st_reconstruction(adopted):
    pump = next(p for p in adopted.project.programs if p.name == "PumpDown")
    code = pump.logic[0].code
    # timer call with parameters survived the tokenized round trip
    assert '#T_stable_t(IN := "pressure_ok",' in code
    assert "PT := T#10s);" in code
    assert "#stable_ok := #T_stable_t.Q;" in code
    # state machine CASE survived, including the explicit 99 code
    assert 'CASE "pumpdown_state" OF' in code
    assert "99:" in code and "END_CASE;" in code
    safety = next(p for p in adopted.project.programs if p.name == "SafetyPermissives")
    assert 'IF NOT ("pressure_ok" AND "gate_valve_closed") THEN' in safety.logic[0].code


def test_adopted_project_validates(adopted):
    # adopted IR must pass semantic validation (st elements are lenient)
    assert validate_project(adopted.project).ok


def test_structure_report(adopted):
    assert "| FB_PumpDown | FB | SCL | yes (st element) |" in adopted.report
    assert "Tags adopted: 12" in adopted.report
