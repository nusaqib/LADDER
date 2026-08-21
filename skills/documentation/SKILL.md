---
name: documentation
description: Produce and maintain the complete controls documentation package (requirements, software specification, conventions, developer and operator manuals, verification report) generated from the IR with ladder docs, plus the project-specific documents generation cannot know. Use when a project needs its deliverable document set or when documentation has drifted from the program.
---

# Documentation: the deliverable package, generated

A controls project is not delivered as code; it is delivered as code
**plus** the document set that lets other people specify, review,
operate, and maintain it. LADDER's position: every document that can be
derived from the single source of truth **is generated** (`ladder docs`),
so it can never drift from the program — regenerating is part of the
change process, and reviewers diff documents like code.

## The generated package (`ladder docs <project-dir>`)

Reads the manifest (IR + scenarios + iomap) and writes
`docs/generated/`:

| Document | Content and audience |
|---|---|
| 01-requirements | One normative SHALL statement per logic element (`REQ-<program>-<id>`), plus the global conventions as normative requirements. Audience: the review board; the traceability anchor. |
| 02-software-specification | Program architecture with load-bearing scan order, element-by-element specified behavior traced to requirement ids, locked element semantics, full data dictionary (tags + UDTs), hardware bindings from the IO map. Audience: the next engineer. |
| 03-conventions | Fail-safe sense, permit polarity, naming grammar, element-id prefixes, language choices with rationale, the change process. Audience: everyone touching the repo. |
| 04-developer-manual | Toolchain, build artifacts per target and what each proves, validation issue codes, extension points. |
| 05-operator-manual | Per protective element: what the operator sees, what their action does and — critically — what it does NOT do (ack ≠ reset; restore ≠ re-arm; a cleared search means a full re-walk). Written in operator language, no tag soup in the prose. |
| 06-verification-report | Scenario inventory, the auto-theorem table with plain-language meanings, the four verification layers, and an explicit statement of limits. |

Regenerate in the same commit as any behavior change; CI-able via
`ladder docs` after `ladder check`.

## Getting a package worth signing

The generator is only as good as the IR it reads. Before generating:

- **Descriptions are the spec.** Every element's `description` and every
  tag's `comment` land verbatim in the package — write them as an
  engineer would for a review board ("Cooling water flow lost
  (debounced)"), not as filler. An element without a description is a
  documentation bug caught here.
- **Ids are the trace.** `REQ-*` ids derive from element ids; stable,
  meaningful ids (`IL_pump`, `GRP_panel`) keep requirement numbering
  stable across revisions — renaming an id is a requirements change and
  should look like one in the diff.
- **The design map completes the picture.** Requirements *rationale*
  (why this debounce, who holds reset authority, what was assumed) lives
  in `design/DESIGN.md` with its citations — the generated requirements
  state *what*, the map records *why*. Keep both; reference the map from
  the project README.

## What generation cannot know — author these deliberately

A complete package for a real facility adds documents whose content is
not in the IR. Author them in `docs/` (not `docs/generated/`) and hold
them to the same review standard:

1. **Functional/system specification upstream of the map** — the
   process narrative, operating modes, and the hazard/what-if analysis
   that justified each protective function. The design map cites it.
2. **Interlock cause-and-effect matrix** — reviewers and commissioning
   engineers think in C&E grids (causes down, effects across, a mark per
   relationship, and *empty columns visible* so "what feeds nothing?"
   has an answer). Derive it from the map §4/§5 and keep exclusions with
   rationale.
3. **Commissioning / site acceptance procedure** — the §9 scenarios
   rewritten as physical test steps with sign-off lines: who operates
   which device, expected indication, pass criteria. Every scenario
   becomes a numbered SAT step; add the physical-only checks
   (wire-pull/channel-fault injection per dual channel, measured trip
   times against the specified bound, PROFIsafe address verification
   against DIP switches, HMI indication cross-check).
4. **Alarm response sheets** (ISA 18.2 discipline) — per alarm/window:
   meaning, consequence of inaction, operator action, allowable response
   time. The operator manual names the windows; the response sheets make
   them actionable.
5. **HMI style guide conformance** (ISA 101 thinking) — color is never
   the only carrier, fault-sense members shown inverted explicitly,
   unimplemented state drawn as such (grey NOT IMPLEMENTED beats a lying
   lamp), one write path per protective acknowledge, momentary contract
   documented.
6. **Decision and finding registers** — numbered decisions (Dnn) and
   open findings (Fnn) with severity and "decision needed by"; nothing
   gets resolved by inference. Mirror the reference practice: a finding
   blocked on a drawing stays open until the drawing is read.

## Drift control

- Generated docs carry a "generated — do not edit" header; hand-edits
  there are reverted by process, not by argument.
- Authored docs cite the generated ones by requirement id, never by
  restating behavior — restated behavior is where drift is born.
- On every release: regenerate, diff, and read the requirement diff
  aloud in review — a changed SHALL statement is the change.
- The package inherits the project's safety boundary: state on the
  cover that generated logic and its documents are not a
  functional-safety certification.
