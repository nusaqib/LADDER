"""Project scaffolding: `ladder init` and the ladder.yaml manifest.

A LADDER *user project* is its own repository that consumes this package.
`ladder init <dir>` creates the standard layout, pre-filled with a small
but complete motor-station starter that validates, passes its scenarios,
and builds for every backend out of the box - users replace content in
working files instead of staring at blank ones:

    my-plant/
      ladder.yaml            manifest: what `ladder check` runs
      design/DESIGN.md       filled Design Inputs Map (the intake)
      ir/<slug>.yaml         the IR - single source of truth
      scenarios/<slug>.scenarios.yaml
      iomaps/<slug>.iomap.yaml
      out/                   generated artifacts (git-ignored)
      README.md  AGENTS.md  CLAUDE.md  .gitignore
      .github/workflows/verify.yml    CI: `ladder check` on every push

`ladder check [dir]` reads the manifest and runs the whole acceptance
gate: validate + lint, scenarios in the simulator, then artifact builds
for the manifest's targets (with the IO map when present).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

LADDER_GIT = "https://github.com/nusaqib/LADDER.git"


class Manifest(BaseModel):
    """ladder.yaml at a project's root."""

    model_config = ConfigDict(extra="forbid")

    project: str
    ir: str = Field(description="Path to the IR document, relative to the manifest.")
    scenarios: Optional[str] = None
    iomap: Optional[str] = None
    targets: list[str] = Field(
        default_factory=lambda: ["iec", "plcopen"],
        description="Artifact targets built by every `ladder check` "
        "(portable; runs anywhere incl. CI). 'name' or 'name@version'.")
    deploy: list[str] = Field(
        default_factory=list,
        description="Vendor IDE projects materialized by `ladder deploy` "
        "(needs the vendor tool on this machine), e.g. [siemens@21].")
    deploy_script: Optional[str] = Field(
        default=None,
        description="Project-specific deploy engine run by `ladder deploy` "
        "instead of the built-in per-vendor steps (.ps1/.py/shell).")
    out: str = "out"


class ManifestError(ValueError):
    pass


