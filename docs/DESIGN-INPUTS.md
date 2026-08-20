# The Design Inputs Map

The single biggest predictor of a successful generated PLC project is not
the model or the prompt — it is whether the *design inputs* were captured
completely before any IR was written. This document defines that intake:
what must be known, in what structure, and how each section maps onto
LADDER artifacts. The `design-intake` skill fills this map from a user's
plain-language description; the `ir-authoring` skill consumes it.

A filled map is an authoring artifact (markdown or YAML — it is read by
people and agents, not parsed by the tool). Keep it next to the IR it
produced, e.g. `myproject.design.md` beside `myproject.yaml`.

## Why a map at all

Plain-language requirements reliably omit the same things: signal sense
(is 1 flow-OK or flow-FAULT?), reset authority, alarm debounce, what
happens *after* a trip, and acceptance criteria. Every one of those
omissions becomes either a wrong-but-valid program or a generation loop
that thrashes. The map forces the questions before generation.

## The map

### 1. Project identity

| Field | Maps to |
|---|---|
| Project name (identifier-safe) | `name:` in the IR |
| One-line purpose | `description:` |
| Target vendor(s) + versions | which backends to build/verify |
| Execution model: one cyclic program or split? periodic rates? | `programs:` structure, `execution`/`interval` |
| Language preferences per program (ladder for electricians? sfc for sequences?) | `language:` |

### 2. Signal list — the IO contract

One row per physical or HMI signal. **This table is the contract; nothing
else in the map may reference a signal that is not in it.**

| Column | Rule |
|---|---|
| name | vendor-portable identifier (letter first, single underscores, ≤40 chars) |
| meaning | one line, plain language |
| type | BOOL / INT / DINT / REAL / TIME |
| direction | input / output / memory (HMI setpoints and states are memory) |
| **sense** | for BOOL inputs: what does 1 mean? LADDER convention is **1 = OK / healthy / closed / present**; flag any signal that violates it and invert at the map level, not in scattered logic |
| address | optional; goes to the IO map document, never the IR |
| device | where it physically comes from (helps reviewers) |

### 3. Equipment list

Motors, valves, heaters, pumps — anything with start/stop or open/close
behavior. Each row names its signals (from §2) and states whether a
library **pattern** fits (`motor_starter`, `valve_with_feedback`, ...).
Patterns first: they encode reviewed semantics and shrink the generation
problem.

### 4. Interlock matrix

One row per protective function. This is the section to be pedantic in.

| Column | Maps to |
|---|---|
| id (`IL_*`) | element `id` |
| protects (equipment/action) | `output` permit tag |
| permissives (all §2 signals, OK-sense) | `permissives:` condition tree |
| latching? | `latching:` (default yes — trips hold) |
| reset authority (which signal, who presses it) | `reset:` |
| trip consequence (what must the rest of the logic do when the permit drops?) | sequence/alarm cross-references |

### 5. Alarm list

| Column | Maps to |
|---|---|
| id (`ALM_*`) / group membership | `alarm` or `alarm_group` member |
| condition (alarm-present sense) | `condition:` |
| debounce | `on_delay:` |
| severity | `severity:` |
| latching + ack signal | `latching:`/`ack:` |
| annunciator outputs: group lamp, horn, first-out display | `alarm_group` `active`/`unacked`/`first_out` |

If three or more alarms share an ack or a horn, use one `alarm_group`,
not separate alarms.

### 6. Sequences

One entry per state machine: states, per-state outputs (every output the
machine owns should be assigned in **every** state — no implicit holds),
transition conditions in priority order, timeout/abort paths back to a
safe state. Maps to `state_machine` (or `language: sfc` program).

### 7. Analog signals

Per analog: raw range (counts), EU range + units, clamp?, alarm
thresholds (which feed §5). Maps to `scale` elements.

### 8. Timing table

Every delay/debounce/pulse in one place: purpose, preset, which element
consumes it. Presets scattered through prose get lost.

### 9. Acceptance scenarios — the definition of done

Three to six concrete behaviors, given/when/then, each naming §2 signals:

> Given flow_ok and temp_ok, when temp_ok drops for 2 s, then horn sounds
> and first_out_code = 2; ack silences the horn but the lamp holds.

These become the `*.scenarios.yaml` suite that gates generation
(`ladder test`, `ladder generate --scenarios`). **A map without
scenarios is not complete** — they are what makes "successful project"
checkable rather than vibes.

### 10. Hardware map (optional at generation time)

Rack/slot/channel per §2 address. Maps to the IO-map document
(`--iomap`), keeping the IR hardware-free.

## Completeness gate

Generate only when:

- [ ] every signal referenced anywhere appears in §2 with type, direction, sense
- [ ] every BOOL input's sense is stated (and OK-sense by convention)
- [ ] every latching interlock/alarm names its reset/ack signal
- [ ] every sequence state assigns all outputs the machine owns
- [ ] at least three acceptance scenarios exist and name only §2 signals
- [ ] safety-rated functions (SIL/PL) are explicitly out of scope — LADDER
      output is not certified safety logic

Anything unknown: ask, or record an explicit assumption in the map and
mark it for review. Never invent a signal.
