---
name: udt-design
description: Design user-defined types (UDTs/DUTs/structs) for PLC data - member conventions, nesting, vendor mapping (Siemens optimized DBs and F-compliance, Logix BIT packing, TwinCAT DUTs). Use when structuring repeated equipment data or capturing an existing type tree.
---

# UDT design: types are the program's vocabulary

A UDT turns "these 9 tags belong to one gate" into a reviewable fact.
Use one wherever the same shape repeats (per-device, per-area) - and
resist one everywhere else.

## Rules that survive contact with vendors

1. **Shape = one physical/logical thing.** `UDT_Gate {Closed_OK,
   Locked_OK, Cmd_Unlock, Faulted, ...}` - members read as the device's
   interface. If a member only makes sense for *some* instances, the
   type is wrong: split it.
2. **Flat beats deep.** One nesting level (area -> device) is
   reviewable; three is archaeology. Model checkers, HMIs, and
   commissioning sheets all pay per level. LADDER validates dotted
   member paths (`key1.Eval_OK`) and flattens them for SMV - arrays of
   UDTs are not model-checkable, so prefer named members over arrays
   for protective data.
3. **Members follow tag conventions** (`_ok` senses, `_cmd`/`_fb`
   pairs) - a UDT is a namespace, not an excuse for new naming.
4. **Version types deliberately.** Adding a member is compatible;
   renaming/retyping breaks every consumer, HMI binding, and archive.
   In brownfield captures, reproduce the existing tree *exactly* first
   (export it), improve later behind a reviewed change.

## Declaring in LADDER IR

```yaml
types:
  - name: SafeInput
    members:
      - {name: Eval_OK, comment: 1oo2 evaluation result}
      - {name: Latched, comment: search latch}
tags:
  - {name: key1, type: SafeInput}
```

Members default BOOL; give `type:` for others. Elements reference
members with dotted paths; validation resolves them (V10).

## Vendor mapping (what the backends do, and why)

- **Siemens**: UDTs emit as PLC data types; complex tags live in a
  generated global DB (TIA PLC tag tables cannot hold structs/arrays).
  Optimized-access DBs reorder members - never assume offsets; address
  by symbol always. **F-systems**: an F-compliant UDT carries
  attributes SCL cannot express - capture/import as SimaticML, only
  BOOL members inside F-UDTs used by F-logic, and the type must exist
  in the project *before* any DB/tag that uses it imports (else
  `Data type "X" is unknown`).
- **Rockwell**: UDT members pack - consecutive BOOLs share hidden SINT
  backing. Member order therefore matters for memory, not for logic;
  keep BOOLs grouped. Predefined types (TIMER, COUNTER) nest fine.
- **Beckhoff/IEC**: plain `TYPE ... : STRUCT ... END_STRUCT` in .TcDUT
  files - the friendliest target; what you declare is what you get.

## Anti-patterns

- The god-struct (`UDT_Everything`) - one instance, no reuse, every
  consumer coupled to every member.
- Booleans encoding an enumeration (`Mode_Auto`, `Mode_Manual`,
  `Mode_Local` as three BOOLs) - use an INT state with named codes (a
  `state_machine` element) so illegal combinations cannot exist.
- HMI-shaped types in the PLC (string labels, color codes) - the PLC
  owns process truth; presentation belongs to the HMI layer.
- Spare members "for later" - they document nothing and get abused;
  add members when the change is real and reviewed.
