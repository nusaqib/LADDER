"""Skills package consistency: frontmatter, stubs in sync, no dead refs."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
SKILLS = ROOT / "skills"
STUBS = ROOT / ".claude" / "skills"

_FRONT = re.compile(r"\A---\nname: (?P<name>[a-z][a-z0-9-]*)\n"
                    r"description: (?P<desc>.+)\n---\n", re.S)


def _frontmatter(path: Path):
    m = _FRONT.match(path.read_text(encoding="utf-8"))
    assert m, f"{path}: missing/malformed frontmatter"
    return m.group("name"), m.group("desc")


def test_every_skill_has_valid_frontmatter_and_stub():
    skills = sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))
    assert skills, "no skills found"
    for name in skills:
        s_name, s_desc = _frontmatter(SKILLS / name / "SKILL.md")
        assert s_name == name, f"{name}: frontmatter name mismatch"
        stub = STUBS / name / "SKILL.md"
        assert stub.exists(), f"{name}: missing .claude discovery stub"
        t_name, t_desc = _frontmatter(stub)
        assert (t_name, t_desc) == (s_name, s_desc), \
            f"{name}: stub frontmatter out of sync with canonical skill"
        assert f"skills/{name}/SKILL.md" in stub.read_text(encoding="utf-8")


def test_skill_doc_references_exist():
    for path in SKILLS.glob("*/SKILL.md"):
        text = path.read_text(encoding="utf-8")
        for ref in re.findall(r"`(docs/[A-Z-]+\.md)`", text):
            assert (ROOT / ref).exists(), f"{path.parent.name}: dead ref {ref}"


def test_skill_cli_subcommands_exist():
    cli_src = (ROOT / "src" / "ladder" / "cli.py").read_text(encoding="utf-8")
    sub = set(re.findall(r'add_parser\("([a-z]+)"', cli_src))
    for path in SKILLS.glob("*/SKILL.md"):
        for cmd in re.findall(r"ladder ([a-z]+)", path.read_text(encoding="utf-8")):
            assert cmd in sub, f"{path.parent.name}: unknown CLI subcommand 'ladder {cmd}'"
