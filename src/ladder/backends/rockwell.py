"""Rockwell Studio 5000 Logix Designer backend (target: V36).

Emits one importable .L5X (controller-scoped) containing:
    controller tags   (IR global tags)
    one Program per IR program, with an ST MainRoutine
    program tags      (IR locals + synthesized timers/edge memories)
    a continuous MainTask (periodic IR programs get periodic tasks)

Notes:
  - Logix has no TIME type in tags: TIME maps to DINT milliseconds.
  - Timers are FBD_TIMER driven by TONR/TOFR in ST.
  - IO module/alias wiring belongs to the engine phase (reverse-engineered
    reference project), not the IR.

vendor hints (project.vendor.rockwell):
    processor:  ProcessorType attribute   (default 1756-L85E)
    major_rev:  controller major revision (default 36)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import quoteattr

from ladder.backends.base import Backend, BackendError, register
from ladder.backends.dialects import RockwellStDialect
from ladder.backends.rungs import (
    CoilAction,
    MoveAction,
    Rung,
    TimerAction,
    bool_roots_for,
    push_not_down,
    to_rungs,
)
from ladder.ir import expr as X
from ladder.ir.lower import LoweredProgram
from ladder.ir.model import Project, Tag

_TYPE_MAP = {
    "BOOL": "BOOL", "INT": "INT", "DINT": "DINT", "REAL": "REAL",
    "LREAL": "LREAL", "TIME": "DINT", "WORD": "INT", "DWORD": "DINT",
    "STRING": "STRING",
}


def _cdata(text: str) -> str:
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


_RLL_CMP = {"=": "EQU", "<>": "NEQ", "<": "LES", "<=": "LEQ",
            ">": "GRT", ">=": "GEQ"}
_TIMER_MEMBERS = {"Q": "DN", "ET": "ACC"}


def _rll_name(ref: X.Ref) -> str:
    head, *rest = ref.path
    rest = [_TIMER_MEMBERS.get(m, m) for m in rest]
    return ".".join([head, *rest])


def _rll_operand(e: X.Expr) -> str:
    if isinstance(e, X.Ref):
        return _rll_name(e)
    if isinstance(e, X.Lit):
        if e.kind == "bool":
            return "1" if e.value else "0"
        return str(e.value)
    raise BackendError("rockwell: RLL compare operands must be tags or literals")


def _rll_cond(e: X.Expr) -> str:
    """Rung input instructions for a (NOT-normalized) boolean expression."""
    if isinstance(e, X.Lit) and e.kind == "bool":
        return "" if e.value else "AFI()"  # empty = always true
    if isinstance(e, X.Ref):
        return f"XIC({_rll_name(e)})"
    if isinstance(e, X.Un) and e.op == "NOT" and isinstance(e.x, X.Ref):
        return f"XIO({_rll_name(e.x)})"
    if isinstance(e, X.Bin):
        if e.op == "AND":
            return _rll_cond(e.left) + _rll_cond(e.right)
        if e.op == "OR":
            return f"[{_rll_cond(e.left)} ,{_rll_cond(e.right)} ]"
        cmp_ = _RLL_CMP.get(e.op)
        if cmp_:
            return f"{cmp_}({_rll_operand(e.left)},{_rll_operand(e.right)})"
    raise BackendError(f"rockwell: no RLL form for expression {e!r}")


def _rll_rung_text(r: Rung) -> str:
    cond = _rll_cond(push_not_down(r.cond)) if r.cond is not None else ""
    a = r.action
    if isinstance(a, CoilAction):
        op = {"out": "OTE", "set": "OTL", "reset": "OTU"}[a.mode]
        act = f"{op}({_rll_name(a.target)})"
    elif isinstance(a, MoveAction):
        act = f"MOV({_rll_operand(a.value)},{_rll_name(a.target)})"
    elif isinstance(a, TimerAction):
        if a.kind not in ("TON", "TOF"):
            raise BackendError("rockwell: RLL has no TP instruction; rework "
                               f"timer {a.instance!r} (e.g. TON + logic)")
        act = f"{a.kind}({a.instance},?,?)"
    else:  # pragma: no cover
        raise BackendError(f"rockwell: unknown rung action {a!r}")
    return cond + act + ";"


def _radix(dtype: str) -> str | None:
    if dtype in ("REAL", "LREAL"):
        return "Float"
    if dtype in ("BOOL", "SINT", "INT", "DINT", "BIT"):
        return "Decimal"
    return None  # UDTs / STRING: no radix attribute


@register
class RockwellBackend(Backend):
    name = "rockwell"
    description = "Rockwell Studio 5000 V36 - controller-scoped L5X with ST routines"
    target = "Studio 5000 Logix Designer V36"

    def emit(self, project: Project, lowered: dict[str, LoweredProgram],
             outdir: Path, iomap=None) -> list[Path]:
        aliases = {}
        if iomap is not None:
            aliases = {name: b.alias for name, b in iomap.section("rockwell").items()
                       if b.alias}
        root = outdir / "rockwell"
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{project.name}.L5X"
        path.write_text(self._render(project, lowered, aliases), encoding="utf-8")
        return [path]

    # ------------------------------------------------------------------ L5X

    def _tag_xml(self, t: Tag, indent: str) -> list[str]:
        dtype = _TYPE_MAP.get(t.type.upper(), t.type)
        radix = _radix(dtype)
        attrs = f'{indent}<Tag Name={quoteattr(t.name)} TagType="Base" DataType="{dtype}"'
        if t.array is not None:
            attrs += f' Dimensions="{t.array}"'
        if radix and t.type.upper() in _TYPE_MAP:
            attrs += f' Radix="{radix}"'
        out = [attrs + ' Constant="false" ExternalAccess="Read/Write">']
        comment = t.comment or ""
        if t.type.upper() == "TIME":
            comment = (comment + " " if comment else "") + "[TIME as DINT ms]"
        if comment:
            out.append(f"{indent}  <Description>{_cdata(comment)}</Description>")
        out.append(f"{indent}</Tag>")
        return out

    def _synth_tag_xml(self, name: str, dtype: str, comment: str, indent: str) -> list[str]:
        radix = "" if dtype == "FBD_TIMER" else ' Radix="Decimal"'
        out = [f'{indent}<Tag Name={quoteattr(name)} TagType="Base" '
               f'DataType="{dtype}"{radix} Constant="false" '
               f'ExternalAccess="Read/Write">']
        if comment:
            out.append(f"{indent}  <Description>{_cdata(comment)}</Description>")
        out.append(f"{indent}</Tag>")
        return out

    def _alias_tag_xml(self, t: Tag, alias_for: str, indent: str) -> list[str]:
        """Controller tag as an alias for a physical IO point."""
        out = [f'{indent}<Tag Name={quoteattr(t.name)} TagType="Alias" '
               f'Radix="Decimal" AliasFor={quoteattr(alias_for)} '
               f'ExternalAccess="Read/Write">']
        if t.comment:
            out.append(f"{indent}  <Description>{_cdata(t.comment)}</Description>")
        out.append(f"{indent}</Tag>")
        return out

    def _render(self, project: Project, lowered: dict[str, LoweredProgram],
                aliases: dict[str, str] | None = None) -> str:
        aliases = aliases or {}
        hints = self.hints(project)
        processor = hints.get("processor", "1756-L85E")
        major = hints.get("major_rev", 36)
        d = RockwellStDialect()
        now = datetime.now().strftime("%a %b %d %H:%M:%S %Y")
        name_a = quoteattr(project.name)

        x: list[str] = []
        x.append('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
        x.append(f'<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="{major}.00" '
                 f'TargetName={name_a} TargetType="Controller" ContainsContext="false" '
                 f'ExportDate="{now}" ExportOptions="References NoRawData L5KData '
                 f'DecoratedData Context Dependencies ForceProtectedEncoding AllProjDocTrans">')
        x.append(f'  <Controller Use="Target" Name={name_a} ProcessorType="{processor}" '
                 f'MajorRev="{major}" MinorRev="11" TimeSlice="20" ShareUnusedTimeSlice="1" '
                 f'ProjectCreationDate="{now}" LastModifiedDate="{now}" '
                 f'SFCExecutionControl="CurrentActive" SFCRestartPosition="MostRecent" '
                 f'SFCLastScan="DontScan" MatchProjectToController="false">')
        if project.description:
            x.append(f"    <Description>{_cdata(project.description)}</Description>")
        x.extend(self._datatypes_xml(project))

        # controller (global) tags
        x.append("    <Tags>")
        for t in project.tags:
            if t.name in aliases:
                x.extend(self._alias_tag_xml(t, aliases[t.name], "      "))
            else:
                x.extend(self._tag_xml(t, "      "))
        x.append("    </Tags>")

        # programs
        x.append("    <Programs>")
        for name, lp in lowered.items():
            x.extend(self._program_xml(project, name, lp, d))
        x.append("    </Programs>")

        # tasks
        x.extend(self._tasks_xml(lowered))

        x.append("  </Controller>")
        x.append("</RSLogix5000Content>")
        return "\n".join(x) + "\n"

    def _datatypes_xml(self, project: Project) -> list[str]:
        """User UDTs. Logix packs BOOL members as BIT views onto hidden
        SINT host members (8 bits per host)."""
        if not project.types:
            return ["    <DataTypes/>"]
        x = ["    <DataTypes>"]
        for t in project.types:
            x.append(f'      <DataType Name={quoteattr(t.name)} '
                     f'Family="NoFamily" Class="User">')
            x.append("        <Members>")
            host, bit = None, 8
            host_n = 0
            for m in t.members:
                dtype = _TYPE_MAP.get(m.type.upper(), m.type)
                if dtype == "BOOL":
                    if bit == 8:  # open a fresh hidden host
                        host = f"ZZZZZZZZZZ{t.name}{host_n}"
                        host_n += 1
                        bit = 0
                        x.append(f'          <Member Name="{host}" DataType="SINT" '
                                 f'Dimension="0" Radix="Decimal" Hidden="true" '
                                 f'ExternalAccess="Read/Write"/>')
                    x.append(f'          <Member Name={quoteattr(m.name)} '
                             f'DataType="BIT" Dimension="0" Radix="Decimal" '
                             f'Hidden="false" Target="{host}" BitNumber="{bit}" '
                             f'ExternalAccess="Read/Write"/>')
                    bit += 1
                else:
                    radix = _radix(dtype)
                    radix_attr = f' Radix="{radix}"' if radix else ""
                    x.append(f'          <Member Name={quoteattr(m.name)} '
                             f'DataType="{dtype}" Dimension="0"{radix_attr} '
                             f'Hidden="false" ExternalAccess="Read/Write"/>')
            x.append("        </Members>")
            x.append("      </DataType>")
        x.append("    </DataTypes>")
        return x

    def _program_xml(self, project: Project, name: str, lp: LoweredProgram,
                     d: RockwellStDialect) -> list[str]:
        ladder = lp.program.language == "ladder"
        rungs: list[Rung] = []
        presets: dict[str, int] = {}
        if ladder:
            rungs = to_rungs(lp, bool_roots_for(lp, project))
            presets = {a.instance: a.preset_ms for r in rungs
                       if isinstance((a := r.action), TimerAction)}

        x = [f'      <Program Name={quoteattr(name)} TestEdits="false" '
             f'MainRoutineName="Main" Disabled="false" UseAsFolder="false">']
        if lp.program.description:
            x.append(f"        <Description>{_cdata(lp.program.description)}</Description>")
        x.append("        <Tags>")
        for t in lp.program.variables:
            x.extend(self._tag_xml(t, "          "))
        for v in lp.synth:
            if v.kind == "timer" and ladder:
                # RLL TON/TOF drive native TIMER structures; preset lives
                # in the tag's PRE member (milliseconds)
                x.extend(self._timer_tag_xml(v.name, presets.get(v.name, 0),
                                             v.comment, "          "))
                continue
            dtype = d.timer_decl_type(v) if v.kind == "timer" else "BOOL"
            x.extend(self._synth_tag_xml(v.name, dtype, v.comment, "          "))
        x.append("        </Tags>")
        x.append("        <Routines>")
        if ladder:
            x.append('          <Routine Name="Main" Type="RLL">')
            x.append("            <RLLContent>")
            for i, r in enumerate(rungs):
                x.append(f'              <Rung Number="{i}" Type="N">')
                if r.comment:
                    x.append(f"                <Comment>{_cdata(r.comment)}</Comment>")
                x.append(f"                <Text>{_cdata(_rll_rung_text(r))}</Text>")
                x.append("              </Rung>")
            x.append("            </RLLContent>")
        else:
            x.append('          <Routine Name="Main" Type="ST">')
            x.append("            <STContent>")
            body = d.body(lp)
            for i, line in enumerate(body.splitlines()):
                x.append(f'              <Line Number="{i}">{_cdata(line)}</Line>')
            x.append("            </STContent>")
        x.append("          </Routine>")
        x.append("        </Routines>")
        x.append("      </Program>")
        return x

    def _timer_tag_xml(self, name: str, preset_ms: int, comment: str,
                       indent: str) -> list[str]:
        out = [f'{indent}<Tag Name={quoteattr(name)} TagType="Base" '
               f'DataType="TIMER" Constant="false" ExternalAccess="Read/Write">']
        if comment:
            out.append(f"{indent}  <Description>{_cdata(comment)}</Description>")
        out.append(f'{indent}  <Data Format="Decorated">')
        out.append(f'{indent}    <Structure DataType="TIMER">')
        out.append(f'{indent}      <DataValueMember Name="PRE" DataType="DINT" '
                   f'Radix="Decimal" Value="{preset_ms}"/>')
        out.append(f'{indent}      <DataValueMember Name="ACC" DataType="DINT" '
                   f'Radix="Decimal" Value="0"/>')
        out.append(f'{indent}    </Structure>')
        out.append(f'{indent}  </Data>')
        out.append(f"{indent}</Tag>")
        return out

    def _tasks_xml(self, lowered: dict[str, LoweredProgram]) -> list[str]:
        continuous = [n for n, lp in lowered.items() if lp.program.execution == "cyclic"]
        periodic = [(n, lp) for n, lp in lowered.items() if lp.program.execution == "periodic"]
        x = ["    <Tasks>"]
        if continuous:
            x.append('      <Task Name="MainTask" Type="CONTINUOUS" Priority="10" '
                     'Watchdog="500" DisableUpdateOutputs="false" InhibitTask="false">')
            x.append("        <ScheduledPrograms>")
            for n in continuous:
                x.append(f"          <ScheduledProgram Name={quoteattr(n)}/>")
            x.append("        </ScheduledPrograms>")
            x.append("      </Task>")
        for n, lp in periodic:
            assert lp.program.interval is not None  # validation V08
            rate_ms = X.parse_time_literal(lp.program.interval)
            if rate_ms <= 0:
                raise BackendError(f"rockwell: bad periodic rate for {n}")
            x.append(f'      <Task Name={quoteattr("Task_" + n)} Type="PERIODIC" '
                     f'Rate="{rate_ms}" Priority="10" Watchdog="500" '
                     'DisableUpdateOutputs="false" InhibitTask="false">')
            x.append("        <ScheduledPrograms>")
            x.append(f"          <ScheduledProgram Name={quoteattr(n)}/>")
            x.append("        </ScheduledPrograms>")
            x.append("      </Task>")
        x.append("    </Tasks>")
        return x
