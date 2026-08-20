---
name: verification
description: Verify LADDER output at every level - scenario simulation, static lint, matiec compilation, nuXmv formal proofs - and report what each check does and does not prove. Use before any deployment or when a user asks "is this correct/safe?".
---

# Verification: what to run, what it proves

LADDER's value over raw code generation is that its output is *checkable*.
Run the layers in this order; each is cheap until the last.

## 1. Validate + lint (always)

`ladder validate <project>.yaml` — schema, semantics (V01–V11), and
warnings W01–W06. Warnings are design smells, not noise: an unwritten
output (W01) or two writers on one tag (W02/W06) is usually a real bug.
Fix the IR, don't rationalize.

## 2. Scenario simulation (always)

`ladder test <project>.yaml <project>.scenarios.yaml` — the scan-accurate
Python simulator (real TON/TOF/TP timing) runs the acceptance scenarios
from the design map. This pins *behavior*: seal-ins, trip-and-reset
cycles, debounce windows, first-out capture, sequence walks.
No scenarios? Write them first (see `design-intake` §9) — an IR without
scenarios has no definition of done.

## 3. Vendor-free compile (always, CI-friendly)

`ladder verify <project>.yaml -t iec -o out` — matiec's `iec2c` compiles
the emitted strict IEC 61131-3 (ST and IL bodies). Env: `MATIEC_BIN`,
`MATIEC_LIB`. This proves the artifacts are standard-conformant with zero
vendor software — it is what CI runs on every push.

## 4. Formal proofs (whenever interlocks or alarm groups exist)

`ladder model <project>.yaml -o out` emits one SMV model per checkable
program, then `ladder verify -t smv` (env `NUXMV_BIN`) proves:

- per interlock: `output -> permissives` — the permit is never TRUE in
  any reachable state with a permissive down;
- per alarm group: `unacked -> active` and `active <-> first_out <> 0`.

Timers are soundly over-approximated (the done bit may rise on any scan
while enabled), so a proved property holds for **every** preset and scan
rate — strictly stronger than any amount of simulation. Skipped programs
(UDT/array refs, REAL math, raw st) are listed; say so in the report
rather than implying they were proved. A counterexample from nuXmv is a
real reachable trace — decode it against the IR and fix the design.

## 5. Vendor compile (when the vendor tool is present)

- Siemens: `ladder verify -t siemens -o out` runs the emitted build.ps1
  headless (see `siemens-deploy`).
- Rockwell: manual L5X import/verify, or SDK 2.x (see `rockwell-deploy`).

## Reporting discipline

State results per layer, with counts ("5 scenarios PASS, 2 models proved,
1 program skipped: REAL math"). Never summarize a partial run as "verified".
And the standing disclaimer: none of this certifies SIL/PL safety
functions — formal proofs cover the modeled logic, not sensors, wiring,
or the runtime.
