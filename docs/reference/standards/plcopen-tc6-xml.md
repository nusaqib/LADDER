# PLCopen tc6 XML — the graphic-exchange format (working notes)

> Normative source: PLCopen TC6 "XML Formats for IEC 61131-3", v2.01
> (tc6_0201). The XSD is freely available from plcopen.org (our CI
> fetches a mirror). These notes record the document shape and the
> validation traps we hit making LADDER's `plcopen` backend XSD-clean.

## Document skeleton

```xml
<project xmlns="http://www.plcopen.org/xml/tc6_0201">
  <fileHeader companyName="..." productName="..." productVersion="..."
              creationDateTime="2026-01-01T00:00:00"/>
  <contentHeader name="ProjectName">
    <coordinateInfo><fbd><scaling x="1" y="1"/></fbd>
      <ld><scaling x="1" y="1"/></ld><sfc><scaling x="1" y="1"/></sfc>
    </coordinateInfo>
  </contentHeader>
  <types>
    <dataTypes>  <!-- derived types (structs = UDTs) -->
    <pous>       <!-- one <pou name= pouType="program|functionBlock|function"> each -->
  </types>
  <instances><configurations>...</configurations></instances>
</project>
```

Element **order inside a sequence is fixed by the XSD** — most of our
early validation errors were ordering, not content.

## POU bodies

A `<pou>` has `<interface>` (localVars/inputVars/outputVars, each
`<variable name=""><type><BOOL/></type></variable>`) and one `<body>`
containing exactly one of `<ST>`, `<IL>`, `<FBD>`, `<LD>`, `<SFC>`.
Textual bodies wrap content in `<xhtml xmlns="http://www.w3.org/1999/xhtml">`.

### LD bodies

Everything is a positioned element with a numeric `localId`; wiring is
expressed by *consumers naming their producers*:

- `<leftPowerRail>` / `<rightPowerRail>` — rails; power flows left→right.
- `<contact negated="false|true">` with `<variable>tag</variable>`.
- `<coil>` (attributes `negated`, `storage="set|reset"` for latch coils).
- `<block typeName="TON" instanceName="t1">` for FB calls in-rung.
- Each element's `<connectionPointIn>` holds `<connection refLocalId="N"
  formalParameter="...">` pointing back at the producer.

**XSD traps we fixed (recorded so nobody re-fights them):**

1. `leftPowerRail` requires a `<connectionPointOut formalParameter="">`
   — the *empty-string* formalParameter attribute must be present.
2. `<comment>` elements require explicit `height` and `width` attributes.
3. SFC `<step>`: its `connectionPointOut` also carries
   `formalParameter=""`.
4. SFC `<action>` references need their own `localId` and
   `<relPosition x="0" y="0"/>`.
5. SFC `<transition>` takes its condition inline (`<condition>` with a
   nested inline body) and a `priority` attribute — emit `priority="0"`
   when unused, don't omit it.
6. Every graphic element needs `<position x="" y=""/>`; coordinates can
   be synthetic (we lay rungs out on a fixed grid) but must be present.

### FBD bodies

Same positioned-element scheme with `<inVariable>`, `<outVariable>`,
`<block>` (AND/OR/NOT are blocks with typeName), connections by
refLocalId. A latch (set/reset pair in LD) has no direct FBD idiom —
LADDER folds it to an RS-equivalent block structure where the
**later-written rung dominates**, mirroring scan order.

## Validating

```bash
python -c "import xmlschema; xmlschema.XMLSchema('tc6_xml_v201.xsd').validate('out/plcopen/X.xml')"
```

CI does exactly this (`TC6_XSD` env var). Round-trip note: import
support in real IDEs varies — CODESYS and Beckhoff read tc6 well;
Siemens TIA does **not** import tc6 (use SimaticML / Openness instead);
Rockwell does not (use L5X). tc6 is our *portable proof* format, not the
Siemens/Rockwell delivery path.
