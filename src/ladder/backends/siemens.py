"""Siemens TIA Portal backend (target: V21, S7-1500, Openness).

Emits per project:
    <Program>.scl   one SCL FUNCTION_BLOCK per IR program
    PlcTags.csv     global tag table (Name,DataType,Address,Comment)
    build.ps1       imports everything into TIA via the validated
                    TiaOpenness PowerShell module (E:/TIA_Portal/TIA_API)

The heavy lifting inside the Portal (sessions, tag tables, SCL import,
compile) is delegated to TiaOpenness - LADDER only generates artifacts.
OB wiring / instance DBs / project structure will follow the reverse-
engineered reference project (engine phase).

vendor hints (project.vendor.siemens):
    tia_api_path:  path to the TIA_API repo (default E:/TIA_Portal/TIA_API)
    tia_version:   Openness version for Connect-TiaPortal (default 21.0)
    fb_prefix:     prefix for generated FB names (default 'FB_')
    cpu:           exact CPU TypeIdentifier ('OrderNumber:6ES7 ...') for the
                   scratch build; otherwise build.ps1 tries a candidate list
"""

from __future__ import annotations

from pathlib import Path

from ladder.backends import common
from ladder.backends.base import Backend, BackendError, register
from ladder.backends.dialects import SiemensSclDialect
from ladder.ir.lower import LoweredProgram
from ladder.ir.model import Project, Tag

# Neutral type -> TIA tag-table type casing (PLC-tag-capable types only)
_TIA_TYPES = {"BOOL": "Bool", "INT": "Int", "DINT": "DInt", "REAL": "Real",
              "TIME": "Time", "WORD": "Word", "DWORD": "DWord"}


class _AddrAlloc:
    """Deterministic %I/%Q/%M address allocation for tags without an address.

    Scratch/compile addresses only - real IO mapping is engine-phase (M2).
    BOOLs pack into bits; 16/32-bit types are word/dword aligned.
    """

    _SIZES = {"INT": 2, "WORD": 2, "DINT": 4, "DWORD": 4, "REAL": 4, "TIME": 4}
    _AREA = {"input": "I", "output": "Q", "memory": "M"}

    def __init__(self) -> None:
        self._state = {a: {"byte": 0, "bit": 0} for a in "IQM"}

    def alloc(self, tag: Tag) -> str:
        t = tag.type.upper()
        area = self._AREA[tag.direction]
        st = self._state[area]
        if t == "BOOL":
            addr = f"%{area}{st['byte']}.{st['bit']}"
            st["bit"] += 1
            if st["bit"] == 8:
                st["bit"], st["byte"] = 0, st["byte"] + 1
            return addr
        if t not in self._SIZES:
            raise BackendError(
                f"siemens: tag {tag.name!r} ({tag.type}) cannot be a PLC tag; "
                "give it an explicit address or wait for DB support (IR v0.2)")
        size = self._SIZES[t]
        if st["bit"]:
            st["bit"], st["byte"] = 0, st["byte"] + 1
        if st["byte"] % size:
            st["byte"] += size - (st["byte"] % size)
        width = "W" if size == 2 else "D"
        addr = f"%{area}{width}{st['byte']}"
        st["byte"] += size
        return addr


