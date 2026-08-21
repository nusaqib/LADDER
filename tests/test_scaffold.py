"""ladder init / ladder check: scaffolded projects work out of the box."""

from pathlib import Path

import pytest

from ladder.cli import main
from ladder.ir.loader import load_project
from ladder.ir.validate import lint_project, validate_project
from ladder.scaffold import (Manifest, ManifestError, init_project,
                             load_manifest, version_satisfies)
from ladder.scenario import run_suite


def test_init_creates_working_project(tmp_path):
    root = tmp_path / "demo-plant"
    files = init_project(root)
    names = {f.relative_to(root).as_posix() for f in files}
    assert {"ladder.yaml", "README.md", "AGENTS.md", "CLAUDE.md",
            ".gitignore", "design/DESIGN.md",
            ".github/workflows/verify.yml",
            "tools/bootstrap.ps1", "tools/bootstrap.sh"} <= names
    # the bootstrap scripts must stay ASCII (PowerShell 5.1 contract)
    for rel in ("tools/bootstrap.ps1", "tools/bootstrap.sh"):
        (root / rel).read_text(encoding="ascii")

    manifest, mroot = load_manifest(root)
    assert mroot == root
    assert manifest.project == "DemoPlant"      # camel-cased from dir name
    project = load_project(root / manifest.ir)
    assert validate_project(project).ok
    assert lint_project(project) == []
    results = run_suite(project, root / manifest.scenarios)
    assert all(r.passed for r in results) and len(results) == 4


def test_check_command_passes_on_scaffold(tmp_path, capsys):
    root = tmp_path / "plant"
    init_project(root, name="TestPlant")
    assert main(["check", str(root)]) == 0
    out = capsys.readouterr().out
    assert "CHECK PASSED" in out
    assert (root / "out" / "iec" / "TestPlant.st").exists()
    assert (root / "out" / "rockwell" / "TestPlant.L5X").exists()


def test_check_junit_output(tmp_path):
    root = tmp_path / "plant"
    init_project(root, name="TestPlant")
    assert main(["check", str(root), "--junit", "out/scenarios.xml"]) == 0
    xml = (root / "out" / "scenarios.xml").read_text(encoding="utf-8")
    assert 'testsuite name="TestPlant" tests="4" failures="0"' in xml
    assert xml.count("<testcase") == 4


def test_scaffold_suite_kills_all_mutants(tmp_path):
    """Dogfood: mutation testing on the starter must find zero survivors
    (this test is why the starter suite grew its 4th scenario)."""
    from ladder.mutate import run_mutation

    root = tmp_path / "p"
    init_project(root, name="P")
    mutants, invalid = run_mutation(root / "ir" / "p.yaml",
                                    root / "scenarios" / "p.scenarios.yaml")
    survivors = [m.description for m in mutants if m.killed is False]
    assert not survivors, survivors
    assert sum(1 for m in mutants if m.killed) >= 6


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


def test_version_satisfies():
    assert version_satisfies("0.2.0", ">=0.2,<0.3")
    assert version_satisfies("0.2.9", ">=0.2,<0.3")
    assert not version_satisfies("0.3.0", ">=0.2,<0.3")
    assert not version_satisfies("0.1.9", ">=0.2")
    assert version_satisfies("0.2.0", "0.2")        # bare version = ==
    assert not version_satisfies("0.2.1", "==0.2")
    assert version_satisfies("1.0.0", "!=0.9")
    with pytest.raises(ManifestError, match="bad requires clause"):
        version_satisfies("0.2.0", ">=abc")


def test_manifest_requires_gate(tmp_path):
    """The scaffolded requires range admits the running toolchain; an
    impossible range refuses every manifest-driven command."""
    root = tmp_path / "p"
    init_project(root, name="P")
    load_manifest(root)                              # scaffold range passes
    text = (root / "ladder.yaml").read_text(encoding="utf-8")
    (root / "ladder.yaml").write_text(
        text.replace('requires: ">=0.2,<0.3"', 'requires: ">=99"'),
        encoding="utf-8")
    with pytest.raises(ManifestError, match="requires LADDER"):
        load_manifest(root)


def test_manifest_rejects_unknown_target(tmp_path):
    init_project(tmp_path / "p", name="P")
    m = Manifest(project="P", ir="ir/p.yaml", targets=["nope"])
    (tmp_path / "p" / "ladder.yaml").write_text(
        "project: P\nir: ir/p.yaml\ntargets: [nope]\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="unknown target"):
        load_manifest(tmp_path / "p")
    assert m.targets == ["nope"]  # model itself is permissive; loader validates
