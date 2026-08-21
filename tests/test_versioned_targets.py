"""name@version target syntax: one backend, several tool generations."""

from ladder.backends import get_backend
from ladder.backends.base import split_target
from ladder.ir.loader import load_project
from ladder.ir.lower import lower_project

from pathlib import Path

EXAMPLE = Path(__file__).parent.parent / "examples" / "vacuum_interlock.yaml"


def test_split_target():
    assert split_target("siemens@21") == ("siemens", "21")
    assert split_target("siemens") == ("siemens", None)
    assert split_target(" rockwell@35 ") == ("rockwell", "35")


def test_siemens_version_flows_to_build_script(tmp_path):
    project = load_project(EXAMPLE)
    lowered = lower_project(project)
    get_backend("siemens@19").emit(project, lowered, tmp_path)
    ps1 = (tmp_path / "siemens" / "build.ps1").read_text()
    assert "$Version     = '19.0'" in ps1


def test_rockwell_version_sets_software_revision(tmp_path):
    project = load_project(EXAMPLE)
    lowered = lower_project(project)
    get_backend("rockwell@35").emit(project, lowered, tmp_path)
    l5x = (tmp_path / "rockwell" / "VacuumInterlock.L5X").read_text()
    assert 'SoftwareRevision="35.00"' in l5x
    assert 'MajorRev="35"' in l5x


def test_manifest_accepts_versioned_targets(tmp_path):
    from ladder.scaffold import init_project, load_manifest

    init_project(tmp_path / "p", name="P")
    my = tmp_path / "p" / "ladder.yaml"
    my.write_text(my.read_text(encoding="utf-8").replace(
        "targets: [iec, plcopen, siemens, rockwell, beckhoff]",
        "targets: [iec, siemens@21, rockwell@36]"), encoding="utf-8")
    manifest, _ = load_manifest(tmp_path / "p")
    assert "siemens@21" in manifest.targets
