# LADDER roadmap

Two tracks: **engineering milestones** (M0–M6) and the **open-source /
community track** (OS1–OS4). Status as of 2026-08-20. Items still open
are marked by what gates them: `[user]` needs a decision or action only
the project owner can take; `[machine]` needs software/licenses not on
this machine; `[eng]` is engineering that can proceed any time.

---

## Where LADDER sits (research + ecosystem context)

Academic work on LLM PLC programming — LLM4PLC, Agents4PLC, online-
feedback ST training — targets **raw Structured Text generation**.
LADDER's niche is different and, as far as we know, unoccupied: a
*declarative, verifiable, vendor-neutral IR* that a **human authors
first** (the LLM is an optional catalyst), with *deterministic* lowering,
*formal verification*, and *real vendor toolchain* deployment. The open
ecosystem we interoperate with: matiec (CI compiles our IEC text), the
official PLCopen tc6 XSD (CI validates our XML), nuXmv (proves our
auto-theorems), IronPLC / OpenPLC / Beremiz (future runtime targets),
blark and the `l5x` Python lib (future reverse adoption).

---

## Engineering milestones

### M0 — IR core + artifact backends ✅ (Aug 2026)

IR model, expression AST, validation, deterministic lowering, JSON
Schema export; five emitting backends (siemens, rockwell, plcopen,
beckhoff, iec).

### M1 — Close the loop on real tools ✅ (core done Aug 2026)

- ✅ Siemens: headless portal → project → CPU → tags → sources →
  **compile 0 errors**, on **V19 and V21** (the V21 license landed);
  the openable TIA project is a build artifact under `out/`.
- ✅ Vendor-free CI: matiec compiles emitted ST/IL/textual-SFC; emitted
  PLCopen XML validates against the official tc6_0201 XSD.
- ✅ `ladder verify` per-target checkers; `ladder deploy` materializes
  IDE projects per the manifest.
- ⬜ `[user/machine]` Rockwell automated import (Logix Designer SDK 2.x
  Python client not installed; manual L5X import verified by hand).
- ⬜ `[machine]` Beckhoff: TwinCAT not installed; artifacts emit, no
  live build.

### M2 — Vendor engines + reverse adoption ✅ (core done Aug 2026)

- ✅ Reverse adoption: `ladder adopt siemens` (Export-TiaToSpec → IR),
  round-trip proven.
- ✅ **The reference program was reverse-engineered and reproduced
  exactly** (SR PPS, private repo): three-layer F-architecture, 144/144
  tags and addresses verified against the live export, F-CPU + PROFIsafe
  hardware via the TIA_API sheet pipeline, as-built F-DB/UDTs, F-LAD
  blocks with 66 certified instruction instances regenerated and proved
  by a rung simulator before import, compiled 0 errors on **V21**, plus
  the full 14-screen WinCC Unified HMI. V21 Openness findings fed back
  into the engine (F-parameter target discovery) and this repo
  (versioned targets, `deploy_script`).
- ✅ What the reference taught became *generic* capability here:
  `dual_channel`, `search_chain`, UDT-aware model checking, per-program
  languages, modular IR.
- ⬜ `[eng]` Reverse adoption for Rockwell (`l5x` lib) and TwinCAT
  (blark).
- ⬜ `[user]` A Studio 5000 reference program for the Rockwell engine.

### M3 — Pattern library + richer IR ✅ (Aug 2026)

- ✅ IR v0.2: UDTs, arrays, typed member validation, `scale`,
  `alarm_group` (annunciator + first-out), `dual_channel` (1oo2),
  `search_chain`, **`pid`** (clamping anti-windup, bumpless freeze),
  per-program `language` (all five IEC languages), modular IR
  directories, IO maps.
- ✅ Patterns: `motor_starter`, `valve_with_feedback`; invocation +
  expansion.
- ⬜ `[eng]` Motion axis element (PLCopen MC vocabulary) — deliberately
  deferred until a real motion reference machine exists; an RFC per
  [VERSIONING](VERSIONING.md) is the entry path.
- ⬜ `[eng]` More mined patterns as further reference programs arrive.

### M4 — Verification & simulation ✅ (Aug 2026)

- ✅ Scan-accurate simulator (real timer semantics) + declarative
  scenario suites as the acceptance gate.
- ✅ Static lint W01–W07.
- ✅ Formal path: `ladder model` emits SMV via symbolic execution
  (timers soundly over-approximated; UDT members supported);
  auto-theorems per interlock / dual_channel / search_chain /
  alarm_group; **user-supplied invariants** via a properties file;
  proved with nuXmv (BDD, or IC3 at scale).

### M5 — Model-agnostic LLM harness + benchmark ✅ (Aug 2026)

- ✅ `ladder prompt` (the contract for any model), `ladder generate`
  (closed loop, any CLI), `ladder bench`.
- ✅ Benchmark: **6 tasks** (conveyor, tank, mixer, annunciator, area
  search, PID trim), scenario-scored, CI-verified references.
- ⬜ `[user]` Publish cross-model results (needs LLM CLIs configured on
  a machine).
- ⬜ `[eng]` Vendor compile as an optional final loop stage.

### M6 / v1.0 — Stability contract (in progress)

- ✅ Backend plugin API documented ([BACKENDS](BACKENDS.md)) with a real
  `ladder.backends` entry-point loader.
- ✅ Versioning + RFC process documented ([VERSIONING](VERSIONING.md));
  versioned tool targets (`name@version`) separate the tool axis from
  the IR axis.
- ⬜ `[eng]` Conformance suite packaging (the examples + scenario corpus
  as a runnable backend-conformance check).
- ⬜ `[user]` Field-name review against adopted programs from a second
  facility; then freeze IR 1.0.
- ⬜ `[user]` Two independent users outside the lab.

---

## Open-source & community track

### OS1 — Be releasable from day one ✅

LICENSE (BSD-3-Clause-LBNL + safety disclaimer), CONTRIBUTING,
**CODE_OF_CONDUCT, SECURITY**, CI badge-ready, docs slope
(getting-started → tutorial → guide → reference), skills. Hard legal
guardrails hold: no vendor binaries, no lab-internal safety content
(the PPS reproduction lives in a private repo that *consumes* LADDER),
clean-room formats only.

### OS2 — Institutional approval ⬜ `[user]`

LBNL open-source release process (IPO rights check, DOE compliance,
export-control consult). Start during M6, not after.

### OS3 — Public launch ⬜ `[user]` (gated on OS2)

PyPI as `ladder-plc`; docs site; launch demo (one YAML → all vendor
artifacts → TIA/Studio 5000 compiling); announce to r/PLC, PLCTalk,
OpenPLC forum, and the scientific-controls community (EPICS meeting,
ICALEPCS paper).

### OS4 — Grow contributors ⬜ (post-launch)

Backend `good-first-issue`s, the pattern library as community commons,
RFC process in use, Agents4PLC benchmark bridge, vendor relations.

---

## Risks to keep honest

| Risk | Mitigation |
|---|---|
| Vendor import formats drift between versions | versioned targets (`name@version`); per-version quirks keyed in one backend; CI fixtures |
| IR too weak for real programs | the PPS reproduction forced it against a real safety program; track `st`-element usage as the escape-hatch metric |
| Safety liability perception | explicit non-SIL disclaimer everywhere; verification report states limits; never market as certified |
| Community never materializes | the lab gets full value single-tenant; OS cost stays low because hygiene is built in |
| Lab approval friction | OS2 starts now `[user]` |
