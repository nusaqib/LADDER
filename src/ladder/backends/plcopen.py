"""PLCopen XML 2.01 / IEC 61131-10 backend.

The standards-based interchange path: programs become ST-bodied PROGRAM
POUs, globals live in a configuration/resource, cyclic/periodic programs
are scheduled as tasks. Useful for CODESYS-family tools and anything else
that imports tc6 XML; Siemens and Rockwell use their native backends.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from ladder.backends.base import Backend, register
from ladder.backends.dialects import Iec61131Dialect
from ladder.ir import expr as X
from ladder.ir.lower import LoweredProgram
from ladder.ir.model import Project, Tag

_SIMPLE_TYPES = {"BOOL", "INT", "DINT", "REAL", "LREAL", "TIME", "WORD", "DWORD", "STRING"}


def _type_xml(type_: str) -> str:
    t = type_.upper()
    if t in _SIMPLE_TYPES:
        return f"<type><{t}/></type>"
    return f"<type><derived name={quoteattr(type_)}/></type>"


def _iso_duration(ms: int) -> str:
    """milliseconds -> xsd:duration, e.g. 100 -> 'PT0.1S'."""
    return f"PT{ms / 1000:g}S"


def _variable_xml(name: str, type_: str, initial: str | None,
                  comment: str | None, indent: str) -> list[str]:
    out = [f"{indent}<variable name={quoteattr(name)}>"]
    out.append(f"{indent}  {_type_xml(type_)}")
    if initial is not None:
        out.append(f"{indent}  <initialValue><simpleValue value={quoteattr(initial)}/></initialValue>")
    if comment:
        out.append(f"{indent}  <documentation><xhtml xmlns=\"http://www.w3.org/1999/xhtml\">"
                   f"{escape(comment)}</xhtml></documentation>")
    out.append(f"{indent}</variable>")
    return out


def _tag_variable_xml(t: Tag, indent: str) -> list[str]:
    from ladder.backends.common import fmt_initial

    return _variable_xml(t.name, t.type, fmt_initial(t.initial, t.type), t.comment, indent)


@register
class PlcopenBackend(Backend):
    name = "plcopen"
    description = "PLCopen XML 2.01 (IEC 61131-10) - ST POUs + configuration"
    target = "PLCopen TC6 XML 2.01"

    def emit(self, project: Project, lowered: dict[str, LoweredProgram],
             outdir: Path) -> list[Path]:
        root = outdir / "plcopen"
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{project.name}.xml"
        path.write_text(self._render(project, lowered), encoding="utf-8")
        return [path]

    def _render(self, project: Project, lowered: dict[str, LoweredProgram]) -> str:
        d = Iec61131Dialect()
        stamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        x: list[str] = []
        x.append('<?xml version="1.0" encoding="utf-8"?>')
        x.append('<project xmlns="http://www.plcopen.org/xml/tc6_0201">')
        x.append(f'  <fileHeader companyName="LADDER" productName="LADDER" '
                 f'productVersion="0.1.0" creationDateTime="{stamp}"/>')
        x.append(f'  <contentHeader name={quoteattr(project.name)} '
                 f'modificationDateTime="{stamp}">')
        x.append("    <coordinateInfo>"
                 '<fbd><scaling x="1" y="1"/></fbd>'
                 '<ld><scaling x="1" y="1"/></ld>'
                 '<sfc><scaling x="1" y="1"/></sfc>'
                 "</coordinateInfo>")
        x.append("  </contentHeader>")
        x.append("  <types>")
        x.append("    <dataTypes/>")
        x.append("    <pous>")
        for name, lp in lowered.items():
            x.extend(self._pou_xml(name, lp, d))
        x.append("    </pous>")
        x.append("  </types>")
        x.append("  <instances>")
        x.append("    <configurations>")
        x.append('      <configuration name="Config">')
        x.append('        <resource name="Res">')
        for name, lp in lowered.items():
            interval = ""
            if lp.program.execution == "periodic" and lp.program.interval:
                interval = f' interval="{_iso_duration(X.parse_time_literal(lp.program.interval))}"'
            x.append(f'          <task name={quoteattr("Task_" + name)}{interval} priority="1">')
            x.append(f'            <pouInstance name={quoteattr("inst_" + name)} '
                     f'typeName={quoteattr(name)}/>')
            x.append("          </task>")
        if project.tags:
            x.append("          <globalVars>")
            for t in project.tags:
                x.extend(_tag_variable_xml(t, "            "))
            x.append("          </globalVars>")
        x.append("        </resource>")
        x.append("      </configuration>")
        x.append("    </configurations>")
        x.append("  </instances>")
        x.append("</project>")
        return "\n".join(x) + "\n"

    def _pou_xml(self, name: str, lp: LoweredProgram, d: Iec61131Dialect) -> list[str]:
        x = [f'      <pou name={quoteattr(name)} pouType="program">']
        x.append("        <interface>")
        x.append("          <localVars>")
        for t in lp.program.variables:
            x.extend(_tag_variable_xml(t, "            "))
        for v in lp.synth:
            type_ = d.timer_decl_type(v) if v.kind == "timer" else "BOOL"
            x.extend(_variable_xml(v.name, type_, None, v.comment, "            "))
        x.append("          </localVars>")
        x.append("        </interface>")
        x.append("        <body>")
        x.append('          <ST><xhtml xmlns="http://www.w3.org/1999/xhtml">')
        x.append(escape(d.body(lp)).rstrip())
        x.append("          </xhtml></ST>")
        x.append("        </body>")
        if lp.program.description:
            x.append(f'        <documentation><xhtml xmlns="http://www.w3.org/1999/xhtml">'
                     f"{escape(lp.program.description)}</xhtml></documentation>")
        x.append("      </pou>")
        return x
