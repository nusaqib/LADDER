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

### dual_channel — 1oo2 two-channel evaluation

```yaml
- element: dual_channel
  id: DC_gate
  channel_a: gate_sw1        # fail-safe sense, 1 = OK
  channel_b: gate_sw2
  output: gate_ok            # BOOL: both channels OK, no latched fault
  discrepancy_time: T#500ms  # optional: enables discrepancy monitoring
  fault: gate_disc_flt       # optional BOOL: latched discrepancy
  ack: area_reset            # required with discrepancy_time
  ack_required: gate_ack_req # optional BOOL: fault latched, channels agree
```

The shape of certified safety evaluations (Siemens `EV1oo2DI`, redundant
limit switches, CW/CCW chains): channels disagreeing longer than the
window latch a fault that forces the output FALSE until acknowledged with
the channels back in agreement. `ladder model` auto-generates
`output -> chA AND chB` for nuXmv. Models the logic only — no
QBAD/passivation/PROFIsafe; the output is **not** certified safety logic.

### search_chain — sequential area search (PPS)

```yaml
- element: search_chain
  id: SRCH_area
  precondition: area_inputs_ok      # chain armed only while this holds
  complete: area_search_complete
  stations:                         # in WALK ORDER
    - {name: SE01, key: se01_key_ok, latched: db.SE01.Latched}
    - {name: SE02, key: se02_key_ok}   # latch synthesized if omitted
```

Locked semantics (accelerator-PPS practice): a station latches on the
**rising edge** of its key (a key held early cannot ride the chain) and
only while its predecessor is latched (station 1: while `precondition`
holds); losing the predecessor clears the station, so a breach cascades
down the walk order and drops `complete` within one scan; **nothing else
clears a station** — never wire an acknowledge here. Known residual: all
keys rising within one scan completes the chain that scan. Auto-theorems:
`complete -> precondition` and `station_i -> station_{i-1}` per pair.

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

## Languages (per program)

`language: st | il | ladder | fbd | sfc` (default `st`) declares the
preferred IEC 61131-3 representation for a program. It is a **rendering
preference, not semantics** — every language renders the same lowered
statement AST, so the simulator, scenarios, and model checker are
unaffected. Backends honor the preference where the target format
supports that language and fall back to ST otherwise (noted in the
output). Validation **V11** rejects logic the chosen language cannot
express:

| language | can express | rejected (V11) |
|---|---|---|
| `st` | everything | — |
| `il` | everything structured | raw `st` elements |
| `ladder` / `fbd` | assign (BOOL), interlock, alarm, alarm_group, timer (no `elapsed`) | state_machine, scale, st, non-BOOL assigns |
| `sfc` | exactly one state_machine | anything else |

Native renderings (everything else falls back to ST with a note):

| language | rendered natively by |
|---|---|
| `il` | iec (`.st` file, matiec-checked in CI), plcopen (`<IL>` body) |
| `ladder` | rockwell (RLL rung routines, native TIMER tags), plcopen (`<LD>` contacts/coils, set/reset via `storage`) |
| `fbd` | plcopen (`<FBD>` block networks; set/reset rungs fold into the standard latch idiom, later-rung dominant) |
| `sfc` | iec (textual SFC: STEP/TRANSITION/ACTION, matiec-checked in CI), plcopen (`<SFC>` steps/transitions); actions also keep `state_tag` truthful |

Emitted PLCopen XML — including all graphic bodies — validates against the
official tc6_0201 XSD (checked in CI).

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
