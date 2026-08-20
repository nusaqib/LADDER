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
  V10 type errors: unknown/cyclic UDTs, bad member paths, out-of-range
      array indices, complex (UDT/array) tags used as IO or whole-value
  V11 program language cannot express the program's logic (e.g. a state
      machine in ladder, raw st in il, non-BOOL assigns in ladder/fbd)

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
    SCALAR_TYPES,
    AlarmEl,
    AlarmGroupEl,
    AssignEl,
    Cond,
    InterlockEl,
    PatternEl,
    Program,
    Project,
    RawStEl,
    ScaleEl,
    StateMachineEl,
    StructType,
    Tag,
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


def resolve_path(types: dict[str, StructType], tag: Tag,
                 path: tuple[str, ...]) -> tuple[str, str]:
    """Resolve a reference path against a tag's type.

    Returns (final_type, "") on success or ("", error message) on failure.
    A whole UDT/array used as a value (path exhausts on a complex type) is
    an error - expressions and targets must land on a scalar.
    """
    _, idx = X.split_segment(path[0])
    cur = tag.type
    if idx is not None:
        if tag.array is None:
            return "", f"{tag.name!r} is not an array"
        if not (0 <= idx < tag.array):
            return "", f"index {idx} out of range for {tag.name!r} (0..{tag.array - 1})"
    elif tag.array is not None and len(path) > 1:
        return "", f"array {tag.name!r} needs an index before member access"
    for seg in path[1:]:
        name, seg_idx = X.split_segment(seg)
        if seg_idx is not None:
            return "", f"member arrays are not supported (segment {seg!r})"
        udt = types.get(cur)
        if udt is None:
            return "", f"{cur!r} has no member {name!r}"
        member = next((m for m in udt.members if m.name == name), None)
        if member is None:
            return "", f"UDT {cur!r} has no member {name!r}"
        cur = member.type
    if cur.upper() not in SCALAR_TYPES:
        if tag.array is not None and idx is None and len(path) == 1:
            return "", f"array {tag.name!r} used without an index"
        return "", f"whole UDT {cur!r} cannot be used as a value"
    if tag.array is not None and idx is None and len(path) == 1:
        return "", f"array {tag.name!r} used without an index"
    return cur.upper(), ""


def _validate_types(project: Project, res: ValidationResult) -> dict[str, StructType]:
    types: dict[str, StructType] = {}
    for t in project.types:
        w = f"types/{t.name}"
        _check_ident(t.name, w, res)
        if t.name in types or t.name.upper() in SCALAR_TYPES:
            res.add("V02", w, "duplicate or reserved type name")
        types[t.name] = t
        member_names = set()
        for m in t.members:
            _check_ident(m.name, f"{w}/{m.name}", res)
            if m.name in member_names:
                res.add("V02", f"{w}/{m.name}", "duplicate member")
            member_names.add(m.name)
    # member types resolve; no cycles
    for t in project.types:
        for m in t.members:
            if m.type.upper() not in SCALAR_TYPES and m.type not in types:
                res.add("V10", f"types/{t.name}/{m.name}",
                        f"unknown member type {m.type!r}")

    def has_cycle(name: str, stack: set[str]) -> bool:
        if name in stack:
            return True
        udt = types.get(name)
        if udt is None:
            return False
        return any(has_cycle(m.type, stack | {name}) for m in udt.members)

    for t in project.types:
        if has_cycle(t.name, set()):
            res.add("V10", f"types/{t.name}", "recursive UDT nesting")
            break
    return types


def validate_project(project: Project) -> ValidationResult:
    res = ValidationResult()
    types = _validate_types(project, res)

    # -- V02 global uniqueness, V01 identifiers, V10 tag typing
    seen: dict[str, str] = {}
    for tag in project.tags:
        _check_ident(tag.name, f"tags/{tag.name}", res)
        if tag.name in seen:
            res.add("V02", f"tags/{tag.name}", f"duplicate of {seen[tag.name]}")
        seen[tag.name] = "global tag"
        _check_tag_type(tag, f"tags/{tag.name}", types, res)
    for prog in project.programs:
        _check_ident(prog.name, f"programs/{prog.name}", res)
        if prog.name in seen:
            res.add("V02", f"programs/{prog.name}", f"duplicate of {seen[prog.name]}")
        seen[prog.name] = "program"

    for prog in project.programs:
        _validate_program(project, prog, types, res)

    return res


