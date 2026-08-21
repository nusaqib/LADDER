"""User-supplied invariants appended to the emitted SMV models."""

import pytest

from ladder.ir.lower import lower_project
from ladder.ir.model import Project
from ladder.model_check import ModelError, emit_smv, load_properties


def _project():
    return Project.model_validate({
        "name": "SafetyDemo",
        "types": [{"name": "SafeInput",
                   "members": [{"name": "Eval_OK"}, {"name": "Latched"}]}],
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
        ],
        "programs": [{"name": "Safety", "logic": [
            {"element": "dual_channel", "id": "DC_k1",
             "channel_a": "k1a", "channel_b": "k1b",
             "output": "key1.Eval_OK", "discrepancy_time": "T#500ms",
             "fault": "k1_flt", "ack": "area_reset"},
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
    })


def _props_file(tmp_path, text):
    f = tmp_path / "props.yaml"
    f.write_text(text, encoding="utf-8")
    return f


def test_properties_appended_and_flattened(tmp_path):
    f = _props_file(tmp_path, """\
properties:
  - program: Safety
    description: a completed search implies station 1
    given: search_done
    always: key1.Latched
  - program: Safety
    always: NOT (k1_flt AND key1.Eval_OK)
""")
    props = load_properties(f)
    p = _project()
    smv = emit_smv(p, lower_project(p)["Safety"], props["Safety"])
    assert "-- user property: a completed search implies station 1" in smv
    assert "INVARSPEC ((search_done) -> (key1_Latched));" in smv
    assert "INVARSPEC ((!(k1_flt & key1_Eval_OK)));" in smv


def test_pattern_sugar_desugars(tmp_path):
    f = _props_file(tmp_path, """\
properties:
  - program: Safety
    never: k1_flt AND key1.Eval_OK
  - program: Safety
    mutex: [inputs_ok, k1_flt]
  - program: Safety
    if: search_done
    then: key1.Latched
""")
    props = load_properties(f)["Safety"]
    assert props[0]["always"].startswith("NOT (")
    assert "NOT (inputs_ok AND k1_flt)" in props[1]["always"]
    assert props[2]["given"] == "search_done"
    p = _project()
    smv = emit_smv(p, lower_project(p)["Safety"], props)
    assert smv.count("INVARSPEC") >= 3 + 4  # 3 user + auto-theorems


def test_bad_mutex_rejected(tmp_path):
    f = _props_file(tmp_path, "properties:\n  - program: P\n    mutex: [one]\n")
    with pytest.raises(ModelError, match="mutex"):
        load_properties(f)


def test_malformed_property_rejected(tmp_path):
    f = _props_file(tmp_path, "properties:\n  - program: Safety\n")
    with pytest.raises(ModelError, match="always"):
        load_properties(f)


def test_nuxmv_proves_user_property(tmp_path):
    import os
    import shutil
    import subprocess

    bin_ = os.environ.get("NUXMV_BIN") or shutil.which("nuXmv") or shutil.which("nuxmv")
    if not bin_:
        pytest.skip("nuXmv not available")
    f = _props_file(tmp_path, """\
properties:
  - program: Safety
    given: search_done
    always: key1.Latched AND key2.Latched
""")
    p = _project()
    smv = emit_smv(p, lower_project(p)["Safety"], load_properties(f)["Safety"])
    m = tmp_path / "m.smv"
    m.write_text(smv, encoding="ascii")
    out = subprocess.run([bin_, "-dcx", str(m)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "is false" not in out.stdout
