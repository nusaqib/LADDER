"""ladder deploy: manifest-driven IDE-project materialization."""

import sys
from pathlib import Path

from ladder.cli import main
from ladder.scaffold import init_project


def _set_manifest(root: Path, **fields):
    lines = (root / "ladder.yaml").read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines
            if not any(ln.startswith(f"{k}:") for k in fields)]
    for k, v in fields.items():
        kept.append(f"{k}: {v}")
    (root / "ladder.yaml").write_text("\n".join(kept) + "\n", encoding="utf-8")


def test_deploy_without_deploy_list_explains(tmp_path, capsys):
    init_project(tmp_path / "p", name="P")
    assert main(["deploy", str(tmp_path / "p")]) == 1
    assert "nothing to deploy" in capsys.readouterr().err


def test_deploy_script_runs_and_gates_exit_code(tmp_path, capsys):
    root = tmp_path / "p"
    init_project(root, name="P")
    script = root / "tools" / "fake_deploy.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "import pathlib, sys\n"
        "pathlib.Path('out/DEPLOYED.marker').write_text('yes')\n"
        "sys.exit(0)\n", encoding="utf-8")
    _set_manifest(root, deploy_script="tools/fake_deploy.py")
    assert main(["deploy", str(root)]) == 0
    assert (root / "out" / "DEPLOYED.marker").exists()
    assert "deploy PASSED" in capsys.readouterr().out

    script.write_text("import sys; sys.exit(3)\n", encoding="utf-8")
    assert main(["deploy", str(root)]) == 3


def test_deploy_unknown_target_rejected(tmp_path, capsys):
    root = tmp_path / "p"
    init_project(root, name="P")
    _set_manifest(root, deploy="[nonsense]")
    assert main(["deploy", str(root)]) == 1
    assert "unknown target" in capsys.readouterr().err


def test_deploy_artifact_only_targets_report(tmp_path, capsys):
    root = tmp_path / "p"
    init_project(root, name="P")
    _set_manifest(root, deploy="[iec, rockwell@36]")
    assert main(["deploy", str(root)]) == 0
    out = capsys.readouterr().out
    assert "artifact-only target" in out          # iec
    assert "Studio 5000" in out                   # rockwell manual note
    assert sys.platform  # keep import used on all platforms
