# LADDER roadmap

Two tracks run in parallel: **engineering milestones** (M0–M6) and an
**open-source / community track** (OS1–OS4) with gates tied to engineering
maturity. Dates are targets, not promises.

---

## Where LADDER sits (research + ecosystem context)

Academic work on LLM PLC programming — LLM4PLC (compiler feedback + model
checking + LoRA), Agents4PLC (multi-agent closed loop + verifiable ST
benchmark), online-feedback ST training — all targets **raw Structured Text
generation**. Nobody occupies LADDER's niche: a *declarative, verifiable,
vendor-neutral IR* the model emits, with *deterministic* lowering and
*real vendor toolchain* deployment (Openness, L5X/SDK, TwinCAT). That's the
gap, and it's also the honest pitch for open-sourcing.

The open ecosystem to interoperate with (not compete against):

| Tool | What it is | Use to LADDER |
|---|---|---|
| matiec | open IEC 61131-3 → C compiler | **vendor-free CI check** of our emitted IEC ST |
| IronPLC | Rust 61131 toolchain + playground | alternative CI check; runtime target later |
| OpenPLC / Beremiz | GPL soft-PLC runtime + IDE | potential backend → run IR on a Pi |
| blark | Python TwinCAT ST parser | reverse adoption (vendor → IR) |
| l5x / acd (Python) | L5X editing, ACD→L5X | Rockwell reverse adoption |
| PLCopen XML / IEC 61131-10 | standard exchange format | already a backend |

---

## Engineering milestones

### M0 — IR core + artifact backends ✅ (Aug 2026)

IR v0.1 (model, expression AST, validation V01–V08, deterministic lowering,
JSON Schema export) + four emitting backends (Siemens SCL/CSV/build.ps1,
Rockwell L5X V36, PLCopen XML 2.01, Beckhoff TcPOU/TcGVL). Example + 33 tests.

### M1 — Close the loop on real tools (target: Sep–Oct 2026) — largely done 2026-08-20

Done: Siemens loop runs headless end-to-end and **compiles 0 errors on V19**
(`build.ps1`: portal → scratch project → CPU 1512SP F-1 → tags → SCL → compile);
`ladder verify` + CI matiec check of the new `iec` backend; reverse adoption
(`ladder adopt siemens`) proven as a full round trip on our own artifacts.
Open: V21 needs a STEP 7 Professional license registered (ALM); Studio 5000
L5X import is a manual check until Logix Designer SDK 2.x (Python client) is
installed; TwinCAT not installed on this machine.

*The generated artifacts import and compile in every vendor tool.*

- Siemens: run emitted `build.ps1` against a scratch TIA **V21** project via
  TiaOpenness; iterate to compile **0/0**.
- Rockwell: import the L5X into Studio 5000 **V36** (manual first, then the
  Logix Designer SDK Python client — requires Professional edition license).
- Beckhoff: add emitted items to a scratch TwinCAT solution; build clean.
- **Vendor-free verification in CI**: compile every backend's IEC-flavored ST
  with matiec (and/or IronPLC) on GitHub Actions — no vendor installs needed,
  so outside contributors get real feedback.
- `ladder verify -t <backend>` wraps whatever check each backend supports.

**Exit criteria:** all four targets demonstrably import/compile; CI green
without any vendor software.

### M2 — Vendor engines + reverse adoption (target: Oct–Dec 2026)

*From "emit files" to "drive the vendor tool", shaped by real programs.*

- Reverse-engineer the reviewed reference TIA program (project tree, OB/FB/DB
  conventions, instance strategy) → encode in the Siemens engine, not the IR.
- Same for the reference Studio 5000 program (task/program/AOI structure).
- Reverse adoption: vendor project → IR (Openness export / L5X parse with the
  `l5x` lib / blark for TwinCAT), so existing plants can be lifted into LADDER.
- Round-trip tests: IR → vendor → IR is stable.

### M3 — Pattern library + richer IR (target: Q1 2027) — invocation shipped early

Done 2026-08-20: IR-level `element: pattern` with expansion before
validation (V09 guard); built-ins `motor_starter`, `valve_with_feedback`;
`examples/pump_skid.yaml`. Remaining: mine the reference programs, richer
IR (UDTs, PID, motion, alarm groups), IO-mapping layer.

*Shrink the LLM's job from "write the IR" to "pick patterns, fill parameters".*

- Mine recurring structures from both reference programs into
  `ladder.patterns`; IR-level invocation (`element: pattern`) expanding
  before validation.
- IR v0.2: UDTs/structs, arrays, analog scaling, PID loop element, motion
  axis element using the **PLCopen Motion Control vocabulary**, alarm
  groups/first-out.
- Separate IO-mapping document (signal list → vendor addresses) keeping the
  IR hardware-free.

### M4 — Verification & simulation (target: Q1–Q2 2027) — core shipped early

Done 2026-08-20: scan-based simulator (`ladder.sim`) with real TON/TOF/TP
timing and scenario tests pinning interlock/alarm/state-machine semantics;
static lint W01–W06 (unused tags, multi-writer hazards, SM reachability);
**formal path shipped**: `ladder model` emits SMV (timers soundly
over-approximated, statement order folded into one TRANS) with an
auto-generated fail-safe theorem per interlock — nuXmv proved
`permit -> permissives` on the example and found the counterexample in a
deliberately bypassed interlock. Remaining: alarm/SM property templates,
user-supplied LTL specs.

