---
name: fbd-programming
description: Author and review Function Block Diagram (FBD) logic - block networks, latch idioms, when FBD beats LAD, PLCopen/vendor mapping. Use when logic is delivered as FBD or a reviewer prefers gate-style diagrams.
---

# FBD: gates for people who think in signal flow

FBD and LAD are the same expressible subset drawn differently: FBD as
AND/OR/NOT blocks wired left-to-right, LAD as contacts. Choose FBD when
the audience reads logic gates (common in European process/safety
practice; Siemens F-FBD is as accepted as F-LAD) - it shines for wide
combinational conditions and named function blocks, and gets clumsy for
long seal-in chains where LAD's rung idiom is clearer.

## Idioms

- **Permissive tree**: one AND block (expand inputs) feeding the
  output - with 1=OK senses the tree reads as the healthy plant.
  Negations live on *pins* (input negation bubbles), not as NOT blocks
  scattered mid-wire; push NOT to the leaves (De Morgan) exactly as
  LADDER's normalizer does.
- **Latch**: the standard cell is an SR/RS block. Safety wants
  **reset-dominant** (RS: R wins while both asserted). LADDER lowers
  latches to explicit set/reset logic where the *later-evaluated* write
  dominates and folds them into the equivalent block form for PLCopen
  FBD - when hand-reviewing vendor FBD, check which dominance the block
  actually implements instead of trusting the name (SR = set-dominant,
  RS = reset-dominant, and people misremember).
- **Edges**: R_TRIG/F_TRIG instances, or the explicit prev-bit pattern
  (portable, model-checkable). Every edge instance is state - name it
  for what it detects (`trig_start_pb`), not `trig1`.
- **Timers**: TON/TOF/TP blocks with the instance named for its
  purpose; consume Q downstream in the same network only if the tool's
  evaluation order is explicit - otherwise a separate network.

## Discipline

1. Networks stay one-decision-sized, like rungs. A network that needs
   scrolling is several networks.
2. Signal flow strictly left-to-right; a feedback wire (output back
   into the network's own input) is a latch in disguise - make it an
   explicit SR/RS or prev-bit so the state is visible and reviewable.
3. Intermediate results that more than one network consumes get a named
   tag, not a duplicated subtree.
4. Same order-safety rule as ladder: FBD networks in a scan see earlier
   networks' writes; order networks by data flow.

## Vendor mapping

- **PLCopen FBD** (LADDER's `language: fbd` on the plcopen backend):
  positioned `<block typeName="AND">` graphs, connections by
  refLocalId + formalParameter; tc6-XSD-validated in CI. Beckhoff and
  CODESYS import this directly.
- **Siemens FBD/F-FBD**: same FlgNet wiring as LAD with gate parts;
  everything in the F-LAD note applies (certified instruction pin sets,
  instance-first, OpenCon on unused pins).
- **Rockwell**: FBD routines exist (sheet-based .L5X `FBDContent`) but
  RLL is the plant-floor default - prefer `ladder` there unless the
  site standard says FBD.

## Choosing between FBD and LAD

Ask who signs the printout. Electricians -> LAD. Process/safety
engineers with logic-diagram P&IDs -> FBD. Never mix within a layer;
per-program `language:` in the IR records the choice as a reviewable
line.
