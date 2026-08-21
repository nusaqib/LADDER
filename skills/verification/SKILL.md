---
name: verification
description: Verify LADDER output at every level - scenario simulation, static lint, matiec compilation, nuXmv formal proofs - and report what each check does and does not prove. Use before any deployment or when a user asks "is this correct/safe?".
---

# Verification: what to run, what it proves, what it cannot

LADDER's value over raw code generation is that its output is
*checkable*. A principal engineer's job here is not just running the
layers — it is stating precisely what each result does and does not
establish, because overclaiming verification on protective logic is
worse than not verifying.

Run the layers in order; each is cheap until the last.

## 1. Validate + lint (always)

`ladder validate` / `ladder check`: schema, semantics V01–V11, warnings
W01–W06. Treat warnings as findings with dispositions, not noise:
- W01 unwritten output / W03 unread input → missing logic, a dead IO
  point, or faithfully-carried future IO. Disposition each; a project
  README should state the expected warning baseline and why (e.g. "38
  W03 = the unmapped front-end tags, kept deliberately").
- W02/W06 multi-writer → an ownership dispute. Last-writer-wins is a
  real scan-order bug generator; resolve in the design.
- W04/W05 → sequence dead-ends; every state needs an exit or a reason.

**Proves**: structural sanity. **Cannot prove**: any behavior.

## 2. Scenario simulation (always)

`ladder test <ir> <scenarios>` — scan-accurate simulator, real
TON/TOF/TP timing. Scenarios are the *acceptance* record: they pin
seal-ins, trip-and-reset cycles (including "restore ≠ re-arm"), debounce
windows, ack-while-standing, first-out capture, edge-vs-level key
behavior, sequence walks and aborts. No suite = no definition of done —
write it (see `design-intake` §9) before claiming anything.

Coverage discipline: every requirement in the design map should be
exercised by at least one step; every *deliberate residual* (documented
quirks kept for fidelity) should be **characterized** by a scenario so a
future "fix" shows up as a diff.

**Proves**: the specified behaviors, for the specific timings simulated.
**Cannot prove**: absence of unspecified bad behaviors, or behavior at
timings you didn't simulate — that is what layer 4 is for.

## 3. Vendor-free compile (always; it is what CI runs)

`ladder verify -t iec` — matiec's `iec2c` compiles the emitted strict
IEC 61131-3 (ST, IL, and textual SFC bodies). The emitted PLCopen XML
additionally validates against the official tc6_0201 XSD in CI.

**Proves**: standards conformance of the artifacts with zero vendor
software — outside contributors get the same signal the lab gets from a
real import. **Cannot prove**: vendor-specific acceptance (that's the
vendor skills) or behavior.

## 4. Formal proofs (whenever protective elements exist)

`ladder model <ir> -o out` emits one SMV model per checkable program
(UDT members supported; arrays and REAL math skipped — the skip list is
part of the result). Then `ladder verify -t smv` (env `NUXMV_BIN`)
checks the auto-generated theorems:

- per `interlock`: `output -> permissives` — the permit is never TRUE in
  any reachable state with a permissive down;
- per `dual_channel`: `output -> chA AND chB`;
- per `search_chain`: `complete -> precondition`, plus walk-order
  monotonicity for every station pair;
- per `alarm_group`: `unacked -> active`, `active <-> first_out ≠ 0`.

Timers are **soundly over-approximated** (the done bit may rise on any
scan while enabled), so a proved property holds for *every* preset and
scan rate — strictly stronger than any simulation. Engine selection
matters at scale: BDD (`-dcx`) is fine to ~10² variables; for hundreds
of variables use IC3 (`read_model; flatten_hierarchy; encode_variables;
build_boolean_model; check_invar_ic3`) — invariant proofs on
250-variable safety programs complete in minutes under IC3 where BDD
runs for hours.

A **counterexample is a real reachable trace**: decode it against the IR
step by step and fix the design; never weaken the property to make it
pass. User-supplied invariants beyond the auto-theorems are welcome —
add them to the emitted SMV and record them in the verification report.

**Proves**: the stated invariants of the modeled logic, exhaustively.
**Cannot prove**: properties of what was skipped (say which programs),
liveness you didn't state, or anything about the physical layer.

## 5. Vendor toolchain (when present)

Siemens: `ladder verify -t siemens` (headless build, 0 errors required;
remember a compile immediately after a clean compile re-checks nothing —
force a re-import when verifying a fix). Rockwell: L5X import + verify.
Where a rung-level pre-import simulator exists for generated safety XML,
run it before every import.

## Reporting discipline

Report per layer with counts and skips: "validate OK (38 expected W03);
9/9 scenarios; 79/79 theorems (Safety via BDD, Certified via IC3); 3
programs modeled, 0 skipped; TIA V21 compile 0 errors." Never compress a
partial run into "verified".

And the standing boundary, stated every time it matters: these layers
verify the **modeled logic**. They do not certify SIL/PL safety
functions, they do not validate sensors, wiring, PROFIsafe parameters,
passivation behavior, or operators, and they are not a substitute for
the facility's functional-safety lifecycle and commissioning tests.
