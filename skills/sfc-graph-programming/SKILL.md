---
name: sfc-graph-programming
description: Sequential logic - SFC / Siemens GRAPH / state machines - step and transition design, action qualifiers, fault paths, when to use which form. Use for any stepped process - startup sequences, batch phases, search/arming procedures.
---

# Sequences: SFC / GRAPH / state machines

Stepped behavior hand-rolled as bit-spaghetti is the top source of
"works until the weird day" bugs. Model it explicitly: LADDER's
`state_machine` element (lowers to a clean CASE, simulable and
enumerable), rendered as SFC (`language: sfc` -> PLCopen SFC + textual
STEP/TRANSITION) or implemented as Siemens GRAPH by the vendor team.

## Designing the chart (form-independent rules)

1. **A step is a stable situation**, named for what IS true
   (`Filling`, `Evacuating`, `Searched`), not for what happens next.
   Step-active does things; transitions only *decide*.
2. **Transitions are complete conditions** - include the operator, the
   timeouts, and the measurement; a transition that is just `step_done`
   pushed the real condition somewhere invisible.
3. **Every step needs an exit for every way reality can go** - success,
   fault, abort. The classic omission: the fault path. Decide per step
   whether faults go to a dedicated fault state (needing operator
   reset) or back to Idle, and be consistent.
4. **One chart, one job.** Parallel branches (simultaneous sequences)
   are legal SFC and almost always better as two charts with an
   interlock between them - reviewability wins.
5. **No auto-restart of protective sequences.** A completed search/arm
   sequence that a fault clears must require re-performing, not resume;
   that property should be structural (LADDER's `search_chain` has
   nowhere to wire a resume, on purpose) and is provable
   (auto-theorems).

## In the IR

```yaml
- element: state_machine
  id: SEQ_pumpdown
  state: pd_state          # INT tag; codes are named, illegal values impossible
  initial: Idle
  states:
    - name: Idle
      transitions: [{to: Roughing, when: start_cmd AND permit_ok}]
    - name: Roughing
      do: [{target: rough_valve_cmd, value: true}]
      transitions:
        - {to: HighVac, when: pressure_below_xover}
        - {to: Faulted, when: NOT permit_ok}
    - name: Faulted
      transitions: [{to: Idle, when: reset_pb}]
```

Scenario every path - the happy walk, each fault exit, and the
"operator does it in the wrong order" story. The simulator's 0-default
inputs make missing-permissive holes fail loudly.

## Rendering / vendor notes

- **SFC output**: `language: sfc` gives textual SFC
  (STEP/TRANSITION/ACTION, matiec-compiled in CI) and PLCopen SFC
  bodies. Action qualifiers: prefer plain `N` (do while active) and
  explicit assignments; `S/R` qualifiers hide latches - if you need
  one, you probably want the latch visible in the evaluation layer
  instead.
- **Siemens GRAPH**: FB per chart with rich supervision
  (interlock/supervision per step, acknowledge machinery). Powerful,
  but its behavior lives in editor settings a diff can't see - when the
  design is in LADDER, prefer the state_machine element and keep GRAPH
  for teams already fluent in it. GRAPH blocks don't exchange; treat
  them as vendor-native implementations of a reviewed chart.
- **Rockwell**: SFC routines exist; many sites standardize on
  state-INT + CASE in ST, which is exactly what the element lowers to.

## Review checklist

- every state reachable and exitable (LADDER lint flags unreachable
  states); every transition condition uses declared, sensed signals;
  timeout on every step that waits on the plant; fault paths total;
  the state tag written by exactly this element.
