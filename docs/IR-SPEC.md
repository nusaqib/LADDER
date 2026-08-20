# LADDER IR — specification (v0.2)

The IR is a YAML or JSON document validated in three layers:

1. **Schema** — `ladder schema` exports the JSON Schema (pydantic-derived).
2. **Semantics** — `ladder validate` runs checks V01–V08 (identifiers,
   name resolution, writability, fail-safe rules, state-machine sanity).
3. **Backend lint** — a backend refuses what it cannot express
   (e.g. Rockwell has no ST pulse timer).

Design intent: keep the generation problem small and checkable. Elements are
*declarative* ("this is a latching interlock on these permissives"), and their
runtime semantics are defined once in `src/ladder/ir/lower.py` for every vendor.

## Document root

```yaml
ir_version: "0.2"
name: ProjectName            # portable identifier
description: ...             # optional
types: [...]                 # user-defined types (see Types)
tags: [...]                  # global variables (see Tags)
programs: [...]              # at least one (see Programs)
vendor:                      # OPTIONAL per-backend hints; IR must stand alone
  siemens:  {tia_version: "21.0", fb_prefix: FB_, tia_api_path: ...}
  rockwell: {processor: 1756-L85E, major_rev: 36}
```

## Types (UDTs)

```yaml
types:
  - name: PumpCtrl
    comment: Everything one pump needs.
    members:
      - {name: run_cmd, type: BOOL}
      - {name: hours,   type: DINT, initial: 0}
      - {name: inner,   type: OtherUdt}     # nesting allowed, cycles rejected (V10)
```

Backends map UDTs to TIA PLC data types, Logix UDTs (BOOL members packed as
BIT views on hidden SINT hosts), IEC STRUCTs, and TwinCAT DUTs.

## Tags

```yaml
- name: pressure_ok          # portable identifier (V01)
  type: BOOL                 # scalar, or a UDT name from types:
  array: 8                   # optional -> elements indexed 0..7
  direction: input           # input | output | memory (default memory)
  address: "%I0.0"           # optional vendor hint; real IO mapping is engine-phase
  initial: false             # optional
  retain: false
  comment: Gauge below setpoint
```

Program-local variables use the same shape (direction must be `memory`).
UDT/array tags must also be `memory` (V10) — IO stays scalar; structuring IO
belongs to the vendor engine. On **Siemens**, complex tags live in a
generated global DB (`"<Project>_DB".pump.run_cmd`) because TIA PLC tags
cannot hold structs/arrays; scalars remain PLC tags. Type mapping notes:
Rockwell has no TIME tag type — it becomes DINT milliseconds (commented);
WORD/DWORD become INT/DINT there.

References reach into structures with members and literal indices:
`pump.run_cmd`, `temps[3]`, `axes[2].pos` — resolution, member existence,
and index range are all validated (V10).

## Expressions and conditions

Anywhere a condition is accepted, write either a **neutral ST expression
string** or a **structured tree** (preferred for LLM output — shallow and
checkable):

```yaml
permissives:
  all:
    - pressure_ok
    - any: [gate_a_closed, gate_b_closed]
    - not: maintenance_mode
    - "fill_level >= setpoint - 2.5"
```

Expression syntax (vendor-neutral ST subset): `AND OR XOR NOT`,
comparisons `= <> < <= > >=`, arithmetic `+ - * / MOD`, parentheses,
`TRUE/FALSE`, numbers, `T#…` TIME literals, identifiers with member access
(`T1.Q`). Expressions are parsed to an AST — never passed through as text —
so each backend renders its own dialect (`#local`/`"global"` in SCL,
`.DN`/ms presets in Logix, plain IEC elsewhere).

## Logic elements

Every element may carry `description`. Elements with state carry a unique `id`.

### assign

```yaml
- element: assign
  target: at_vacuum
  value: pressure_ok AND stable_ok     # any condition
```

### interlock — fail-safe permissive

```yaml
- element: interlock
  id: IL_shutter
  permissives: {all: [pressure_ok, gate_valve_closed]}
  output: beam_shutter_permit          # BOOL, TRUE = permitted
  latching: true                       # default
  reset: {signal: reset_pb, edge: rising}   # required when latching (V05)
```

Semantics: output drops the same scan any permissive is lost; when latching,
it re-arms **only** on the reset (rising edge by default) while all
permissives are healthy. Non-latching (`latching: false`) is a plain follow.

### alarm

```yaml
- element: alarm
  id: ALM_vacuum
  condition: NOT pressure_ok
  on_delay: T#2s          # optional debounce (TON before the alarm)
  latching: true          # requires ack (V05)
  ack: ack_pb
  output: vacuum_alarm    # BOOL, TRUE = active
  severity: critical      # info | warning | alarm | critical
```

Latched alarms clear on an ack rising edge only after the (delayed)
condition has gone.

### alarm_group — annunciator with first-out

```yaml
- element: alarm_group
  id: GRP_panel
  ack: ack_pb             # common acknowledge (rising edge)
  active: alarm_lamp      # BOOL: any member latched (group lamp)
  unacked: horn           # optional BOOL: any unacknowledged (horn)
  first_out: fo_code      # optional INT/DINT: 1-based index of first trip
  alarms:
    - name: no_flow
      condition: {not: flow_ok}
      on_delay: T#2s      # optional per-member debounce
      output: flow_lamp   # optional BOOL mirroring this member's latch
    - name: overtemp
      condition: {not: temp_ok}
```

