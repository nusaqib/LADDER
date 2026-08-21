"""LADDER command line.

    ladder validate examples/vacuum_interlock.yaml
    ladder build examples/vacuum_interlock.yaml -t all -o out
    ladder schema -o ir-schema.json
    ladder targets
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ladder.backends import get_backend, registry
from ladder.ir.loader import json_schema, load_project
from ladder.ir.lower import lower_project
from ladder.ir.validate import validate_project


def _load_validated(path: str):
    from ladder.ir.loader import IRLoadError

    try:
        project = load_project(path)
    except IRLoadError as e:
        raise SystemExit(str(e)) from None
    validate_project(project).raise_if_failed()
    return project


def cmd_validate(args) -> int:
    from ladder.ir.loader import IRLoadError
    from ladder.ir.validate import lint_project

    try:
        project = load_project(args.ir)
    except IRLoadError as e:
        print(str(e), file=sys.stderr)
        return 1
    res = validate_project(project)
    for warn in lint_project(project):
        print(f"  {warn}")
    if res.ok:
        print(f"OK: {args.ir} - {project.name} "
              f"({len(project.tags)} tags, {len(project.programs)} program(s))")
        return 0
    for issue in res.issues:
        print(f"  {issue}", file=sys.stderr)
    print(f"FAILED: {len(res.issues)} issue(s)", file=sys.stderr)
    return 1


def _load_iomap(args, project):
    if not getattr(args, "iomap", None):
        return None
    from ladder.iomap import load_iomap, validate_iomap

    iomap = load_iomap(args.iomap)
    problems = validate_iomap(project, iomap)
    if problems:
        for p in problems:
            print(f"  iomap: {p}", file=sys.stderr)
        raise SystemExit(1)
    return iomap


def cmd_build(args) -> int:
    project = _load_validated(args.ir)
    iomap = _load_iomap(args, project)
    lowered = lower_project(project)
    targets = sorted(registry) if args.targets == "all" else args.targets.split(",")
    outdir = Path(args.out)
    for t in targets:
        backend = get_backend(t.strip())
        files = backend.emit(project, lowered, outdir, iomap=iomap)
        print(f"[{backend.name}] {backend.target}")
        for f in files:
            print(f"  {f}")
    return 0


def cmd_verify(args) -> int:
    from ladder.verify import verify_targets

    project = _load_validated(args.ir)
    iomap = _load_iomap(args, project)
    lowered = lower_project(project)
    from ladder.backends.base import split_target

    targets = sorted(registry) if args.targets == "all" else args.targets.split(",")
    targets = [t.strip() for t in targets]
    outdir = Path(args.out)
    for t in targets:
        if split_target(t)[0] in registry:  # 'smv' is a checker, not a backend
            get_backend(t).emit(project, lowered, outdir, iomap=iomap)
    results = verify_targets(project, outdir,
                             [split_target(t)[0] for t in targets],
                             properties=getattr(args, "properties", None))
    failed = False
    for r in results:
        print(r)
        failed |= r.status == "fail"
    return 1 if failed else 0


def cmd_schema(args) -> int:
    text = json.dumps(json_schema(), indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


def cmd_test(args) -> int:
    from ladder.scenario import run_suite

    project = _load_validated(args.ir)
    results = run_suite(project, args.scenarios,
                        on_raw="skip" if args.skip_raw else "error")
    failed = 0
    for r in results:
        print(r)
        failed += not r.passed
    print(f"{len(results) - failed}/{len(results)} scenarios passed")
    return 1 if failed else 0


def cmd_generate(args) -> int:
    import os

    from ladder.generate import generate, lint_report

    cmd = args.cmd or os.environ.get("LADDER_LLM_CMD")
    if not cmd:
        print("no LLM command: pass --cmd or set LADDER_LLM_CMD "
              '(any shell command reading the prompt on stdin, e.g. "claude -p")',
              file=sys.stderr)
        return 2
    src = Path(args.requirement)
    requirement = src.read_text(encoding="utf-8") if src.is_file() else args.requirement
    result = generate(requirement, cmd, accept=args.accept, max_iters=args.max_iters)
    for i, att in enumerate(result.attempts, 1):
        status = "ok" if not att.problems else f"{len(att.problems)} problem(s)"
        print(f"attempt {i}: {status}")
        for p in att.problems:
            print(f"    {p}")
    if not result.ok:
        print(f"FAILED after {result.iterations} attempt(s)", file=sys.stderr)
        return 1
    Path(args.out).write_text(result.yaml_text + "\n", encoding="utf-8")
    print(f"wrote {args.out} (accepted after {result.iterations} attempt(s))")
    for w in lint_report(result.project):
        print(f"  {w}")
    return 0


def cmd_model(args) -> int:
    from ladder.model_check import emit_project

    project = _load_validated(args.ir)
    files, skipped = emit_project(project, Path(args.out) / "smv",
                                  properties=args.properties)
    for f in files:
        print(f"  {f}")
    for note in skipped:
        print(f"  skipped {note}")
    if not files:
        print("no model-checkable programs", file=sys.stderr)
        return 1
    print(f"{len(files)} model(s) emitted - check with: nuxmv <file.smv> "
          "(or ladder verify -t smv with NUXMV_BIN set)")
    return 0


def cmd_bench(args) -> int:
    import json as _json
    import os

    from ladder.generate import generate

    cmd = args.cmd or os.environ.get("LADDER_LLM_CMD")
    if not cmd:
        print("no LLM command: pass --cmd or set LADDER_LLM_CMD", file=sys.stderr)
        return 2
    bench_dir = Path(args.dir)
    tasks = sorted(p for p in bench_dir.iterdir()
                   if p.is_dir() and (p / "requirement.md").exists())
    if args.tasks:
        wanted = set(args.tasks.split(","))
        tasks = [t for t in tasks if t.name in wanted]
    if not tasks:
        print(f"no tasks found under {bench_dir}", file=sys.stderr)
        return 2
    results = []
    for task in tasks:
        requirement = (task / "requirement.md").read_text(encoding="utf-8")
        try:
            r = generate(requirement, cmd, accept=task / "scenarios.yaml",
                         max_iters=args.max_iters)
            row = {"task": task.name, "passed": r.ok, "iterations": r.iterations,
                   "problems_last": r.attempts[-1].problems if r.attempts else []}
        except RuntimeError as e:
            row = {"task": task.name, "passed": False, "iterations": 0,
                   "problems_last": [str(e)]}
        results.append(row)
        status = "PASS" if row["passed"] else "FAIL"
        print(f"{status} {task.name} ({row['iterations']} attempt(s))")
    passed = sum(r["passed"] for r in results)
    print(f"\n{passed}/{len(results)} tasks passed - cmd: {cmd}")
    if args.out:
        Path(args.out).write_text(_json.dumps(
            {"cmd": cmd, "max_iters": args.max_iters, "results": results},
            indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


def cmd_prompt(args) -> int:
    from ladder.promptgen import build_intake_prompt, build_prompt

    if getattr(args, "intake", False):
        text = build_intake_prompt()
    else:
        if not args.requirement:
            print("a requirement is needed (or use --intake)", file=sys.stderr)
            return 1
        src = Path(args.requirement)
        requirement = (src.read_text(encoding="utf-8") if src.is_file()
                       else args.requirement)
        text = build_prompt(requirement)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(text)} chars) - paste into any LLM")
    else:
        print(text)
    return 0


def cmd_adopt(args) -> int:
    import yaml

    from ladder.adopt import adopt_siemens_spec

    if args.vendor != "siemens":
        print(f"no adopter for {args.vendor!r} yet (siemens only)", file=sys.stderr)
        return 1
    result = adopt_siemens_spec(args.spec)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    def _str_presenter(dumper, data):
        style = "|" if "\n" in data else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)

    yaml.add_representer(str, _str_presenter, Dumper=yaml.SafeDumper)
    ir_path = outdir / f"{result.project.name}.yaml"
    ir_path.write_text(yaml.safe_dump(
        result.project.model_dump(exclude_none=True, by_alias=True),
        sort_keys=False, allow_unicode=True), encoding="utf-8")
    report_path = outdir / "STRUCTURE.md"
    report_path.write_text(result.report, encoding="utf-8")
    print(f"adopted {len(result.project.tags)} tags, "
          f"{sum(b.lifted for b in result.blocks)}/{len(result.blocks)} blocks lifted")
    print(f"  {ir_path}\n  {report_path}")
    # round-trip sanity: the adopted IR must itself validate
    res = validate_project(result.project)
    if not res.ok:
        for issue in res.issues:
            print(f"  warning: {issue}", file=sys.stderr)
    return 0


def cmd_init(args) -> int:
    from ladder.scaffold import ManifestError, init_project

    try:
        files = init_project(args.directory, name=args.name, force=args.force)
    except ManifestError as e:
        print(str(e), file=sys.stderr)
        return 1
    for f in files:
        print(f"  {f}")
    print(f"created LADDER project in {args.directory} - next:\n"
          f"  ladder check {args.directory}\n"
          "then make it self-contained (pins LADDER as vendor/LADDER):\n"
          f"  git -C {args.directory} init && tools\\bootstrap.ps1\n"
          "then replace the starter motor station: edit design/DESIGN.md "
          "first, mirror it in ir/, keep scenarios/ in sync.")
    return 0


def cmd_check(args) -> int:
    """Manifest-driven acceptance gate: validate + lint + scenarios + build."""
    from ladder.ir.validate import lint_project
    from ladder.scaffold import ManifestError, load_manifest

    try:
        manifest, root = load_manifest(args.directory)
    except ManifestError as e:
        print(str(e), file=sys.stderr)
        return 1

    print(f"project {manifest.project} ({root / manifest.ir})")
    failed = False

    # 1. validate + lint
    from ladder.ir.loader import IRLoadError

    try:
        project = load_project(root / manifest.ir)
    except IRLoadError as e:
        print(str(e), file=sys.stderr)
        print("validate   FAILED (schema)", file=sys.stderr)
        return 1
    res = validate_project(project)
    for w in lint_project(project):
        print(f"  {w}")
    if res.ok:
        print(f"validate   OK ({len(project.tags)} tags, "
              f"{len(project.programs)} program(s))")
    else:
        for issue in res.issues:
            print(f"  {issue}", file=sys.stderr)
        print(f"validate   FAILED ({len(res.issues)} issue(s))", file=sys.stderr)
        return 1

    # 2. scenarios
    if manifest.scenarios:
        from ladder.scenario import run_suite

        results = run_suite(project, root / manifest.scenarios)
        bad = [r for r in results if not r.passed]
        for r in bad:
            print(f"  {r}", file=sys.stderr)
        print(f"scenarios  {'OK' if not bad else 'FAILED'} "
              f"({len(results) - len(bad)}/{len(results)} passed)")
        if getattr(args, "junit", None):
            from ladder.scenario import junit_xml

            junit_path = Path(args.junit)
            if not junit_path.is_absolute():
                junit_path = root / junit_path
            junit_path.parent.mkdir(parents=True, exist_ok=True)
            junit_path.write_text(junit_xml(results, manifest.project),
                                  encoding="utf-8")
            print(f"           junit -> {junit_path}")
        failed |= bool(bad)
    else:
        print("scenarios  none declared (add some - they are the definition of done)")

    # 3. build all manifest targets
    iomap = None
    if manifest.iomap:
        from ladder.iomap import load_iomap, validate_iomap

        iomap = load_iomap(root / manifest.iomap)
        problems = validate_iomap(project, iomap)
        if problems:
            for p in problems:
                print(f"  iomap: {p}", file=sys.stderr)
            print("iomap      FAILED", file=sys.stderr)
            return 1
    lowered = lower_project(project)
    outdir = root / manifest.out
    n = 0
    for t in manifest.targets:
        n += len(get_backend(t).emit(project, lowered, outdir, iomap=iomap))
    print(f"build      OK ({n} file(s) -> {outdir}, "
          f"targets: {', '.join(manifest.targets)})")

    print("CHECK " + ("FAILED" if failed else "PASSED"))
    return 1 if failed else 0


def cmd_deploy(args) -> int:
    """Materialize the vendor IDE project(s) named by the manifest's
    `deploy:` list (or run its `deploy_script`). Separate from `check`
    on purpose: artifact builds are portable; driving a vendor IDE needs
    the licensed tool on THIS machine."""
    import subprocess

    from ladder.backends.base import split_target
    from ladder.scaffold import ManifestError, load_manifest

    try:
        manifest, root = load_manifest(args.directory)
    except ManifestError as e:
        print(str(e), file=sys.stderr)
        return 1

    # fresh artifacts first (same gate as check would have used)
    project = _load_validated(root / manifest.ir)
    iomap = None
    if manifest.iomap:
        from ladder.iomap import load_iomap

        iomap = load_iomap(root / manifest.iomap)
    lowered = lower_project(project)
    outdir = root / manifest.out
    for spec in (manifest.deploy or manifest.targets):
        if split_target(spec)[0] in registry:
            get_backend(spec).emit(project, lowered, outdir, iomap=iomap)

    def run(cmd: list[str]) -> int:
        print(f"  running: {' '.join(cmd)}")
        return subprocess.call(cmd, cwd=root)

    if manifest.deploy_script:
        script = str(root / manifest.deploy_script)
        if script.endswith(".ps1"):
            rc = run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                      "-File", script])
        elif script.endswith(".py"):
            rc = run([sys.executable, script])
        else:
            rc = run([script])
        print("deploy " + ("PASSED" if rc == 0 else "FAILED"))
        return rc

    if not manifest.deploy:
        print("nothing to deploy: add `deploy: [siemens@21, ...]` (or a "
              "deploy_script) to ladder.yaml — `targets:` builds artifacts "
              "only", file=sys.stderr)
        return 1
    failed = False
    for spec in manifest.deploy:
        name, ver = split_target(spec)
        if name == "siemens":
            build = outdir / "siemens" / "build.ps1"
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                   "-File", str(build)]
            if ver:
                cmd += ["-Version", ver if "." in ver else f"{ver}.0"]
            rc = run(cmd)
            failed |= rc != 0
            if rc == 0:
                print(f"  openable project: {outdir / 'siemens' / 'project'}")
        elif name == "rockwell":
            print(f"  rockwell: import {outdir / 'rockwell'} L5X into Studio "
                  "5000 (automated creation needs Logix Designer SDK 2.x; "
                  "not installed on this machine -> manual import)")
        elif name in ("beckhoff",):
            print(f"  {name}: add the emitted items from {outdir / name} to a "
                  "TwinCAT solution (Automation Interface driver is roadmap)")
        else:
            print(f"  {name}: artifact-only target; nothing to deploy")
    print("deploy " + ("FAILED" if failed else "PASSED"))
    return 1 if failed else 0


def cmd_render(args) -> int:
    """Human-readable HTML logic report: rungs, scenarios, theorems."""
    from ladder.render import render_html
    from ladder.scaffold import ManifestError, load_manifest

    src = Path(args.directory)
    scenarios = None
    if src.is_file():
        project = _load_validated(src)
        out = Path(args.out or src.with_suffix(".report.html"))
    else:
        try:
            manifest, root = load_manifest(src)
        except ManifestError as e:
            print(str(e), file=sys.stderr)
            return 1
        project = _load_validated(root / manifest.ir)
        if manifest.scenarios:
            scenarios = root / manifest.scenarios
        if args.out:
            out = Path(args.out)
            if not out.is_absolute():
                out = root / out
        else:
            out = root / manifest.out / "report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(project, scenarios), encoding="utf-8")
    print(f"report -> {out}")
    return 0


def cmd_doctor(args) -> int:
    """Preflight: report what this machine can run and what's missing."""
    from ladder.doctor import format_report, run_doctor

    project_dir = args.directory if Path(args.directory, "ladder.yaml").exists() else None
    print(format_report(run_doctor(project_dir)))
    return 0


