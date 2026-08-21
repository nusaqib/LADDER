---
name: ir-authoring
description: Generate and iterate LADDER IR YAML plus its scenario suite from a completed Design Inputs Map, driving ladder validate/test until both pass. Use when a design map (or an equivalent structured requirement) exists and IR is needed.
---

# IR authoring: Design Inputs Map → validated IR + scenarios

Input: a completed Design Inputs Map (`docs/DESIGN-INPUTS.md` format) or
an equivalently structured requirement. Output, inside the user's project
repository (`docs/PROJECT-LAYOUT.md` layout): the IR and its scenario
suite, gated by `ladder check <project-dir>` (validate + lint + scenarios
+ build). Outside a project repo the per-file commands are
`ladder validate` and `ladder test`. The full model-facing contract
(rules, element vocabulary, JSON Schema) is printed by
`ladder prompt "<requirement>"` — regenerate it rather than trusting
memory.

## Structure before elements

- **One program per responsibility**, in deliberate order — order is the
  scan order and it is load-bearing (evaluate inputs before logic that
  consumes them; compute permits before the sequences that obey them).
  Typical shape: input conditioning → protective logic → sequences →
  output words. Name programs for their responsibility, not "Main".
- **Large projects: modular IR directory** (`ir/project.yaml` +
  `types.yaml` + `tags.yaml` + `programs/NN_name.yaml`, numeric prefixes
  fixing scan order) so each section has an owner and a reviewable diff.
- `language:` is a *communication* decision: `ladder` for programs plant
  electricians must review as rungs, `sfc` for a program that is exactly
  one sequence, default `st`. V11 rejects logic the language cannot
  express — treat that as a design signal, not an obstacle.
- **UDTs mirror the plant**: one type per device class, one member per
  observable/commandable aspect, area/skid structs composing them. The
  DB then reads like the P&ID and the HMI binds to a handful of
  structured tags instead of hundreds of flat ones.

## Element selection (strict priority)

1. **Library pattern** (`element: pattern`) when equipment matches one.
2. **`dual_channel`** for every redundant input pair (1oo2 evaluations,
   dual E-stop channels, CW/CCW chains) — with `discrepancy_time` and an
   `ack` authority from the map; never hand-AND two channels.
3. **`alarm_group`** for any alarms sharing an ack or horn; wire
   `first_out` when the map's operators care what tripped first.
4. **`search_chain`** for sequential arm/search/permissive walks (PPS
   practice): rising-edge keys, walk order, breach cascade — and never
   wire an ack/reset to it.
5. **Structured elements**: `interlock`, `alarm`, `state_machine`,
   `scale`, `timer`, `assign`.
6. **`st` escape hatch**: last resort; it suppresses usage lint and
   blocks the model checker. Every `st` element needs a description
   saying *why* no structured element fits — that sentence is what the
   reviewer audits.

Mechanics: map §2 rows → `tags:` with `comment:` from the meaning column
(addresses go to the IO map, never the IR); permissive cells →
`all:/any:/not:` trees, not expression strings (trees diff and review
better); timing rows → presets; every sequence state assigns **all**
outputs the machine owns — implicit holds are where sequences rot.

## The loop

1. Write the IR (or the generator producing it — for generated projects
   edit the generator, never its output).
2. `ladder check` — fix by issue code:

| Code | Meaning / usual fix |
|---|---|
| V01/V02 | bad or duplicate identifier — ≤40 chars, letter first |
| V03/V04 | unknown reference/target, or writing an input — a §2 row is missing or misspelled; never invent the tag, fix the map |
| V05 | latching element without reset/ack; discrepancy monitoring without ack — the map row names the authority |
| V06 | wrong type (BOOL outputs, INT state/first_out tags) |
| V07 | state machine: unknown initial/goto, duplicate codes |
| V08 | periodic program without interval |
| V10 | UDT/array misuse (member names, index range, complex IO) |
| V11 | language can't express the logic — change element or language |

3. **Lint (W01–W06) is design review, not noise.** W01 unwritten output
   and W03 unread input are missing logic or a dead point; W02/W06
   multi-writer is an ownership dispute; W04/W05 are sequence dead-ends.
   Fix the design; if a warning is *correct* (e.g. wired-but-not-yet-used
   inputs kept faithfully), say so in the project README with the count,
   so the next engineer knows the expected baseline.
4. Convert map §9 to scenarios (`set/pulse/scan/run/expect`,
   `docs/SCENARIOS.md`). Inputs default to 0 = fault, so healthy states
   are set explicitly; latching protective functions need their startup
   acknowledge step. Pin the *uncomfortable* behaviors too: ack while
   the cause stands, reset held from before the trip, signal restoring
   without re-arm, out-of-order operation.
5. `ladder test` until green. A failing expect is a semantics bug in the
   IR until proven otherwise — reread the map row before touching the
   scenario. When the scenario really was wrong, fix the map in the same
   commit.
6. Where interlocks / dual channels / search chains exist, run
   `ladder model` and (with nuXmv) `ladder verify -t smv`: the
   auto-theorems are free proofs over every timing. Report exactly what
   was proved and what was skipped.
7. `ladder docs` regenerates the documentation package — same commit as
   any behavior change.
8. Hand off to the vendor skill; `verification` before any handoff.

## Non-negotiables

- Never write vendor syntax; the IR is the only logic artifact.
- Never invent a signal that is not in the map — go back to
  `design-intake`.
- Every stateful element: unique meaningful `id` (`IL_*`, `ALM_*`,
  `GRP_*`, `DC_*`, `SRCH_*`, `SEQ_*`) and a `description` — ids are how
  requirements, theorems, and HMI faceplates trace back to logic.
- Generated logic is not certified safety logic; carry the disclaimer
  where the map flagged safety-adjacent functions.
