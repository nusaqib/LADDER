"""Adopt a Siemens spec folder (Export-TiaToSpec output) into LADDER IR.

Input layout (produced by TIA_API's Export-TiaToSpec):
    project.json          manifest
    data/<plc>.tags.csv   TagTable,Name,DataType,Address,Comment,Retain
    types/*.xml           UDTs (SimaticML)
    blocks/*.xml          OB/FB/FC/DB (SimaticML)

v0.1 fidelity:
    tags        -> IR global tags (direction inferred from %I/%Q address)
    SCL FB/OB   -> one IR program each; interface VAR section -> variables,
                   body reconstructed from tokenized SimaticML -> `st` element
    LAD/FBD/DB  -> inventoried in STRUCTURE.md only (not lifted yet)
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from ladder.ir.model import Program, Project, RawStEl, Tag

# TIA -> neutral scalar types (pass anything else through verbatim, e.g. UDTs)
_TYPES = {"BOOL": "BOOL", "INT": "INT", "DINT": "DINT", "REAL": "REAL",
          "LREAL": "LREAL", "TIME": "TIME", "WORD": "WORD", "DWORD": "DWORD",
          "STRING": "STRING"}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _direction(address: str) -> str:
    a = (address or "").lstrip("%").upper()
    if a.startswith("I"):
        return "input"
    if a.startswith("Q"):
        return "output"
    return "memory"


# ------------------------------------------------------------ ST rebuild


def _render_access(el: ET.Element) -> str:
    """SimaticML <Access> -> SCL-ish source text."""
    scope = el.get("Scope", "")
    if scope in ("LiteralConstant", "TypedConstant"):
        c = el.find(".//{*}ConstantValue")
        return (c.text or "") if c is not None else ""
    if scope == "Call":
        # instance name precedes as its own Access; the Call node holds an
        # Instruction with inline tokens and Parameter nodes - just walk it
        return "".join(_walk_st(el))
    symbol = el.find("{*}Symbol")
    if symbol is not None:
        parts: list[str] = []
        first_component = True
        for c in symbol:
            kind = _local(c.tag)
            if kind == "Component":
                name = c.get("Name", "")
                quoted = (scope == "GlobalVariable") and first_component
                parts.append(f'"{name}"' if quoted else name)
                first_component = False
            elif kind == "Token":
                parts.append(c.get("Text", ""))
        text = "".join(parts)
        return text if scope == "GlobalVariable" else f"#{text}"
    return el.get("Name", "")


def _walk_st(parent: ET.Element) -> list[str]:
    """Reconstruct source text from tokenized SimaticML StructuredText."""
    out: list[str] = []
    for el in parent:
        kind = _local(el.tag)
        if kind == "Token":
            out.append(el.get("Text", ""))
        elif kind == "Blank":
            out.append(" " * int(el.get("Num", "1")))
        elif kind == "NewLine":
            out.append("\n" * int(el.get("Num", "1")))
        elif kind == "Access":
            out.append(_render_access(el))
        elif kind == "Parameter":
            out.append(el.get("Name", ""))
            out.extend(_walk_st(el))
        elif kind == "LineComment":
            text = el.find("{*}Text")
            out.append("//" + (text.text or "" if text is not None else ""))
        elif kind == "Comment":
            text = el.find("{*}Text")
            out.append("(*" + (text.text or "" if text is not None else "") + "*)")
        else:  # unknown node: recurse so nothing silently disappears
            out.extend(_walk_st(el))
    return out


def _block_body(root: ET.Element) -> str:
    chunks = []
    for st in root.iter():
        if _local(st.tag) == "StructuredText":
            chunks.append("".join(_walk_st(st)).strip("\n"))
    return "\n".join(c for c in chunks if c)


def _interface_vars(root: ET.Element) -> list[Tag]:
    """Static/VAR section members of the block interface -> program locals."""
    tags: list[Tag] = []
    for section in root.iter():
        if _local(section.tag) != "Section" or section.get("Name") not in ("Static", "VAR"):
            continue
        for m in section:
            if _local(m.tag) != "Member":
                continue
            name, dtype = m.get("Name", ""), m.get("Datatype", "BOOL").strip('"')
            tags.append(Tag(name=name, type=_TYPES.get(dtype.upper(), dtype)))
    return tags


@dataclass
class BlockInfo:
    name: str
    kind: str  # FB / FC / OB / GlobalDB / ...
    language: str
    file: str
    lifted: bool = False


@dataclass
class AdoptResult:
    project: Project
    blocks: list[BlockInfo] = field(default_factory=list)
    report: str = ""


def _read_tags(specdir: Path, manifest: dict) -> list[Tag]:
    tags: list[Tag] = []
    for plc in manifest.get("plcs", []):
        for rel in plc.get("tags", []):
            with open(specdir / rel, newline="", encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    tags.append(Tag(
                        name=row["Name"],
                        type=_TYPES.get(row["DataType"].upper(), row["DataType"]),
                        direction=_direction(row.get("Address", "")),
                        address=row.get("Address") or None,
                        comment=row.get("Comment") or None,
                        retain=(row.get("Retain") or "").lower() in ("1", "true", "x"),
                    ))
    return tags


_STRIP_PREFIX = re.compile(r"^(FB_|FC_|OB_)", re.IGNORECASE)


def adopt_siemens_spec(specdir: str | Path) -> AdoptResult:
    specdir = Path(specdir)
    manifest = json.loads((specdir / "project.json").read_text(encoding="utf-8-sig"))
    proj_name = manifest.get("project", {}).get("name", specdir.name)

    tags = _read_tags(specdir, manifest)

    blocks: list[BlockInfo] = []
    programs: list[Program] = []
    for xml_file in sorted((specdir / "blocks").glob("*.xml")):
        root = ET.parse(xml_file).getroot()
        block_el = next((el for el in root.iter()
                         if _local(el.tag).startswith("SW.Blocks.")), None)
        if block_el is None:
            continue
        kind = _local(block_el.tag).split(".")[-1]
        name_el = next((e for e in block_el.iter() if _local(e.tag) == "Name"), None)
        lang_el = next((e for e in block_el.iter()
                        if _local(e.tag) == "ProgrammingLanguage"), None)
        name = name_el.text if name_el is not None else xml_file.stem
        lang = lang_el.text if lang_el is not None else "?"
        info = BlockInfo(name, kind, lang, xml_file.name)
        blocks.append(info)
        if kind in ("FB", "OB", "FC") and lang == "SCL":
            body = _block_body(block_el)
            if body:
                prog_name = _STRIP_PREFIX.sub("", name)
                programs.append(Program(
                    name=prog_name,
                    description=f"adopted from {kind} {name} ({xml_file.name})",
                    variables=_interface_vars(block_el),
                    logic=[RawStEl(element="st", id=f"adopted_{prog_name}",
                                   code=body,
                                   description="verbatim lift; refactor into "
                                               "structured elements over time")],
                ))
                info.lifted = True

    if not programs:  # IR requires >=1 program; keep the inventory useful anyway
        programs = [Program(name="Adopted", description="no SCL blocks lifted",
                            logic=[RawStEl(element="st", id="placeholder", code=";")])]

    project = Project(name=proj_name, description=f"adopted from {specdir}",
                      tags=tags, programs=programs)
    result = AdoptResult(project=project, blocks=blocks)
    result.report = _structure_report(proj_name, specdir, result)
    return result


def _structure_report(name: str, specdir: Path, r: AdoptResult) -> str:
    lines = [f"# {name} - structure report (adopted from {specdir})", ""]
    lines.append("| Block | Kind | Language | Lifted to IR |")
    lines.append("|---|---|---|---|")
    for b in r.blocks:
        lines.append(f"| {b.name} | {b.kind} | {b.language} | "
                     f"{'yes (st element)' if b.lifted else 'inventory only'} |")
    lines.append("")
    lines.append(f"Tags adopted: {len(r.project.tags)}  |  "
                 f"Programs lifted: {sum(b.lifted for b in r.blocks)}")
    lines.append("")
    lines.append("Not lifted yet: LAD/FBD blocks, DBs, UDTs (inventoried in "
                 "types/), hardware. These inform the engine phase (M2).")
    return "\n".join(lines) + "\n"
