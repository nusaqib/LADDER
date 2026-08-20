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


def iec_var_line(tag: Tag, indent: str = "    ") -> str:
    init = fmt_initial(tag.initial, tag.type)
    line = f"{indent}{tag.name} : {tag.type}"
    if init is not None:
        line += f" := {init}"
    line += ";"
    if tag.comment:
        line += f"  // {tag.comment}"
    return line


def synth_var_line(v: SynthVar, timer_type: str, indent: str = "    ") -> str:
    type_ = timer_type if v.kind == "timer" else "BOOL"
    line = f"{indent}{v.name} : {type_};"
    if v.comment:
        line += f"  // {v.comment}"
    return line


def local_declarations(lp: LoweredProgram, dialect, indent: str = "    ") -> list[str]:
    """VAR-block lines for program locals plus lowering-synthesized vars."""
    lines = [iec_var_line(t, indent) for t in lp.program.variables]
    lines += [
        synth_var_line(v, dialect.timer_decl_type(v) if v.kind == "timer" else "BOOL", indent)
        for v in lp.synth
    ]
    return lines
