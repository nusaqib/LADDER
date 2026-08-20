"""Built-in patterns (v0.1: the shape, with one worked example)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ladder.ir.model import LogicElement, RawStEl, Tag


@dataclass
class Fragment:
    """What a pattern returns: tags + elements to splice into a program."""

    tags: list[Tag] = field(default_factory=list)
    locals_: list[Tag] = field(default_factory=list)
    logic: list[LogicElement] = field(default_factory=list)


def motor_starter(name: str, start: str, stop: str, fault: str,
                  run_output: str | None = None) -> Fragment:
    """Classic seal-in motor starter.

    start/stop/fault are existing BOOL tag names (stop and fault in
    fail-safe sense: TRUE = healthy). Creates <name>_run if run_output
    is not given.
    """
    run = run_output or f"{name}_run"
    tags = [] if run_output else [
        Tag(name=run, type="BOOL", direction="output", comment=f"{name} run command")
    ]
    seal_in = RawStEl(
        element="st",
        id=f"{name}_seal_in",
        description=f"seal-in starter for {name}",
        code=f"{run} := ({start} OR {run}) AND {stop} AND {fault};",
    )
    return Fragment(tags=tags, logic=[seal_in])
