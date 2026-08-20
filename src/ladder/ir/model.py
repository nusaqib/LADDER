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

IR_VERSION = "0.2"

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

#: Opaque system FB instance types (appear in adopted programs' locals).
INSTANCE_TYPES = {"TON", "TOF", "TP", "TON_TIME", "TOF_TIME", "TP_TIME",
                  "R_TRIG", "F_TRIG", "CTU", "CTD", "FBD_TIMER", "IEC_TIMER"}

Direction = Literal["input", "output", "memory"]


class StructMember(BaseModel):
    """One member of a user-defined struct (scalar or another struct)."""

    model_config = ConfigDict(extra="forbid")
    name: str
    type: str = "BOOL"
    initial: Optional[Any] = None
    comment: Optional[str] = None

    @field_validator("type")
    @classmethod
    def _norm_type(cls, v: str) -> str:
        return v.upper() if v.upper() in SCALAR_TYPES else v


class StructType(BaseModel):
    """User-defined data type (UDT). Backends map it to a TIA PLC data
    type, a Logix UDT, an IEC STRUCT, or a TwinCAT DUT."""

    model_config = ConfigDict(extra="forbid")
    name: str
    members: list[StructMember] = Field(min_length=1)
    comment: Optional[str] = None


class Tag(BaseModel):
    """A variable. Global (project.tags) or local to a program."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: str = "BOOL"
    array: Optional[int] = Field(
        default=None, ge=1,
        description="Array length N -> elements indexed 0..N-1.")
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

    @property
    def is_complex(self) -> bool:
        """UDT-typed or array tags (need a DB on Siemens, a UDT on Logix)."""
        return self.array is not None or self.type.upper() not in SCALAR_TYPES


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


class GroupAlarm(BaseModel):
    """One member of an alarm group. Same sense as `alarm`: condition TRUE
    = alarm present; optional on-delay debounce."""

    model_config = ConfigDict(extra="forbid")
    name: str
    condition: Cond
    on_delay: Optional[str] = Field(
        default=None, description="IEC TIME literal, e.g. 'T#2s'."
    )
    output: Optional[str] = Field(
        default=None, description="Optional BOOL tag mirroring this member's latched bit."
    )
    description: Optional[str] = None

    @field_validator("on_delay")
    @classmethod
    def _check_delay(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            X.parse_time_literal(v)
        return v


class AlarmGroupEl(BaseModel):
    """Annunciator-style alarm group: N latched alarms with a common
    acknowledge, a group-active lamp, an unacknowledged (horn) output that
    re-sounds on every new alarm, and first-out capture.

    Semantics (locked in lowering): each member latches on the rising edge
    of its (optionally delayed) condition. Ack (rising edge) silences the
    horn immediately and clears any latched member whose condition is gone.
    `first_out` receives the 1-based list index of the first member to trip
    after the group was clean; it resets to 0 when all members clear.
    """

    model_config = ConfigDict(extra="forbid")
    element: Literal["alarm_group"]
    id: str
    alarms: list[GroupAlarm] = Field(min_length=1)
    ack: str = Field(description="Common acknowledge signal (BOOL, rising edge).")
    active: str = Field(description="BOOL tag: any member latched (group lamp).")
    unacked: Optional[str] = Field(
        default=None,
        description="Optional BOOL tag: any member not yet acknowledged (horn).",
    )
    first_out: Optional[str] = Field(
        default=None,
        description="Optional INT/DINT tag: 1-based index of the first member "
        "to trip (0 = none). Resets when the group clears.",
    )
    description: Optional[str] = None


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


class ScaleEl(BaseModel):
    """Linear analog scaling: raw counts -> engineering units (REAL).

    output := input * k + b with k/b precomputed from the two ranges;
    clamped to the EU range by default.
    """

    model_config = ConfigDict(extra="forbid")
    element: Literal["scale"]
    id: str
    input: str = Field(description="Raw tag (INT/DINT/REAL), e.g. ADC counts.")
    output: str = Field(description="REAL/LREAL tag receiving engineering units.")
    raw_min: int = 0
    raw_max: int
    eu_min: float = 0.0
    eu_max: float
    clamp: bool = True
    description: Optional[str] = None

    @field_validator("raw_max")
    @classmethod
    def _nonzero_span(cls, v: int, info) -> int:
        if v == info.data.get("raw_min"):
            raise ValueError("raw_max must differ from raw_min")
        return v


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
    Union[AssignEl, InterlockEl, AlarmEl, AlarmGroupEl, TimerEl,
          StateMachineEl, ScaleEl, PatternEl, RawStEl],
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
    types: list[StructType] = Field(default_factory=list)
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
