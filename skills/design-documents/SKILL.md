---
name: design-documents
description: Maintain the authored design package - the Design Inputs Map, decision records, assumptions, revision discipline - and keep it ahead of the IR. Use when design documents need writing, updating, or auditing against the implementation.
---

# Design documents: the authored half of the package

Two documentation halves: **generated** (requirements, manuals,
verification report - `ladder docs`, never hand-edited; see the
`documentation` skill) and **authored** (this skill): the Design Inputs
Map, decisions, and assumptions. The authored half leads: *no IR change
lands whose design change isn't in the same commit.*

## The map (design/DESIGN.md)

Structure per `docs/DESIGN-INPUTS.md` - identity, signal table,
equipment, interlock matrix, alarm list, sequences, analogs, timing
table, acceptance scenarios, hardware map, completeness gate. Rules:

1. Ground-truth cells (senses, resets, timings, stories) are the
   human's; an assistant drafts around them, never over them.
2. Every number has a row in the timing table; every latch names its
   reset; every signal states its 1-meaning. The completeness gate at
   the bottom is checked, honestly, before authoring IR.
3. The map speaks plant language - a section a vendor programmer can't
   misread and an operator's supervisor can review.

## Decisions (the table that saves the next engineer)

Anything decided against an alternative gets a numbered decision row -
`D07 | keys rest at 0, edge-read | alternatives: level-read | why:
matches reference; prevents taped-down keys | date`. Especially record
**tool-limit decisions** ("F-addresses set in GUI - Openness rejects
the write, tested V19+V21") so nobody re-spikes them. The SR PPS
reproduction's decision table is the house exemplar: every delta from
the reference is a cited row.

## Assumptions (the greppable kind)

Unknowns are recorded as `ASSUMPTION:` lines with owner and impact -
`ASSUMPTION: discrepancy time T#500ms (vendor default; PPS group to
confirm; affects DC_* elements)`. They must be greppable (one keyword,
one per line), revisited at each review, and burned down to zero before
anything ships. An assumption silently promoted to fact is the
design-doc failure mode.

## Revision discipline

- The design package lives in git with the IR - the commit IS the
  revision record; keep an 01_Revisions section only if the facility
  requires human-readable history, and generate it from git log rather
  than maintaining it by hand.
- Cross-references cite stable anchors (decision numbers, signal
  names), never page numbers.
- On brownfield captures: reference-project facts carry citations (file
  and export they came from); reproduction deltas are decisions, not
  silent fixes.

## Auditing docs against implementation

Quarterly (or per milestone): (1) `ladder docs` + `ladder render`
regenerate clean with no diff (else logic changed without docs);
(2) every ASSUMPTION still true and still needed; (3) the map's signal
table matches the tag list (count and senses); (4) decision table
covers every deviation a reviewer would question. Findings become
commits, not sticky notes.