def _check_tag_type(tag: Tag, w: str, types: dict[str, StructType],
                    res: ValidationResult) -> None:
    from ladder.ir.model import INSTANCE_TYPES

    if tag.type.upper() in INSTANCE_TYPES:
        return  # opaque system FB instance (adopted programs)
    if tag.type.upper() not in SCALAR_TYPES and tag.type not in types:
        res.add("V10", w, f"unknown type {tag.type!r}")
    if tag.is_complex:
        if tag.direction != "memory":
            res.add("V10", w, "UDT/array tags must be direction 'memory' "
                    "(map IO to scalar tags; structuring IO is engine-phase)")
        if tag.address:
            res.add("V10", w, "UDT/array tags cannot carry an address hint")


def _validate_program(project: Project, prog: Program,
                      types: dict[str, StructType], res: ValidationResult) -> None:
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
        _check_tag_type(tag, f"{pw}/variables/{tag.name}", types, res)
    ids_seen: set[str] = set()
    for el in prog.logic:
        el_id = getattr(el, "id", None)
        if el_id:
            _check_ident(el_id, f"{pw}/{el_id}", res)
            if el_id in ids_seen:
                res.add("V02", f"{pw}/{el_id}", "duplicate element id")
            ids_seen.add(el_id)

    def lookup(name: str):
        try:
            root = X.split_segment(name.split(".")[0])[0]
        except X.ExprError:
            return None
        return locals_.get(root) or globals_.get(root)

    def resolve(name: str, where: str, code: str) -> str | None:
        """Full typed resolution of a dotted/indexed path; returns the
        final scalar type or None (an issue was recorded)."""
        path = tuple(name.split("."))
        tag = lookup(name)
        if tag is None:
            res.add(code, where, f"unknown {'target' if code == 'V04' else 'reference'} {name!r}")
            return None
        final, err = resolve_path(types, tag, path)
        if err:
            res.add("V10", where, f"{name!r}: {err}")
            return None
        return final

    def check_read(c: Cond, where: str) -> None:
        for ref in _cond_refs(c, where, res):
            # timer-instance members (e.g. T1.Q) are synthesized later; the
            # IR author only references declared tags, so resolve fully
            resolve(str(ref), where, "V03")

    def check_write(name: str, where: str, want_bool: bool = False) -> str | None:
        tag = lookup(name)
        if tag is not None and tag.direction == "input":
            res.add("V04", where, f"target {name!r} is an input and cannot be written")
        final = resolve(name, where, "V04")
        if want_bool and final is not None and final not in BOOL_TYPES:
            res.add("V06", where, f"target {name!r} must be BOOL, is {final}")
        return final

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
        elif isinstance(el, AlarmGroupEl):
            member_names: set[str] = set()
            for m in el.alarms:
                mw = f"{w}/{m.name}"
                _check_ident(m.name, mw, res)
                if m.name in member_names:
                    res.add("V02", mw, "duplicate alarm name in group")
                member_names.add(m.name)
                check_read(m.condition, mw)
                if m.output:
                    check_write(m.output, mw, want_bool=True)
            check_read(el.ack, w)
            check_write(el.active, w, want_bool=True)
            if el.unacked:
                check_write(el.unacked, w, want_bool=True)
            if el.first_out:
                fo_type = check_write(el.first_out, w)
                if fo_type is not None and fo_type not in STATE_TYPES:
                    res.add("V06", w, f"first_out {el.first_out!r} must be "
                            f"INT or DINT, is {fo_type}")
        elif isinstance(el, TimerEl):
            check_read(el.input, w)
            if el.done:
                check_write(el.done, w, want_bool=True)
            if el.elapsed:
                check_write(el.elapsed, w)
        elif isinstance(el, StateMachineEl):
            _validate_state_machine(el, w, resolve, check_read, check_write, res)
        elif isinstance(el, ScaleEl):
            src_type = resolve(el.input, w, "V03")
            if src_type is not None and src_type not in ("INT", "DINT", "REAL", "LREAL"):
                res.add("V06", w, f"scale input {el.input!r} must be "
                        f"INT/DINT/REAL, is {src_type}")
            dst_type = check_write(el.output, w)
            if dst_type is not None and dst_type not in ("REAL", "LREAL"):
                res.add("V06", w, f"scale output {el.output!r} must be "
                        f"REAL or LREAL, is {dst_type}")
        elif isinstance(el, PatternEl):
            res.add("V09", w, f"pattern {el.ref!r} not expanded - load the IR "
                    "via load_project (or call ladder.patterns.expand_project)")
        elif isinstance(el, RawStEl):
            pass  # escape hatch: backends lint lightly

    _check_language(prog, pw, resolve, res)


#: elements a graphic boolean language (LD / FBD) can express
_GRAPHIC_ELEMENTS = {"assign", "interlock", "alarm", "alarm_group", "timer"}


