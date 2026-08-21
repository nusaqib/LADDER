---
name: hmi-design
description: Operator interface design and generation - screen hierarchy, alarm presentation, write contracts, tag binding, WinCC Unified / vendor specifics, HMI-from-design-data generation. Use when a project needs operator screens or an HMI layer must be captured/reproduced.
---

# HMI: the operator's contract with the logic

The HMI is generated from the same design data as the logic wherever
possible (screens per area, faceplates per device UDT) - hand-drawn
screens drift from the program the same way hand-written docs do.

## Structure (the hierarchy that works)

- **Overview** (one screen): every area's summary state, permits, and
  active-alarm count - the "is the plant OK" glance.
- **Area screens** (one per area/UDT instance): the area's devices with
  live states, its permit chain visualized (show WHICH permissive is
  down - the operator's first question), area commands.
- **Detail/diagnostic screens** per device class where depth exists
  (per-door, per-chain-input pages in the PPS reproduction: 14 screens
  = overview + 3 areas x detail set + gates).
- Navigation strictly tree-shaped, depth <= 3, every screen labeled
  with its area name - operators navigate under stress.

## Display rules

1. Show plant truth, not raw IO: bind to the evaluated/typed members
   (`DB.Area.Door2_OK`), never to raw channels.
2. State is shown by **shape/position + color**, never color alone
   (color-blind operators exist; alarms flash + move to a list).
3. Every latched condition displays with its reset path visible ("Trip:
   overload - RESET at panel PB3" beats a red lamp).
4. Alarm presentation follows the alarm philosophy (ISA-18.2 note in
   docs/reference): unacked flashing + horn, acked steady,
   cleared-unacked distinct; first-out visibly marked in group
   displays.

## The write contract (where HMIs cause incidents)

- HMI writes go to *command* tags the logic consumes and clears -
  never directly to outputs, never to permits.
- Momentary buttons need an explicit contract: write-1-on-press /
  write-0-on-release (and the PPS convention: logic also clears the
  bit, so a stuck client can't hold a command). Document per button.
- Nothing safety-critical originates from the HMI: an HMI "reset" is a
  *request* the safety layer validates against physical conditions.
  Setpoint writes get PLC-side clamps - the HMI limit is UX, the PLC
  limit is the contract.

## Tag binding and generation

- Bind via an integrated/connected tag layer referencing PLC symbols;
  generate HMI tags from the UDT tree so names match the program
  exactly. Typed struct binding (one HMI tag per area UDT) keeps
  faceplates reusable.
- Generate screens from design data: devices per area from the UDT/tag
  tables, one faceplate per device class. The PPS HMI builder
  (Build-PpsHmi pattern) is the reference implementation: screens,
  faceplate instances, and bindings all derived - a new door is a table
  row, not a drawing task.

## Vendor notes (tested findings)

- **WinCC Unified (TIA)**: panels + screens + tags scriptable via
  Openness; but an *integrated* HMI connection cannot be created
  headlessly (Partner/Station read-only on V19 AND V21) - create the
  connection with driver + address, generate typed-but-unbound tags,
  and document the one-time GUI bind step. Screen-item surface differs
  per version (V21 adds faceplate generation APIs V19 lacks).
- **Rockwell**: FactoryTalk View projects are not text-friendly; keep
  the generated layer to the tag/alarm export and display lists.
- Keep HMI content OUT of the PLC IR (labels, colors, layouts) - the
  IR carries the process contract (tags, alarms with severities,
  states) the HMI generator consumes.

## Review checklist

- every screen reachable from overview in <=2 clicks; every command
  tag's write contract documented; alarm colors/behavior match the
  philosophy doc; every displayed value traceable to a typed member;
  the manual bind/connection steps (if any) in the runbook.
