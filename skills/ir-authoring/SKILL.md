---
name: ir-authoring
description: Generate and iterate LADDER IR YAML plus its scenario suite from a completed Design Inputs Map, driving ladder validate/test until both pass. Use when a design map (or an equivalent structured requirement) exists and IR is needed.
---

# IR authoring: Design Inputs Map → validated IR + scenarios

Input: a completed Design Inputs Map (`docs/DESIGN-INPUTS.md` format) or an
equivalently structured requirement. Output: `<project>.yaml` (IR),
`<project>.scenarios.yaml`, both passing:

```
.venv\Scripts\ladder validate <project>.yaml
.venv\Scripts\ladder test <project>.yaml <project>.scenarios.yaml
```

The full model-facing contract (rules, element vocabulary, JSON Schema) is
printed by `ladder prompt "<requirement>"` — regenerate it rather than
trusting memory if unsure of a field.

## Element selection (strict priority)

1. **Library pattern** (`element: pattern`) when equipment matches one —
   `ladder targets` / `ladder prompt` lists them with signatures.
2. **alarm_group** for any set of alarms sharing an ack or horn
   (map §5 grouping) — never N copy-pasted `alarm` elements.
3. **Structured elements**: `interlock` (map §4 rows), `alarm` (§5),
   `state_machine` (§6), `scale` (§7), `timer` (§8), `assign`.
4. **`st` escape hatch**: last resort only; it suppresses usage lint and
   blocks the model checker — say so in the element description.

Map-to-IR mechanics: §2 rows → `tags:` (with `comment:` from the meaning
column; addresses go to the IO map, never the IR); interlock permissive
cells → `all:`/`any:`/`not:` trees (not expression strings); timing rows →
`on_delay`/`preset`; sequences → one `state_machine` with every owned
output assigned in every state. UDTs (`types:`) and `array:` tags for
structured data; complex tags stay direction `memory`.

Program structure: one program per map responsibility (safety permissives /
alarms / sequence / drives). Set `language:` only where the map asks for it
(ladder for electrician-facing boolean programs, sfc for a pure sequence
program) — V11 rejects logic the language cannot express; default st.

## The loop

1. Write the IR. 2. `ladder validate` — fix by issue code:

| Code | Meaning / usual fix |
|---|---|
| V01/V02 | bad or duplicate identifier — rename, ≤40 chars, letter first |
| V03/V04 | unknown reference/target, or writing an input — a §2 row is missing or misspelled |
| V05 | latching element without reset/ack — the map row names it |
| V06 | wrong type (BOOL outputs, INT state/first_out tags) |
| V07 | state machine: unknown initial/goto, duplicate codes |
| V08 | periodic program without interval |
| V10 | UDT/array misuse (member names, index range, complex IO) |
| V11 | language can't express the logic — change element or language |
| W01–W06 | lint: unused tags, multi-writer hazards, trap/unreachable states — fix the design, don't suppress |

3. Convert map §9 scenarios to `scenarios:` steps (`set` / `pulse` /
   `scan` / `run` / `expect` — see `docs/SCENARIOS.md`; remember inputs
   default to 0 = fault, so healthy states must be `set` first).
4. `ladder test` until green. A failing expect is a semantics bug in the
   IR, not in the scenario — reread the map row before touching the
   scenario.
5. Where interlocks exist, run `ladder model <project>.yaml -o out` and
   (with nuXmv available) `ladder verify -t smv` — the auto-generated
   fail-safe theorems are free; report what was proved.
6. Hand off to a vendor skill (`siemens-deploy`, `rockwell-deploy`) or
   `ladder build -t all -o out`.

For fully automated generation with an external LLM CLI, the same loop is
`ladder generate` (env `LADDER_LLM_CMD`) with the scenarios as the
acceptance gate.

## Non-negotiables

- Never write vendor syntax; the IR is the only artifact.
- Never invent a tag that is not in the map — go back to `design-intake`.
- Every stateful element: unique meaningful `id` (`IL_*`, `ALM_*`,
  `GRP_*`, `SEQ_*`) and a `description`.
- Generated logic is not certified safety logic; keep the disclaimer in
  project descriptions where the map flagged safety-adjacent functions.
