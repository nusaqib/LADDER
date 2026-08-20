"""Built-in patterns: parameterized fragments of real IR elements.

A pattern returns structured elements (never raw ST when avoidable), so
expanded logic stays validatable, lowerable, and simulatable like anything
hand-written. Signal-sense convention is fail-safe throughout: parameters
named *_ok are TRUE when healthy.

The library grows by mining reference programs (M3); patterns contributed
here are the community commons once the project is public.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ladder.ir.model import AlarmEl, AssignEl, LogicElement, Tag


@dataclass
class Fragment:
    """What a pattern expansion produces: elements plus any program locals.

    Patterns never invent global tags - the IR author declares those, so
    name resolution and writability stay honestly validated.
    """

    logic: list[LogicElement] = field(default_factory=list)
    locals_: list[Tag] = field(default_factory=list)


class PatternError(ValueError):
    """Unknown pattern or bad parameters."""


def motor_starter(el_id: str, *, start: str, stop_ok: str, fault_ok: str,
                  run_output: str, description: str | None = None) -> Fragment:
    """Classic seal-in starter: momentary start, drops on stop or fault.

    stop_ok / fault_ok are fail-safe (TRUE = healthy). run_output must be a
    declared BOOL output tag; it participates in its own seal-in branch.
    """
    return Fragment(logic=[AssignEl(
        element="assign",
        target=run_output,
        value=f"({start} OR {run_output}) AND {stop_ok} AND {fault_ok}",
        description=description or f"seal-in motor starter {el_id}",
    )])


def valve_with_feedback(el_id: str, *, command: str, open_fb: str,
                        closed_fb: str, alarm_output: str,
                        travel_time: str = "T#5s", ack: str | None = None,
                        description: str | None = None) -> Fragment:
    """Commanded valve with position feedback supervision.

    Alarms when the feedback disagrees with the command for longer than the
    travel time (commanded open but not open_fb, or commanded closed but
    not closed_fb). Latching when an ack signal is given.
    """
    return Fragment(logic=[AlarmEl(
        element="alarm",
        id=f"{el_id}_mismatch",
        condition=f"({command} AND NOT {open_fb}) OR (NOT {command} AND NOT {closed_fb})",
        on_delay=travel_time,
        latching=ack is not None,
        ack=ack,
        output=alarm_output,
        severity="alarm",
        description=description or f"valve {el_id}: position feedback mismatch",
    )])


#: name -> callable(el_id, **params) -> Fragment
PATTERNS = {
    "motor_starter": motor_starter,
    "valve_with_feedback": valve_with_feedback,
}
