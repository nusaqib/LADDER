---
name: safety-matrix
description: Cause-and-effect matrices (CEM) for protective logic - building the interlock matrix, matrix-to-elements mapping, coverage discipline, safety-layer boundaries. Use when protective functions are specified as cause/effect tables or a Siemens Safety Matrix / CEM-style spec arrives.
---

# Safety matrix (CEM): the grid IS the specification

Cause-and-effect is how process-safety people specify interlocks: rows
= effects (trips/permits), columns = causes (devices/conditions), a
mark where a cause drives an effect. Siemens sells an editor for it
(Safety Matrix / CEM language); LADDER treats the matrix as *design
data* (a CSV a generator consumes) - same idea, reviewable in git.

## Building the matrix

1. **Columns are every credible cause** - one per protective device
   evaluation (post-1oo2, post-debounce), named by the tag list.
   **Every device gets a column even if unmarked**: the grid is the
   coverage claim, and "nobody considered it" must be visually distinct
   from "considered and excluded". If exclusions need justifying,
   keep a companion exclusions table with reasons.
2. **Rows are effects with stated safe state** - "close beam shutter",
   "drop area permit", "de-energize contactor group 2" - each mapping
   to one output/permit tag.
3. Cell semantics must be written down once, at the top: default is
   "cause active (=unhealthy) forces effect to its safe state,
   latching, manual reset per row". Non-default cells (non-latching,
   time-delayed, vote-of) get explicit cell codes with a legend.
4. The matrix lives beside the design map, versioned; a change to
   protective logic is a *cell diff* a safety engineer can read.

## Matrix -> elements (mechanical, so generate it)

- A row with marked causes c1..cn, latching + manual reset:

```yaml
- element: interlock
  id: IL_<effect>
  permissives: {all: [c1_ok, c2_ok, ...]}   # 1=OK senses
  output: <effect_permit>
  reset: {signal: <named reset>, }
```

- Redundant-pair causes enter the matrix as ONE column fed by a
  `dual_channel` element (the 1oo2 + discrepancy semantics live there,
  not in the matrix).
- Search/arming preconditions to an effect come from `search_chain`
  completes.
- Voting cells (2oo3) get an explicit vote expression in the
  conditioning layer with its own column.

Because the mapping is mechanical, write the generator (rows -> IR
elements) rather than transcribing by hand - transcription is where
cells silently drop. Then two artifacts gate every change: scenarios
per row (cause in -> effect safe; cause clears -> effect stays until
reset) and the auto-theorems (permit implies all permissives - the
matrix row as a proved invariant).

## Layer boundaries (what the matrix does NOT contain)

- No debounce times, no channel pairing, no sensor conditioning -
  that's the evaluation layer feeding the columns.
- No sequencing - a matrix cell must never encode "after step 3".
  If an effect depends on a sequence, the cause is the sequence's
  completion flag.
- Standard (non-safety) logic reads matrix *outputs* (permits), never
  reaches into causes; on Siemens F-systems that boundary is physical
  (F-DB members), and everything inside the F-group re-signs on change,
  so keep the matrix's implementation inside and consumers outside.

## Review checklist

- every column traceable to a sensed, sense-stated tag; every row's
  safe state and reset authority named; empty columns individually
  acknowledged; matrix, IR, scenarios, and theorem list regenerate from
  the same commit; non-default cells have legend entries.
