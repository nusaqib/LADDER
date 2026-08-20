"""Semantic validation of a LADDER IR project.

Runs after pydantic schema validation and before lowering. Everything here
is vendor-agnostic; per-vendor lint (reserved words, length limits a vendor
tightens further) lives in the backend.

Checks:
  V01 identifiers are portable across all target vendors
  V02 tag / program / element-id names are unique in their scope
  V03 every referenced name resolves (global tag or program local)
  V04 assignment / output targets exist and are not inputs
  V05 latching interlocks declare a reset; latching alarms declare an ack
  V06 boolean-element outputs are BOOL; state_tag is INT/DINT
  V07 state machine: initial/goto states exist, codes unique
  V08 periodic programs declare an interval
  V09 pattern elements must be expanded before validation

lint_project() adds non-fatal warnings on top:
  W01 output tag never written by any program
  W02 tag written by more than one program (scan-order hazard)
  W03 input tag never read
  W04 state machine trap state (no outgoing transitions)
  W05 unreachable state (not initial, no incoming transition)
  W06 tag written by multiple elements in one program (last writer wins)
Usage lint (W01-W03) is suppressed when the project contains raw `st`
elements - their reads/writes are opaque, so absence is not evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ladder.ir import expr as X
from ladder.ir.model import (
    AlarmEl,
    AssignEl,
    Cond,
    InterlockEl,
    PatternEl,
    Program,
    Project,
    RawStEl,
    ScaleEl,
    StateMachineEl,
    TimerEl,
    compile_cond,
)

# Portable across TIA Portal, Studio 5000, CODESYS/TwinCAT:
# starts with a letter, single underscores only, no trailing underscore.
_IDENT_RE = re.compile(r"^[A-Za-z](?:_?[A-Za-z0-9])*$")
_MAX_IDENT = 40  # Studio 5000 tag-name limit; strictest of the targets

# Union of IEC 61131-3 / SCL / Studio 5000 ST reserved words likely to bite.
_RESERVED = {
    "AND", "OR", "XOR", "NOT", "MOD", "TRUE", "FALSE", "IF", "THEN", "ELSE",
    "ELSIF", "END_IF", "CASE", "OF", "END_CASE", "FOR", "TO", "BY", "DO",
    "END_FOR", "WHILE", "END_WHILE", "REPEAT", "UNTIL", "END_REPEAT",
    "RETURN", "EXIT", "VAR", "END_VAR", "BOOL", "INT", "DINT", "REAL",
    "LREAL", "TIME", "WORD", "DWORD", "STRING", "BYTE", "SINT", "USINT",
    "UINT", "UDINT", "ARRAY", "STRUCT", "END_STRUCT", "TON", "TOF", "TP",
    "CTU", "CTD", "R_TRIG", "F_TRIG", "TASK", "PROGRAM", "END_PROGRAM",
    "FUNCTION", "FUNCTION_BLOCK", "TYPE", "END_TYPE", "CONSTANT", "RETAIN",
}


@dataclass
class Issue:
    code: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.code} [{self.where}] {self.message}"


@dataclass
class ValidationResult:
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def add(self, code: str, where: str, message: str) -> None:
        self.issues.append(Issue(code, where, message))

    def raise_if_failed(self) -> None:
        if self.issues:
            body = "\n".join(f"  {i}" for i in self.issues)
            raise ValueError(f"IR validation failed ({len(self.issues)} issue(s)):\n{body}")


def _check_ident(name: str, where: str, res: ValidationResult) -> None:
    if not _IDENT_RE.match(name):
        res.add("V01", where, f"identifier {name!r} is not vendor-portable "
                "(letter first, single underscores, no trailing underscore)")
    elif len(name) > _MAX_IDENT:
        res.add("V01", where, f"identifier {name!r} exceeds {_MAX_IDENT} chars (Studio 5000 limit)")
    elif name.upper() in _RESERVED:
        res.add("V01", where, f"identifier {name!r} is an IEC/vendor reserved word")


def _cond_refs(c: Cond, where: str, res: ValidationResult) -> list[X.Ref]:
    try:
        return list(X.refs(compile_cond(c)))
    except X.ExprError as e:
        res.add("V03", where, str(e))
        return []


BOOL_TYPES = {"BOOL"}
STATE_TYPES = {"INT", "DINT"}


def validate_project(project: Project) -> ValidationResult:
    res = ValidationResult()

    # -- V02 global uniqueness, V01 identifiers
    seen: dict[str, str] = {}
    for tag in project.tags:
        _check_ident(tag.name, f"tags/{tag.name}", res)
        if tag.name in seen:
            res.add("V02", f"tags/{tag.name}", f"duplicate of {seen[tag.name]}")
        seen[tag.name] = "global tag"
    for prog in project.programs:
        _check_ident(prog.name, f"programs/{prog.name}", res)
        if prog.name in seen:
            res.add("V02", f"programs/{prog.name}", f"duplicate of {seen[prog.name]}")
        seen[prog.name] = "program"

    for prog in project.programs:
        _validate_program(project, prog, res)

    return res


def _validate_program(project: Project, prog: Program, res: ValidationResult) -> None:
    pw = f"programs/{prog.name}"
    globals_ = {t.name: t for t in project.tags}
    locals_ = {t.name: t for t in prog.variables}

    # -- V08
    if prog.execution == "periodic" and not prog.interval:
        res.add("V08", pw, "periodic program must declare an interval")
    if prog.interval:
        try:
            X.parse_time_literal(prog.interval)
        except X.ExprError as e:
            res.add("V08", pw, str(e))

    # -- V02 locals, element ids
    for tag in prog.variables:
        _check_ident(tag.name, f"{pw}/variables/{tag.name}", res)
        if tag.name in globals_:
            res.add("V02", f"{pw}/variables/{tag.name}", "shadows a global tag")
        if tag.direction != "memory":
            res.add("V02", f"{pw}/variables/{tag.name}",
                    "program locals must be direction 'memory'; IO tags are global")
    ids_seen: set[str] = set()
    for el in prog.logic:
        el_id = getattr(el, "id", None)
        if el_id:
            _check_ident(el_id, f"{pw}/{el_id}", res)
            if el_id in ids_seen:
                res.add("V02", f"{pw}/{el_id}", "duplicate element id")
            ids_seen.add(el_id)

    def lookup(name: str):
        root = name.split(".")[0]
        return locals_.get(root) or globals_.get(root)

    def check_read(c: Cond, where: str) -> None:
        for ref in _cond_refs(c, where, res):
            if lookup(ref.root) is None:
                res.add("V03", where, f"unknown reference {ref}")

    def check_write(name: str, where: str, want_bool: bool = False) -> None:
        tag = lookup(name)
        if tag is None:
            res.add("V04", where, f"unknown target {name!r}")
            return
        if tag.direction == "input":
            res.add("V04", where, f"target {name!r} is an input and cannot be written")
        if want_bool and tag.type.upper() not in BOOL_TYPES:
            res.add("V06", where, f"target {name!r} must be BOOL, is {tag.type}")

    for el in prog.logic:
        w = f"{pw}/{getattr(el, 'id', None) or el.element}"
        if isinstance(el, AssignEl):
            check_read(el.value, w)
            check_write(el.target, w)
        elif isinstance(el, InterlockEl):
            check_read(el.permissives, w)
            check_write(el.output, w, want_bool=True)
            if el.latching and el.reset is None:
                res.add("V05", w, "latching interlock requires a reset")
            if el.reset:
                check_read(el.reset.signal, w)
        elif isinstance(el, AlarmEl):
            check_read(el.condition, w)
            check_write(el.output, w, want_bool=True)
            if el.latching and not el.ack:
                res.add("V05", w, "latching alarm requires an ack signal")
            if el.ack:
                check_read(el.ack, w)
        elif isinstance(el, TimerEl):
            check_read(el.input, w)
            if el.done:
                check_write(el.done, w, want_bool=True)
            if el.elapsed:
                check_write(el.elapsed, w)
        elif isinstance(el, StateMachineEl):
            _validate_state_machine(el, w, lookup, check_read, check_write, res)
        elif isinstance(el, ScaleEl):
            src = lookup(el.input)
            if src is None:
                res.add("V03", w, f"unknown scale input {el.input!r}")
            elif src.type.upper() not in ("INT", "DINT", "REAL", "LREAL"):
                res.add("V06", w, f"scale input {el.input!r} must be "
                        f"INT/DINT/REAL, is {src.type}")
            check_write(el.output, w)
            dst = lookup(el.output)
            if dst is not None and dst.type.upper() not in ("REAL", "LREAL"):
                res.add("V06", w, f"scale output {el.output!r} must be "
                        f"REAL or LREAL, is {dst.type}")
        elif isinstance(el, PatternEl):
            res.add("V09", w, f"pattern {el.ref!r} not expanded - load the IR "
                    "via load_project (or call ladder.patterns.expand_project)")
        elif isinstance(el, RawStEl):
            pass  # escape hatch: backends lint lightly

def lint_project(project: Project) -> list[Issue]:
    """Non-fatal warnings: unused/multiply-written tags, SM reachability."""
    warns: list[Issue] = []
    reads: set[str] = set()
    writes: dict[str, set[str]] = {}  # tag -> programs writing it
    opaque = False

    def add_reads(c: Cond) -> None:
        try:
            reads.update(r.root for r in X.refs(compile_cond(c)))
        except X.ExprError:
            pass  # V03 already reports it

    def add_write(name: str, prog: str) -> None:
        writes.setdefault(name.split(".")[0], set()).add(prog)

    for prog in project.programs:
        for el in prog.logic:
            if isinstance(el, AssignEl):
                add_reads(el.value)
                add_write(el.target, prog.name)
            elif isinstance(el, InterlockEl):
                add_reads(el.permissives)
                add_write(el.output, prog.name)
                if el.reset:
                    reads.add(el.reset.signal.split(".")[0])
            elif isinstance(el, AlarmEl):
                add_reads(el.condition)
                add_write(el.output, prog.name)
                if el.ack:
                    reads.add(el.ack.split(".")[0])
            elif isinstance(el, TimerEl):
                add_reads(el.input)
                for t in (el.done, el.elapsed):
                    if t:
                        add_write(t, prog.name)
            elif isinstance(el, StateMachineEl):
                reads.add(el.state_tag.split(".")[0])
                add_write(el.state_tag, prog.name)
                for st in el.states:
                    for act in st.do:
                        add_reads(act.value)
                        add_write(act.target, prog.name)
                    for tr in st.transitions:
                        add_reads(tr.when)
                _lint_state_machine(el, f"programs/{prog.name}/{el.id}", warns)
            elif isinstance(el, ScaleEl):
                reads.add(el.input.split(".")[0])
                add_write(el.output, prog.name)
            elif isinstance(el, RawStEl):
                opaque = True

    # W06: two elements in the same program writing the same tag fight each
    # other every scan (last writer wins) - almost always a mistake.
    for prog in project.programs:
        writers: dict[str, list[str]] = {}
        for el in prog.logic:
            el_id = getattr(el, "id", None) or el.element
            for t in _element_writes(el):
                writers.setdefault(t.split(".")[0], []).append(el_id)
        for tag_name, els in writers.items():
            if len(els) > 1:
                warns.append(Issue("W06", f"programs/{prog.name}/{tag_name}",
                                   f"written by multiple elements ({', '.join(els)}) "
                                   "- last writer wins every scan"))

    if not opaque:
        for tag in project.tags:
            if tag.direction == "output" and tag.name not in writes:
                warns.append(Issue("W01", f"tags/{tag.name}",
                                   "output is never written by any program"))
            elif tag.direction == "input" and tag.name not in reads:
                warns.append(Issue("W03", f"tags/{tag.name}",
                                   "input is never read"))
    for name, progs in writes.items():
        if len(progs) > 1:
            warns.append(Issue("W02", f"tags/{name}",
                               f"written by multiple programs ({', '.join(sorted(progs))}) "
                               "- scan-order hazard"))
    return warns


def _element_writes(el) -> list[str]:
    """Tags an element writes (state machines count as one writer)."""
    if isinstance(el, AssignEl):
        return [el.target]
    if isinstance(el, (InterlockEl, AlarmEl)):
        return [el.output]
    if isinstance(el, TimerEl):
        return [t for t in (el.done, el.elapsed) if t]
    if isinstance(el, ScaleEl):
        return [el.output]
    if isinstance(el, StateMachineEl):
        return list({act.target for st in el.states for act in st.do} | {el.state_tag})
    return []


def _lint_state_machine(el: StateMachineEl, w: str, warns: list[Issue]) -> None:
    incoming = {tr.goto for st in el.states for tr in st.transitions}
    for st in el.states:
        if not st.transitions:
            warns.append(Issue("W04", f"{w}/{st.name}",
                               "trap state: no outgoing transitions"))
        if st.name != el.initial and st.name not in incoming:
            warns.append(Issue("W05", f"{w}/{st.name}",
                               "unreachable: not initial and no transition targets it"))


def _validate_state_machine(el: StateMachineEl, w: str, lookup, check_read,
                            check_write, res: ValidationResult) -> None:
    tag = lookup(el.state_tag)
    if tag is None:
        res.add("V04", w, f"unknown state_tag {el.state_tag!r}")
    elif tag.type.upper() not in STATE_TYPES:
        res.add("V06", w, f"state_tag {el.state_tag!r} must be INT or DINT, is {tag.type}")
    names = [s.name for s in el.states]
    if len(set(names)) != len(names):
        res.add("V07", w, "duplicate state names")
    codes = [s.code for s in el.states if s.code is not None]
    if len(set(codes)) != len(codes):
        res.add("V07", w, "duplicate state codes")
    if el.initial not in names:
        res.add("V07", w, f"initial state {el.initial!r} not defined")
    for st in el.states:
        for act in st.do:
            check_read(act.value, f"{w}/{st.name}")
            check_write(act.target, f"{w}/{st.name}")
        for tr in st.transitions:
            check_read(tr.when, f"{w}/{st.name}")
            if tr.goto not in names:
                res.add("V07", f"{w}/{st.name}", f"transition to unknown state {tr.goto!r}")
