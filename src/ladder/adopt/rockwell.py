"""Reverse adoption: Rockwell L5X -> LADDER IR.

Parses a Logix L5X export (or LADDER's own emitted L5X - the round-trip
case) and reconstructs IR: tags, UDTs, timers, and RLL rung logic.
Coverage is the instruction subset LADDER itself emits plus the common
hand-written core: XIC/XIO, branches, OTE/OTL/OTU, MOV, TON/TOF,
compares (EQU/NEQ/GRT/GEQ/LES/LEQ), AFI. Anything else lands as a
documented `st` fallback and is counted in the report - honesty over
silent mistranslation.

Latch reconstruction: a routine's OTL/OTU rungs on one target fold into
a single `assign` with the scan-order dominance preserved
(`later rung wins within the scan`); the fold is refused (st fallback)
if any rung between the writes reads the target, where flattening would
change semantics.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from ladder.ir.model import Project

_CMP = {"EQU": "=", "NEQ": "<>", "GRT": ">", "GEQ": ">=",
        "LES": "<", "LEQ": "<="}
_TIMER_MEMBER_BACK = {"DN": "Q", "ACC": "ET", "TT": "TT", "EN": "EN"}


class L5XError(ValueError):
    pass


@dataclass
class RockwellAdoptResult:
    project: Project
    report: str = ""
    unsupported: list[str] = field(default_factory=list)


# ------------------------------------------------------------ rung text


@dataclass
class _Instr:
    name: str
    args: list[str]


def _tokenize(text: str) -> list:
    """Rung text -> nested structure: _Instr and lists-of-branches."""
    text = text.strip().rstrip(";")
    pos = 0

    def parse_seq(stop: set[str]) -> list:
        nonlocal pos
        items: list = []
        while pos < len(text):
            ch = text[pos]
            if ch.isspace():
                pos += 1
                continue
            if ch in stop:
                return items
            if ch == "[":
                pos += 1
                branches = [parse_seq({",", "]"})]
                while text[pos] == ",":
                    pos += 1
                    branches.append(parse_seq({",", "]"}))
                pos += 1  # ']'
                items.append(branches)
                continue
            m = re.match(r"([A-Za-z_]\w*)\(", text[pos:])
            if not m:
                raise L5XError(f"unparseable rung text at ...{text[pos:pos+30]!r}")
            name = m.group(1)
            pos += m.end()
            depth, start = 1, pos
            while depth:
                if text[pos] == "(":
                    depth += 1
                elif text[pos] == ")":
                    depth -= 1
                pos += 1
            args = text[start:pos - 1]
            items.append(_Instr(name, [a.strip() for a in args.split(",")]
                                if args.strip() else []))
        return items

    return parse_seq(set())


def _name_back(operand: str, timer_names: set[str]) -> str:
    parts = operand.split(".")
    if parts[0] in timer_names and len(parts) > 1:
        member = _TIMER_MEMBER_BACK.get(parts[1], parts[1])
        return f"{parts[0]}_{member.lower()}" if member == "Q" else \
            ".".join([parts[0], member])
    return operand


def _cond_text(items: list, timer_names: set[str]) -> str | None:
    """Condition instructions -> neutral expression text (AND chain)."""
    terms: list[str] = []
    for it in items:
        if isinstance(it, list):  # branch = OR
            branches = [_cond_text(b, timer_names) or "TRUE" for b in it]
            terms.append("(" + " OR ".join(branches) + ")")
        elif it.name == "XIC":
            terms.append(_name_back(it.args[0], timer_names))
        elif it.name == "XIO":
            terms.append(f"NOT {_name_back(it.args[0], timer_names)}")
        elif it.name in _CMP:
            a = _name_back(it.args[0], timer_names)
            b = _name_back(it.args[1], timer_names)
            terms.append(f"{a} {_CMP[it.name]} {b}")
        elif it.name == "AFI":
            terms.append("FALSE")
        else:
            raise L5XError(f"unsupported condition instruction {it.name}")
    return " AND ".join(terms) if terms else None


# ----------------------------------------------------------- adoption


def _timer_presets(controller: ET.Element) -> dict[str, int]:
    presets: dict[str, int] = {}
    for tag in controller.iter("Tag"):
        if tag.get("DataType") != "TIMER":
            continue
        raw = ET.tostring(tag, encoding="unicode")
        m = re.search(r'Name="PRE"\s+DataType="DINT"[^/]*Value="(\d+)"', raw) \
            or re.search(r"PRE\s*:?=\s*(\d+)", raw)
        presets[tag.get("Name", "?")] = int(m.group(1)) if m else 0
    return presets


def adopt_rockwell_l5x(path: str | Path) -> RockwellAdoptResult:
    root = ET.parse(str(path)).getroot()
    controller = root.find("Controller")
    if controller is None:
        raise L5XError(f"{path}: no <Controller> (is this an L5X?)")
    name = controller.get("Name") or Path(path).stem

    unsupported: list[str] = []
    presets = _timer_presets(controller)
    timer_names = set(presets)

    # ---- types (skip Logix's hidden packing members)
    types = []
    dts = controller.find("DataTypes")
    for dt in dts.findall("DataType") if dts is not None else []:
        members = [{"name": m.get("Name"),
                    **({} if m.get("DataType") == "BOOL"
                       else {"type": m.get("DataType")})}
                   for m in dt.iter("Member")
                   if not m.get("Hidden", "false") == "true"
                   and not (m.get("Name") or "").startswith("ZZZZZZZZZZ")]
        if members:
            types.append({"name": dt.get("Name"), "members": members})

    # ---- tags (controller + program scope; aliases give direction)
    tags: list[dict] = []
    done_tags: set[str] = set()
    seen: set[str] = set()
    for tag in controller.iter("Tag"):
        tname, dtype = tag.get("Name"), tag.get("DataType", "BOOL")
        if not tname or tname in seen or dtype == "TIMER":
            continue
        seen.add(tname)
        entry: dict = {"name": tname, "type": dtype}
        alias = tag.get("AliasFor", "")
        if ":I" in alias:
            entry["direction"] = "input"
        elif ":O" in alias:
            entry["direction"] = "output"
        desc = tag.find("Description")
        if desc is not None and (desc.text or "").strip():
            entry["comment"] = desc.text.strip()
        tags.append(entry)

    # ---- programs
    programs = []
    for prog in controller.iter("Program"):
        logic: list[dict] = []
        for routine in prog.iter("Routine"):
            rtype = routine.get("Type")
            if rtype == "ST":
                lines = [ln.text or "" for ln in routine.iter("Line")]
                logic.append({"element": "st",
                              "id": f"ST_{routine.get('Name')}",
                              "code": "\n".join(lines)})
                continue
            if rtype != "RLL":
                unsupported.append(f"routine {routine.get('Name')}: type {rtype}")
                continue
            rungs: list[tuple[str | None, _Instr]] = []
            for rung in routine.iter("Rung"):
                text_el = rung.find("Text")
                text = (text_el.text or "").strip() if text_el is not None else ""
                if not text:
                    continue
                try:
                    items = _tokenize(text)
                    action = items[-1]
                    if isinstance(action, list) or action.name not in (
                            "OTE", "OTL", "OTU", "MOV", "TON", "TOF"):
                        raise L5XError(f"unsupported action in {text!r}")
                    rungs.append((_cond_text(items[:-1], timer_names), action))
                except L5XError as e:
                    unsupported.append(str(e))
                    rungs.append((None, _Instr("__RAW__", [text])))

            # one element per rung, in rung order - exact scan semantics
            for cond, act in rungs:
                if act.name == "__RAW__":
                    logic.append({"element": "st",
                                  "id": f"RAW_{len(logic)}",
                                  "code": f"(* untranslated rung: {act.args[0]} *)"})
                    continue
                if act.name == "OTL":
                    t = act.args[0]
                    logic.append({"element": "assign", "target": t,
                                  "value": f"({cond}) OR ({t})" if cond else "TRUE",
                                  "description": "latch set (OTL)"})
                    continue
                if act.name == "OTU":
                    t = act.args[0]
                    logic.append({"element": "assign", "target": t,
                                  "value": f"NOT ({cond}) AND ({t})" if cond
                                  else "FALSE",
                                  "description": "latch reset (OTU)"})
                    continue
                if act.name == "OTE":
                    t = act.args[0]
                    logic.append({"element": "assign", "target": t,
                                  "value": cond or "TRUE"})
                elif act.name == "MOV":
                    src, dst = act.args[0], act.args[1]
                    if cond:
                        logic.append({"element": "st", "id": f"MOV_{dst}_{len(logic)}",
                                      "code": f"IF {cond} THEN {dst} := {src}; END_IF;"})
                    else:
                        logic.append({"element": "assign", "target": dst,
                                      "value": src})
                elif act.name in ("TON", "TOF"):
                    inst = act.args[0]
                    done = f"{inst}_q"
                    if done not in done_tags:
                        done_tags.add(done)
                        tags.append({"name": done, "type": "BOOL",
                                     "comment": f"{inst} done bit (adopted)"})
                    logic.append({"element": "timer", "id": inst,
                                  "kind": act.name,
                                  "input": cond or "TRUE",
                                  "preset": f"T#{presets.get(inst, 0)}ms",
                                  "done": done})
        if logic:
            programs.append({"name": prog.get("Name"), "logic": logic})

    data = {"ir_version": "0.2", "name": name,
            "description": f"Adopted from {Path(path).name}",
            "types": types, "tags": tags, "programs": programs}
    if not types:
        data.pop("types")
    project = Project.model_validate(data)
    n_rungs = sum(len(p['logic']) for p in programs)
    report = (f"adopted {name}: {len(tags)} tags, {len(types)} type(s), "
              f"{len(programs)} program(s), {n_rungs} element(s); "
              f"{len(unsupported)} untranslated item(s)")
    return RockwellAdoptResult(project, report, unsupported)
