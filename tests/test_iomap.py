"""IO map: validation and per-backend application."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from ladder.backends import get_backend
from ladder.iomap import IoMap, load_iomap, validate_iomap
from ladder.ir.loader import load_project
from ladder.ir.lower import lower_project

EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture(scope="module")
def project():
    return load_project(EXAMPLES / "vacuum_interlock.yaml")


@pytest.fixture(scope="module")
def iomap():
    return load_iomap(EXAMPLES / "vacuum_interlock.iomap.yaml")


@pytest.fixture(scope="module")
def built(project, iomap, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    lowered = lower_project(project)
    for name in ("siemens", "rockwell", "beckhoff", "plcopen", "iec"):
        get_backend(name).emit(project, lowered, out, iomap=iomap)
    return out


def test_example_iomap_is_clean(project, iomap):
    assert validate_iomap(project, iomap) == []


def test_validation_catches_problems(project):
    bad = IoMap.model_validate({
        "project": "WrongName",
        "siemens": {
            "no_such_tag": {"address": "%I0.0"},
            "at_vacuum": {"address": "%I0.1"},          # memory tag
            "pressure_ok": {"alias": "Local:1:I.Data.0"},  # alias not allowed here
            "reset_pb": {"address": "%I9.0"},
            "ack_pb": {"address": "%I9.0"},             # duplicate address
        },
    })
    problems = "\n".join(validate_iomap(project, bad))
    assert "WrongName" in problems
    assert "unknown tag" in problems
    assert "memory tag" in problems
    assert "alias" in problems
    assert "already bound" in problems


def test_binding_needs_exactly_one_of_address_alias():
    with pytest.raises(Exception, match="exactly one"):
        IoMap.model_validate({"project": "P", "siemens": {"x": {}}})
    with pytest.raises(Exception, match="exactly one"):
        IoMap.model_validate({"project": "P", "siemens": {
            "x": {"address": "%I0.0", "alias": "Local:1:I.Data.0"}}})


def test_siemens_addresses_applied(built):
    csv = (built / "siemens" / "PlcTags.csv").read_text()
    assert "pressure_ok,Bool,%I8.0" in csv        # mapped, not auto-allocated
    assert "beam_shutter_permit,Bool,%Q4.0" in csv
    assert "pumpdown_state,Int,%MW" in csv        # memory tags still allocated


def test_rockwell_alias_tags(built):
    root = ET.parse(built / "rockwell" / "VacuumInterlock.L5X").getroot()
    tags = {t.get("Name"): t for t in root.find(".//Controller/Tags")}
    assert tags["pressure_ok"].get("TagType") == "Alias"
    assert tags["pressure_ok"].get("AliasFor") == "Local:1:I.Data.0"
    assert tags["pressure_ok"].get("DataType") is None  # aliases carry no type
    assert tags["pumpdown_state"].get("TagType") == "Base"  # unmapped memory


def test_beckhoff_located_variables(built):
    gvl = (built / "beckhoff" / "GVL_VacuumInterlock.TcGVL").read_text()
    assert "pressure_ok AT %I* : BOOL;" in gvl
    assert "beam_shutter_permit AT %Q* : BOOL;" in gvl
    assert "at_vacuum : BOOL;" in gvl  # memory tag: not located


def test_plcopen_address_attribute(built):
    ns = {"p": "http://www.plcopen.org/xml/tc6_0201"}
    root = ET.parse(built / "plcopen" / "VacuumInterlock.xml").getroot()
    # plcopen section is empty in the example map -> no address attributes
    for v in root.findall(".//p:globalVars/p:variable", ns):
        assert v.get("address") is None


def test_iec_located_variables(built):
    st = (built / "iec" / "VacuumInterlock.st").read_text()
    assert "pressure_ok AT %IX8.0 : BOOL;" in st
    assert "VAR_EXTERNAL" in st
    # externals must NOT be located (the global declaration carries it)
    ext = st.split("PROGRAM SafetyPermissives")[1].split("END_VAR")[0]
    assert " AT " not in ext


def test_build_without_iomap_unchanged(project, tmp_path):
    lowered = lower_project(project)
    files = get_backend("siemens").emit(project, lowered, tmp_path)
    csv = (tmp_path / "siemens" / "PlcTags.csv").read_text()
    assert "pressure_ok,Bool,%I0.0" in csv  # auto-allocation still works
    del files
