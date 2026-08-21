---
name: block-architecture
description: Organize PLC programs - OBs/FBs/FCs/DBs on Siemens, tasks/programs/routines on Rockwell, POUs on TwinCAT - scan order, layering, instance strategy. Use when deciding how a project's logic is partitioned or reviewing an existing structure.
---

# Block architecture: partition by responsibility, order by data flow

The unit of review is the program/block. Partitioning decides whether a
change is a one-block diff or a scavenger hunt.

## The layering that works (proved on a real safety program)

Pipeline layers, executed in order, each with one responsibility:

1. **IO / conditioning** - map physical channels to plant-truth tags
   (sense inversion, debounce, analog scaling). No decisions.
2. **Evaluation / protection** - interlocks, dual-channel evaluation,
   alarm conditions. Decisions, no sequencing.
3. **Sequencing / coordination** - search chains, state machines,
   permits combining evaluations.
4. **Outputs / commands** - the only layer that writes physical
   outputs, from permits + commands.

The SR PPS reproduction is exactly this (FB_IOMap -> FB_Certified ->
FB_Safety), and the reason its logic layer could be simulated and
model-checked while certified evaluation stayed quarantined library
instances. Default to it.

## Scan order is load-bearing

Within a scan, later logic sees earlier writes. Order programs so data
flows forward (inputs -> protection -> sequence -> outputs); a backward
read is a one-scan delay that becomes a race under exactly the timing
nobody tested. In LADDER, modular IR filename order IS the scan order
(`programs/10_inputs.yaml`, `20_protection.yaml`, ...) - number the
prefixes and leave gaps.

## Vendor structure mapping

- **Siemens**: cyclic OB1 calls FBs in layer order; each FB gets an
  instance DB; shared plant state in a typed global DB (UDT per area).
  Safety: an F-OB (cyclic interrupt) calls Main_Safety which calls the
  F-FBs - the safety group is checksummed as a unit (collective
  F-signature), so keep standard logic OUT of it: every block in the
  group re-signs on any change.
- **Rockwell**: one continuous task -> programs (one per layer or per
  area) -> routines; program-scoped tags for layer-internal state,
  controller-scoped only for cross-program data. MainRoutine JSRs
  subroutines in a fixed, visible order.
- **Beckhoff/IEC**: one PROGRAM per layer, a task binding fixing the
  order; FUNCTION_BLOCKs for repeated equipment with instances declared
  where the layer owns them.

## Instances vs copies

Repeated equipment (N pumps) is one FB/pattern + N instances - never N
edited copies (copy-drift is how plants end up with "pump 3 is special
and nobody knows why"). In LADDER: a `pattern` invocation per pump, or
one program with per-device UDT instances. Reserve genuinely-special
handling for an explicit, commented deviation.

## Numbering and naming

- Deterministic block numbers matter where audits reference them
  (safety projects): derive as base + area*step + layer-offset so
  adding an area never renumbers existing blocks.
- Block names carry the layer (`FB_IOMap`, `FB_Certified`,
  `FB_Safety`; `P10_Inputs`, `P20_Protection`) so a call tree reads as
  the architecture.

## Review checklist

- each block's one-line responsibility is statable ("maps channels",
  "evaluates area interlocks") - if it needs "and", split it;
- physical outputs written in exactly one layer;
- no backward data flow without an explicit, commented reason;
- safety/standard boundary crossed only via the designated DB members;
- adding equipment touches tables/instances, not copied logic.
