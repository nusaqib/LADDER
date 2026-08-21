# Tutorial: your first real project

You've done [Getting started](GETTING-STARTED.md). Now we build something
real, the way a controls engineer actually works: requirement → design
map → logic → acceptance tests → proofs → deliverables. One step at a
time; every step ends green.

On a real project you would hand most of the typing below to an
assistant — `ladder prompt --intake` makes any LLM run this exact
sequence, interviewing you for the decisions and drafting the files
(see [WORKFLOW](WORKFLOW.md)). We do it by hand here because the steps
*are* the review skill: every question this tutorial makes you answer
is a question you'll later be checking an assistant's draft against.

**The requirement** (from an imaginary plant meeting):

> "A vacuum pump skid. The pump needs cooling water and must not run hot.
> There's a gate valve to the beamline that must only open once we're
> actually under vacuum. Operators want a proper alarm panel — lamp,
> horn, and it has to show what tripped first. Oh, and nothing restarts
> by itself after a trip."

## Step 1 — start from the map, not the logic

```powershell
ladder init vacuum-skid
cd vacuum-skid
```

Open `design/DESIGN.md`. Before writing any logic, we answer the
questions the prose skipped — this is the habit that separates a good
project from a haunted one:

- *What does each signal mean when its wire breaks?* We adopt the house
  rule: every BOOL input reads **1 = OK/healthy/closed**. A broken wire
  then reads as a fault. Write it in §2.
- *Who may reset, and when?* "Nothing restarts by itself" → the pump
  permit is **latching** with a `reset_pb`, and the alarm panel has a
  separate `ack_pb`. Two different authorities, two different signals.
- *"Runs hot", how long is too long?* Ask; the plant says debounce the
  flow switch 2 s so a pressure blip doesn't nuisance-trip. That is a
  row in §8 (the timing table), with its reason.

Replace the starter tables in §2–§8 with the skid's: five inputs
(`water_flow_ok`, `pump_temp_ok`, `vacuum_ok`, `gate_open_fb`,
`gate_closed_fb`), four pushbuttons, and outputs for the pump, the
valve command, and the panel (`panel_lamp`, `horn`, plus an INT
`first_out` for the HMI).

## Step 2 — the protective core (one interlock)

Edit `ir/vacuum_skid.yaml`. Replace the starter tags with §2, then write
the first element and *only* the first element:

```yaml
- element: interlock
  id: IL_pump
  description: Cooling water and pump temperature; manual reset after a trip.
  permissives: {all: [water_flow_ok, pump_temp_ok]}
  output: pump_permit
  reset: {signal: reset_pb}
```

`ladder check .` — validation passes, scenarios fail (they still test the
starter). Delete the starter scenarios and write just one:

```yaml
- name: permit_needs_reset_after_trip
  steps:
    - set: {water_flow_ok: true, pump_temp_ok: true}
    - pulse: reset_pb                      # startup acknowledge
    - expect: {pump_permit: true}
    - set: {water_flow_ok: false}
    - scan: {}
    - expect: {pump_permit: false}
    - set: {water_flow_ok: true}           # water returns...
    - scan: {}
    - expect: {pump_permit: false}         # ...but nothing self-restarts
    - pulse: reset_pb
    - expect: {pump_permit: true}
```

Green. Notice what the scenario pins: not just "it trips" but the two
behaviors that matter in the field — the startup acknowledge, and
*restore ≠ re-arm*.

## Step 3 — equipment from the library

The pump start/stop is a solved problem; use the pattern instead of
re-deriving a seal-in:

```yaml
- element: pattern
  id: MTR_pump
  ref: motor_starter
  params: {start: start_pb, stop_ok: stop_ok, fault_ok: pump_permit,
           run_output: pump_run}
```

And the valve, with its supervision (commanded open but never reaches
the open switch within 5 s = a real fault):

```yaml
- element: assign
  target: gate_open_cmd
  value: {all: [pump_run, vacuum_ok]}
  description: Gate opens only while pumping under good vacuum.

- element: pattern
  id: VLV_gate
  ref: valve_with_feedback
  params: {command: gate_open_cmd, open_fb: gate_open_fb,
           closed_fb: gate_closed_fb, alarm_output: gate_fault,
           travel_time: T#5s, ack: ack_pb}
```

Add a scenario per behavior (gate waits for vacuum; mismatch alarms
after 5 s and acks only once the feedback is healthy). `ladder check .`
after each one — never write two features between checks.

## Step 4 — the annunciator (one element, not a page of rungs)

"Lamp, horn, what tripped first" is the classic annunciator, and it is
one element:

```yaml
- element: alarm_group
  id: GRP_panel
  ack: ack_pb
  active: panel_lamp
  unacked: horn
  first_out: first_out
  alarms:
    - {name: no_water, condition: {not: water_flow_ok}, on_delay: T#2s}
    - {name: overtemp, condition: {not: pump_temp_ok}}
    - {name: vac_loss, condition: {all: [gate_open_fb, {not: vacuum_ok}]}}
```

The semantics you did not have to write (they're locked in LADDER's
lowering, identically on every vendor): the horn re-sounds for every
*new* alarm, acknowledging silences the horn but a standing cause keeps
its lamp, and `first_out` holds the first member's number until the
panel clears. Pin the one that surprises people:

```yaml
- name: ack_silences_horn_lamp_stays
  steps:
    - set: {water_flow_ok: true, pump_temp_ok: true, vacuum_ok: true}
    - scan: {}
    - set: {pump_temp_ok: false}
    - scan: {}
    - expect: {horn: true, panel_lamp: true, first_out: 2}
    - pulse: ack_pb
    - expect: {horn: false, panel_lamp: true, first_out: 2}
```

## Step 5 — prove it, don't just test it

Scenarios check the timings you thought of. The model checker checks
**all of them**:

```powershell
ladder model ir\vacuum_skid.yaml -o out
```

Every interlock and alarm group gets auto-generated theorems (the permit
is never TRUE with a permissive down; the horn never sounds without the
lamp; first-out is consistent). With nuXmv installed
(`NUXMV_BIN=...\nuXmv.exe`):

```powershell
ladder verify ir\vacuum_skid.yaml -t smv -o out
```

`all properties proved` means those statements hold for *every* preset
and scan rate — a stronger claim than any number of simulations.

## Step 6 — addresses, artifacts, deliverables

Hardware lives in the IO map, never in the logic. Fill
`iomaps/vacuum_skid.iomap.yaml` from the panel drawings, then:

```powershell
ladder check .      # now builds with real %I/%Q addresses
ladder docs .       # requirements, software spec, operator manual...
```

Open `docs/generated/05-operator-manual.md` — the operator's view of your
annunciator, derived from the same file that generated the PLC code, so
it can never drift. If this machine has TIA Portal, set
`deploy: [siemens@21]` in `ladder.yaml` and `ladder deploy .` for an
openable, compiled TIA project under `out/siemens/project/`.

## What you practiced

Design map before logic · one element per check · scenarios that pin the
uncomfortable behaviors (restore ≠ re-arm, ack ≠ reset) · patterns for
solved problems · proofs for protective functions · hardware out of the
IR · documentation as a build product. That loop scales from this skid
to a personnel protection system — the elements get more serious
(`dual_channel`, `search_chain`), the loop stays identical.

Next: the [guide](GUIDE.md) for task-sized recipes, or
[DESIGN-INPUTS](DESIGN-INPUTS.md) to run a real intake.
