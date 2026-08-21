---
name: tags-and-io
description: Design tag lists and IO binding - naming, BOOL senses, directions, scaling metadata, per-vendor address/alias mapping. Use when defining a project's signal list or wiring logic names to physical IO.
---

# Tags and IO: the signal list is the contract

The tag list is the most-reviewed table in any controls project. Get it
right before logic exists; every late tag rename is a diff across
logic, HMI, docs, and commissioning sheets.

## Naming

- Names are portable identifiers: letters/digits/underscore, no leading
  digit, ASCII. Assume case-insensitive matching (IEC rule) - never two
  tags differing only by case.
- Encode the *plant meaning*, not the wiring: `gate_sw_closed`, not
  `DI_04_12`. Wiring lives in the iomap.
- One consistent scheme per project, stated in the design map. Good
  default: `area_device_signal` (`bta_door2_closed`). For pattern-heavy
  plants a derived scheme works ({Area}_{Device}_{Signal} expanded by
  the generator) - then the scheme, not the names, is what's reviewed.
- Suffix conventions that pay off: `_ok` (healthy, 1=OK), `_pb`
  (pushbutton), `_cmd` (output command), `_fb` (feedback), `_alm`
  (alarm), `_flt` (fault latch).

## The sense rule (the classic field error)

Every BOOL input states what 1 means, in its comment, at design time.
House convention (fail-safe): **1 = OK / healthy / closed / not
tripped**, so a broken wire reads as a fault. NC field devices give you
this electrically - E-stops, gate switches, overload contacts are NC
for exactly this reason. When a device is genuinely NO (a start PB),
the name says so (`start_pb`, 1 = pressed). Never absorb an inversion
silently in logic: invert at the IO boundary (iomap/IOMap layer) and
document it, so the logic layer reads plant truth.

## Directions and hygiene

- `direction: input|output` on every field signal; internal state tags
  get none. Inputs are never written by logic (validator enforces);
  outputs written by exactly one element (lint W06).
- Analog inputs carry raw counts; convert once with a `scale` element
  into an engineering-units tag (`_eu` or unit suffix: `flow_lpm`) and
  use only that downstream. Record range/units in the design map's
  signal table.
- Simulator/scenarios default every input to 0 = fault: scenario
  first steps must set the healthy state explicitly. This default is a
  feature - forgetting a permissive shows up as a failing test.

## IO maps (hardware never in the IR)

One document per project, sections per vendor:

```yaml
project: Plant
siemens:  {estop_ok: {address: "%I0.0"}}
rockwell: {estop_ok: {alias: "Local:1:I.Data.0"}}
iec:      {estop_ok: {address: "%IX0.0"}}
```

- **Siemens**: absolute `%I/%Q` addresses; take byte offsets from the
  generated address map report, never from memory.
- **Rockwell**: alias tags onto module members - logic reads the alias,
  wiring changes touch only the iomap.
- **Beckhoff/IEC**: located variables (`AT %IX...`) or TwinCAT deferred
  `%I*` links.
- Unmapped tags get auto-allocated scratch addresses - fine for compile
  checks, wrong on a real panel; `ladder check` with the iomap wired in
  the manifest is the gate.

## Review checklist

- every input's 1-meaning stated; NC/NO of the field device recorded;
- no two names differing only by case or only by an easily-confused
  pair (l/1, O/0);
- every latching element's reset/ack is a named, physical, documented
  signal; and
- the iomap covers every `direction:` tag for every deploy target.
