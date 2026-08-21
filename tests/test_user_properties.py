"""User-supplied invariants appended to the emitted SMV models."""

import pytest

from ladder.ir.lower import lower_project
from ladder.model_check import ModelError, emit_smv, load_properties
from tests.test_safety_elements import _project


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
