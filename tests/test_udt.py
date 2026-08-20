"""IR v0.2: UDTs + arrays across validation, simulation, and all backends."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from ladder.backends import get_backend
from ladder.ir.loader import load_project
from ladder.ir.lower import lower_project
from ladder.ir.model import Project
from ladder.ir.validate import lint_project, validate_project
from ladder.model_check import emit_project
from ladder.sim import SimError, Simulator

EXAMPLE = Path(__file__).parent.parent / "examples" / "chiller_udt.yaml"


@pytest.fixture(scope="module")
def project():
    return load_project(EXAMPLE)


@pytest.fixture(scope="module")
def built(project, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    lowered = lower_project(project)
    for name in ("siemens", "rockwell", "plcopen", "beckhoff", "iec"):
        get_backend(name).emit(project, lowered, out)
    return out


def test_example_validates_and_lints_clean(project):
    assert validate_project(project).ok
    assert lint_project(project) == []


# ------------------------------------------------------------- validation


def _chiller(mutate):
    import yaml

    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    mutate(data)
    return Project.model_validate(data)


def _codes(p):
    return {i.code for i in validate_project(p).issues}


def test_unknown_member_v10():
    p = _chiller(lambda d: d["programs"][0]["logic"].append(
        {"element": "assign", "target": "pump.run_cmdd", "value": "TRUE"}))
    assert "V10" in _codes(p)


def test_index_out_of_range_v10():
    p = _chiller(lambda d: d["programs"][0]["logic"].append(
        {"element": "assign", "target": "temps[4]", "value": "0.0"}))
    assert "V10" in _codes(p)


def test_whole_array_use_v10():
    p = _chiller(lambda d: d["programs"][0]["logic"].append(
        {"element": "assign", "target": "pump_run_out", "value": "temps"}))
    assert "V10" in _codes(p)


def test_complex_tag_as_io_v10():
    p = _chiller(lambda d: d["tags"][5].update({"direction": "input"}))  # pump
    assert "V10" in _codes(p)


def test_recursive_udt_v10():
    p = _chiller(lambda d: d["types"].append(
        {"name": "A", "members": [{"name": "b", "type": "B"}]}) or
        d["types"].append({"name": "B", "members": [{"name": "a", "type": "A"}]}))
    assert "V10" in _codes(p)


# ------------------------------------------------------------- simulation


def test_simulated_struct_and_array(project):
    sim = Simulator(project)
    sim.set("temp0_raw", 13824)  # 50 degC
    sim.set("temp1_raw", 0)
    sim.scan()
    assert sim.get("temps[0]") == pytest.approx(50.0)
    assert sim.get("temps[1]") == pytest.approx(0.0)
    # seal-in on a struct member, mirrored to the physical output
    sim.pulse("start_pb")
    assert sim.get("pump.run_cmd") is True
    assert sim.get("pump_run_out") is True
    # over-temperature trips the pump via the struct fault member
    sim.set("temp0_raw", 20000)  # ~72 degC
    sim.run(1200, dt_ms=100)
    assert sim.get("hot_alarm") is True
    assert sim.get("pump.fault") is True
    sim.scan()
    assert sim.get("pump.run_cmd") is False


def test_sim_member_write_from_scenario_style(project):
    sim = Simulator(project)
    sim.set("pump.hours", 1234)
    assert sim.get("pump.hours") == 1234
    with pytest.raises(SimError):
        sim.set("pump.nope", 1)
    with pytest.raises(SimError):
        sim.set("temps[9]", 1.0)


# ------------------------------------------------------------- backends


def test_siemens_db_and_types(built):
    udt = (built / "siemens" / "Types.udt").read_text()
    assert 'TYPE "PumpCtrl"' in udt and "run_cmd : Bool;" in udt
    db = (built / "siemens" / "Chiller_DB.db").read_text()
    assert 'DATA_BLOCK "Chiller_DB"' in db
    assert "temps : Array[0..3] of Real;" in db
    assert 'pump : "PumpCtrl";' in db
    fb = (built / "siemens" / "FB_Chiller.scl").read_text()
    assert '"Chiller_DB".temps[0] :=' in fb          # DB-resident array
    assert '"Chiller_DB".pump.run_cmd' in fb         # DB-resident struct
    assert '"pump_run_out" := "Chiller_DB".pump.run_cmd;' in fb
    csv = (built / "siemens" / "PlcTags.csv").read_text()
    assert "temps" not in csv and "pump," not in csv  # complex tags not PLC tags
    ps1 = (built / "siemens" / "build.ps1").read_text()
    assert "'Types.udt', 'Chiller_DB.db', 'FB_Chiller.scl'" in ps1  # import order


def test_rockwell_udt_and_array(built):
    root = ET.parse(built / "rockwell" / "Chiller.L5X").getroot()
    dt = root.find(".//DataType")
    assert dt.get("Name") == "PumpCtrl"
    members = {m.get("Name"): m for m in dt.find("Members")}
    assert members["run_cmd"].get("DataType") == "BIT"
    assert members["run_cmd"].get("Target", "").startswith("ZZZZZZZZZZ")
    assert members["hours"].get("DataType") == "DINT"
    host = members["run_cmd"].get("Target")
    assert members[host].get("Hidden") == "true"
    tags = {t.get("Name"): t for t in root.find(".//Controller/Tags")}
    assert tags["temps"].get("Dimensions") == "4"
    assert tags["pump"].get("DataType") == "PumpCtrl"
    st = "\n".join(l.text or "" for l in root.iter("Line"))
    assert "temps[0] :=" in st and "pump.run_cmd" in st


def test_plcopen_struct_and_array(built):
    ns = {"p": "http://www.plcopen.org/xml/tc6_0201"}
    root = ET.parse(built / "plcopen" / "Chiller.xml").getroot()
    dt = root.find(".//p:dataTypes/p:dataType", ns)
    assert dt.get("name") == "PumpCtrl"
    assert dt.find(".//p:struct/p:variable", ns) is not None
    arr = root.find(".//p:globalVars/p:variable[@name='temps']//p:array", ns)
    assert arr.find("p:dimension", ns).get("upper") == "3"


def test_beckhoff_dut(built):
    dut = (built / "beckhoff" / "PumpCtrl.TcDUT").read_text()
    assert "TYPE PumpCtrl :" in dut and "END_STRUCT" in dut
    gvl = (built / "beckhoff" / "GVL_Chiller.TcGVL").read_text()
    assert "temps : ARRAY[0..3] OF REAL;" in gvl
    assert "pump : PumpCtrl;" in gvl


def test_iec_struct_and_array(built):
    st = (built / "iec" / "Chiller.st").read_text()
    assert "TYPE" in st and "STRUCT" in st and "PumpCtrl :" in st
    assert "temps : ARRAY[0..3] OF REAL;" in st
    assert "VAR_EXTERNAL" in st


def test_model_check_skips_udt_program(project, tmp_path):
    files, skipped = emit_project(project, tmp_path)
    assert not files
    assert skipped and "model-checkable" in skipped[0]
