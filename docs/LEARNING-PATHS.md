# Learning paths — pick the track that matches you

Four tracks, four depths. Each lists what to read (in order), what to
actually do, and what you can safely ignore.

---

## Track 1 — "I'm new to PLC programming"

You know some programming; ladder logic and interlocks are new.

**Read:** [Getting started](GETTING-STARTED.md) →
[reference/standards/iec-61131-3](reference/standards/iec-61131-3.md)
(just "The software model" + the language table) →
[Tutorial](TUTORIAL.md).

**Do:** the Getting-started motor station, slowly — especially step 5
(break it on purpose). Then `ladder render .` and read your own logic
as rungs; that's the notation the industry speaks. Then the tutorial's
vacuum skid end to end.

**Concepts to internalize before anything else:** the scan cycle
(inputs → logic top-to-bottom → outputs, forever); fail-safe sense
(1 = OK, so broken wires trip); latching + who may reset. The elements
encode all three — that's why they exist.

**Ignore for now:** formal verification, vendor deploys, the LLM loop.

---

## Track 2 — "I'm a controls engineer, new to LADDER"

You've written PLC programs; you want to know what this buys you.

**Read:** [Getting started](GETTING-STARTED.md) (20 minutes, do it
anyway — the gate philosophy is the point) → [WORKFLOW](WORKFLOW.md)
(who provides what) → [PROJECT-LAYOUT](PROJECT-LAYOUT.md) →
[GUIDE](GUIDE.md) recipes as needed.

**Do:** `ladder init` a real small machine you know. Fill
`design/DESIGN.md` from memory, mirror it in IR, write the scenarios
you'd commission with, `ladder check`, `ladder render`, then `ladder
deploy` to your vendor and open the generated project in your IDE —
judge the output like you'd judge a contractor's. Then run `ladder
mutate .` and see whether your scenarios would catch a dropped
permissive; that number is the honest quality of your acceptance tests.

**Your vocabulary mapping:** rungs → elements ([IR-SPEC](IR-SPEC.md));
your tag database → `tags:` + iomap; your functional spec → the design
map; your FAT checklist → scenarios; block architecture and language
choices → the [skills library](../skills/README.md)
(`block-architecture`, `lad-programming`, ...).

**Ignore until it bites:** backend internals, SMV syntax (read the
theorem *descriptions*, not the models).

---

## Track 3 — "I review/approve, I don't write code"

Safety engineer, lead, or physicist signing off on protective logic.

**Read:** [WORKFLOW](WORKFLOW.md) (your four gates are defined there) →
the project's own `design/DESIGN.md` → its `out/report.html`.

**Do — your entire toolchain is three artifacts:**
1. `out/report.html` (`ladder render`): the logic as rungs, the
   scenario tables, the theorem list. If a rung contradicts the design
   map, that's a finding.
2. The **scenario suite**: do the stories match what you'd test at
   commissioning? The story it *doesn't* contain is your most valuable
   comment. Ask for the `ladder mutate` score — survivors are faults
   the suite would wave through.
3. The **verification report** (`docs/generated/`): what was proved,
   what was only tested, and the stated limits (timers
   over-approximated; `st` blocks not proved).

**Hold the line on:** every latch naming its reset authority; every
BOOL sense stated; ASSUMPTION lines burned down before approval; the
non-certification disclaimer staying attached to anything
safety-adjacent.

---

## Track 4 — "I extend the tool" (integrator / contributor)

**Read:** [BACKENDS](BACKENDS.md) (the plugin contract) →
[VERSIONING](VERSIONING.md) (IR semver + RFC) →
[RELATED-WORK](RELATED-WORK.md) (what exists, what we adopted) →
`docs/reference/` for the vendor formats you'll touch.

**Do:** clone, `pip install -e .[dev]`, `pytest`. Write a toy backend
against the neutral statement AST, register it via the
`ladder.backends` entry point, then make `ladder conformance -t
yourbackend` pass — that IS the compatibility contract, and it runs the
whole example+benchmark corpus through your emitter. For IR changes:
RFC first (VERSIONING.md), and remember every element addition owes
lowering + simulator semantics + validation + at least one auto-theorem
+ docs, in one commit.

**House rules that are not negotiable:** semantics live in lowering
only (backends render, never reinterpret); no vendor binaries in the
repo; emitted PowerShell stays ASCII; every live-tool discovery gets
recorded in `docs/reference/` in the same commit.