@register
class SiemensBackend(Backend):
    name = "siemens"
    description = "Siemens TIA Portal V21 - SCL FBs + tag CSV + TiaOpenness build script"
    target = "TIA Portal V21 (Openness)"

    def emit(self, project: Project, lowered: dict[str, LoweredProgram],
             outdir: Path, iomap=None) -> list[Path]:
        if iomap is not None:
            from ladder.iomap import apply_addresses

            project = apply_addresses(project, iomap, "siemens")
        hints = self.hints(project)
        fb_prefix = hints.get("fb_prefix", "FB_")
        db_name = hints.get("db_name", f"{project.name}_DB")
        db_tags = {t.name for t in project.tags if t.is_complex}
        d = SiemensSclDialect(db_name=db_name, db_tags=db_tags)
        root = outdir / "siemens"
        root.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        sources: list[str] = []  # import order: types -> DB -> FBs

        if project.types:
            path = root / "Types.udt"
            path.write_text(self._render_types(project), encoding="utf-8")
            written.append(path)
            sources.append(path.name)

        if db_tags:
            path = root / f"{db_name}.db"
            path.write_text(self._render_db(project, db_name), encoding="utf-8")
            written.append(path)
            sources.append(path.name)

        for name, lp in lowered.items():
            path = root / f"{fb_prefix}{name}.scl"
            path.write_text(self._render_fb(fb_prefix, lp, d), encoding="utf-8")
            written.append(path)
            sources.append(path.name)

        tags_csv = root / "PlcTags.csv"
        tags_csv.write_text(self._render_tags_csv(project), encoding="utf-8")
        written.append(tags_csv)

        build = root / "build.ps1"
        build.write_text(self._render_build_ps1(project, sources, hints), encoding="ascii")
        written.append(build)
        return written

    # --------------------------------------------------------- types + DB

    def _tia_type(self, type_: str) -> str:
        return _TIA_TYPES.get(type_.upper(), f'"{type_}"')  # UDTs are quoted

    def _member_decl(self, name: str, type_: str, initial, comment,
                     indent: str = "      ") -> str:
        from ladder.backends.common import fmt_initial

        init = fmt_initial(initial, type_)
        line = f"{indent}{name} : {self._tia_type(type_)}"
        if init is not None:
            line += f" := {init}"
        line += ";"
        if comment:
            line += f"  // {comment}"
        return line

    def _render_types(self, project: Project) -> str:
        out = ["// generated by LADDER - PLC data types"]
        for t in project.types:
            out.append(f'TYPE "{t.name}"')
            out.append("VERSION : 0.1")
            out.append("   STRUCT")
            for m in t.members:
                out.append(self._member_decl(m.name, m.type, m.initial, m.comment))
            out.append("   END_STRUCT;")
            out.append("END_TYPE")
            out.append("")
        return "\n".join(out)

    def _render_db(self, project: Project, db_name: str) -> str:
        out = [f'DATA_BLOCK "{db_name}"',
               "{ S7_Optimized_Access := 'TRUE' }",
               "VERSION : 0.1",
               "// generated by LADDER - complex (UDT/array) global tags",
               "VAR"]
        for t in project.tags:
            if not t.is_complex:
                continue
            if t.array is not None:
                type_txt = f"Array[0..{t.array - 1}] of {self._tia_type(t.type)}"
                line = f"   {t.name} : {type_txt};"
                if t.comment:
                    line += f"  // {t.comment}"
                out.append(line)
            else:
                out.append(self._member_decl(t.name, t.type, t.initial,
                                             t.comment, indent="   "))
        out += ["END_VAR", "BEGIN", "END_DATA_BLOCK"]
        return "\n".join(out) + "\n"

    # ------------------------------------------------------------------ SCL

    def _render_fb(self, fb_prefix: str, lp: LoweredProgram,
                   d: SiemensSclDialect) -> str:
        prog = lp.program
        out = [f'FUNCTION_BLOCK "{fb_prefix}{prog.name}"']
        out.append("{ S7_Optimized_Access := 'TRUE' }")
        out.append("VERSION : 0.1")
        if prog.description:
            out.append(f"// {prog.description}")
        out.append("// generated by LADDER - do not edit by hand")
        decls = []
        for t in prog.variables:
            if t.array is not None:
                line = f"    {t.name} : Array[0..{t.array - 1}] of {self._tia_type(t.type)};"
                if t.comment:
                    line += f"  // {t.comment}"
                decls.append(line)
            else:
                decls.append(self._member_decl(t.name, t.type, t.initial,
                                               t.comment, indent="    "))
        decls += [
            common.synth_var_line(
                v, d.timer_decl_type(v) if v.kind == "timer" else "BOOL")
            for v in lp.synth
        ]
        if decls:
            out.append("VAR")
            out.extend(decls)
            out.append("END_VAR")
        out.append("")
        out.append("BEGIN")
        body = d.body(lp)
        out.extend("    " + line if line else "" for line in body.splitlines())
        out.append("END_FUNCTION_BLOCK")
        return "\n".join(out) + "\n"

    # ------------------------------------------------------------------ tags

    def _render_tags_csv(self, project: Project) -> str:
        alloc = _AddrAlloc()
        lines = ["Name,DataType,Address,Comment"]
        for t in project.tags:
            if t.is_complex:
                continue  # UDT/array tags live in the global DB
            dtype = _TIA_TYPES.get(t.type.upper())
            if dtype is None:
                raise BackendError(
                    f"siemens: {t.type} tag {t.name!r} cannot be a PLC tag")
            address = t.address or alloc.alloc(t)
            comment = (t.comment or "").replace(",", ";")
            lines.append(f"{t.name},{dtype},{address},{comment}")
        return "\n".join(lines) + "\n"

    # ----------------------------------------------------------------- build

    _BUILD_TEMPLATE = r"""# build.ps1 - build LADDER-generated artifacts in a scratch TIA Portal project
# Generated by LADDER for project '__PROJECT__'. Windows PowerShell 5.1 only.
# Requires the TiaOpenness module: __API__
# Starts its OWN headless portal instance - never touches a human's live session.

param(
    [string]$TiaApiPath  = '__API__',
    [string]$Version     = '__VERSION__',
    [string]$ProjectName = '__PROJECT__',
    # the openable IDE project is a build artifact: it lands in the
    # (git-ignored) out folder next to this script and is disposable -
    # regenerate it, never hand-edit it
    [string]$WorkDir     = "$PSScriptRoot\project",
    [string]$Cpu         = '__CPU__',   # exact TypeIdentifier wins over candidates
    [switch]$KeepOpen                    # leave the portal running for inspection
)

$ErrorActionPreference = 'Stop'
$log = Join-Path $PSScriptRoot 'build.log'
Start-Transcript -Path $log -Force | Out-Null
$exit = 1
try {
    Import-Module (Join-Path $TiaApiPath 'src/TiaOpenness/TiaOpenness.psd1') -Force

    Write-Host "Starting headless TIA Portal V$Version ..."
    Connect-TiaPortal -New -WithUserInterface:$false -Version $Version | Out-Null

    $projDir = Join-Path $WorkDir $ProjectName
    if (Test-Path $projDir) {
        try { Remove-Item $projDir -Recurse -Force }
        catch { throw "Cannot refresh $projDir - close the project in TIA Portal first. ($($_.Exception.Message))" }
    }
    New-TiaProject -Name $ProjectName -Path $WorkDir | Out-Null
    Write-Host "Created project $projDir"

    # CPU: explicit -Cpu first, then candidates until the catalog accepts one.
    $candidates = @()
    if ($Cpu) { $candidates += $Cpu }
    $candidates += @(
        'OrderNumber:6ES7 512-1SK01-0AB0/V2.9'   # CPU 1512SP F-1 PN (in this machine's V21 catalog)
        'OrderNumber:6ES7 511-1AK02-0AB0/V2.9'   # S7-1511-1 PN (standard)
        'OrderNumber:6ES7 513-1AL02-0AB0/V2.9'   # S7-1513-1 PN
        'OrderNumber:6ES7 515-2AM02-0AB0/V2.9'   # S7-1515-2 PN
        'OrderNumber:6ES7 511-1FK02-0AB0/V2.9'   # S7-1511F-1 PN
    )
    $added = $null
    foreach ($mlfb in $candidates) {
        try {
            New-TiaDevice -TypeIdentifier $mlfb -Name 'PLC_1' | Out-Null
            $added = $mlfb; Write-Host "Added CPU: $mlfb"; break
        } catch { Write-Host "  device add failed for ${mlfb}: $($_.Exception.Message)" }
    }
    if (-not $added) { throw 'No candidate CPU accepted by this catalog; pass -Cpu with the exact MLFB.' }

    $sw = (Get-TiaPlc | Select-Object -First 1).PlcSoftware

    Write-Host 'Creating PLC tags ...'
    Import-Csv (Join-Path $PSScriptRoot 'PlcTags.csv') | ForEach-Object {
        $p = @{ Plc = $sw; TagTable = 'LADDER'; Name = $_.Name
                DataType = $_.DataType; Address = $_.Address }
        if ($_.Comment) { $p.Comment = $_.Comment }
        New-TiaTag @p | Out-Null
    }

    Write-Host 'Importing sources (types -> DB -> FBs) ...'
    foreach ($f in @(__SCL_FILES__)) {
        Import-TiaScl -Plc $sw -Path (Join-Path $PSScriptRoot $f) | Out-Null
        Write-Host "  imported $f"
    }

    Write-Host 'Compiling ...'
    $c = Invoke-TiaCompile -Plc $sw
    Write-Host ("Compile State={0} Errors={1} Warnings={2}" -f $c.State, $c.Errors, $c.Warnings)
    $c.Messages | ForEach-Object { Write-Host "  $_" }

    Save-TiaProject
    if ($c.Errors -eq 0) { $exit = 0; Write-Host 'BUILD PASSED (0 errors)' }
    else { Write-Host 'BUILD FAILED (compile errors above)' }
} catch {
    Write-Host "BUILD FAILED: $($_.Exception.Message)"
} finally {
    if (-not $KeepOpen) { try { Disconnect-TiaPortal -Close } catch {} }
    Stop-Transcript | Out-Null
}
exit $exit
"""

    def _render_build_ps1(self, project: Project, sources: list[str],
                          hints: dict) -> str:
        scl_files = ", ".join(f"'{s}'" for s in sources)
        # ASCII only: PS 5.1 reads BOM-less files as ANSI (TIA_API convention)
        # target version: 'siemens@19' beats the vendor hint beats the default
        tia_version = self.version or str(hints.get("tia_version", "21.0"))
        if "." not in tia_version:
            tia_version += ".0"
        return (self._BUILD_TEMPLATE
                .replace("__API__", str(hints.get("tia_api_path", "E:/TIA_Portal/TIA_API")))
                .replace("__VERSION__", tia_version)
                .replace("__PROJECT__", project.name)
                .replace("__CPU__", str(hints.get("cpu", "")))
                .replace("__SCL_FILES__", scl_files))
