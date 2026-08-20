---
name: rockwell-deploy
description: Build a Studio 5000 L5X from LADDER IR, wire alias tags to module IO, import into Logix Designer v36, and triage import errors. Use when a validated IR targets a Rockwell/Allen-Bradley controller.
---

# Rockwell deployment: IR → Studio 5000 L5X

Prerequisites: a validated IR (see `ir-authoring`); Studio 5000 Logix
Designer (v36 tested) for import. The Logix Designer SDK's Python client
(SDK 2.x) automates import/verify; with SDK 1.1 or none, import is a
2-minute manual step.

## Procedure

1. **IO map**: Rockwell binds by **alias tags**, never absolute addresses:

   ```yaml
   project: <ProjectName>
   rockwell:
     flow_ok: {alias: "Local:1:I.Data.0"}
     horn:    {alias: "Local:2:O.Data.0"}
   ```

   Emission then adds `TagType="Alias" AliasFor=...` tags; unmapped IO
   stays as base tags (fine for a logic review, wrong on hardware).

2. **Build**: `ladder build <project>.yaml -t rockwell -o out [--iomap <map>]`
   → `out/rockwell/<Project>.L5X`, a controller-scoped import
   (SoftwareRevision 36.00, processor from `vendor: rockwell: processor`,
   default 1756-L85E; continuous task for cyclic programs, periodic tasks
   with the IR interval otherwise).

3. **Import**: Studio 5000 → New/Open project → File → *Import Component*
   (or open the L5X directly as a new project since it is
   controller-scoped) → verify (Ctrl+Shift+V). With the SDK 2.x Python
   client, script open→import→verify headlessly instead.

4. **Know the dialect quirks** (already handled by the backend — listed so
   errors make sense):
   - Timers are `FBD_TIMER` driven by `TONR`/`TOFR` in ST; presets and
     accumulators are DINT **milliseconds**; done bit `.DN`, elapsed
     `.ACC`. There is no TP instruction in Logix ST — the IR validator
     lets TP through for other targets, but the rockwell build will
     refuse it; redesign with TON + logic.
   - UDT BOOL members are Logix `BIT`s packed on hidden SINT hosts
     (`ZZZZZZZZZZ...` members) — Studio 5000 shows them normally.
   - No `TRUE`/`FALSE` literals in ST bodies; the backend emits 1/0.
   - Identifiers ≤40 chars (the validator's V01 limit *is* the Logix
     limit).

5. **Triage** verify errors:
   - "Unknown instruction TONR" → controller family too old for FBD_TIMER
     ST instructions; target a Logix 5580/5380 class processor.
   - Alias target not found → the module in the iomap (`Local:1:...`)
     doesn't exist in the project's IO tree; create the module or fix the
     slot.
   - Datatype conflicts on import → a same-named UDT already exists in the
     target project with different members; rename in `types:` or remove
     the stale UDT.

## Hard rules

- L5X structure is written clean-room from Rockwell's public L5X
  documentation; keep it that way — never paste vendor-generated XML
  wholesale into the emitter.
- Never commit Logix SDK binaries.
- A clean verify is not commissioning approval; qualified review applies.
