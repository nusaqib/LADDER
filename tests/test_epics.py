"""EPICS interface backend: records + alarm list from the same IR."""

from pathlib import Path

from ladder.backends import get_backend
from ladder.ir.loader import load_project
from ladder.ir.lower import lower_project


def test_epics_records_and_alarm_list(tmp_path):
    project = load_project(Path("examples/vacuum_interlock.yaml"))
    files = get_backend("epics").emit(project, lower_project(project), tmp_path)
    db = next(f for f in files if f.suffix == ".db")
    text = db.read_text(encoding="ascii")
    # one record per directional tag, macro-prefixed
    assert 'record(bi, "$(P)' in text and 'record(bo, "$(P)' in text
    assert "$(LINK=)" in text                       # transport-agnostic
    assert 'field(ONAM, "OK/ON")' in text
    assert 'field(ZSV, "MAJOR")' in text            # _ok input fail-safe alarm

    csv = next(f for f in files if f.suffix == ".csv")
    rows = csv.read_text(encoding="ascii").splitlines()
    assert rows[0] == "pv,tag,severity,message"


def test_epics_alarm_severity_from_elements(tmp_path):
    project = load_project(Path("examples/annunciator.yaml"))
    files = get_backend("epics").emit(project, lower_project(project), tmp_path)
    csv = next(f for f in files if f.suffix == ".csv").read_text(encoding="ascii")
    assert csv.count("\n") >= 2  # group members made it into the alarm list
    db = next(f for f in files if f.suffix == ".db").read_text(encoding="ascii")
    assert 'field(OSV, "MAJOR")' in db