def cmd_apply(args) -> int:
    """Land an assistant's intake response (three fenced blocks) into the
    project, then run the full check gate on it."""
    from ladder.apply import ApplyError, apply_response
    from ladder.scaffold import ManifestError

    try:
        written = apply_response(args.response, args.directory)
    except (ApplyError, ManifestError) as e:
        print(str(e), file=sys.stderr)
        return 1
    for p in written:
        print(f"  wrote {p}")
    print("running the gate on the applied draft:")
    args2 = argparse.Namespace(directory=args.directory, junit=None)
    rc = cmd_check(args2)
    if rc != 0:
        print("\nthe draft did not pass - feed the issue codes above back "
              "to the assistant (or fix by hand) and apply again",
              file=sys.stderr)
    return rc


def cmd_docs(args) -> int:
    from ladder.docgen import generate_docs, load_doc_inputs

    di = load_doc_inputs(args.path)
    outdir = Path(args.out) if args.out else Path(args.path) / "docs" / "generated"
    files = generate_docs(di, outdir)
    for f in files:
        print(f"  {f}")
    print(f"documentation package: {len(files)} document(s) -> {outdir}")
    return 0


def cmd_targets(args) -> int:
    for name in sorted(registry):
        b = registry[name]
        print(f"{name:10} {b.target:35} {b.description}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ladder", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate", help="schema + semantic validation of an IR file")
    p.add_argument("ir")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("build", help="generate vendor artifacts from an IR file")
    p.add_argument("ir")
    p.add_argument("-t", "--targets", default="all",
                   help="comma-separated backends, or 'all' (default)")
    p.add_argument("-o", "--out", default="out", help="output directory (default: out)")
    p.add_argument("--iomap", default=None,
                   help="IO map YAML binding IO tags to vendor addresses/aliases")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("verify", help="build then check artifacts with available tools "
                                      "(matiec for iec, TiaOpenness for siemens)")
    p.add_argument("ir")
    p.add_argument("-t", "--targets", default="iec",
                   help="comma-separated backends, or 'all' (default: iec)")
    p.add_argument("-o", "--out", default="out")
    p.add_argument("--iomap", default=None,
                   help="IO map YAML binding IO tags to vendor addresses/aliases")
    p.add_argument("--properties", default=None,
                   help="YAML of user invariants for the smv checker")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("schema", help="export the IR JSON Schema (the LLM contract)")
    p.add_argument("-o", "--out", default=None)
    p.set_defaults(fn=cmd_schema)

    p = sub.add_parser("test", help="run acceptance scenarios against an IR file "
                                    "in the simulator")
    p.add_argument("ir")
    p.add_argument("scenarios", help="scenarios YAML (see docs/SCENARIOS.md)")
    p.add_argument("--skip-raw", action="store_true",
                   help="skip st escape-hatch elements instead of erroring")
    p.set_defaults(fn=cmd_test)

    p = sub.add_parser("generate", help="model-agnostic generation loop: prompt -> "
                                        "LLM -> validate -> feedback -> accept")
    p.add_argument("requirement", help="requirement text, or a path to a text file")
    p.add_argument("--cmd", default=None,
                   help="shell command reading prompt on stdin, writing the answer "
                        "to stdout (default: env LADDER_LLM_CMD)")
    p.add_argument("--accept", default=None, help="acceptance scenarios YAML")
    p.add_argument("--max-iters", type=int, default=3)
    p.add_argument("-o", "--out", default="generated.yaml")
    p.set_defaults(fn=cmd_generate)

    p = sub.add_parser("model", help="emit SMV models + auto fail-safe properties "
                                     "for nuXmv model checking")
    p.add_argument("ir")
    p.add_argument("-o", "--out", default="out")
    p.add_argument("--properties", default=None,
                   help="YAML of user invariants (program/given/always) "
                        "appended as INVARSPECs")
    p.set_defaults(fn=cmd_model)

    p = sub.add_parser("bench", help="score an LLM across the benchmark tasks "
                                     "(generate + scenario acceptance per task)")
    p.add_argument("--cmd", default=None, help="LLM shell command (default: env LADDER_LLM_CMD)")
    p.add_argument("--dir", default="benchmarks", help="benchmark root (default: benchmarks)")
    p.add_argument("--tasks", default=None, help="comma-separated task names (default: all)")
    p.add_argument("--max-iters", type=int, default=3)
    p.add_argument("-o", "--out", default=None, help="write results JSON")
    p.set_defaults(fn=cmd_bench)

    p = sub.add_parser("prompt", help="build a model-agnostic IR-generation prompt "
                                      "bundle (schema + rules + patterns) for any LLM")
    p.add_argument("requirement", nargs="?", default=None,
                   help="requirement text, or a path to a text file")
    p.add_argument("--intake", action="store_true",
                   help="emit the design-intake interview contract instead: "
                        "an LLM interviews the human for the ground truth "
                        "only they have, then drafts map/IR/scenarios")
    p.add_argument("-o", "--out", default=None, help="write to file (default: stdout)")
    p.set_defaults(fn=cmd_prompt)

    p = sub.add_parser("doctor", help="preflight: what can this machine run, "
                                      "what is missing, and how to fix it")
    p.add_argument("directory", nargs="?", default=".",
                   help="project root (adds manifest/deploy checks)")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("apply", help="land an assistant's intake response "
                                     "(design map + IR + scenarios fenced "
                                     "blocks) into the project and run check")
    p.add_argument("response", help="file holding the model's full response")
    p.add_argument("directory", nargs="?", default=".",
                   help="project root containing ladder.yaml (default: .)")
    p.set_defaults(fn=cmd_apply)

    p = sub.add_parser("render", help="human-readable HTML logic report: ladder "
                                      "rung art, scenarios, safety theorems")
    p.add_argument("directory", nargs="?", default=".",
                   help="project root with ladder.yaml, or a single IR file")
    p.add_argument("-o", "--out", default=None,
                   help="output file (default: <out>/report.html)")
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("adopt", help="reverse adoption: vendor project spec -> IR "
                                     "(siemens: Export-TiaToSpec folder)")
    p.add_argument("vendor", choices=["siemens"])
    p.add_argument("spec", help="spec folder (Export-TiaToSpec output)")
    p.add_argument("-o", "--out", default="adopted")
    p.set_defaults(fn=cmd_adopt)

    p = sub.add_parser("init", help="scaffold a new LADDER user project "
                                    "(manifest, design map, working starter IR)")
    p.add_argument("directory")
    p.add_argument("--name", default=None,
                   help="project name (default: derived from the directory)")
    p.add_argument("--force", action="store_true",
                   help="scaffold into a non-empty directory")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("check", help="run a project's full acceptance gate from "
                                     "its ladder.yaml: validate + lint + "
                                     "scenarios + build")
    p.add_argument("directory", nargs="?", default=".",
                   help="project root containing ladder.yaml (default: .)")
    p.add_argument("--junit", metavar="FILE", default=None,
                   help="also write scenario results as JUnit XML "
                        "(CI-renderable), e.g. out/scenarios.xml")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("deploy", help="materialize the vendor IDE project(s) "
                                      "named by the manifest's deploy: list "
                                      "(or run its deploy_script)")
    p.add_argument("directory", nargs="?", default=".",
                   help="project root containing ladder.yaml (default: .)")
    p.set_defaults(fn=cmd_deploy)

    p = sub.add_parser("docs", help="generate the documentation package "
                                    "(requirements, software spec, conventions, "
                                    "developer + operator manuals, verification "
                                    "report) from the IR")
    p.add_argument("path", nargs="?", default=".",
                   help="project root with ladder.yaml, or an IR file/dir")
    p.add_argument("-o", "--out", default=None,
                   help="output directory (default: <path>/docs/generated)")
    p.set_defaults(fn=cmd_docs)

    p = sub.add_parser("targets", help="list available backends")
    p.set_defaults(fn=cmd_targets)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
