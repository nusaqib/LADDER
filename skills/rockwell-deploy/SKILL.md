---
name: rockwell-deploy
description: Build a Studio 5000 L5X from LADDER IR, wire alias tags to module IO, import into Logix Designer v36, and triage import errors. Use when a validated IR targets a Rockwell/Allen-Bradley controller.
---

# Rockwell deployment: IR → Studio 5000 L5X

Prerequisites: a validated IR (see `ir-authoring`); Studio 5000 Logix
Designer (v36 tested) for import. The Logix Designer SDK 2.x Python
client automates import/verify; with SDK 1.1 or none, import is a
2-minute manual step — do it, don't skip the verification.

## Procedure

1. **IO map — aliases, never addresses.** Logix binds tags to module IO
   through alias tags:

   ```yaml
   rockwell:
     flow_ok: {alias: "Local:1:I.Data.0"}
     horn:    {alias: "Local:2:O.Data.0"}
   ```

   Emission adds `TagType="Alias" AliasFor=...`. The alias target's
   module must exist in the project's IO tree with matching slot and
   connection format — aliases resolve at *verify* time, and a wrong
   slot is a verify error, not an import error. Unmapped IO stays as
   base tags (fine for logic review, wrong on hardware).

2. **Build**: `ladder build <ir> -t rockwell -o out [--iomap <map>]` →
   `out/rockwell/<Project>.L5X`, controller-scoped
   (SoftwareRevision 36.00; processor from `vendor: rockwell:
   processor`, default 1756-L85E; continuous task for cyclic programs,
   periodic tasks with the IR interval otherwise). Programs with
   `language: ladder` emit **native RLL rung routines**; others emit ST.

3. **Import**: open the L5X directly as a new project (it is
   controller-scoped), or File → Import Component into an existing one.
   **Always verify** (Ctrl+Shift+V) and read the whole output — Logix
   verify warnings are load-bearing (unreferenced aliases, connection
   faults) in a way import success is not.

4. **Dialect facts** (handled by the backend — listed so errors and
   reviews make sense):
   - ST timers are `FBD_TIMER` driven by `TONR/TOFR`; presets and
     accumulators are DINT **milliseconds**; done is `.DN`, elapsed
     `.ACC`. RLL routines use native `TIMER` tags with `TON/TOF`
     instructions and the preset in the tag's `PRE` member.
   - **No TP instruction exists in Logix ST** — the build refuses TP
     timers; redesign (TON + logic) rather than approximating silently.
   - UDT BOOL members are `BIT`s packed on hidden SINT hosts
     (`ZZZZZZZZZZ...`) — Studio 5000 displays them normally; do not
     "fix" the XML.
   - No `TRUE/FALSE` literals in ST bodies (1/0 emitted); identifiers
     ≤40 chars (the V01 limit *is* the Logix limit).
   - RLL has no NOT-of-branch: conditions are De Morgan-normalized to
     XIO contacts; compares render as EQU/NEQ/GRT/GEQ/LES/LEQ input
     instructions.

5. **Verify-error triage**:
   - *Unknown instruction TONR* → controller family too old for
     FBD_TIMER ST instructions; target 5580/5380-class.
   - *Alias target not found* → module missing from the IO tree, wrong
     slot, or wrong connection format; create/fix the module — never
     re-point the alias to make the error go away.
   - *Datatype conflict on import* → a same-named UDT already exists
     with different members; reconcile deliberately (rename in `types:`
     or migrate the old UDT) — Logix will not merge.
   - *Downloaded-vs-offline mismatch on a live controller* → stop;
     correlation of a running plant is a commissioning activity with its
     own procedure, not part of artifact deployment.

6. **Safety controllers (GuardLogix)**: LADDER emits standard task
   logic. Safety-task logic, safety-signature-locked instructions, and
   SIL-rated IO belong to the GuardLogix safety workflow (safety task,
   safety signature, IEC 61508-certified instructions) — interface to it
   through mapped standard tags and document the boundary; never present
   standard-task logic as the safety layer.

## Evidence and change control

Keep the verify output with the change record. L5X is text — diff it
between builds; an unexplained diff in a rung you didn't change means a
generator or ordering bug worth catching before the plant does. The
project's safety and interlock semantics are already pinned by scenarios
and (where applicable) nuXmv proofs — the Logix import must not require
any hand edit; if it does, fix the backend, not the artifact.

## Hard rules

- L5X structure stays clean-room from Rockwell's public documentation;
  never paste vendor-generated XML wholesale into the emitter.
- Never commit Logix SDK binaries.
- A clean verify is not commissioning approval; qualified review
  applies, and generated logic is not certified safety logic.
