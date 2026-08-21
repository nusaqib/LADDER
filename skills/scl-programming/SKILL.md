---
name: scl-programming
description: Structured Text / SCL authoring and review - style, portable subset, vendor dialect deltas (Siemens SCL, Logix ST, TwinCAT), and the discipline around LADDER's raw-ST escape hatch. Use for text-language logic, calculations, and dialect questions.
---

# ST/SCL: the textual workhorse, kept portable

ST (Siemens: SCL) is the right form for arithmetic, data handling, and
anything with real control flow. In LADDER it is also the *output*
form: every element lowers to a neutral statement AST rendered as ST
per dialect - so hand-written ST should be the exception (`st` element,
last resort), and this skill is mostly about reviewing/authoring that
exception plus vendor-dialect fluency.

## The portable subset (write this, nothing else)

- `IF/ELSIF/ELSE`, `CASE ... OF` with literal labels, assignments,
  comparisons, boolean/arith operators, `T#` literals.
- Standard FBs by instance: `t1(IN := x, PT := T#5s); y := t1.Q;`
- Avoid: vendor built-ins (`REGION`, `#var` prefixes, direct bit access
  `w.3`, `GOTO`, `EXIT` where avoidable), implicit conversions
  (write `INT_TO_REAL` explicitly), and clock/system calls (they kill
  portability *and* simulability).
- matiec is the arbiter: if `iec2c` rejects it, it isn't portable IEC
  ST regardless of what a vendor accepts (`ladder verify -t iec`;
  grammar traps in `docs/reference/tools/matiec.md`).

## Style that survives review

1. One statement per line; no clever expression nesting - a compound
   condition used twice gets a named intermediate variable.
2. State updates last: compute conditions into locals, then the
   latch/output writes, so a reader finds every write at the bottom.
3. Comments state constraints ("clamp before integrate: anti-windup"),
   never restate the code.
4. Numeric literals carry meaning through names or the timing table -
   a bare `0.85` in logic is a review question by definition.

## Vendor dialect deltas (the ones that actually bite)

| topic | Siemens SCL | Rockwell ST | TwinCAT/IEC |
|---|---|---|---|
| timer call | instance DB, `#t1(IN:=, PT:=)` | TONR or TIMER + instruction quirks; no TP in ST | plain `t1(IN:=, PT:=)` |
| TIME type | `T#...`, TIME | DINT milliseconds in TIMER.PRE | `T#...`, TIME |
| conversions | explicit `INT_TO_REAL` | mostly implicit | explicit |
| local refs | `#name` prefix | none | none |
| strings | `'...'` STRING[n] | quirky - avoid in portable logic | `'...'` |

LADDER's dialect renderers encode these once; when writing raw `st`,
write neutral and let validation object.

## The escape-hatch discipline (`element: st`)

Raw ST bypasses element semantics: no auto-theorems, not
rung-renderable, simulated only if it stays in the neutral subset.
Before reaching for it, ask which *element* is missing - the answer is
usually `assign` with a richer expression, a `pattern`, or a real gap
worth an RFC. When you do use it: keep it short, single-purpose, name
it (`id:`), and cover it with scenarios - it is the one part of the
program with no other net under it. Track `st` usage as a health
metric; a project accreting `st` blocks is telling you its vocabulary
is wrong.

## Sequences in ST

Don't hand-roll step counters with magic integers. Use the
`state_machine` element (lowers to a clean CASE with named states) or
`language: sfc` - reviewable, simulable, and the state can't take
illegal values.
