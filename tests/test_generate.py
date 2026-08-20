"""Generation loop with fake LLM commands (no network, no provider)."""

import sys
import textwrap
from pathlib import Path

import pytest

from ladder.generate import extract_yaml, generate

BENCH = Path(__file__).parent.parent / "benchmarks" / "task01_conveyor_jam"


def _fake_llm(tmp_path, name: str, body: str) -> str:
    """Write a python script acting as the LLM; return the shell command."""
    script = tmp_path / name
    script.write_text(textwrap.dedent(body), encoding="utf-8")
    return f'"{sys.executable}" "{script}"'


def test_extract_yaml_fences():
    assert extract_yaml("```yaml\nname: X\n```") == "name: X"
    assert extract_yaml("preamble\n```\nname: X\n```\ntrailer") == "name: X"
    assert extract_yaml("name: X\n") == "name: X"


def test_single_pass_success(tmp_path):
    ref = (BENCH / "reference.yaml").as_posix()
    cmd = _fake_llm(tmp_path, "good.py", f"""
        import sys
        sys.stdin.read()  # consume the prompt like a real model would
        print("```yaml")
        print(open({ref!r}, encoding="utf-8").read())
        print("```")
    """)
    result = generate("conveyor", cmd, accept=BENCH / "scenarios.yaml")
    assert result.ok and result.iterations == 1
    assert result.project.name == "ConveyorJam"


def test_feedback_retry_loop(tmp_path):
    ref = (BENCH / "reference.yaml").as_posix()
    counter = (tmp_path / "count.txt").as_posix()
    cmd = _fake_llm(tmp_path, "flaky.py", f"""
        import os, sys
        prompt = sys.stdin.read()
        n = int(open({counter!r}).read()) if os.path.exists({counter!r}) else 0
        open({counter!r}, "w").write(str(n + 1))
        if n == 0:
            # first attempt: references an undeclared tag -> V03
            print("ir_version: '0.1'")
            print("name: Bad")
            print("tags: [{{name: x, type: BOOL, direction: input}}]")
            print("programs: [{{name: M, logic: [{{element: assign, target: x2, value: x}}]}}]")
        else:
            # second attempt must have seen the feedback section
            assert "Problems found" in prompt and "previous attempt" in prompt.lower()
            print(open({ref!r}, encoding="utf-8").read())
    """)
    result = generate("conveyor", cmd, accept=BENCH / "scenarios.yaml", max_iters=3)
    assert result.ok and result.iterations == 2
    assert any("V04" in p or "V03" in p for p in result.attempts[0].problems)


def test_gives_up_after_max_iters(tmp_path):
    cmd = _fake_llm(tmp_path, "hopeless.py", """
        import sys
        sys.stdin.read()
        print("not: [valid, ladder, ir]")
    """)
    result = generate("anything", cmd, max_iters=2)
    assert not result.ok and result.iterations == 2


def test_failing_command_raises(tmp_path):
    cmd = _fake_llm(tmp_path, "broken.py", """
        import sys
        sys.stdin.read()
        sys.exit(3)
    """)
    with pytest.raises(RuntimeError, match="exit 3"):
        generate("anything", cmd)
