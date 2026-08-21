"""dual_channel + search_chain: semantics, validation, model checking."""

import pytest

from ladder.ir.lower import lower_project
from ladder.ir.model import Project
from ladder.ir.validate import validate_project
from ladder.model_check import emit_smv
from ladder.sim import Simulator


def _project(**over):
    d = {
        "name": "SafetyDemo",
        "types": [
            {"name": "SafeInput", "members": [
                {"name": "Eval_OK"}, {"name": "Latched"}]},
        ],
        "tags": [
            {"name": "k1a", "type": "BOOL", "direction": "input"},
            {"name": "k1b", "type": "BOOL", "direction": "input"},
            {"name": "k2a", "type": "BOOL", "direction": "input"},
            {"name": "k2b", "type": "BOOL", "direction": "input"},
            {"name": "door_ok", "type": "BOOL", "direction": "input"},
            {"name": "area_reset", "type": "BOOL", "direction": "input"},
            {"name": "key1", "type": "SafeInput"},
            {"name": "key2", "type": "SafeInput"},
            {"name": "inputs_ok", "type": "BOOL", "direction": "output"},
            {"name": "search_done", "type": "BOOL", "direction": "output"},
            {"name": "k1_flt", "type": "BOOL", "direction": "output"},
            {"name": "k1_ackreq", "type": "BOOL", "direction": "output"},
        ],
        "programs": [{"name": "Safety", "logic": [
            {"element": "dual_channel", "id": "DC_k1",
             "channel_a": "k1a", "channel_b": "k1b",
             "output": "key1.Eval_OK", "discrepancy_time": "T#500ms",
             "fault": "k1_flt", "ack": "area_reset",
             "ack_required": "k1_ackreq"},
            {"element": "dual_channel", "id": "DC_k2",
             "channel_a": "k2a", "channel_b": "k2b",
             "output": "key2.Eval_OK"},
            {"element": "assign", "target": "inputs_ok", "value": "door_ok"},
            {"element": "search_chain", "id": "SRCH",
             "precondition": "inputs_ok",
             "stations": [
                 {"name": "S1", "key": "key1.Eval_OK", "latched": "key1.Latched"},
                 {"name": "S2", "key": "key2.Eval_OK", "latched": "key2.Latched"},
             ],
             "complete": "search_done"},
        ]}],
    }
    d.update(over)
    return Project.model_validate(d)


@pytest.fixture(scope="module")
def project():
    p = _project()
    assert validate_project(p).ok
    return p


def _armed(sim):
    sim.set("door_ok", True)
    for t in ("k1a", "k1b", "k2a", "k2b"):
        sim.set(t, False)
    sim.scan()


def _turn_key(sim, a, b, on=True):
    sim.set(a, on)
    sim.set(b, on)
    sim.scan()


def test_walk_order_completes(project):
    sim = Simulator(project)
    _armed(sim)
    _turn_key(sim, "k1a", "k1b")
    assert sim.get("key1.Latched") is True
    _turn_key(sim, "k1a", "k1b", on=False)          # key released: latch holds
    assert sim.get("key1.Latched") is True
    _turn_key(sim, "k2a", "k2b")
    assert sim.get("search_done") is True


def test_out_of_order_key_does_not_latch(project):
    sim = Simulator(project)
    _armed(sim)
    _turn_key(sim, "k2a", "k2b")                    # station 2 before station 1
    assert sim.get("key2.Latched") is False
    assert sim.get("search_done") is False


def test_held_key_does_not_ride_the_chain(project):
    sim = Simulator(project)
    _armed(sim)
    _turn_key(sim, "k2a", "k2b")                    # key 2 held early...
    _turn_key(sim, "k1a", "k1b")                    # ...then station 1 latches
    sim.scan(n=3)
    assert sim.get("key2.Latched") is False         # no rising edge -> no ride
    _turn_key(sim, "k2a", "k2b", on=False)
    _turn_key(sim, "k2a", "k2b")                    # re-turn: genuine edge
    assert sim.get("search_done") is True


def test_breach_cascades_within_one_scan(project):
    sim = Simulator(project)
    _armed(sim)
    _turn_key(sim, "k1a", "k1b")
    _turn_key(sim, "k2a", "k2b")
    assert sim.get("search_done") is True
    sim.set("door_ok", False)                       # breach
    sim.scan()
    assert sim.get("key1.Latched") is False
    assert sim.get("key2.Latched") is False
    assert sim.get("search_done") is False
    sim.set("door_ok", True)                        # healing does NOT restore
    sim.scan(n=2)
    assert sim.get("search_done") is False


def test_discrepancy_latches_and_acks(project):
    sim = Simulator(project)
    _armed(sim)
    sim.set("k1a", True)                            # single channel only
    sim.run(600, dt_ms=50)
    assert sim.get("k1_flt") is True
    assert sim.get("key1.Eval_OK") is False
    sim.set("k1b", True)                            # both channels OK again
    sim.scan()
    assert sim.get("key1.Eval_OK") is False         # fault still latched
    assert sim.get("k1_ackreq") is True
    sim.pulse("area_reset")
    assert sim.get("k1_flt") is False
    sim.scan()
    assert sim.get("key1.Eval_OK") is True


def test_brief_disagreement_inside_window_is_tolerated(project):
    sim = Simulator(project)
    _armed(sim)
    sim.set("k1a", True)
    sim.run(300, dt_ms=50)                          # inside 500ms window
    sim.set("k1b", True)
    sim.scan()
    assert sim.get("k1_flt") is False
    assert sim.get("key1.Eval_OK") is True


# ------------------------------------------------------------- validation


def _codes(p):
    return {i.code for i in validate_project(p).issues}


def test_discrepancy_requires_ack_v05():
    p = _project()
    p.programs[0].logic[0].ack = None
    assert "V05" in _codes(p)


def test_fault_without_discrepancy_time_v05():
    p = _project()
    p.programs[0].logic[1].fault = "k1_flt"
    assert "V05" in _codes(p)


def test_duplicate_station_v02():
    p = _project()
    p.programs[0].logic[3].stations[1].name = "S1"
    assert "V02" in _codes(p)


def test_complete_must_be_bool_v06():
    d_extra = {"name": "n", "type": "INT"}
    p = _project()
    p.tags.append(type(p.tags[0]).model_validate(d_extra))
    p.programs[0].logic[3].complete = "n"
    assert "V06" in _codes(p)


# ----------------------------------------------------- model checking


def test_smv_with_udt_members_and_theorems(project):
    lp = lower_project(project)["Safety"]
    smv = emit_smv(project, lp)
    assert "key1_Latched : boolean;" in smv         # UDT member flattened
    assert "INVARSPEC (key1_Eval_OK -> (k1a & k1b));" in smv
    assert "INVARSPEC (search_done -> inputs_ok);" in smv
    assert "INVARSPEC (key2_Latched -> key1_Latched);" in smv


def test_nuxmv_proves_search_chain(project, tmp_path):
    import os
    import shutil
    import subprocess

    bin_ = os.environ.get("NUXMV_BIN") or shutil.which("nuXmv") or shutil.which("nuxmv")
    if not bin_:
        pytest.skip("nuXmv not available")
    lp = lower_project(project)["Safety"]
    f = tmp_path / "safety.smv"
    f.write_text(emit_smv(project, lp), encoding="ascii")
    out = subprocess.run([bin_, "-dcx", str(f)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "is false" not in out.stdout
    assert out.stdout.count("is true") >= 4
