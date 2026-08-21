"""pid element: control behavior, anti-windup, enable freeze, backends."""

import pytest

from ladder.backends import get_backend
from ladder.ir.lower import lower_project
from ladder.ir.model import Project
from ladder.ir.validate import lint_project, validate_project
from ladder.sim import Simulator


def _project(**pid_over):
    pid = {
        "element": "pid", "id": "PID_t",
        "setpoint": "sp", "process_value": "pv", "output": "cv",
        "kp": 2.0, "ti": "T#5s", "interval": "T#100ms",
        "out_min": 0.0, "out_max": 100.0, "enable": "auto",
    }
    pid.update(pid_over)
    return Project.model_validate({
        "name": "Loop",
        "tags": [
            {"name": "sp", "type": "REAL"},
            {"name": "pv", "type": "REAL"},
            {"name": "cv", "type": "REAL", "direction": "output"},
            {"name": "auto", "type": "BOOL", "direction": "input"},
        ],
        "programs": [{"name": "Ctrl", "execution": "periodic",
                      "interval": "T#100ms", "logic": [pid]}],
    })


def test_validates_and_lints_clean():
    p = _project()
    assert validate_project(p).ok
    assert lint_project(p) == []


def test_w07_when_period_mismatches():
    p = _project()
    p.programs[0].execution = "cyclic"
    p.programs[0].interval = None
    assert any(w.code == "W07" for w in lint_project(p))


def test_closed_loop_converges_to_setpoint():
    sim = Simulator(_project())
    sim.set("auto", True)
    sim.set("sp", 50.0)
    pv = 0.0
    for _ in range(400):                       # 40 s of 100 ms scans
        sim.set("pv", pv)
        sim.scan(dt_ms=100)
        pv += (sim.get("cv") * 0.6 - pv) * 0.05   # first-order plant
    assert sim.get("pv") == pytest.approx(50.0, abs=1.0)


def test_output_clamps_and_integrator_does_not_wind_up():
    sim = Simulator(_project())
    sim.set("auto", True)
    sim.set("sp", 1000.0)                      # unreachable -> saturate
    sim.set("pv", 0.0)
    sim.run(5000, dt_ms=100)
    assert sim.get("cv") == 100.0              # clamped at out_max
    # anti-windup: on setpoint reversal the output must leave saturation
    # immediately, not after unwinding a huge integrator
    sim.set("sp", 0.0)
    sim.scan(dt_ms=100)
    assert sim.get("cv") < 100.0


def test_disable_freezes_output_and_state():
    sim = Simulator(_project())
    sim.set("auto", True)
    sim.set("sp", 50.0)
    sim.set("pv", 40.0)
    sim.run(1000, dt_ms=100)
    held = sim.get("cv")
    sim.set("auto", False)
    sim.set("sp", 90.0)                        # provocation while frozen
    sim.run(2000, dt_ms=100)
    assert sim.get("cv") == held


def test_p_only_form():
    sim = Simulator(_project(ti=None, enable=None))
    sim.set("sp", 10.0)
    sim.set("pv", 6.0)
    sim.scan(dt_ms=100)
    assert sim.get("cv") == pytest.approx(8.0)  # kp*(sp-pv) = 2*4


def test_validation_rejects_bool_output():
    with pytest.raises(Exception):
        p = _project(output="auto")
        validate_project(p).raise_if_failed()


def test_backends_declare_real_synth(tmp_path):
    p = _project(td="T#1s")
    lowered = lower_project(p)
    for name in ("siemens", "rockwell", "plcopen", "beckhoff", "iec"):
        get_backend(name).emit(p, lowered, tmp_path)
    iec = (tmp_path / "iec" / "Loop.st").read_text()
    assert "PID_t_i : REAL;" in iec and "PID_t_ep : REAL;" in iec
    l5x = (tmp_path / "rockwell" / "Loop.L5X").read_text()
    assert 'Name="PID_t_i" TagType="Base" DataType="REAL" Radix="Float"' in l5x


def test_model_checker_skips_pid_program(tmp_path):
    from ladder.model_check import emit_project

    files, skipped = emit_project(_project(), tmp_path)
    assert not files and skipped
