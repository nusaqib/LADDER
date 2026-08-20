---
name: siemens-deploy
description: Build, address-map, and live-compile a LADDER project on Siemens TIA Portal via the TiaOpenness module, and triage compile errors. Use when a validated IR needs to land in TIA Portal (V19/V21).
---

# Siemens deployment: IR → TIA Portal, compiled 0/0

Prerequisites: a validated IR (see `ir-authoring`); Windows machine with
TIA Portal + Openness and the TiaOpenness PowerShell module (default
`E:/TIA_Portal/TIA_API`, overridable via `vendor: siemens: tia_api_path`).

## Procedure

1. **IO map** (if hardware addresses are known — map §10): write
   `<project>.iomap.yaml` with a `siemens:` section of absolute addresses:

   ```yaml
   project: <ProjectName>
   siemens:
     flow_ok:  {address: "%I8.0"}
     horn:     {address: "%Q4.0"}
   ```

   Only scalar IO tags; BOOLs pack bits, words align. Without a map,
   emission auto-allocates scratch addresses — fine for compile checks,
   wrong for the real panel.

2. **Build**: `ladder build <project>.yaml -t siemens -o out [--iomap <map>]`
   Artifacts in `out/siemens/`: `Types.udt` (UDTs), `<Project>_DB.db`
   (global DB for UDT/array tags — TIA PLC tag tables cannot hold them),
   `FB_<Program>.scl` per program, `PlcTags.csv` (scalars), `build.ps1`.

3. **Live compile**: `powershell -NoProfile -ExecutionPolicy Bypass -File out\siemens\build.ps1 -Version 19.0`
   (headless portal → scratch project → CPU → tags → source import in
   types→DB→FB order → compile; exits nonzero on errors). Equivalent:
   `ladder verify <project>.yaml -t siemens -o out`.
   - Never attach to a human's open portal session; the script always
     starts its own (`Connect-TiaPortal -New`).
   - **V21 gotcha**: SCL import needs a STEP 7 Professional license
     registered for V21 in the Automation License Manager; on this
     machine only V19 carries it — pass `-Version 19.0` until that is
     fixed.
   - The only CPU accepted by this machine's catalog:
     `OrderNumber:6ES7 512-1SK01-0AB0/V2.9` (CPU 1512SP F-1 PN). Other
     targets: put the MLFB in `vendor: siemens: cpu`.

4. **Triage** compile output (the script prints per-error messages):
   - "not defined" on a tag → PlcTags.csv row missing (is it complex? then
     it must come from the DB, check the `"<Project>_DB".` prefix) or the
     tag table import failed earlier.
   - Type conflicts → check the IR type against usage; Siemens is strict
     about implicit conversions (the lowering emits explicit `*_TO_*`).
   - Import failed with license text → the V21 gotcha above.
   - Address overlaps → two iomap rows collide; the emitter packs BOOLs
     but respects the map verbatim.

5. **Round trip** (optional review artifact): in a portal session,
   `Export-TiaToSpec -OutDir <dir>` then `ladder adopt siemens <dir>` to
   reconstruct IR from what TIA actually holds — diff against the source
   IR to prove nothing was lost.

## Hard rules

- ASCII only in anything fed to PowerShell 5.1 (build.ps1 is emitted
  ASCII; keep it that way).
- Never commit `Siemens.Engineering.dll` or any vendor binary; the module
  reflection-loads from the user's licensed install.
- Generated logic must be reviewed by a qualified controls engineer before
  deployment; never present a 0-error compile as commissioning approval.
