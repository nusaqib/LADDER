"""Benchmark integrity: every reference solution validates, lints clean,
and passes all of its own acceptance scenarios."""

from pathlib import Path

import pytest

from ladder.ir.loader import load_project
from ladder.ir.validate import lint_project, validate_project
from ladder.scenario import run_suite

BENCH = Path(__file__).parent.parent / "benchmarks"
TASKS = sorted(p for p in BENCH.iterdir() if p.is_dir())


def test_tasks_present():
    assert len(TASKS) >= 3
    for task in TASKS:
        assert (task / "requirement.md").exists()
        assert (task / "scenarios.yaml").exists()
        assert (task / "reference.yaml").exists()


@pytest.mark.parametrize("task", TASKS, ids=lambda p: p.name)
def test_reference_solution(task):
    project = load_project(task / "reference.yaml")
    validate_project(project).raise_if_failed()
    assert lint_project(project) == []
    results = run_suite(project, task / "scenarios.yaml")
    failed = [str(r) for r in results if not r.passed]
    assert not failed, failed
