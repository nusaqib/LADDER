"""Validate emitted PLCopen XML against the official tc6_0201 XSD.

Skipped unless the schema is available: set TC6_XSD to a local copy of
tc6_xml_v201.xsd (PLCopen distributes it as a code component of
IEC 61131-10) and have `xmlschema` installed. CI downloads both.
"""

import os
from pathlib import Path

import pytest

from ladder.backends import get_backend
from ladder.ir.loader import load_project
from ladder.ir.lower import lower_project

EXAMPLES = Path(__file__).parent.parent / "examples"

xmlschema = pytest.importorskip("xmlschema")

_XSD = os.environ.get("TC6_XSD")
pytestmark = pytest.mark.skipif(
    not (_XSD and Path(_XSD).exists()),
    reason="set TC6_XSD to a local tc6_xml_v201.xsd")


@pytest.fixture(scope="module")
def schema():
    return xmlschema.XMLSchema(_XSD)


@pytest.mark.parametrize("example", [
    "vacuum_interlock.yaml", "pump_skid.yaml", "chiller_udt.yaml",
    "annunciator.yaml", "languages_demo.yaml",
])
def test_examples_are_schema_valid(example, schema, tmp_path):
    project = load_project(EXAMPLES / example)
    [path] = get_backend("plcopen").emit(project, lower_project(project), tmp_path)
    errors = list(schema.iter_errors(str(path)))
    assert not errors, "\n".join(f"{e.reason} | {e.path}" for e in errors[:10])
