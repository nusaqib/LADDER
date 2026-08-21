# Rockwell L5X — Logix project XML (working notes)

> Official references: Rockwell publication 1756-RM084 "Logix 5000
> Controllers Import/Export Reference Manual" (free PDF from
> literature.rockwellautomation.com — the single best document) and the
> `.xsd` installed with Studio 5000. Also useful: the open-source Python
> `l5x` library as executable documentation.

## Document shape

```xml
<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="36.00"
                    TargetName="MyPlant" TargetType="Controller"
                    ContainsContext="false" ExportOptions="...">
  <Controller Use="Target" Name="MyPlant" ProcessorType="1756-L83E"
              MajorRev="36" MinorRev="11">
    <DataTypes>   ... UDTs ...            </DataTypes>
    <Tags>        ... controller tags ... </Tags>
    <Programs>
      <Program Name="MainProgram" MainRoutineName="Main">
        <Tags> ... program-scoped tags ... </Tags>
        <Routines>
          <Routine Name="Main" Type="RLL"> <RLLContent> ... </RLLContent> </Routine>
          <Routine Name="Calc" Type="ST">  <STContent> <Line Number="0">...</Line> </STContent> </Routine>
        </Routines>
      </Program>
    </Programs>
    <Tasks><Task Name="MainTask" Type="CONTINUOUS">
      <ScheduledPrograms><ScheduledProgram Name="MainProgram"/></ScheduledPrograms>
    </Task></Tasks>
  </Controller>
</RSLogix5000Content>
```

- `SoftwareRevision`/`MajorRev` pin the Studio 5000 version (v36 = the
  current LTS-ish line; LADDER's `rockwell@36` maps here).
- An L5X can be a whole controller (`TargetType="Controller"`) or a
  partial import (a routine, a UDT, `ContainsContext="true"`); whole-
  controller is the reproducible path.
- Human text lives in `<Description><![CDATA[...]]></Description>`
  children — CDATA everywhere.

## Tags

```xml
<Tag Name="motor_run" TagType="Base" DataType="BOOL" Radix="Decimal"
     Constant="false" ExternalAccess="Read/Write">
  <Data Format="L5K"><![CDATA[0]]></Data>
</Tag>
```

- REAL tags: `Radix="Float"`. TIMER tags: `DataType="TIMER"` with a
  decorated-data block carrying `PRE` (milliseconds, DINT), `ACC`, and
  the EN/TT/DN bits. LADDER writes `PRE` natively from the IR's `T#...`.
- **Alias tags** bind logic names to IO:
  `<Tag Name="estop_ok" TagType="Alias" AliasFor="Local:1:I.Data.0"/>`
  — this is what the iomap's `rockwell:` section becomes; logic then
  reads like the design, wiring stays swappable.
- IO module tags (`Local:1:I`...) come from `<Modules>` config; for a
  logic-only L5X, alias targets may reference modules added later — the
  import reconciles.

## RLL (ladder) text grammar

Each rung is one text line: instructions with parenthesized operands,
series = space, parallel branch = `[ ... , ... ]`:

```
<Rung Number="0" Type="N">
  <Text><![CDATA[XIC(estop_ok)XIC(overload_ok)[XIC(start_pb),XIC(motor_run)]XIO(stop_req)OTE(motor_run);]]></Text>
</Rung>
```

The instruction set LADDER emits (all vanilla):

| instr | meaning |
|---|---|
| `XIC(t)` / `XIO(t)` | examine if closed / open (NO / NC contact) |
| `OTE(t)` | output energize (non-retentive coil) |
| `OTL(t)` / `OTU(t)` | latch / unlatch (set/reset) |
| `MOV(src,dst)` | move (used for INT/REAL assignments) |
| `TON(timer,?,?)` | on-delay timer on its TIMER tag |
| `ONS(storage)` | one-shot (LADDER prefers explicit prev-bools instead) |

Rungs end with `;`. Comments attach as rung `<Comment>` CDATA.

## Import paths

- GUI: File → Open the `.L5X` (whole controller) or right-click →
  Import Component (partial).
- Automated: the **Logix Designer SDK** (v2+, Python/.NET client) can
  create an `.ACD` from L5X headlessly — needs Studio 5000 installed and
  licensed; LADDER's `rockwell` deploy step uses it when present and
  prints manual instructions otherwise.
- Verification without Studio 5000: schema-validate against the
  installed XSD, plus semantic checks (LADDER's `ladder verify -t
  rockwell` re-parses rung text and tag tables).
