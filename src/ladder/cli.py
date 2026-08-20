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
    project = load_project(path)
    validate_project(project).raise_if_failed()
    return project


def cmd_validate(args) -> int:
    from ladder.ir.validate import lint_project

    project = load_project(args.ir)
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


def cmd_build(args) -> int:
    project = _load_validated(args.ir)
    lowered = lower_project(project)
    targets = sorted(registry) if args.targets == "all" else args.targets.split(",")
    outdir = Path(args.out)
    for t in targets:
        backend = get_backend(t.strip())
        files = backend.emit(project, lowered, outdir)
        print(f"[{backend.name}] {backend.target}")
        for f in files:
            print(f"  {f}")
    return 0


def cmd_verify(args) -> int:
    from ladder.verify import verify_targets

    project = _load_validated(args.ir)
    lowered = lower_project(project)
    targets = sorted(registry) if args.targets == "all" else args.targets.split(",")
    outdir = Path(args.out)
    for t in targets:
        get_backend(t.strip()).emit(project, lowered, outdir)
    results = verify_targets(project, outdir, [t.strip() for t in targets])
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


def cmd_prompt(args) -> int:
    from ladder.promptgen import build_prompt

    src = Path(args.requirement)
    requirement = src.read_text(encoding="utf-8") if src.is_file() else args.requirement
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
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("verify", help="build then check artifacts with available tools "
                                      "(matiec for iec, TiaOpenness for siemens)")
    p.add_argument("ir")
    p.add_argument("-t", "--targets", default="iec",
                   help="comma-separated backends, or 'all' (default: iec)")
    p.add_argument("-o", "--out", default="out")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("schema", help="export the IR JSON Schema (the LLM contract)")
    p.add_argument("-o", "--out", default=None)
    p.set_defaults(fn=cmd_schema)

    p = sub.add_parser("prompt", help="build a model-agnostic IR-generation prompt "
                                      "bundle (schema + rules + patterns) for any LLM")
    p.add_argument("requirement", help="requirement text, or a path to a text file")
    p.add_argument("-o", "--out", default=None, help="write to file (default: stdout)")
    p.set_defaults(fn=cmd_prompt)

    p = sub.add_parser("adopt", help="reverse adoption: vendor project spec -> IR "
                                     "(siemens: Export-TiaToSpec folder)")
    p.add_argument("vendor", choices=["siemens"])
    p.add_argument("spec", help="spec folder (Export-TiaToSpec output)")
    p.add_argument("-o", "--out", default="adopted")
    p.set_defaults(fn=cmd_adopt)

    p = sub.add_parser("targets", help="list available backends")
    p.set_defaults(fn=cmd_targets)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
