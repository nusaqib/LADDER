# Beckhoff TwinCAT 3 — project anatomy and import (working notes)

> Official docs: Beckhoff Information System (infosys.beckhoff.com) —
> TE1000 (PLC), the Automation Interface reference, and the PLCopen
> import/export pages. TwinCAT is free to install in engineering mode
> (7-day renewable runtime licenses), which makes it the cheapest real
> vendor target to close the loop on.

## Project anatomy

TwinCAT 3 lives inside Visual Studio (or the XAE shell):

```
Solution.sln
└─ Project.tsproj                 # the TwinCAT system project (XML)
   └─ PlcProject.plcproj          # a PLC project (MSBuild-style XML)
      ├─ POUs/*.TcPOU             # one XML file per POU
      ├─ DUTs/*.TcDUT             # data types (UDTs)
      ├─ GVLs/*.TcGVL             # global variable lists
      └─ PlcTask (in .tsproj)     # task binding
```

Everything is text/XML on disk — TwinCAT is the vendor friendliest to
git and to file-level generation.

## TcPOU format (what LADDER emits)

```xml
<TcPlcObject Version="1.1.0.1">
  <POU Name="MotorStation" Id="{guid}" SpecialFunc="None">
    <Declaration><![CDATA[
PROGRAM MotorStation
VAR
    t1 : TON;
END_VAR
]]></Declaration>
    <Implementation>
      <ST><![CDATA[ ... structured text ... ]]></ST>
    </Implementation>
  </POU>
</TcPlcObject>
```

- Declaration and implementation are plain IEC ST inside CDATA — the
  easiest vendor format in existence.
- `.TcDUT` files are the same wrapper around `TYPE ... END_TYPE`;
  `.TcGVL` around `VAR_GLOBAL ... END_VAR`.
- Located IO: TwinCAT convention is `AT %I*` / `AT %Q*` (the `*` defers
  address assignment to the linker) — physical mapping happens in the
  .tsproj IO tree against EtherCAT terminals, not in the POU. LADDER's
  iomap therefore feeds link names, not fixed offsets.

## Getting generated code in

1. **File drop** (LADDER's path): write `.TcPOU`/`.TcDUT`/`.TcGVL` files
   and include them in a `.plcproj` — a template project plus generated
   files is fully reproducible.
2. **PLCopen XML import**: TwinCAT imports tc6 XML natively
   (PLC project → right-click → Import PLCopenXML) — the same file
   LADDER's `plcopen` backend emits; good for graphic bodies.
3. **Automation Interface** (COM, `TcXaeShell` scripting, usually
   PowerShell/C#): `ITcSysManager` drives project creation, IO scan,
   link mapping, activation — the TwinCAT equivalent of TIA Openness.
   Needed only for end-to-end deploy (create solution, map IO,
   activate); not for code generation.

## Verify/test loop

- Headless build: `msbuild` on the .plcproj / `TcXaeShell.exe` with an
  Automation Interface script; errors come back as normal MSBuild output.
- Unit testing convention in the ecosystem: **TcUnit** (FB-based xUnit,
  results as xUnit XML) — the pattern LADDER's scenario runner mirrors
  at the IR level.
- Runtime simulation: a local runtime (`TwinCAT/BSD` or the Windows
  real-time core) runs without hardware; useful as an
  emulator-in-the-loop stage after artifact generation.