def load_manifest(path: str | Path) -> tuple[Manifest, Path]:
    """Load ladder.yaml from a project dir (or an explicit file path).
    Returns (manifest, project_root)."""
    p = Path(path)
    file = p if p.is_file() else p / "ladder.yaml"
    if not file.exists():
        raise ManifestError(f"no ladder.yaml found at {p} - not a LADDER "
                            "project? (create one with: ladder init <dir>)")
    data = yaml.safe_load(file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ManifestError(f"{file}: expected a YAML mapping")
    m = Manifest.model_validate(data)
    root = file.parent
    if not (root / m.ir).exists():
        raise ManifestError(f"{file}: ir file {m.ir!r} does not exist")
    for field in ("scenarios", "iomap"):
        rel = getattr(m, field)
        if rel and not (root / rel).exists():
            raise ManifestError(f"{file}: {field} file {rel!r} does not exist")
    from ladder.backends import registry
    from ladder.backends.base import split_target

    unknown = [t for t in m.targets + m.deploy
               if split_target(t)[0] not in registry]
    if unknown:
        raise ManifestError(f"{file}: unknown target(s) {unknown} "
                            f"(known: {sorted(registry)}, optionally "
                            "'name@version', e.g. siemens@21)")
    if m.deploy_script and not (root / m.deploy_script).exists():
        raise ManifestError(f"{file}: deploy_script {m.deploy_script!r} "
                            "does not exist")
    return m, root


# ------------------------------------------------------------------ init


def _camel(name: str) -> str:
    parts = re.split(r"[^0-9A-Za-z]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def _snake(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    return re.sub(r"[^0-9A-Za-z]+", "_", s).strip("_").lower()


def init_project(directory: str | Path, name: str | None = None,
                 force: bool = False) -> list[Path]:
    """Create a new LADDER project. Returns the created files."""
    from ladder.ir.validate import _IDENT_RE

    root = Path(directory)
    raw = name or root.name
    # a name that is already a portable identifier is kept verbatim
    name = raw if _IDENT_RE.match(raw) else _camel(raw)
    if not _IDENT_RE.match(name):
        raise ManifestError(f"project name {name!r} is not a portable identifier")
    slug = _snake(name)
    if root.exists() and any(root.iterdir()) and not force:
        raise ManifestError(f"{root} is not empty (use --force to scaffold anyway)")

    files: dict[str, str] = {
        "ladder.yaml": _MANIFEST,
        "README.md": _README,
        "AGENTS.md": _AGENTS,
        "CLAUDE.md": _CLAUDE,
        ".gitignore": _GITIGNORE,
        f"ir/{slug}.yaml": _IR,
        f"scenarios/{slug}.scenarios.yaml": _SCENARIOS,
        f"iomaps/{slug}.iomap.yaml": _IOMAP,
        "design/DESIGN.md": _DESIGN,
        ".github/workflows/verify.yml": _CI,
    }
    written: list[Path] = []
    for rel, template in files.items():
        text = (template.replace("__NAME__", name)
                        .replace("__SLUG__", slug)
                        .replace("__LADDER_GIT__", LADDER_GIT))
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    (root / "out").mkdir(exist_ok=True)
    return written


# ------------------------------------------------------------- templates
#
# The starter is a deliberately small but *complete* motor station: one
# fail-safe interlock, a sealed-in motor command, and a latching overload
# alarm - so every project begins green and users replace, not invent.

_MANIFEST = """\
# LADDER project manifest.
project: __NAME__
ir: ir/__SLUG__.yaml
scenarios: scenarios/__SLUG__.scenarios.yaml
iomap: iomaps/__SLUG__.iomap.yaml
# artifact targets: built + verified by every `ladder check` (portable, CI)
targets: [iec, plcopen, siemens, rockwell, beckhoff]
# vendor IDE projects: materialized only by `ladder deploy`, only on a
# machine with the vendor tool - e.g. [siemens@21]; a project with its own
# engine can point deploy_script at it instead
deploy: []
out: out
"""

_IR = """\
# __NAME__ - LADDER IR (the single source of truth for this project's logic).
# Replace the starter motor station with your plant, keeping design/DESIGN.md
# in sync. Conventions: BOOL inputs are 1 = OK/healthy/closed; interlock
# outputs are permits; latching elements name their reset/ack.
ir_version: "0.2"
name: __NAME__
description: Starter motor station - replace with your plant.

tags:
  - {name: estop_ok,       type: BOOL, direction: input,  comment: E-stop chain healthy}
  - {name: overload_ok,    type: BOOL, direction: input,  comment: Motor overload relay healthy}
  - {name: stop_ok,        type: BOOL, direction: input,  comment: "Stop pushbutton (NC, 1 = not pressed)"}
  - {name: start_pb,       type: BOOL, direction: input,  comment: Start pushbutton}
  - {name: reset_pb,       type: BOOL, direction: input,  comment: Interlock reset pushbutton}
  - {name: ack_pb,         type: BOOL, direction: input,  comment: Alarm acknowledge pushbutton}

  - {name: run_permit,     type: BOOL, direction: output, comment: Motor run permit (interlock)}
  - {name: motor_run,      type: BOOL, direction: output, comment: Motor contactor command}
  - {name: overload_alarm, type: BOOL, direction: output, comment: Overload alarm lamp}

programs:
  - name: MotorStation
    description: Permissive chain, sealed-in start, overload alarm.
    logic:
      - element: interlock
        id: IL_motor
        description: E-stop and overload chain; manual reset after a trip.
        permissives: {all: [estop_ok, overload_ok]}
        output: run_permit
        reset: {signal: reset_pb}

      - element: assign
        target: motor_run
        value: {all: [run_permit, stop_ok, {any: [start_pb, motor_run]}]}
        description: Seal-in motor start; stop or permit loss drops it.

      - element: alarm
        id: ALM_overload
        description: Overload trip, debounced; ack clears after it heals.
        condition: {not: overload_ok}
        on_delay: T#1s
        latching: true
        ack: ack_pb
        output: overload_alarm
        severity: alarm
"""

_SCENARIOS = """\
# Acceptance scenarios - the definition of done for __NAME__.
# `ladder check` runs these in the scan-accurate simulator; keep them in
# sync with design/DESIGN.md section 9. Inputs default to 0 (= fault), so
# healthy states must be set explicitly first.
scenarios:
  - name: start_seals_in_and_stop_drops_it
    steps:
      - set: {estop_ok: true, overload_ok: true, stop_ok: true}
      - pulse: reset_pb
      - expect: {run_permit: true, motor_run: false}
      - pulse: start_pb
      - expect: {motor_run: true}          # sealed in after release
      - set: {stop_ok: false}
      - scan: {}
      - expect: {motor_run: false}

  - name: estop_trips_and_stays_down_until_reset
    steps:
      - set: {estop_ok: true, overload_ok: true, stop_ok: true}
      - pulse: reset_pb
      - pulse: start_pb
      - set: {estop_ok: false}
      - scan: {}
      - expect: {run_permit: false, motor_run: false}
      - set: {estop_ok: true}
      - scan: {}
      - expect: {run_permit: false}        # healthy again, still tripped
      - pulse: reset_pb
      - expect: {run_permit: true}

  - name: overload_alarm_debounces_and_acks_after_clear
    steps:
      - set: {estop_ok: true, overload_ok: true, stop_ok: true}
      - scan: {}
      - set: {overload_ok: false}
      - run: {ms: 800, dt_ms: 100}
      - expect: {overload_alarm: false}    # inside the 1s debounce
      - run: {ms: 400, dt_ms: 100}
      - expect: {overload_alarm: true}
      - pulse: ack_pb                      # condition still present
      - expect: {overload_alarm: true}
      - set: {overload_ok: true}
      - scan: {}
      - pulse: ack_pb
      - expect: {overload_alarm: false}
"""

_IOMAP = """\
# Hardware bindings for __NAME__ - kept out of the IR on purpose.
# Fill per deployed target; unmapped tags get auto-allocated scratch
# addresses (fine for compile checks, wrong on a real panel).
project: __NAME__

siemens:                       # absolute addresses
  estop_ok:       {address: "%I0.0"}
  overload_ok:    {address: "%I0.1"}
  stop_ok:        {address: "%I0.2"}
  start_pb:       {address: "%I0.3"}
  reset_pb:       {address: "%I0.4"}
  ack_pb:         {address: "%I0.5"}
  run_permit:     {address: "%Q0.0"}
  motor_run:      {address: "%Q0.1"}
  overload_alarm: {address: "%Q0.2"}

rockwell:                      # alias tags onto module IO
  estop_ok:       {alias: "Local:1:I.Data.0"}
  overload_ok:    {alias: "Local:1:I.Data.1"}
  stop_ok:        {alias: "Local:1:I.Data.2"}
  start_pb:       {alias: "Local:1:I.Data.3"}
  reset_pb:       {alias: "Local:1:I.Data.4"}
  ack_pb:         {alias: "Local:1:I.Data.5"}
  run_permit:     {alias: "Local:2:O.Data.0"}
  motor_run:      {alias: "Local:2:O.Data.1"}
  overload_alarm: {alias: "Local:2:O.Data.2"}

iec:                           # located variables (%IX/%QX)
  estop_ok:       {address: "%IX0.0"}
  overload_ok:    {address: "%IX0.1"}
  stop_ok:        {address: "%IX0.2"}
  start_pb:       {address: "%IX0.3"}
  reset_pb:       {address: "%IX0.4"}
  ack_pb:         {address: "%IX0.5"}
  run_permit:     {address: "%QX0.0"}
  motor_run:      {address: "%QX0.1"}
  overload_alarm: {address: "%QX0.2"}
"""

_DESIGN = """\
# __NAME__ - Design Inputs Map

> Filled per the LADDER Design Inputs Map (docs/DESIGN-INPUTS.md in the
> LADDER repo). This document is the intake: every signal, interlock,
> alarm, and acceptance behavior is decided HERE before it exists in the
> IR. Replace the starter content with your plant; never let the IR get
> ahead of this map.

## 1. Project identity

- **Name:** __NAME__
- **Purpose:** Starter motor station (replace me).
- **Targets:** all backends (trim `targets:` in ladder.yaml as needed)
- **Execution:** one cyclic program.

## 2. Signal list (the IO contract)

| name | meaning | type | direction | sense (1 =) | address | device |
|---|---|---|---|---|---|---|
| estop_ok | E-stop chain healthy | BOOL | input | OK | see iomap | safety relay |
| overload_ok | Overload relay healthy | BOOL | input | OK | see iomap | MCC |
| stop_ok | Stop PB not pressed (NC) | BOOL | input | OK | see iomap | panel |
| start_pb | Start PB pressed | BOOL | input | pressed | see iomap | panel |
| reset_pb | Interlock reset | BOOL | input | pressed | see iomap | panel |
| ack_pb | Alarm acknowledge | BOOL | input | pressed | see iomap | panel |
| run_permit | Motor run permit | BOOL | output | permitted | see iomap | lamp/logic |
| motor_run | Contactor command | BOOL | output | run | see iomap | MCC |
| overload_alarm | Overload lamp | BOOL | output | active | see iomap | panel |

## 3. Equipment

| equipment | signals | pattern |
|---|---|---|
| Main motor | start_pb/stop_ok/motor_run | seal-in assign (motor_starter pattern also fits) |

## 4. Interlock matrix

| id | protects | permissives | latching | reset | trip consequence |
|---|---|---|---|---|---|
| IL_motor | motor | estop_ok AND overload_ok | yes | reset_pb | motor_run drops same scan |

## 5. Alarm list

| id | condition | debounce | severity | latching/ack |
|---|---|---|---|---|
| ALM_overload | NOT overload_ok | T#1s | alarm | latching, ack_pb |

## 6. Sequences

None (replace if your plant has stepped behavior; consider `language: sfc`).

## 7. Analog signals

None.

## 8. Timing table

| purpose | preset | consumer |
|---|---|---|
| overload debounce | T#1s | ALM_overload on_delay |

## 9. Acceptance scenarios

See scenarios/__SLUG__.scenarios.yaml - start/seal/stop, estop trip and
manual reset, overload debounce/ack cycle.

## 10. Hardware map

iomaps/__SLUG__.iomap.yaml (siemens / rockwell / iec sections filled with
placeholder rack-0 addresses - fix before commissioning).

## Completeness gate

- [x] every referenced signal in section 2 with type/direction/sense
- [x] every BOOL input sense stated
- [x] every latching element names reset/ack
- [x] no sequence states (none defined)
- [x] 3+ acceptance scenarios naming only section-2 signals
- [x] no SIL/PL safety functions in scope
"""

_README = """\
# __NAME__

A [LADDER](__LADDER_GIT__) project: the PLC logic lives as vendor-neutral,
verifiable IR in [ir/__SLUG__.yaml](ir/__SLUG__.yaml); everything vendor-
specific is generated.

```
design/DESIGN.md        what the plant needs (the intake - edit FIRST)
ir/__SLUG__.yaml        the logic (IR - the only hand-written source)
scenarios/*.yaml        acceptance behavior (the definition of done)
iomaps/*.yaml           hardware addresses/aliases per vendor
out/                    generated vendor artifacts (never edit, never commit)
```

## Workflow

```bash
pip install git+__LADDER_GIT__   # once
ladder check .          # validate + lint + scenarios + build all targets
```

Change process: update `design/DESIGN.md` → mirror it in the IR and
scenarios → `ladder check .` until green → deploy from `out/` (Siemens:
run `out/siemens/build.ps1`, which writes the openable TIA project to
`out/siemens/project/`; Rockwell: import `out/rockwell/*.L5X`). Everything
under `out/` is a disposable build artifact — regenerate, never hand-edit.

Generated logic must be reviewed by a qualified controls engineer; it is
not certified for SIL/PL-rated safety functions.
"""

_AGENTS = """\
# Agent guide - __NAME__

This is a LADDER user project. You write **IR YAML**, never vendor code.
Full agent docs and skills ship with the LADDER repo (__LADDER_GIT__):
design-intake, ir-authoring, siemens-deploy, rockwell-deploy, verification.

## The contract

1. `design/DESIGN.md` is the intake. A requested change edits it first;
   never invent a signal that is not in its section-2 table - ask, or
   record an explicit ASSUMPTION there.
2. `ir/__SLUG__.yaml` mirrors the map. Prefer patterns, then structured
   elements (interlock / alarm / alarm_group / timer / state_machine /
   scale / assign); raw `st` is a last resort. Fail-safe sense: BOOL
   inputs are 1 = OK/healthy/closed; interlock outputs are permits;
   latching elements name their reset/ack.
3. `scenarios/__SLUG__.scenarios.yaml` is the definition of done - update
   it with every behavior change (inputs default to 0 = fault).
4. Gate everything with `ladder check .` - it validates (V01-V11 issue
   codes are machine-actionable), lints (W01-W06 are design smells, fix
   the design), runs scenarios, and builds every manifest target.
5. Hardware addresses belong in `iomaps/`, never in the IR.
6. `out/` is generated - never edit or commit it.

Useful commands: `ladder prompt "<req>"` (the full model-facing contract),
`ladder model ir/__SLUG__.yaml -o out` (SMV + auto fail-safe theorems for
nuXmv), `ladder verify ir/__SLUG__.yaml -t iec -o out` (matiec compile).
"""

_CLAUDE = """\
# CLAUDE.md

All agent guidance is tool-agnostic and lives in [AGENTS.md](AGENTS.md) -
read that. Nothing in this project is specific to any one LLM.
"""

_GITIGNORE = """\
out/
__pycache__/
*.pyc
.venv/
generated.yaml
"""

_CI = """\
name: verify
on:
  push:
  pull_request:
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install git+__LADDER_GIT__
      - run: ladder check .
"""