*The reason the IR exists: checks that are impossible on raw vendor code.*

- Python interpreter for the neutral statement AST → scenario tests
  ("gate opens during pump-down ⇒ permit drops within one scan").
- Static checks: interlock reachability, unwritten-member detection,
  state-machine liveness/deadlock.
- Optional formal path: emit SMV for nuXmv model checking (the LLM4PLC /
  Agents4PLC playbook, but over a tiny well-defined AST instead of full ST).

### M5 — Model-agnostic LLM harness + benchmark (target: Q2 2027) — shipped early

Done 2026-08-20: `ladder generate` — provider-neutral loop (any shell
command reading prompt on stdin: hosted CLI, curl, local model) with
validator issue codes as feedback and **simulation scenarios as the
acceptance gate** (`ladder test`, docs/SCENARIOS.md); `benchmarks/` with
3 spec-to-IR tasks, scenario-scored, CI-verified reference solutions.
Remaining: grow the benchmark, publish results across models, vendor
compile as a final loop stage (needs M1 vendor items).

### M6 / v1.0 — Stability contract

- IR spec frozen at 1.0 with a versioning + RFC process for changes.
- Two independent users outside the lab in production-adjacent use.
- Backend plugin API documented (entry points) so third-party backends
  (CODESYS, Mitsubishi, Omron, OpenPLC runtime) live in their own repos.

---

## Open-source & community track

### OS1 — Be releasable from day one (now)

- Repo hygiene: LICENSE, CONTRIBUTING.md, CODE_OF_CONDUCT.md, CI badge,
  SECURITY.md. Core tests are pure Python — anyone can contribute without
  owning vendor software.
- **Hard legal guardrails** (enforced forever):
  - Never commit vendor binaries (`Siemens.Engineering.dll`, Logix SDK bits)
    — engines load them from the *user's* licensed install (TIA_API already
    reflection-loads; keep it that way).
  - No lab-internal content: the SR PPS safety programs, drawings, and any
    facility-specific configuration stay in private repos that *consume*
    LADDER (the TIA_API submodule model).
  - Clean-room formats only: L5X/SCL/tc6 emission is from public
    documentation, no decompiled vendor code.
- Safety disclaimer in README and generated headers: generated logic must be
  reviewed by a qualified controls engineer; not for SIL/PL-rated safety
  functions without the applicable certification process.

### OS2 — Institutional approval (before anything goes public)

LADDER is developed at Berkeley Lab, so release goes through the Lab's
open-source reporting/approval process (rights check, license fit, DOE
compliance) via IPO, plus an export-control consult (fundamental-research
exemption expected, but it's the liaison's call, especially for control-
system software). License recommendation: **BSD-3-Clause-LBNL** (the
OSI-approved LBNL variant) or plain BSD-3-Clause — permissive licensing is
what lets controls vendors and integrators actually use it.

### OS3 — Public launch (gate: after M1, so the demo is "it compiles for real")

- GitHub public repo; PyPI as **`ladder-plc`** (the name `ladder` is taken by
  an unrelated path library — import name stays `ladder` for now, revisit if
  it causes confusion).
- Docs site (mkdocs) with the IR spec front and center; the JSON Schema is
  the advertised, model-agnostic contract.
- Launch demo: one YAML file → four vendor artifacts → screen capture of TIA
  and Studio 5000 compiling them.
- Announce where controls people actually are: r/PLC, PLCTalk, the OpenPLC
  forum, GitHub topics `iec-61131-3` / `structured-text`; and the scientific
  controls community — an EPICS collaboration meeting talk and an ICALEPCS
  paper (accelerator labs share exactly this interlock/state-machine
  workload, and EPICS already has PLC-adjacent tooling appetite).

### OS4 — Grow contributors (ongoing after launch)

- Label backend work `good-first-issue` — a new vendor backend is a
  self-contained ~300-line module against a documented statement AST.
- Pattern library as the community commons: reviewed, tested, parameterized
  control patterns (the shared engineering knowledge PLC forums exchange as
  screenshots today).
- IR change process: lightweight RFCs; semver on `ir_version`; conformance
  suite so backends can claim support levels.
- Academic bridge: run LADDER against the Agents4PLC benchmark, invite the
  LLM4PLC/Agents4PLC groups to target the IR; the M5 benchmark gives
  researchers a citable artifact.
- Vendor relations: Siemens ships official open-source Openness extensions on
  NuGet and Rockwell ships a Python SDK client — both signal that third-party
  tooling is welcome; stay scrupulously inside their API terms.

---

## Risks to keep honest

| Risk | Mitigation |
|---|---|
| Vendor import formats drift between versions | pin tested versions per backend; CI fixtures; version matrix in docs |
| IR too weak for real programs → escape-hatch abuse | M2 reverse adoption forces the IR against reality early; track `st`-element usage as a metric |
| Safety liability perception | explicit non-SIL disclaimer; M4 verification story; never market as certified |
| Community never materializes | the lab still gets full value single-tenant; OS cost is low because hygiene is built in from M0 |
| Lab approval friction | start OS2 paperwork during M1, not after |
