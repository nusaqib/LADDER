# Offline reference library

Original-authored working notes on the standards, vendor APIs, and tools
that LADDER's backends and verification path are built on. The point:
**search here first, go online only when you need normative text or
something these notes don't cover.** Inside a self-contained user project
this whole library is available at `vendor/LADDER/docs/reference/`.

These notes are distilled from building LADDER against the real tools —
they record the object models, formats, gotchas, and version quirks we
actually hit. They are *not* reproductions of any standard or vendor
manual: normative wording, tables, and requirements live only in the
official documents linked at the top of each note.

## Standards

| note | covers |
|---|---|
| [iec-61131-3](standards/iec-61131-3.md) | the software model: POUs, the five languages, data types, what's portable in practice |
| [plcopen-tc6-xml](standards/plcopen-tc6-xml.md) | the tc6_0201 XML exchange format: document shape, FBD/LD/SFC bodies, XSD validation traps |
| [profisafe](standards/profisafe.md) | F-addresses, F-parameters, watchdog, 1oo2 evaluation, what Openness can and cannot set |
| [alarm-management-isa-18-2](standards/alarm-management-isa-18-2.md) | alarm lifecycle, annunciator/first-out behavior, why `alarm_group` looks the way it does |
| [functional-safety-61508-61511](standards/functional-safety-61508-61511.md) | SIL vocabulary, safety lifecycle, redundancy architectures, and LADDER's explicit non-certification stance |

## Vendor APIs

| note | covers |
|---|---|
| [siemens-openness](vendors/siemens-openness.md) | TIA Portal Openness: process model, object tree, import/export, compile, HMI, V19/V21 quirk table |
| [siemens-simatic-ml](vendors/siemens-simatic-ml.md) | SimaticML block/UDT/DB XML: document skeletons, FlgNet LAD wiring, interface sections |
| [rockwell-l5x](vendors/rockwell-l5x.md) | L5X project XML: controller/tags/programs/routines, RLL text grammar, TIMER/Radix details |
| [beckhoff-twincat](vendors/beckhoff-twincat.md) | TwinCAT 3 project anatomy, TcPOU format, PLCopen import, automation interface pointers |

## Tools

| note | covers |
|---|---|
| [matiec](tools/matiec.md) | the open IEC 61131-3 compiler: invocation, dialect limits, the IL formal-call trap |
| [nuxmv](tools/nuxmv.md) | model checking LADDER's emitted SMV: BDD vs IC3, invariants, counterexample reading |

## Ground rules for these notes

1. **Original text only.** Facts and interfaces aren't copyrightable;
   wording is. Never paste standard clauses or vendor manual passages.
2. **Record what we proved, mark what we assume.** A claim like
   "SetAttribute rejects Failsafe_FDestinationAddress on every CLR path"
   is recorded because we tested it; version-tag such claims (V19/V21).
3. **Update in the same commit** as the engine change that taught us
   something new.
