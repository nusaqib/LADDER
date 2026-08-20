"""LADDER IR data model (pydantic).

This is the contract the LLM (or a human) writes against, in YAML or JSON.
It is deliberately high-level and declarative: interlocks, alarms, timers,
state machines - not rungs or vendor syntax. `ladder schema` exports the
JSON Schema so generated IR can be machine-validated before any vendor
code exists.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ladder.ir import expr as X

IR_VERSION = "0.1"

# ------------------------------------------------------------- conditions
#
# A condition is either a neutral ST expression string, or a structured
# boolean tree - the tree form keeps LLM output shallow and checkable:
#
#   permissives:
#     all:
#       - pressure_ok
#       - any: [gate_a_closed, gate_b_closed]
#       - not: maintenance_mode


class CondAll(BaseModel):
    model_config = ConfigDict(extra="forbid")
    all: list["Cond"] = Field(min_length=1)


class CondAny(BaseModel):
    model_config = ConfigDict(extra="forbid")
    any: list["Cond"] = Field(min_length=1)


class CondNot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    not_: "Cond" = Field(alias="not")


Cond = Union[str, CondAll, CondAny, CondNot]


def compile_cond(c: Cond) -> X.Expr:
    """Compile a condition (string or structured tree) to an expression AST."""
    if isinstance(c, str):
        return X.parse_expr(c)
    if isinstance(c, CondAll):
        return X.all_of([compile_cond(x) for x in c.all])
    if isinstance(c, CondAny):
        return X.any_of([compile_cond(x) for x in c.any])
    if isinstance(c, CondNot):
        return X.Un("NOT", compile_cond(c.not_))
    raise TypeError(f"not a condition: {c!r}")


# ------------------------------------------------------------------- tags

#: Neutral scalar types every backend maps natively.
SCALAR_TYPES = {"BOOL", "INT", "DINT", "REAL", "LREAL", "TIME", "WORD", "DWORD", "STRING"}

Direction = Literal["input", "output", "memory"]


class Tag(BaseModel):
    """A variable. Global (project.tags) or local to a program."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: str = "BOOL"
    direction: Direction = "memory"
    address: Optional[str] = Field(
        default=None,
        description="Optional vendor address hint (e.g. '%I0.0'). Real IO "
        "mapping belongs to the vendor engine phase, not the IR.",
    )
    initial: Optional[Any] = None
    retain: bool = False
    comment: Optional[str] = None

    @field_validator("type")
    @classmethod
    def _norm_type(cls, v: str) -> str:
        return v.upper() if v.upper() in SCALAR_TYPES else v


# --------------------------------------------------------- logic elements


class ResetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    signal: str
    edge: Literal["rising", "level"] = "rising"


class AssignEl(BaseModel):
    """Unconditional assignment: target := value (every scan)."""

    model_config = ConfigDict(extra="forbid")
    element: Literal["assign"]
    target: str
    value: Cond
    description: Optional[str] = None


class InterlockEl(BaseModel):
    """Permissive interlock. Fail-safe sense: output TRUE = permitted.

    Latching (default): the permit drops the scan any permissive goes false
    and stays down until a manual reset while all permissives are healthy.
    """

    model_config = ConfigDict(extra="forbid")
    element: Literal["interlock"]
    id: str
    permissives: Cond
    output: str
    latching: bool = True
    reset: Optional[ResetSpec] = None
    description: Optional[str] = None


class AlarmEl(BaseModel):
    """Alarm: condition TRUE = alarm active, optional on-delay and latching."""

    model_config = ConfigDict(extra="forbid")
    element: Literal["alarm"]
    id: str
    condition: Cond
    output: str
    on_delay: Optional[str] = Field(
        default=None, description="IEC TIME literal, e.g. 'T#2s'."
    )
    latching: bool = False
    ack: Optional[str] = Field(
        default=None, description="Acknowledge signal (required if latching)."
    )
    severity: Literal["info", "warning", "alarm", "critical"] = "alarm"
    description: Optional[str] = None

    @field_validator("on_delay")
    @classmethod
    def _check_delay(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            X.parse_time_literal(v)
        return v


class TimerEl(BaseModel):
    """Standalone IEC timer (TON / TOF / TP)."""

    model_config = ConfigDict(extra="forbid")
    element: Literal["timer"]
    id: str
    kind: Literal["TON", "TOF", "TP"] = "TON"
    input: Cond
    preset: str = Field(description="IEC TIME literal, e.g. 'T#500ms'.")
    done: Optional[str] = Field(default=None, description="BOOL tag receiving Q/DN.")
    elapsed: Optional[str] = Field(default=None, description="TIME/DINT tag receiving ET/ACC.")
    description: Optional[str] = None

    @field_validator("preset")
    @classmethod
    def _check_preset(cls, v: str) -> str:
        X.parse_time_literal(v)
        return v


class SMAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str
    value: Cond


class SMTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    when: Cond
    goto: str


class SMState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    code: Optional[int] = Field(default=None, description="Numeric code; defaults to list order.")
    do: list[SMAction] = Field(default_factory=list)
    transitions: list[SMTransition] = Field(default_factory=list)
    description: Optional[str] = None


class StateMachineEl(BaseModel):
    """Flat state machine, lowered to a CASE statement per vendor."""

    model_config = ConfigDict(extra="forbid")
    element: Literal["state_machine"]
    id: str
    state_tag: str = Field(description="INT/DINT tag holding the current state code.")
    initial: str
    states: list[SMState] = Field(min_length=1)
    description: Optional[str] = None


class PatternEl(BaseModel):
    """Invocation of a library pattern - expanded into real elements before
    validation (see ladder.patterns.expand_project). This is the intended
    LLM fast path: pick a pattern, fill in parameters."""

    model_config = ConfigDict(extra="forbid")
    element: Literal["pattern"]
    id: str
    ref: str = Field(description="Pattern name in the library, e.g. 'motor_starter'.")
    params: dict[str, Any] = Field(default_factory=dict)
    description: Optional[str] = None


class RawStEl(BaseModel):
    """Escape hatch: neutral Structured Text passed through verbatim.

    Use only for logic no structured element expresses; it bypasses most
    IR-level checking, so backends can only lint it lightly.
    """

    model_config = ConfigDict(extra="forbid")
    element: Literal["st"]
    id: str
    code: str
    description: Optional[str] = None


LogicElement = Annotated[
    Union[AssignEl, InterlockEl, AlarmEl, TimerEl, StateMachineEl, PatternEl, RawStEl],
    Field(discriminator="element"),
]


# ---------------------------------------------------------------- program


class Program(BaseModel):
    """One program organization unit. Backends map it to an FB (Siemens),
    a Program with an ST routine (Rockwell), or a PROGRAM POU (61131)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    execution: Literal["cyclic", "periodic"] = "cyclic"
    interval: Optional[str] = Field(
        default=None, description="TIME literal, required when execution='periodic'."
    )
    variables: list[Tag] = Field(default_factory=list)
    logic: list[LogicElement] = Field(min_length=1)
    description: Optional[str] = None


class Project(BaseModel):
    """Root of a LADDER IR document."""

    model_config = ConfigDict(extra="forbid")

    ir_version: str = IR_VERSION
    name: str
    description: Optional[str] = None
    tags: list[Tag] = Field(default_factory=list)
    programs: list[Program] = Field(min_length=1)
    vendor: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Optional per-backend hints, e.g. rockwell: {processor: 1756-L85E}. "
        "Never required; the IR must stand alone.",
    )


CondAll.model_rebuild()
CondAny.model_rebuild()
CondNot.model_rebuild()
