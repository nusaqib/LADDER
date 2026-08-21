---
name: siemens-deploy
description: Build, address-map, and live-compile a LADDER project on Siemens TIA Portal via the TiaOpenness module, and triage compile errors. Use when a validated IR needs to land in TIA Portal (V19/V21).
---

# Siemens deployment: IR → TIA Portal, compiled 0/0

Prerequisites: a validated IR (see `ir-authoring`); Windows with TIA
Portal + Openness and the TiaOpenness PowerShell module (default
`E:/TIA_Portal/TIA_API`, overridable via `vendor: siemens:
tia_api_path`). PowerShell 5.1 only — Openness does not load under
PowerShell 7. Never attach to a human's open portal session; generated
scripts always start their own (`Connect-TiaPortal -New`).

## Standard path (standard blocks, SCL)

1. **IO map**: `<project>.iomap.yaml`, `siemens:` section of absolute
   addresses (`{address: "%I8.0"}`). Only scalar IO tags; BOOLs pack
   bits, words align. Without a map, emission auto-allocates scratch
   addresses — fine for compile checks, wrong on a panel. Cross-check
   against the panel drawings, not the old program: addresses are where
   as-built and as-designed quietly diverge.
2. **Build**: `ladder build <ir> -t siemens -o out [--iomap <map>]` →
   `out/siemens/`: `Types.udt`, `<Project>_DB.db` (UDT/array tags live
   in a global DB — TIA tag tables cannot hold them), `FB_<Program>.scl`
   per program, `PlcTags.csv`, `build.ps1`.
3. **Live compile**: `powershell -NoProfile -ExecutionPolicy Bypass
   -File out\siemens\build.ps1 [-Version 21.0]`. Headless portal →
   project → CPU → tags → import in types→DB→FB order → compile; exits
   nonzero on errors. The **openable TIA project** lands at
   `out\siemens\project\<Name>\<Name>.ap<ver>` (`-WorkDir` overrides) —
   a git-ignored, disposable build artifact: regenerate, never
   hand-edit, close it in TIA before rebuilding.

### Version and license realities

- The Openness assembly resolves **once per PowerShell process** and
  cannot switch; when both V19 and V21 are installed the default
  resolution can prefer V19 — pass `-Version` explicitly, and use a
  fresh process to change versions.
- Device creation and SCL import each need a **STEP 7 Professional**
  license *for that portal version*; safety compilation needs **STEP 7
  Safety**. License errors surface as misleading failures (a "catalog
  rejected" CPU, an import refusal) — read the inner exception before
  blaming the artifact.
- CPU catalog acceptance is per-machine (installed HSPs). Pin the real
  MLFB via `vendor: siemens: cpu` (e.g.
  `OrderNumber:6ES7 515-2FM01-0AB0/V2.9`); the build's candidate loop is
  a fallback, not a target choice.

### Compile triage

- *"not defined"* on a tag → missing PlcTags.csv row, or a complex tag
  referenced without its `"<Project>_DB".` prefix.
- Type conflicts → Siemens is strict about conversions; the lowering
  emits explicit `*_TO_*`, so a conflict usually means the IR type is
  wrong, not the renderer.
- Import refusals naming a license → the license, not the file.
- Address overlaps → two iomap rows collide; the emitter respects the
  map verbatim.
- A clean compile **immediately after** a previous clean compile proves
  nothing was re-checked — re-import a block to force a real compile
  when verifying a fix.

## Fail-safe (F-system) path — what changes and what to respect

Reproducing F-programs (F-CPU, F-DB, F-LAD, certified instructions) is
engine work layered on Openness, with hard platform rules a deployment
must respect:

- **F-attributes are XML-only.** A UDT's `IsFailsafeCompliant` and a
  DB's `ProgrammingLanguage=F_DB` cannot be set from SCL — SCL-created
  objects are standard and the safety program rejects them. F-compliant
  member types are `Bool, Int, DInt, Word, Time` (never `Byte` — which
  is why certified `DIAG` outputs cannot land in an F-DB; diagnostics go
  to a standard DB).
- **Certified instructions** (`EV1oo2DI`, `ESTOP1`, `SFDOOR`, ...) are
  imported as F-LAD SimaticML with the instance declared as an FB static
  carrying the full inlined interface and a pinned version; every pin
  present (unused → `OpenCon`, except unused box *outputs*, which omit
  the wire). `DIAG` may not be wired to a fail-safe parameter at all.
- **FlgNet importer quirks** (each cost a live failed import to learn):
  one wire per `Access` element; no parallel OR converging on a coil
  (use set/reset rungs or a flip-flop); flip-flop/edge storage must live
  in the F-DB, not a standard DB; input pins wire `IdentCon` then
  `NameCon`, output pins the reverse; the importer rejects `Time`
  literals on certified pins (`DISCTIME`/`TIME_DEL` are set in TIA and
  recorded as engineering decisions).
- **PROFIsafe F-destination addresses are never auto-assigned through
  Openness** — every F-module keeps the catalogue default and the
  compiler does not object, which is a silent commissioning landmine.
  Declare them in the hardware data (matching the BaseUnit DIP
  switches) and verify the built values read back.
- **Re-integration**: without ACK_REI logic, a passivated F-module stays
  passivated until CPU restart. Expect the compiler warnings; track the
  finding.
- Always run a behavioral check of generated safety XML **before**
  import when one exists (a rung-level simulator catching an
  un-negated reset input is cheaper than a commissioning surprise).

## Round trip and evidence

`Export-TiaToSpec -OutDir <dir>` then `ladder adopt siemens <dir>`
reconstructs IR from what TIA actually holds — diff against the source
IR to prove nothing was lost. Keep the compile transcript (`build.log`)
with the change record.

## Hard rules

- ASCII only in anything fed to PowerShell 5.1.
- Never commit `Siemens.Engineering*.dll` or any vendor binary.
- Never bypass TIA safety access protection; never modify a live or
  production safety project without explicit consent.
- A 0-error compile is evidence the generator works — never present it
  as commissioning approval or design validation.