def _check_language(prog: Program, pw: str, resolve, res: ValidationResult) -> None:
    """V11: the chosen language must be able to express the program."""
    lang = prog.language
    if lang == "st":
        return
    if lang == "il":
        for el in prog.logic:
            if isinstance(el, RawStEl):
                res.add("V11", f"{pw}/{el.id}",
                        "raw st element cannot be rendered as il")
        return
    if lang == "sfc":
        real = [el for el in prog.logic if not isinstance(el, PatternEl)]
        if len(real) != 1 or not isinstance(real[0], StateMachineEl):
            res.add("V11", pw, "an sfc program must contain exactly one "
                    "state_machine element and nothing else")
        return
    # ladder / fbd: boolean networks, timers, and annunciators only
    for el in prog.logic:
        w = f"{pw}/{getattr(el, 'id', None) or el.element}"
        if el.element not in _GRAPHIC_ELEMENTS:
            res.add("V11", w, f"element {el.element!r} cannot be rendered as "
                    f"{lang} (use st, or sfc for state machines)")
        elif isinstance(el, AssignEl):
            final = resolve(el.target, w, "V04")
            if final is not None and final not in BOOL_TYPES:
                res.add("V11", w, f"{lang} assigns must target BOOL tags "
                        f"({el.target!r} is {final})")
        elif isinstance(el, TimerEl):
            if el.elapsed:
                res.add("V11", w, f"timer 'elapsed' output is not rendered in "
                        f"{lang}; drop it or use st")

def _lint_root(name: str) -> str:
    try:
        return X.split_segment(name.split(".")[0])[0]
    except X.ExprError:
        return name.split(".")[0]


def lint_project(project: Project) -> list[Issue]:
    """Non-fatal warnings: unused/multiply-written tags, SM reachability."""
    warns: list[Issue] = []
    reads: set[str] = set()
    writes: dict[str, set[str]] = {}  # full target path -> programs writing it
    written_roots: set[str] = set()
    opaque = False

    def add_reads(c: Cond) -> None:
        try:
            reads.update(r.root for r in X.refs(compile_cond(c)))
        except X.ExprError:
            pass  # V03 already reports it

    def add_write(name: str, prog: str) -> None:
        written_roots.add(_lint_root(name))
        writes.setdefault(name, set()).add(prog)  # full path: temps[0] != temps[1]

    for prog in project.programs:
        for el in prog.logic:
            if isinstance(el, AssignEl):
                add_reads(el.value)
                add_write(el.target, prog.name)
            elif isinstance(el, InterlockEl):
                add_reads(el.permissives)
                add_write(el.output, prog.name)
                if el.reset:
                    reads.add(_lint_root(el.reset.signal))
            elif isinstance(el, AlarmEl):
                add_reads(el.condition)
                add_write(el.output, prog.name)
                if el.ack:
                    reads.add(_lint_root(el.ack))
            elif isinstance(el, AlarmGroupEl):
                for m in el.alarms:
                    add_reads(m.condition)
                    if m.output:
                        add_write(m.output, prog.name)
                reads.add(_lint_root(el.ack))
                for t in (el.active, el.unacked, el.first_out):
                    if t:
                        add_write(t, prog.name)
            elif isinstance(el, TimerEl):
                add_reads(el.input)
                for t in (el.done, el.elapsed):
                    if t:
                        add_write(t, prog.name)
            elif isinstance(el, StateMachineEl):
                reads.add(_lint_root(el.state_tag))
                add_write(el.state_tag, prog.name)
                for st in el.states:
                    for act in st.do:
                        add_reads(act.value)
                        add_write(act.target, prog.name)
                    for tr in st.transitions:
                        add_reads(tr.when)
                _lint_state_machine(el, f"programs/{prog.name}/{el.id}", warns)
            elif isinstance(el, ScaleEl):
                reads.add(_lint_root(el.input))
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
                writers.setdefault(t, []).append(el_id)  # full path, not root
        for tag_name, els in writers.items():
            if len(els) > 1:
                warns.append(Issue("W06", f"programs/{prog.name}/{tag_name}",
                                   f"written by multiple elements ({', '.join(els)}) "
                                   "- last writer wins every scan"))

    if not opaque:
        for tag in project.tags:
            if tag.direction == "output" and tag.name not in written_roots:
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
    if isinstance(el, AlarmGroupEl):
        return ([t for t in (el.active, el.unacked, el.first_out) if t]
                + [m.output for m in el.alarms if m.output])
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


def _validate_state_machine(el: StateMachineEl, w: str, resolve, check_read,
                            check_write, res: ValidationResult) -> None:
    final = resolve(el.state_tag, w, "V04")
    if final is not None and final not in STATE_TYPES:
        res.add("V06", w, f"state_tag {el.state_tag!r} must be INT or DINT, is {final}")
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
