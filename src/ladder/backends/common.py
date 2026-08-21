"""Helpers shared by backends."""

from __future__ import annotations

from ladder.ir import expr as X
from ladder.ir.lower import LoweredProgram, SynthVar
from ladder.ir.model import Tag


def fmt_initial(value, type_: str) -> str | None:
    """IEC-style initial value text, or None if no initializer."""
    if value is None:
        return None
    t = type_.upper()
    if t == "BOOL":
        return "TRUE" if value in (True, 1, "true", "TRUE") else "FALSE"
    if t == "TIME":
        return value if isinstance(value, str) else X.format_time_ms(int(value))
    if t == "STRING":
        return f"'{value}'"
    if t in ("REAL", "LREAL"):
        s = str(float(value))
        return s if "." in s else s + ".0"
    return str(value)


def iec_type_text(tag: Tag) -> str:
    """IEC type text for a tag, including arrays: 'ARRAY[0..7] OF REAL'."""
    base = tag.type
    if tag.array is not None:
        return f"ARRAY[0..{tag.array - 1}] OF {base}"
    return base


def iec_var_line(tag: Tag, indent: str = "    ") -> str:
    init = fmt_initial(tag.initial, tag.type) if tag.array is None else None
    line = f"{indent}{tag.name} : {iec_type_text(tag)}"
    if init is not None:
        line += f" := {init}"
    line += ";"
    if tag.comment:
        line += f"  // {tag.comment}"
    return line


def iec_struct_lines(struct, indent: str = "    ") -> list[str]:
    """TYPE ... : STRUCT body lines for a StructType (61131 syntax)."""
    lines = [f"TYPE {struct.name} :", f"{indent}STRUCT"]
    for m in struct.members:
        init = fmt_initial(m.initial, m.type)
        line = f"{indent}{indent}{m.name} : {m.type}"
        if init is not None:
            line += f" := {init}"
        lines.append(line + ";")
    lines += [f"{indent}END_STRUCT;", "END_TYPE"]
    return lines


def synth_type(v: SynthVar, dialect) -> str:
    """Declaration type of a lowering-synthesized variable: timer instance
    (dialect-specific), REAL state (pid), or BOOL (edge memories/latches)."""
    if v.kind == "timer":
        return dialect.timer_decl_type(v)
    return "REAL" if v.kind == "real" else "BOOL"


def synth_var_line(v: SynthVar, type_: str, indent: str = "    ") -> str:
    line = f"{indent}{v.name} : {type_};"
    if v.comment:
        line += f"  // {v.comment}"
    return line


def local_declarations(lp: LoweredProgram, dialect, indent: str = "    ") -> list[str]:
    """VAR-block lines for program locals plus lowering-synthesized vars."""
    lines = [iec_var_line(t, indent) for t in lp.program.variables]
    lines += [synth_var_line(v, synth_type(v, dialect), indent) for v in lp.synth]
    return lines
