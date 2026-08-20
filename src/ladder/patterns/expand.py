"""Expand pattern elements into real IR elements (runs before validation)."""

from __future__ import annotations

from ladder.ir.model import PatternEl, Program, Project
from ladder.patterns.library import PATTERNS, PatternError


def expand_program(prog: Program) -> Program:
    if not any(isinstance(el, PatternEl) for el in prog.logic):
        return prog
    logic, extra_locals = [], []
    for el in prog.logic:
        if not isinstance(el, PatternEl):
            logic.append(el)
            continue
        fn = PATTERNS.get(el.ref)
        if fn is None:
            raise PatternError(
                f"[{prog.name}/{el.id}] unknown pattern {el.ref!r}; "
                f"available: {', '.join(sorted(PATTERNS))}")
        try:
            fragment = fn(el.id, **el.params)
        except TypeError as e:
            raise PatternError(f"[{prog.name}/{el.id}] bad params for "
                               f"{el.ref!r}: {e}") from None
        logic.extend(fragment.logic)
        extra_locals.extend(fragment.locals_)
    return prog.model_copy(update={
        "logic": logic,
        "variables": [*prog.variables, *extra_locals],
    })


def expand_project(project: Project) -> Project:
    programs = [expand_program(p) for p in project.programs]
    if all(a is b for a, b in zip(programs, project.programs)):
        return project
    return project.model_copy(update={"programs": programs})
