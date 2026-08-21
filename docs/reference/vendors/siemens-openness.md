# Siemens TIA Portal Openness — working API notes (V19/V21)

> Official docs: "TIA Portal Openness: API for automation of engineering
> workflows" (Siemens manual, per TIA version, on SIOS), plus the object
> model help shipped with TIA. **Never vendor `Siemens.Engineering*.dll`
> into a repo** — resolve it from the installed Portal at runtime.
> Everything below was verified against real V19 and V21 installs;
> claims are version-tagged where they differ.

## Process and assembly model

- Openness is an in-process CLR API: your process loads
  `Siemens.Engineering.dll` for **one specific TIA version** and that
  binding is **process-wide and permanent** — the first resolved
  assembly wins for the process lifetime. On machines with V19+V21
  side-by-side the resolver *prefers the older/classic* one; if you need
  V21, **pin it before anything else touches Siemens.Engineering**
  (LADDER practice: `Connect-TiaPortal -New -Version 21.0` first, even
  if you immediately disconnect).
- Never attach to a human's live session for automation. Always start a
  fresh headless instance (`TiaPortalMode.WithoutUserInterface`); users
  keep their portal, we keep ours.
- Firewall/permissions: the first Openness connection per user needs the
  Openness group membership (`Siemens TIA Openness`) and a one-time
  confirmation unless whitelisted.

## The object tree (the 20% used for the 80%)

```
TiaPortal
└─ Projects.Create/Open(path)            # path is DirectoryInfo of the *parent*
   ├─ Devices                            # stations (PLC, HMI, IO devices)
   │   └─ DeviceItems (recursive!)       # racks → modules → submodules/channels
   │       └─ GetService<...>()          # role interfaces hang off items:
   │           NetworkInterface, AddressController, ...
   ├─ Subnets / IoSystems                # PROFINET wiring
   └─ PLC software: DeviceItem.GetService<SoftwareContainer>().Software
       ├─ BlockGroup.Blocks / Groups     # OBs, FBs, FCs, DBs
       ├─ TypeGroup.Types                # UDTs (PlcTypes)
       ├─ TagTableGroup.TagTables        # PLC tag tables
       └─ ExternalSourceGroup            # SCL/AWL/DB source import path
```

Key idioms:

- **Attributes** are dynamic: `GetAttribute("Name")` /
  `SetAttribute(name, value)`; discover with
  `GetAttributeInfos()` (each has `Name` + `AccessMode`). AccessMode
  saying ReadWrite is **not a guarantee the write succeeds** (see the
  F-table below).
- **Catalog placement**: `Devices.CreateWithItem("OrderNumber:6ES7...
  /V2.9", name, station)`; module into a rack:
  `DeviceItems.CanPlugNew(mlfb, name, pos)` then `PlugNew`.
- **Compile**: `GetService<ICompilable>().Compile()` → walk the
  `CompilerResult` message tree; `State`, `ErrorCount`, `WarningCount`.
  Treat warnings as data — print them all; diffs against a reference
  project's warning count catch regressions.
- **Import/export**: blocks/UDTs via SimaticML XML
  (`BlockGroup.Blocks.Import(FileInfo, ImportOptions.Override)`,
  `TypeGroup.Types.Import(...)`) — see
  [siemens-simatic-ml](siemens-simatic-ml.md). Text sources (SCL) go via
  `ExternalSourceGroup` then `GenerateBlocksFromSource()`.
  Order matters: **UDTs before DBs that use them** — a DB import fails
  with `Data type "X" is unknown` otherwise.

## Version quirk table (tested)

| topic | V19 | V21 |
|---|---|---|
| SimaticML stamped for V19 | native | imports fine (upward compatible) |
| `Failsafe_FDestinationAddress` write | rejected | rejected — GUI-only on both; attribute lives on a child DeviceItem where it even *reports* ReadWrite, and `SetAttribute` still throws. Budget a documented manual step. |
| `Failsafe_FMonitoringtime` | read-only until the manual-assignment flag | same |
| HMI `HmiConnection.Create(name)` | n/a (project-dependent) | only `name`; `Partner`/`Station`/`Node` are read-only → an **integrated** HMI connection cannot be made via Openness. Writable: `CommunicationDriver`, `InitialAddress`. Consequence: HMI tags bound to PLC tags need one manual Devices & Networks step, or stay typed-but-unbound. |
| assembly preference with both installed | — | resolver picks V19 first; pin V21 explicitly before first use |

## Practical rules distilled

1. **Idempotency**: design every step as ensure-not-create (`Find` then
   create) so re-runs converge instead of erroring.
2. **Project paths**: `Projects.Create(DirectoryInfo, "Name")` produces
   `<dir>/Name/Name.apXX` — tooling that takes a "project path" must be
   told which of the two conventions it means.
3. **One writer**: a `.ap*` open in the GUI is locked; builds fail with a
   lock error — detect and say so rather than retrying.
4. **Save explicitly** (`project.Save()`); dispose the TiaPortal object
   when you created it, never when you attached.
5. Keep automation scripts **ASCII** — Windows PowerShell 5.1 mangles
   UTF-8 without BOM, and Openness error text then misleads you.
6. **Derive version facts from the bound API, never from memory**: the
   `<Engineering version>` stamp, project extension (`.ap19`/`.ap21`),
   certified F-instruction versions (EV1oo2DI 1.3, ESTOP1 1.6, SFDOOR
   1.3 — captured from exports and Portal-release-specific), and the
   Interface/FlgNet namespace revision are each easy to leave hardcoded
   at the version you learned them on. Re-probe when the Portal version
   changes; a wrong literal fails two phases later with a misleading
   error.
7. On multi-threaded headless start/attach the CLR raises
   `AssemblyResolve` storms; a scriptblock resolver can re-enter and
   overflow — a compiled handler with a re-entrancy guard (see the
   tia-autocode engine's `TiaAssembly.ps1`) is the proven fix.

## Deeper engine reference

The PowerShell engine LADDER's Siemens deploys delegate to (the
`TiaOpenness` module, repo `tia-autocode`) carries the full working
knowledge: FlgNet wiring invariants (every pin wired or explicitly
`OpenCon`; one power rail per network; `<Instance>` first child of a
Part), UTF-8-BOM requirement on SimaticML imports, order-sensitivity of
SimaticML elements, per-attribute writable-target discovery for
F-parameters, and a symptom→cause failure catalogue. Consult it before
re-deriving any Siemens fact experimentally.
