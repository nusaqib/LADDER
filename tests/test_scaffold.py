"""ladder init / ladder check: scaffolded projects work out of the box."""

from pathlib import Path

import pytest

from ladder.cli import main
from ladder.ir.loader import load_project
from ladder.ir.validate import lint_project, validate_project
from ladder.scaffold import Manifest, ManifestError, init_project, load_manifest
from ladder.scenario import run_suite


def test_init_creates_working_project(tmp_path):
    root = tmp_path / "demo-plant"
    files = init_project(root)
    names = {f.relative_to(root).as_posix() for f in files}
    assert {"ladder.yaml", "README.md", "AGENTS.md", "CLAUDE.md",
            ".gitignore", "design/DESIGN.md",
            ".github/workflows/verify.yml"} <= names

    manifest, mroot = load_manifest(root)
    assert mroot == root
    assert manifest.project == "DemoPlant"      # camel-cased from dir name
    project = load_project(root / manifest.ir)
    assert validate_project(project).ok
    assert lint_project(project) == []
    results = run_suite(project, root / manifest.scenarios)
    assert all(r.passed for r in results) and len(results) == 3


def test_check_command_passes_on_scaffold(tmp_path, capsys):
    root = tmp_path / "plant"
    init_project(root, name="TestPlant")
    assert main(["check", str(root)]) == 0
    out = capsys.readouterr().out
    assert "CHECK PASSED" in out
    assert (root / "out" / "iec" / "TestPlant.st").exists()
    assert (root / "out" / "rockwell" / "TestPlant.L5X").exists()


def test_init_refuses_nonempty_dir(tmp_path):
    (tmp_path / "junk.txt").write_text("x")
    with pytest.raises(ManifestError, match="not empty"):
        init_project(tmp_path)
    init_project(tmp_path, force=True)          # --force overrides


def test_init_rejects_bad_name(tmp_path):
    with pytest.raises(ManifestError, match="identifier"):
        init_project(tmp_path / "x", name="123 bad !")


def test_manifest_errors(tmp_path):
    with pytest.raises(ManifestError, match="no ladder.yaml"):
        load_manifest(tmp_path)
    (tmp_path / "ladder.yaml").write_text(
        "project: P\nir: ir/missing.yaml\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="does not exist"):
        load_manifest(tmp_path)


def test_manifest_rejects_unknown_target(tmp_path):
    init_project(tmp_path / "p", name="P")
    m = Manifest(project="P", ir="ir/p.yaml", targets=["nope"])
    (tmp_path / "p" / "ladder.yaml").write_text(
        "project: P\nir: ir/p.yaml\ntargets: [nope]\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="unknown target"):
        load_manifest(tmp_path / "p")
    assert m.targets == ["nope"]  # model itself is permissive; loader validates
