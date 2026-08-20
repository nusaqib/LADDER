# LADDER

**L**LM-**A**ssisted **D**esign & **D**eployment of **E**ngineering **R**outines —
autonomous, vendor-agnostic PLC program generation.

An LLM (any LLM: hosted or local — the contract is a JSON Schema, not a model)
emits a small, declarative, verifiable intermediate representation. LADDER
validates it, lowers it deterministically, and per-vendor backends render real
engineering artifacts:

```
 LLM / human ──► LADDER IR (YAML/JSON, schema- + semantically-validated)
                    │  deterministic lowering (semantics locked in one place)
                    ▼
              neutral statement AST
                    │
      ┌─────────────┼──────────────┬───────────────┐
      ▼             ▼              ▼               ▼
   siemens       rockwell       plcopen         beckhoff
 TIA Portal V21  Studio 5000    PLCopen XML     TwinCAT 3
 SCL FBs + tag   V36 L5X with   2.01 / IEC      TcPOU + TcGVL
 CSV + Openness  ST routines,   61131-10        items
 build script    tasks, tags
```

The point: the model never writes vendor syntax. It selects patterns and fills
in parameters against one well-specified schema — a small, constrained,
checkable generation problem — while everything vendor-quirky lives in
deterministic code.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]

.venv\Scripts\ladder validate examples\vacuum_interlock.yaml
.venv\Scripts\ladder build examples\vacuum_interlock.yaml -t all -o out
.venv\Scripts\ladder verify examples\vacuum_interlock.yaml -t iec   # matiec, vendor-free
.venv\Scripts\ladder schema -o ir-schema.json    # the LLM contract
.venv\Scripts\ladder targets
.venv\Scripts\python -m pytest
```

## What the IR expresses (v0.1)

Declarative logic elements, not rungs: `interlock` (fail-safe, latching with
manual reset), `alarm` (on-delay, latching with ack, severity), `timer`
(TON/TOF/TP), `state_machine` (lowered to CASE), `assign`, and `st` (neutral
Structured Text escape hatch). Full reference: [docs/IR-SPEC.md](docs/IR-SPEC.md).

Semantics (what "latching interlock" *means*) are locked in
`src/ladder/ir/lower.py`, once, for every vendor — backends only render.

## Layout

```
src/ladder/ir/          IR: pydantic model, expression language, semantic
                        validation (V01–V08), lowering to statement AST
src/ladder/backends/    dialects.py (ST dialect renderers) + one module
                        per vendor; register via backends/base.py
src/ladder/patterns/    parameterized IR fragments (grows from mined
                        reference programs)
examples/               IR documents
docs/                   IR spec, roadmap
```

## Vendor engines vs. backends

Backends (this repo, today) **generate artifacts**. Engines (next phase)
**drive vendor tools** to import/compile/deploy them and adopt real project
structure:

- **Siemens** — delegates to the validated
  [TIA_API / TiaOpenness](../TIA_API/README.md) PowerShell module
  (Openness, V21). `build.ps1` emitted per project is the seam. Project
  structure will be reverse-engineered from the reviewed reference TIA program.
- **Rockwell** — L5X imports directly into Studio 5000 V36; the Logix Designer
  SDK is the automation path. Structure to be reverse-engineered from the
  reference Studio 5000 program.
- **Beckhoff / PLCopen** — native items / tc6 XML; Automation Interface later.

## Status

| Piece | State |
|---|---|
| IR model + JSON Schema export | ✅ v0.1 |
| Expression language (neutral ST subset, parsed AST) | ✅ |
| Semantic validation (identifiers, resolution, fail-safe rules) | ✅ V01–V08 |
| Lowering (interlock/alarm/timer/state machine semantics) | ✅ |
| Backends: siemens / rockwell / plcopen / beckhoff / iec | ✅ artifacts emit, tests green |
| `ladder verify` + vendor-free CI (matiec checks emitted IEC ST) | ✅ |
| **Live TIA build: portal → project → CPU → tags → SCL → compile** | ✅ **0 errors on V19** (V21 SCL import needs a STEP 7 license — see AGENTS.md) |
| Reverse adoption: `ladder adopt siemens` (Export-TiaToSpec → IR) | ✅ round-trip proven: IR → SCL → TIA → SimaticML → IR |
| Simulator (`ladder.sim`): scan-based interpreter, real timer semantics | ✅ scenario tests pin interlock/alarm/state-machine behavior |
| Pattern invocation (`element: pattern` → expansion before validation) | ✅ `motor_starter`, `valve_with_feedback`; see [examples/pump_skid.yaml](examples/pump_skid.yaml) |
| Static lint W01–W05 (unused/multi-written tags, SM reachability) | ✅ surfaced by `ladder validate` |
| `ladder prompt` — model-agnostic generation bundle for any LLM | ✅ schema + rules + patterns in one paste-able doc |
| `ladder test` — declarative acceptance scenarios in the simulator | ✅ [docs/SCENARIOS.md](docs/SCENARIOS.md) |
| `ladder generate` — full loop: any LLM → validate → feedback → accept | ✅ provider-neutral (stdin/stdout shell contract) |
| [Benchmark](benchmarks/README.md): spec → IR tasks, simulation-scored | ✅ 3 tasks with CI-verified references; `ladder bench` scores any model |
| `scale` element — analog raw→EU scaling with per-dialect conversion | ✅ |
| Studio 5000 L5X import validation | ⬜ manual: open `out\rockwell\*.L5X` in v36 (SDK 2.x for automation) |
| Vendor engines (structure adoption from reference programs) | ⬜ next — see [docs/ROADMAP.md](docs/ROADMAP.md) |
| Pattern library from reference programs | ⬜ seeded |
| LAD/FBD rendering, formal checks, simulation | ⬜ roadmap |

Agent/LLM working notes (tool-agnostic): [AGENTS.md](AGENTS.md).
