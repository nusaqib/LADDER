# AGENTS.md — working notes for any LLM/agent in this repo

This file is deliberately tool-agnostic: the same notes apply whether the
agent is Claude, ChatGPT, Gemini, or a local model. There is no
model-specific structure in this repo; the machine-readable contract is the
IR JSON Schema (`ladder schema`).

## What LADDER is

Vendor-agnostic PLC program generation. An LLM emits a declarative IR
(YAML/JSON); deterministic code validates, lowers, and renders it into
Siemens TIA V21 (SCL + Openness build script), Rockwell Studio 5000 V36
(L5X), PLCopen XML 2.01, and Beckhoff TwinCAT 3 artifacts. See README.md.

## Rules

- **The LLM never writes vendor syntax.** All vendor knowledge lives in
  `src/ladder/backends/`. If a generation task seems to need vendor code,
  the fix is a new IR element, pattern, or backend feature — not inline
  vendor text in the IR (the `st` element is neutral ST, an escape hatch,
  and should stay rare).
- **Semantics are defined once, in `src/ladder/ir/lower.py`.** Never make a
  backend "fix up" element behavior; if two vendors would disagree about
  what an element means, the lowering is underspecified — fix it there.
- **Fail-safe conventions** (inherited from the lab's safety work): at the
  PLC input `1 = OK / healthy / closed`, `0 = fault`. Interlock outputs are
  permits (`TRUE = permitted`) that trip immediately and re-arm only on a
  manual reset while healthy. Signal sense comes from drawings/specs — never
  from a name heuristic.
- **Validation is layered**: pydantic schema → semantic pass
  (`ir/validate.py`, codes V01–V08) → per-backend lint (`BackendError`).
  New IR features need checks at the right layer plus tests.
- **Identifiers must be portable** across all vendors (letter first, single
  underscores, ≤40 chars, no reserved words) — enforced by V01; don't relax
  it for one vendor's convenience.
- Keep generated-artifact conventions: emitted `build.ps1` must be
  **ASCII-only** (Windows PowerShell 5.1 reads BOM-less files as ANSI) and
  target the TiaOpenness module in `E:/TIA_Portal/TIA_API`.

## Environment (this machine)

- Windows 11; Python 3.13 venv at `.venv` (`.venv\Scripts\python`).
- TIA Portal V19/V20/V21 with Openness (target **V21**); driving module:
  `E:/TIA_Portal/TIA_API` (PowerShell 5.1 only — see that repo's docs).
- Studio 5000 Logix Designer **V36** available; reference L5X program to be
  reverse-engineered for the Rockwell engine.

## Build / test

```powershell
.venv\Scripts\python -m pytest            # all tests must stay green
.venv\Scripts\ladder validate examples\vacuum_interlock.yaml
.venv\Scripts\ladder build examples\vacuum_interlock.yaml -t all -o out
.venv\Scripts\ladder verify examples\vacuum_interlock.yaml -t iec   # matiec if installed
```

## Live Siemens validation (M1 findings, 2026-08-20)

- The emitted `out/siemens/build.ps1` runs the full loop headless: new V21
  portal -> scratch project -> CPU -> tags from CSV -> SCL import -> compile.
- This machine's V21 catalog accepts only
  `OrderNumber:6ES7 512-1SK01-0AB0/V2.9` (CPU 1512SP F-1 PN); every other
  probed S7-1500 MLFB is rejected. The example pins it via
  `vendor.siemens.cpu`. Probe script pattern: try candidates in one session.
- **V21 blocker:** `GenerateBlocksFromSource` (SCL import) fails with
  "Necessary license 'STEP 7 Professional' is missing" on headless V21;
  V19 has the working license. Check Automation License Manager for a V21
  STEP 7 Professional license before re-testing V21.

`out/` is generated and git-ignored; never hand-edit artifacts there.

## Model checking (nuXmv)

`ladder model <ir>` emits SMV per program with auto fail-safe theorems
(interlock `permit -> permissives`); `ladder verify -t smv` runs nuXmv when
`NUXMV_BIN` is set (or nuxmv is on PATH). Windows binary:
https://es-static.fbk.eu/tools/nuxmv/downloads/nuXmv-2.0.0-win64.tar.gz
(extract anywhere, point NUXMV_BIN at bin/nuXmv.exe; do NOT commit it).
Timers are over-approximated (done may rise any scan while enabled), so
proofs hold for every preset and scan rate.

## Generating IR (for any model)

1. Get the contract: `ladder schema -o ir-schema.json` and
   [docs/IR-SPEC.md](docs/IR-SPEC.md).
2. Emit YAML/JSON conforming to it; prefer structured condition trees
   (`all:/any:/not:`) over long expression strings.
3. Validate (`ladder validate`) and iterate on the issue codes before any
   vendor build. The validator's messages are written to be machine-actionable.

## Skills (expert workflows, tool-agnostic)

[skills/](skills/) packages the expert workflows as SKILL.md documents any
agent framework can load (Claude Code discovers them via thin stubs in
`.claude/skills/`; other tools can read them directly — they are plain
markdown with name/description frontmatter):

- **design-intake** — plain-language requirement → the Design Inputs Map
  ([docs/DESIGN-INPUTS.md](docs/DESIGN-INPUTS.md)), the structured intake
  that makes generation reliable.
- **ir-authoring** — design map → validated IR + scenario suite
  (element-selection priority, issue-code loop, scenario authoring).
- **siemens-deploy** / **rockwell-deploy** — vendor-specific build,
  IO-map, import/compile, and triage procedures.
- **verification** — the four proof layers (simulate, lint, matiec,
  nuXmv) and what each does and does not prove.
- **documentation** — the deliverable document package: `ladder docs`
  generates requirements / software spec / conventions / developer and
  operator manuals / verification report from the IR; the skill also
  covers the authored documents generation cannot know (C&E matrix,
  SAT procedure, alarm response sheets, decision/finding registers).

The intended flow: design-intake → ir-authoring → vendor skill, with
verification before any handoff.

## User projects (plant logic lives elsewhere)

Real plant logic never goes in this repo: each machine/skid gets its own
repository scaffolded by `ladder init <dir>` and gated by `ladder check`
(manifest-driven validate + lint + scenarios + build). Layout and change
process: [docs/PROJECT-LAYOUT.md](docs/PROJECT-LAYOUT.md). The scaffold
ships a working motor-station starter, so a new project is green from
its first commit.
