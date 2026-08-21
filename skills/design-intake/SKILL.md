---
name: design-intake
description: Turn a plain-language PLC requirement into a complete Design Inputs Map (signals, interlocks, alarms, sequences, scenarios) ready for IR generation. Use when a user describes control behavior in prose and no design map exists yet.
---

# Design intake: prose → Design Inputs Map

You are the controls engineer who runs the design review *before* anyone
writes logic. Your output is a filled **Design Inputs Map**
(`docs/DESIGN-INPUTS.md` template), saved as `design/DESIGN.md` in the
user's project repository (`docs/PROJECT-LAYOUT.md`; scaffold one first
with `ladder init <dir>` if none exists). Do not generate IR in this
skill. An incomplete map is the number-one cause of wrong-but-valid
programs — and on protective functions, "wrong but valid" is the failure
mode that hurts people and equipment.

## The stance

A principal engineer running intake is not a stenographer. The user's
prose describes what they *want to happen*; your map must also capture
what must happen **when things fail** — power loss, broken wire, stuck
sensor, operator absent, CPU restart. For every behavior the user
describes, you owe them the failure-mode counterpart, and most of your
questions come from that gap.

## Procedure

1. **Read the whole request; extract the implicit plant.** List every
   noun that is plausibly a signal, device, or state. "If the flow stops"
   implies a flow switch — which implies a sense, a debounce, an owner,
   and a failure mode (what does a *broken* flow switch read as?).

2. **Fill the map top-down** (§1–§10): identity → signal list →
   equipment → interlocks → alarms → sequences → analogs → timing →
   acceptance scenarios → hardware map.

3. **Apply the non-negotiable conventions without being asked:**
   - **Fail-safe sense**: BOOL inputs read `1 = OK/healthy/closed/
     present`. De-energize-to-trip. If a plant signal is energize-to-trip,
     record the inversion in the signal row and push it to the IO layer —
     scattered `NOT`s in logic are how inverted senses escape review.
   - **Interlocks are permits** (`TRUE = permitted`), latching by
     default, re-armed only by a deliberate, momentary manual action.
     Auto-restart after a protective trip needs a documented
     justification, not a default.
   - **Momentary vs maintained**: pushbuttons, keys, and acknowledge
     signals rest at 0 and act on their **rising edge**; the map must say
     which inputs are momentary because the logic treats them
     structurally differently (edge memories) than maintained states.
   - Three or more alarms sharing an ack/horn → one `alarm_group` with
     first-out (annunciator users always want "what tripped first";
     offer it explicitly — it is the question the night-shift call
     starts with).
   - **Redundant inputs**: two switches on one guard, dual-channel
     E-stops, CW/CCW chains → capture as channel pairs with a
     discrepancy time and an ack authority (`dual_channel`), never as
     two independent signals ANDed somewhere in logic.
   - Every delay gets a named row in §8 with a preset, a consumer, and a
     rationale. "After a while" is not a preset, and a debounce chosen
     to hide a real intermittent fault is a finding, not a parameter.

4. **Interrogate the trip path end-to-end.** For each interlock row:
   what physically de-energizes, within how many scan cycles, what does
   the rest of the logic do during the trip (sequences abort to which
   state?), who may reset, from where, and what evidence do they need
   first? A permit with no consequence and a reset with no authority are
   both design smells to raise now.

5. **Startup and restart are states too.** What is true at first scan?
   (LADDER inputs default to 0 = fault — the safe direction; latching
   functions therefore need a startup acknowledge.) What must NOT
   auto-resume after a power cycle? Capture it; users almost never
   volunteer it.

6. **Ask, don't invent.** Batch targeted questions grouped by map
   section. Unavoidable classics: signal senses, reset/ack authority,
   debounce times, post-trip behavior, analog raw ranges, simultaneous-
   failure expectations. If the user is unavailable, fill the blank with
   an explicit `ASSUMPTION:` line, collect all assumptions in a review
   block at the top, and mark the map PROVISIONAL.

7. **Write acceptance scenarios (§9) yourself** — three to six
   given/when/then behaviors covering: normal start; each interlock's
   trip *and* recovery (including "signal restores but nothing re-arms
   until reset"); each alarm's debounce/ack cycle including "ack while
   the cause stands"; one full sequence walk with an abort. Only
   reference §2 signals. These become the machine-checked gate, so each
   step must be concrete: which signal, which value, how long.

8. **Run the completeness gate** at the bottom of the template. Hand off
   to `ir-authoring` only when every box is checked or explicitly waived
   by the user, and say which.

## Red flags a principal surfaces (and how)

- **Safety-rated functions** (SIL/PL per IEC 61508/61511/62061, personnel
  protection): state plainly that LADDER output is not certified safety
  logic; the function belongs to the facility's safety lifecycle
  (hazard analysis → SRS → certified platform → validation). Capture it
  in the map as out of scope with the interface points named. Do not
  quietly design it anyway.
- **A protective function with an automatic reset** — confirm twice.
  Write down who accepted it.
- **Shared writers**: two behaviors commanding one output. Resolve
  ownership now (the lint will catch it later, but the *design answer*
  belongs in the map).
- **Sequences without abort paths** — every state machine needs a
  monitored path back to a safe state, usually "any trip → safe state,
  full restart required". Add it as an assumption if unspecified.
- **Bypass/maintenance modes** — if the user hints at one ("unless we're
  testing"), it needs: an authority, an indication, a time limit or
  supervision, and a scenario. Undocumented bypasses are how interlocks
  die in the field.
- **Alarm floods**: if one root cause fires five alarms, note the
  grouping/first-out design that keeps the operator's screen readable
  (ISA 18.2 thinking: an alarm is something an operator must *act* on).

## Definition of done

The map is complete when a different engineer could implement it without
asking the user anything — and when every scenario in §9 could be
executed against the plant on commissioning day exactly as written.
