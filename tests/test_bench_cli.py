"""ladder bench: score a fake model against one benchmark task."""

import json
import sys
import textwrap
from pathlib import Path

from ladder.cli import main

BENCH = Path(__file__).parent.parent / "benchmarks"


def test_bench_single_task(tmp_path, capsys):
    ref = (BENCH / "task01_conveyor_jam" / "reference.yaml").as_posix()
    script = tmp_path / "fake.py"
    script.write_text(textwrap.dedent(f"""
        import sys
        sys.stdin.read()
        print(open({ref!r}, encoding="utf-8").read())
    """), encoding="utf-8")
    out = tmp_path / "results.json"
    rc = main(["bench", "--cmd", f'"{sys.executable}" "{script}"',
               "--dir", str(BENCH), "--tasks", "task01_conveyor_jam",
               "-o", str(out)])
    assert rc == 0
    text = capsys.readouterr().out
    assert "PASS task01_conveyor_jam" in text and "1/1 tasks passed" in text
    data = json.loads(out.read_text())
    assert data["results"][0] == {
        "task": "task01_conveyor_jam", "passed": True,
        "iterations": 1, "problems_last": []}
