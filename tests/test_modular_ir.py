"""Modular IR: a directory of section files loads as one Project."""

import pytest

from ladder.ir.loader import load_project
from ladder.ir.validate import validate_project


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _make_modular(root):
    _write(root, "project.yaml",
           'ir_version: "0.2"\nname: Modular\ndescription: split IR\n')
    _write(root, "types.yaml",
           "types:\n  - name: Pump\n    members: [{name: run}, {name: fault}]\n")
    _write(root, "tags.yaml", """\
tags:
  - {name: start_pb, type: BOOL, direction: input}
  - {name: stop_ok, type: BOOL, direction: input}
  - {name: motor, type: BOOL, direction: output}
  - {name: p1, type: Pump}
""")
    _write(root, "programs/20_second.yaml", """\
name: Second
logic:
  - {element: assign, target: p1.run, value: motor}
""")
    _write(root, "programs/10_first.yaml", """\
name: First
logic:
  - {element: assign, target: motor, value: "start_pb AND stop_ok OR motor AND stop_ok"}
""")


def test_modular_directory_loads(tmp_path):
    _make_modular(tmp_path)
    p = load_project(tmp_path)
    assert p.name == "Modular"
    assert [t.name for t in p.types] == ["Pump"]
    assert len(p.tags) == 4
    # program order = filename order = scan order
    assert [pr.name for pr in p.programs] == ["First", "Second"]
    assert validate_project(p).ok


def test_fragment_files_merge(tmp_path):
    _make_modular(tmp_path)
    (tmp_path / "tags.yaml").unlink()
    _write(tmp_path, "tags/10_io.yaml", """\
- {name: start_pb, type: BOOL, direction: input}
- {name: stop_ok, type: BOOL, direction: input}
""")
    _write(tmp_path, "tags/20_state.yaml", """\
tags:
  - {name: motor, type: BOOL, direction: output}
  - {name: p1, type: Pump}
""")
    p = load_project(tmp_path)
    assert [t.name for t in p.tags] == ["start_pb", "stop_ok", "motor", "p1"]


def test_duplicate_section_definition_rejected(tmp_path):
    _make_modular(tmp_path)
    _write(tmp_path, "project.yaml",
           'name: Modular\ntags: [{name: x}]\n')
    with pytest.raises(ValueError, match="both"):
        load_project(tmp_path)


def test_missing_root_rejected(tmp_path):
    (tmp_path / "tags.yaml").write_text("tags: []", encoding="utf-8")
    with pytest.raises(ValueError, match="project.yaml"):
        load_project(tmp_path)
