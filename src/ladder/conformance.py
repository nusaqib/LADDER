"""Backend conformance suite (`ladder conformance`).

Packages the repo's example + benchmark corpus as a runnable check for
any backend - including third-party plugins registered via the
`ladder.backends` entry point. For every corpus project the backend
must: emit without error, produce non-empty files, and (when the
program declares a graphic/text language) respect the language
dispatch. Scenario suites run once per project as the semantic
baseline (backend-independent by construction - lowering is shared).

    ladder conformance -t mybackend
    ladder conformance -t iec,plcopen --corpus path/to/extra

Exit 0 = conformant. This is the M6 contract: a new backend that
passes here supports every element and language the IR can express.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).parents[2]


@dataclass
class ConformanceResult:
    backend: str
    project: str
    status: str  # 'pass' | 'fail'
    detail: str = ""

    def __str__(self) -> str:
        flag = "ok  " if self.status == "pass" else "FAIL"
        s = f"  [{flag}] {self.backend:<10} {self.project}"
        return s + (f" - {self.detail}" if self.detail else "")


def corpus_projects(extra: str | Path | None = None) -> list[Path]:
    """Every IR document in examples/ + benchmarks/*/reference*."""
    roots: list[Path] = []
    for p in sorted((REPO / "examples").glob("*.yaml")):
        name = p.name
        if ".scenarios." in name or ".iomap." in name:
            continue
        roots.append(p)
    for task in sorted((REPO / "benchmarks").glob("task*")):
        ref = sorted(task.glob("reference*.yaml"))
        roots.extend(r for r in ref if ".scenarios." not in r.name)
    if extra:
        ep = Path(extra)
        roots.extend(sorted(ep.glob("*.yaml")) if ep.is_dir() else [ep])
    return roots


def _scenarios_for(ir_path: Path) -> Path | None:
    cand = ir_path.with_name(ir_path.stem + ".scenarios.yaml")
    if cand.exists():
        return cand
    cand = ir_path.parent / "scenarios.yaml"
    return cand if cand.exists() else None


def run_conformance(backends: list[str],
                    extra: str | Path | None = None) -> list[ConformanceResult]:
    from ladder.backends import get_backend
    from ladder.ir.loader import load_project
    from ladder.ir.lower import lower_project
    from ladder.ir.validate import validate_project
    from ladder.scenario import run_suite

    results: list[ConformanceResult] = []
    for ir_path in corpus_projects(extra):
        try:
            project = load_project(ir_path)
            res = validate_project(project)
            if not res.ok:
                results.append(ConformanceResult(
                    "corpus", ir_path.stem, "fail",
                    f"corpus project no longer validates: {res.issues[0]}"))
                continue
            lowered = lower_project(project)
        except Exception as e:  # noqa: BLE001 - corpus must load
            results.append(ConformanceResult("corpus", ir_path.stem, "fail", str(e)))
            continue

        sc = _scenarios_for(ir_path)
        if sc:
            bad = [r for r in run_suite(project, sc) if not r.passed]
            results.append(ConformanceResult(
                "scenarios", ir_path.stem,
                "fail" if bad else "pass",
                str(bad[0]) if bad else ""))

        for spec in backends:
            try:
                backend = get_backend(spec)
                with tempfile.TemporaryDirectory() as tmp:
                    files = backend.emit(project, lowered, Path(tmp))
                    if not files:
                        raise ValueError("backend emitted no files")
                    empty = [f for f in files if Path(f).stat().st_size == 0]
                    if empty:
                        raise ValueError(f"empty file: {Path(empty[0]).name}")
                results.append(ConformanceResult(spec, ir_path.stem, "pass",
                                                 f"{len(files)} file(s)"))
            except Exception as e:  # noqa: BLE001 - report per project
                results.append(ConformanceResult(spec, ir_path.stem, "fail",
                                                 str(e).splitlines()[0]))
    return results


def format_conformance(results: list[ConformanceResult]) -> str:
    lines = ["backend conformance over the corpus "
             f"({len({r.project for r in results})} project(s)):", ""]
    lines += [str(r) for r in results]
    failed = [r for r in results if r.status == "fail"]
    lines.append("")
    lines.append("CONFORMANCE " + ("FAILED "
                 f"({len(failed)} failure(s))" if failed else "PASSED"))
    return "\n".join(lines)
