---
name: beckhoff-deploy
description: Deploy LADDER output to Beckhoff TwinCAT 3 - project assembly from emitted TcPOU/TcDUT/TcGVL, PLCopen XML import, task binding, TcUnit-style checks. Use when the target runtime is TwinCAT.
---

# Beckhoff deployment: the friendliest vendor target

TwinCAT is text on disk (XML project files, CDATA-wrapped IEC inside),
free to engineer (XAE, license-free engineering mode; renewable 7-day
runtime licenses), and imports PLCopen XML natively - the lowest-wall
vendor loop. Reference: `docs/reference/vendors/beckhoff-twincat.md`.

## What LADDER emits

`ladder build -t beckhoff` -> `out/beckhoff/`: one `.TcPOU` per
program (declaration + ST implementation), `.TcDUT` per UDT, a
`.TcGVL` with the global tags (iomap-located `AT %I*/%Q*` when bound).
Deterministic IDs, so re-generation diffs cleanly.

## Assembling a runnable solution

1. Once per project: create a TwinCAT solution in XAE (or script it via
   the Automation Interface), add an empty PLC project, delete the
   sample POU.
2. Add the emitted files (Existing Item, or reference them from
   `.plcproj` - they're MSBuild items; a committed template .plcproj
   listing `out/beckhoff/*.TcPOU` etc. makes the whole step one copy).
3. Bind the PROGRAM(s) to a cyclic PlcTask in scan order (one task;
   order = the IR's program order).
4. Alternative path for graphic bodies: PLC project -> Import
   PLCopenXML -> `out/plcopen/<Name>.xml` (LD/FBD/SFC render as real
   graphic editors' content).
5. Build (F7 / `msbuild`). Zero errors is the gate; TwinCAT's ST is
   close to strict IEC, so surprises here usually mean a real emitter
   bug - report upstream, don't hand-patch `out/`.

## IO linking

Emitted variables use deferred addresses (`AT %I*`); after the EtherCAT
scan finds the terminals, link variables to channels in the Solution
Explorer (or Automation Interface `ConsumeMapping` for scripted links).
Keep the link map exported next to the iomap - it is the Beckhoff
equivalent of the Siemens address report.

## Verification on target

- Activate configuration onto the local runtime (no hardware needed:
  run-time in simulation ticks the task) and watch the program live -
  the cheapest real-runtime smoke test any vendor offers.
- Site standard for on-target regression is TcUnit (FB-based xUnit);
  LADDER's scenarios already cover IR-level behavior, so reserve TcUnit
  for integration seams (IO mapping, task timing) rather than
  duplicating logic tests.

## Boundaries

- No Automation Interface driver ships in LADDER yet (roadmap): project
  assembly is the manual/templated step above; everything inside the
  PLC project is generated.
- TwinCAT motion (MC axes), NC tasks, and C++ modules are out of scope
  for generated logic - integrate them as consumers of the generated
  program's outputs.
