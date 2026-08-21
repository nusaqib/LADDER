# Alarm management (ISA-18.2 / IEC 62682) — working notes

> Normative sources: ANSI/ISA-18.2 "Management of Alarm Systems for the
> Process Industries" and its international twin IEC 62682. Also useful:
> EEMUA 191. Original summaries below of the concepts LADDER encodes.

## The alarm state model (what an alarm *is*)

An alarm is a combination of two independent axes:

- **process state**: the abnormal condition is present or absent;
- **acknowledge state**: the operator has or hasn't acknowledged it.

That yields the classic four states: Normal → **Unacknowledged Alarm**
(condition in, not acked) → **Acknowledged Alarm** (condition in, acked)
→ **Return-To-Normal Unacknowledged** (condition cleared, not acked;
only exists for latching alarms) → Normal. LADDER's `alarm` element
implements exactly this: `latching: true` keeps the output up after the
condition clears until acked; a non-latching alarm follows the condition.

Rules that keep the model honest:

1. **Ack never clears an active condition.** Acknowledging while the
   condition persists changes the annunciation (silence the horn, steady
   the lamp) — the alarm output stays up. LADDER enforces this ordering
   structurally in `alarm` and `alarm_group`.
2. **Debounce (on-delay) before annunciation**, not after — a chattering
   input must not chatter the horn. `on_delay: T#1s` in the IR.
3. **Every latching alarm names its ack signal.** An alarm with no
   documented ack path is a design error (LADDER lint flags it).

## Annunciator sequences (the `alarm_group` element)

Physical annunciator behavior is standardized by ISA-18.1 (sequences
named A, F1A, F2A…, M). The one plants actually mean by default is
**sequence A**: new alarm → flashing lamp + horn; ack → horn off, lamp
steady while condition persists; condition clears after ack → lamp off;
reset for latched cleared alarms. LADDER's `alarm_group` implements the
sequence-A contract with:

- per-member latched outputs,
- one shared `horn` output (any unacknowledged member drives it),
- one shared `ack`,
- **first-out** (`first_out` INT): records which member tripped first in
  a group of related trips — the diagnostic gold during a cascade — and
  holds it until group reset. ISA-18.1 calls these "first-out sequences";
  the INT-index design (0 = none, 1-based member index) is LADDER's.

## Design guidance the standard insists on (and we mirror)

- Alarms are for conditions **requiring operator action** — a status
  lamp is not an alarm; don't put it in the alarm list.
- **Severity/priority** is an attribute assigned at design time from
  consequence and time-to-respond (`severity:` in the IR; the docgen
  package carries it into the operator manual's alarm response table).
- Alarm response documentation — cause, consequence, operator action —
  belongs with the alarm's definition. In LADDER that's the element's
  `description` plus the generated operator manual; write them as if the
  operator reads them at 3 a.m., because they will.
- Suppression/shelving is an HMI-layer discipline with audit trails —
  deliberately *not* in LADDER's PLC-side IR.
