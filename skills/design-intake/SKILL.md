---
name: design-intake
description: Turn a plain-language PLC requirement into a complete Design Inputs Map (signals, interlocks, alarms, sequences, scenarios) ready for IR generation. Use when a user describes control behavior in prose and no design map exists yet.
---

# Design intake: prose → Design Inputs Map

You are acting as the controls engineer who runs the design review *before*
anyone writes logic. Your output is a filled **Design Inputs Map** (the
template in `docs/DESIGN-INPUTS.md`), saved as `<project>.design.md` next to
where the IR will live. Do not generate IR in this skill — an incomplete map
is the number-one cause of wrong-but-valid programs.

## Procedure

1. **Read the whole request first.** List every noun that is plausibly a
   signal, device, or state. Users mention signals implicitly ("if the flow
   stops" implies a flow switch — with a sense, a debounce, and an owner).

2. **Fill the map top-down** (§1–§10 of `docs/DESIGN-INPUTS.md`):
   identity → signal list → equipment → interlocks → alarms → sequences →
   analogs → timing → acceptance scenarios → hardware map.

3. **Apply the conventions without being asked:**
   - Fail-safe sense: BOOL inputs are `1 = OK / healthy / closed / present`.
     If the plant signal is inverted, record it in the signal row and note
     the inversion belongs at the map level, not scattered through logic.
   - Interlocks are permits (`TRUE = permitted`), latching by default,
     re-armed only by an explicit reset signal — so every latching row
     must name its reset before the map is complete.
   - Three or more alarms sharing an ack/horn → one `alarm_group` row set
     (with first-out if the user cares "what tripped first" — annunciator
     users always do, offer it).
   - Every delay gets a named row in the timing table (§8) with a preset
     and a consumer. "After a while" is not a preset.

4. **Ask, don't invent.** For each blank you cannot fill from the request,
   ask a targeted question, batched (one message, grouped by map section).
   Typical unavoidable questions: signal senses, reset/ack authority,
   debounce times, what happens after a trip, analog raw ranges.
   If the user is unavailable, fill the blank with an explicit
   `ASSUMPTION:` line and collect all assumptions in a review block at the
   top of the map.

5. **Write acceptance scenarios (§9) yourself** — three to six
   given/when/then behaviors covering: normal start, each interlock trip
   and recovery, each alarm's debounce/ack cycle, and one sequence walk.
   Only reference signals from §2. These become the `*.scenarios.yaml`
   gate later, so make each step concrete (which signal, which value, how
   long).

6. **Run the completeness gate** at the bottom of `docs/DESIGN-INPUTS.md`.
   Only hand off to the `ir-authoring` skill when every box is checked or
   explicitly waived by the user.

## Red flags to surface during intake

- Safety-rated functions (SIL/PL, personnel protection): state that LADDER
  output is not certified safety logic and the function needs the
  facility's safety process; capture it in the map as out of scope.
- A "simple" request with no reset story ("the pump just restarts") —
  confirm auto-restart is truly wanted; latching + manual reset is the
  safe default.
- Sequences with no abort/timeout path — every state machine needs a way
  back to a safe state; add one and mark it as an assumption if the user
  didn't specify.
- Multi-writer intent (two behaviors commanding the same output) — resolve
  ownership now; the validator will flag it later (W02/W06) but the design
  answer belongs in the map.
