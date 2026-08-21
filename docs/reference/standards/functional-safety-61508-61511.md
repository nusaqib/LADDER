# Functional safety (IEC 61508 / 61511) — vocabulary and stance

> Normative sources: IEC 61508 (basic functional safety, parts 1-7) and
> IEC 61511 (process-industry sector standard); for machinery, ISO 13849
> (PL levels) and IEC 62061. These are original orientation notes — the
> standards themselves are the only citable authority for requirements.

## The vocabulary you need to read safety specs

- **Safety function**: a specific hazard-mitigating function (e.g. "close
  the beam shutter when a door opens"), with a defined safe state.
- **SIL (Safety Integrity Level)** 1–4: the *reliability requirement*
  assigned to a safety function — not a property of a product or a
  programming language. ISO 13849's PL a–e is the machinery-world analog.
- **SIF / SIS**: safety instrumented function / system (61511 terms) —
  sensor + logic solver + final element as one loop.
- **Architectures**: `1oo1` (single channel), `1oo2` (either of two can
  demand the safe action — trips are OR'd, run-permits are AND'd),
  `2oo3` (voting). PROFIsafe F-DI 1oo2 evaluation = the sensor half of a
  1oo2 loop; see [profisafe](profisafe.md).
- **Proof test, PFD, dangerous undetected failure**: the reliability
  math (61508-6). Outside LADDER's scope — belongs to the safety
  engineer's SIL verification, not to code generation.
- **Safety lifecycle**: hazard analysis → allocation → **safety
  requirements specification (SRS)** → design → verification →
  validation → operation/modification, each phase with review gates.
  A code generator lives inside "design"; it never substitutes for the
  lifecycle around it.

## What the standards imply for *generated* logic

61508-3 (software) cares about: traceable requirements, restricted
language subsets, defensive coding, verification evidence, and tool
qualification. Two consequences for LADDER-style tooling:

1. **Tool classification**: a code generator is an *offline support
   tool* (61508-3 T2/T3 depending on whether its output is verified).
   Because every LADDER artifact is re-verified downstream — vendor
   compiler, scenario simulation, model checking, and for the Siemens
   F-system the certified F-compiler's own signature — the burden sits
   where it should: on verifying the *output*, not on certifying the
   generator. Keep it that way; never claim the generator is qualified.
2. **The patterns the IR bakes in are the standard's defensive idioms**:
   de-energize-to-trip (1 = OK, 0 = safe/trip), reset-dominant latches,
   manual reset after trip, no automatic restoration of a completed
   search, discrepancy monitoring on redundant inputs, explicit
   acknowledge paths. These come from 61511/13849 practice and are the
   reason the elements exist instead of free-form logic.

## LADDER's stance (state it everywhere, verbatim-equivalent)

LADDER-generated logic is **not certified** for SIL/PL-rated safety
functions. Formal proofs and simulations are *evidence*, not
certification. Anything personnel-protecting must go through the
facility's safety lifecycle: qualified engineers, certified logic
solvers/instructions where required, independent validation, and
configuration control. The SR PPS reproduction exists in a private repo
precisely because it is a study of a personnel protection system, not a
deployable one.