Annunciator semantics (ISA 18.1 sequence A, simplified), locked in
lowering: each member latches on the rising edge of its (delayed)
condition; a **new** alarm re-sounds the horn even while older alarms
stand unacknowledged; ack silences the horn immediately and clears any
latched member whose condition has gone (a standing condition stays
latched until it clears and is acked again). `first_out` receives the
1-based list index of the first member to trip after the group was clean
(0 = none) and resets when the group clears. `ladder model` auto-generates
the theorems `unacked -> active` and `active <-> first_out <> 0` for
nuXmv.

### timer

```yaml
- element: timer
  id: T_stable
  kind: TON               # TON | TOF | TP  (TP unsupported on Rockwell)
  input: pressure_ok
  preset: T#10s
  done: stable_ok         # optional BOOL  (Q / .DN)
  elapsed: t_elapsed      # optional TIME/DINT (ET / .ACC)
```

### state_machine

```yaml
- element: state_machine
  id: SM_pumpdown
  state_tag: pumpdown_state   # INT/DINT tag (V06)
  initial: IDLE
  states:
    - name: PUMPING
      code: 1                 # optional; defaults to list order
      do:                     # runs every scan while in the state
        - {target: pump_start_cmd, value: "TRUE"}
      transitions:            # evaluated in order, first match wins
        - {when: pump_fault_alarm, goto: FAULT}
        - {when: stable_ok,        goto: AT_VACUUM}
```

Lowered to a CASE on `state_tag` with an IF/ELSIF transition chain.

### scale — analog scaling

```yaml
- element: scale
  id: SC_level
  input: level_raw        # INT/DINT/REAL raw value (e.g. ADC counts)
  output: level_pct       # REAL/LREAL engineering units (V06)
  raw_min: 0
  raw_max: 27648          # vendor ADC ranges differ - always explicit
  eu_min: 0.0
  eu_max: 100.0
  clamp: true             # default: clamp output to the EU range
```

Lowered to a precomputed multiply-add (`output := INT_TO_REAL(input) * k + b`)
plus clamp; dialects that convert numeric types implicitly (Logix ST) drop
the explicit conversion.

### pattern — library invocation (the LLM fast path)

```yaml
- element: pattern
  id: pump_motor
  ref: motor_starter          # library name (see src/ladder/patterns/library.py)
  params:
    start: start_pb
    stop_ok: stop_ok          # fail-safe: TRUE = healthy
    fault_ok: motor_fault_ok
    run_output: pump_run
```

Expanded into real elements before validation (`load_project` does this by
default), so pattern output is checked, lowered, and simulated exactly like
hand-written IR. Patterns never invent global tags — declare those yourself.
Built-ins so far: `motor_starter` (seal-in), `valve_with_feedback`
(position mismatch supervision). Unexpanded patterns fail validation (V09).

### st — escape hatch

```yaml
- element: st
  id: custom_calc
  code: |
    scaled := raw * span / 27648.0 + offs;
```

Neutral ST passed through with reference decoration only. Bypasses most
IR-level checking — keep rare; recurring uses should become new elements
or patterns.

## Programs

```yaml
- name: SafetyPermissives
  execution: cyclic        # cyclic | periodic
  interval: T#100ms        # required when periodic (V08)
  variables: [...]         # locals
  logic: [...]             # elements, emitted in order
```

Mapping: Siemens → SCL `FUNCTION_BLOCK` (instance/OB wiring is engine-phase);
Rockwell → `Program` with an ST `Main` routine, scheduled in a continuous or
periodic task; PLCopen/Beckhoff → `PROGRAM` POU (+ tc6 task entry).

Lowering also **synthesizes** hidden locals per program: timer instances
(`<id>_ton`, `<id>_t`) and edge memories (`<id>_rst_mem`, `<id>_ack_mem`) —
identical state on every vendor.

## IO maps (separate document)

The IR never carries hardware. A per-vendor IO map binds IO tags to real
addresses at build time (`ladder build --iomap plant.iomap.yaml`):

```yaml
io_version: "0.1"
project: VacuumInterlock            # must match the IR project name
siemens:
  pressure_ok: {address: "%I8.0"}   # absolute PLC-tag address
rockwell:
  pressure_ok: {alias: "Local:1:I.Data.0"}   # controller tag becomes an alias
beckhoff:
  pressure_ok: {address: "%IX0.0"}  # AT %.. located variable ("%I*" = link later)
iec:
  pressure_ok: {address: "%IX8.0"}  # 61131 located variable
```

Each section uses that vendor's own syntax; the map is cross-checked
against the IR (tags exist, are IO, no duplicate bindings) before any
backend runs. Unmapped IO keeps default behavior (auto-allocated scratch
addresses on Siemens, plain tags elsewhere). See
[examples/vacuum_interlock.iomap.yaml](../examples/vacuum_interlock.iomap.yaml).

## Validation codes

| Code | Meaning |
|---|---|
| V01 | identifier not vendor-portable / too long / reserved word |
| V02 | duplicate or shadowed name; IO tag declared as a local |
| V03 | unresolved reference or bad expression syntax |
| V04 | write to an unknown target or an input |
| V05 | latching interlock without reset / latching alarm without ack |
| V06 | wrong type (interlock/alarm outputs BOOL; state_tag INT/DINT) |
| V07 | state machine: unknown initial/goto, duplicate names/codes |
| V08 | periodic program without a valid interval |
| V09 | pattern element not expanded before validation |
