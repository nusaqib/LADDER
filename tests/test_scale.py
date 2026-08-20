"""Scale element: lowering, per-dialect conversion, simulation, lint W06."""

import pytest

from ladder.backends import get_backend
from ladder.backends.dialects import (
    Iec61131Dialect,
    RenderContext,
    RockwellStDialect,
    SiemensSclDialect,
)
from ladder.ir.lower import lower_project
from ladder.ir.model import Project
from ladder.ir.validate import lint_project, validate_project
from ladder.sim import Simulator


def _project(**scale_over):
    scale = {
        "element": "scale", "id": "SC_level",
        "input": "level_raw", "output": "level_pct",
        "raw_min": 0, "raw_max": 27648, "eu_min": 0.0, "eu_max": 100.0,
    }
    scale.update(scale_over)
    return Project.model_validate({
        "name": "P",
        "tags": [
            {"name": "level_raw", "type": "INT", "direction": "input",
             "comment": "ADC counts"},
            {"name": "level_pct", "type": "REAL", "direction": "output"},
        ],
        "programs": [{"name": "Main", "logic": [scale]}],
    })


def test_validates_and_lints_clean():
    p = _project()
    assert validate_project(p).ok
    assert lint_project(p) == []


def test_output_must_be_real():
    p = _project()
    p.tags[1].type = "INT"
    assert "V06" in {i.code for i in validate_project(p).issues}


def test_raw_span_must_be_nonzero():
    with pytest.raises(Exception, match="raw_max"):
        _project(raw_max=0)


def test_simulated_scaling_and_clamp():
    sim = Simulator(_project())
    sim.set("level_raw", 13824)  # half scale
    sim.scan()
    assert sim.get("level_pct") == pytest.approx(50.0)
    sim.set("level_raw", 30000)  # over-range -> clamped
    sim.scan()
    assert sim.get("level_pct") == 100.0
    sim.set("level_raw", -5)
    sim.scan()
    assert sim.get("level_pct") == 0.0


def test_no_clamp():
    sim = Simulator(_project(clamp=False))
    sim.set("level_raw", 30000)
    sim.scan()
    assert sim.get("level_pct") > 100.0


def test_offset_range():
    # 4-20 mA style: raw 5530..27648 -> 0..250.0
    sim = Simulator(_project(raw_min=5530, raw_max=27648, eu_max=250.0))
    sim.set("level_raw", 5530)
    sim.scan()
    assert sim.get("level_pct") == pytest.approx(0.0)
    sim.set("level_raw", 27648)
    sim.scan()
    assert sim.get("level_pct") == pytest.approx(250.0)


def test_dialect_conversion_rendering():
    p = _project()
    lp = lower_project(p)["Main"]
    ctx = RenderContext.for_program(lp)
    siemens = SiemensSclDialect().body(lp)
    assert 'INT_TO_REAL("level_raw")' in siemens
    iec = Iec61131Dialect().body(lp)
    assert "INT_TO_REAL(level_raw)" in iec
    rockwell = RockwellStDialect().body(lp)
    assert "INT_TO_REAL" not in rockwell  # Logix converts implicitly
    assert "(level_raw) *" in rockwell
    del ctx


def test_builds_on_all_backends(tmp_path):
    from ladder.backends import registry

    p = _project()
    lowered = lower_project(p)
    for name in sorted(registry):
        assert get_backend(name).emit(p, lowered, tmp_path)


def test_w06_multiple_writers_same_program():
    p = _project()
    p.programs[0].logic.append(Project.model_validate({
        "name": "T",
        "tags": [{"name": "level_pct", "type": "REAL", "direction": "output"}],
        "programs": [{"name": "M", "logic": [
            {"element": "assign", "target": "level_pct", "value": "0.0"}]}],
    }).programs[0].logic[0])
    warns = {w.code for w in lint_project(p)}
    assert "W06" in warns
