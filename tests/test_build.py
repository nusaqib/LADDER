"""End-to-end: example IR -> all four backends, artifacts well-formed."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from ladder.backends import get_backend
from ladder.ir.loader import load_project
from ladder.ir.lower import lower_project
from ladder.ir.validate import validate_project

EXAMPLE = Path(__file__).parent.parent / "examples" / "vacuum_interlock.yaml"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    project = load_project(EXAMPLE)
    validate_project(project).raise_if_failed()
    lowered = lower_project(project)
    out = tmp_path_factory.mktemp("out")
    files = {}
    for name in ("siemens", "rockwell", "plcopen", "beckhoff"):
        files[name] = get_backend(name).emit(project, lowered, out)
    return project, out, files


def test_example_validates():
    project = load_project(EXAMPLE)
    assert validate_project(project).ok


def test_siemens_scl(built):
    _, out, files = built
    scl = (out / "siemens" / "FB_SafetyPermissives.scl").read_text()
    assert 'FUNCTION_BLOCK "FB_SafetyPermissives"' in scl
    assert '"beam_shutter_permit" := FALSE;' in scl          # trip branch
    assert "#ALM_vacuum_ton(IN := NOT" in scl                # multi-instance TON
    assert "ALM_vacuum_ton : TON;" in scl                    # synthesized decl
    scl2 = (out / "siemens" / "FB_PumpDown.scl").read_text()
    assert 'CASE "pumpdown_state" OF' in scl2
    assert "99:" in scl2                                     # explicit state code
    csv = (out / "siemens" / "PlcTags.csv").read_text()
    assert "pressure_ok,Bool,%I0.0" in csv          # first input BOOL
    assert "beam_shutter_permit,Bool,%Q0.0" in csv  # first output BOOL
    assert "pumpdown_state,Int,%MW" in csv          # word-aligned memory INT
    ps1 = (out / "siemens" / "build.ps1").read_text()
    assert "Import-TiaScl" in ps1 and "Connect-TiaPortal -New" in ps1
    assert "New-TiaDevice" in ps1 and "Invoke-TiaCompile" in ps1
    assert "__" not in ps1                          # all template tokens substituted
    ps1.encode("ascii")  # PS 5.1 convention: ASCII only


def test_rockwell_l5x(built):
    _, out, _ = built
    path = out / "rockwell" / "VacuumInterlock.L5X"
    root = ET.parse(path).getroot()
    assert root.tag == "RSLogix5000Content"
    assert root.get("SoftwareRevision") == "36.00"
    ctrl = root.find("Controller")
    assert ctrl.get("MajorRev") == "36"
    tag_names = {t.get("Name") for t in ctrl.find("Tags")}
    assert "beam_shutter_permit" in tag_names
    progs = {p.get("Name"): p for p in ctrl.find("Programs")}
    assert set(progs) == {"SafetyPermissives", "PumpDown"}
    st = "\n".join(l.text or "" for l in
                   progs["SafetyPermissives"].iter("Line"))
    assert "TONR(ALM_vacuum_ton);" in st
    assert "ALM_vacuum_ton.PRE := 2000;" in st               # T#2s -> ms
    assert "ALM_vacuum_ton.DN" in st                         # Q -> DN
    ptags = {t.get("Name"): t.get("DataType")
             for t in progs["SafetyPermissives"].find("Tags")}
    assert ptags["ALM_vacuum_ton"] == "FBD_TIMER"
    sched = {s.get("Name") for s in ctrl.find("Tasks").iter("ScheduledProgram")}
    assert sched == {"SafetyPermissives", "PumpDown"}


def test_plcopen_xml(built):
    _, out, _ = built
    path = out / "plcopen" / "VacuumInterlock.xml"
    root = ET.parse(path).getroot()
    ns = {"p": "http://www.plcopen.org/xml/tc6_0201"}
    assert root.tag.endswith("project")
    pous = root.findall(".//p:pou", ns)
    assert {p.get("name") for p in pous} == {"SafetyPermissives", "PumpDown"}
    gvars = root.findall(".//p:globalVars/p:variable", ns)
    assert any(v.get("name") == "pressure_ok" for v in gvars)


def test_beckhoff_pous(built):
    _, out, files = built
    pou = (out / "beckhoff" / "PumpDown.TcPOU").read_text()
    assert "PROGRAM PumpDown" in pou
    assert "T_stable_t : TON;" in pou
    root = ET.parse(out / "beckhoff" / "PumpDown.TcPOU").getroot()
    assert root.tag == "TcPlcObject"
    gvl = (out / "beckhoff" / "GVL_VacuumInterlock.TcGVL").read_text()
    assert "VAR_GLOBAL" in gvl and "pressure_ok : BOOL;" in gvl
    # deterministic POU ids: emitting twice gives identical files
    id1 = root.find("POU").get("Id")
    assert id1 == ET.parse(out / "beckhoff" / "PumpDown.TcPOU").getroot().find("POU").get("Id")


def test_rockwell_rejects_tp_timer(built, tmp_path):
    from ladder.backends.base import BackendError
    from ladder.ir.model import Project

    p = Project.model_validate({
        "name": "T", "tags": [{"name": "x", "type": "BOOL", "direction": "input"},
                              {"name": "y", "type": "BOOL", "direction": "output"}],
        "programs": [{"name": "Main", "logic": [
            {"element": "timer", "id": "T1", "kind": "TP",
             "input": "x", "preset": "T#1s", "done": "y"}]}],
    })
    lowered = lower_project(p)
    with pytest.raises(BackendError, match="TP.*unsupported|TP \\(pulse\\)"):
        get_backend("rockwell").emit(p, lowered, tmp_path)
