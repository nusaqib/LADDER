---
name: stl-programming
description: STL/IL (instruction list) - reading legacy accumulator code, migrating it to structured elements, and emitting the strict IL subset when a legacy runtime demands it. Use when a brownfield program arrives in STL/AWL or a target requires IL.
---

# STL/IL: read fluently, write rarely, migrate deliberately

IL was deprecated in IEC 61131-3 ed.3 and Siemens S7-1500 STL is a
compatibility layer - but decades of plant logic live in it, so the
real skills are *reading* it during adoption and *migrating* it without
changing behavior. LADDER can also emit IL (`language: il`,
matiec-proved in CI) for legacy runtimes.

## Reading the accumulator model (Siemens STL vocabulary)

- `A x` (AND), `O x` (OR), `AN/ON x` (negated) build the RLO (result of
  logic operation); `= y` writes it; `S y`/`R y` set/reset when RLO=1.
- `A(` ... `)` parenthesizes; `FP/FN m` are edge flags with a memory
  bit; `L/T` load/transfer through accumulators for data; `SPB/SPBN
  lbl` conditional jumps.
- Translation reflexes: an `A/A/=` run is a permissive chain; `S` +
  `R` on the same bit is a latch (find which is later - that one
  dominates); `FP m` + `S` is a rising-edge latch; jump-around blocks
  (`SPBN`) are IF bodies.
- Danger zones needing extra care: RLO carried across network
  boundaries, `SAVE/BR`, indirect addressing (`AR1`, P# pointers),
  STATUS-word tricks (`A BR`, `SET/CLR`). Treat any of these as "stop
  and understand" markers - naive line-by-line translation of these is
  how migrations introduce bugs.

## Migration procedure (STL -> elements)

1. Segment by write target: collect the instruction run feeding each
   `=`/`S`/`R` - that's one rung-equivalent.
2. Reconstruct each as a boolean expression + action; classify into
   element vocabulary: permissive chain -> `interlock` or `assign`;
   S/R pair -> latch inside `interlock`/`alarm`; FP + counter/step
   pattern -> `state_machine` or `search_chain`.
3. Preserve *scan order* - STL networks execute in order and later
   logic sees earlier writes; keep the same element order.
4. Pin behavior BEFORE restructuring: write scenarios from the old
   program's observed behavior (or the design docs), get them green
   against the migrated IR, then improve structure in later commits.
5. Anything untranslatable stays quarantined as documented `st` (or the
   original block kept called-but-frozen) with a scenario fence around
   its outputs.

## Emitting IL (when a target insists)

`language: il` renders the lowered statements as strict IEC IL. The one
grammar trap everyone hits - formal calls need a newline after `(` and
one parameter per line:

```
CAL t1 (
    IN := start,
    PT := T#5s
)
```

Single-line formal CAL is rejected by matiec (and the standard's
grammar, read closely). Stay in the simple operator subset
(LD/ST/AND/OR/S/R/CAL/JMPC); anything fancier belongs in ST.
Reference: `docs/reference/tools/matiec.md`,
`docs/reference/standards/iec-61131-3.md`.

## Review checklist for arriving STL

- every edge flag (`FP/FN`) memory bit unique and never written
  elsewhere; every S has a reachable R (and which dominates is
  intended); no RLO crossing network boundaries; jumps only forward and
  structured; indirect addressing inventoried and justified.
