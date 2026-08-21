# SimaticML — TIA block/type XML (working notes)

> Official reference: the "SimaticML" schemas shipped with TIA Portal
> (`...\Portal Vxx\PublicAPI\...\Schemas`) and the Openness manual's
> export-format chapter. The reliable way to learn any construct:
> **build a minimal example in the GUI, export it, and imitate** — the
> exporter is the ground truth for what the importer accepts.

## Document shape (block export)

```xml
<Document>
  <Engineering version="V19" />        <!-- V19-stamped imports fine on V21 -->
  <SW.Blocks.FB ID="0">                <!-- or .FC / .OB / .GlobalDB -->
    <AttributeList>
      <Name>FB_Example</Name>
      <Number>501</Number>             <!-- block number -->
      <ProgrammingLanguage>F_LAD</ProgrammingLanguage>  <!-- LAD, FBD, SCL, DB, F_LAD, F_DB -->
      <Interface><Sections>...</Sections></Interface>
      <MemoryLayout>Optimized</MemoryLayout>
    </AttributeList>
    <ObjectList>
      <SW.Blocks.CompileUnit ID="3" CompositionName="CompileUnits">
        ... one per network ...
      </SW.Blocks.CompileUnit>
      <MultilingualText ...>            <!-- block title/comment -->
    </ObjectList>
  </SW.Blocks.FB>
</Document>
```

- `ID` attributes are hex-ish strings unique within the document; the
  importer renumbers, but they must be internally consistent.
- UDTs: `<SW.Types.PlcStruct>` with the same Interface/Sections scheme.
- Global DBs: `<SW.Blocks.GlobalDB>`; instance DBs of an FB:
  `<SW.Blocks.InstanceDB>` with `<InstanceOfName>`.

## Interface sections

`<Sections xmlns="...v5">` → `<Section Name="Input|Output|InOut|Static|
Temp|Constant|Return">` → `<Member Name="x" Datatype="Bool">`.
Details that bite:

- Datatype strings are TIA spellings: `Bool`, `Int`, `Time`, `"UDT_X"`
  (quoted when user-defined), `Array[0..7] of Bool`.
- F-blocks: members carry F-attributes
  (`<BooleanAttribute Name="F_DataFormat" ...>` etc. in exports);
  imitate the export exactly — hand-inventing F-interface attributes is
  how imports fail cryptically.
- `Remanence`, `ExternalAccessible/Visible/Writable` attributes appear
  per member in exports; safe to reproduce verbatim.

## Networks: FlgNet (LAD/FBD wiring)

Each CompileUnit's `<NetworkSource>` holds a
`<FlgNet xmlns="...FlgNet/v4">` with two halves:

- `<Parts>`: the nodes — `<Access Scope="GlobalVariable">` (a tag
  reference: `<Symbol><Component Name="DB_X"/><Component Name="Member"/>
  </Symbol>`), `<Part Name="Contact" UId="21">` /
  `Coil` / `SCoil` / `RCoil` / `PBox` (edge) / instruction calls
  (`<Call>` with `<CallInfo Name="EV1oo2DI" BlockType="FB">` and an
  `<Instance>` binding).
- `<Wires>`: connectivity — `<Wire UId="51"><Powerrail/>
  <NameCon UId="21" Name="in"/></Wire>` chains outputs to inputs by
  UId + port name (`in`, `out`, `operand`, `eno`...). Contacts AND by
  chaining `out → in`; OR branches by several wires feeding one `in`.

Conventions that keep the importer happy (all learned from exports):

1. UIds: parts and wires share one numeric space; exports start parts at
   21 and wires above them — any consistent scheme works.
2. Negated contact: `<Negated Name="operand"/>` inside the Part.
3. Every `<Access>` symbol component chain must resolve against tags/DBs
   that already exist in the project **at import time** — import order
   is UDTs → tags → DBs → FBs → OB.
4. F-LAD blocks import like LAD with `ProgrammingLanguage=F_LAD`; the
   safety compiler then owns them (certified instructions appear as
   `<Call>`s to the library FBs with version, e.g. EV1oo2DI V1.3).

## Import call

```powershell
$software.BlockGroup.Blocks.Import([IO.FileInfo]$path,
    [Siemens.Engineering.ImportOptions]::Override)
$software.TypeGroup.Types.Import(...)   # UDTs
```

Export (for imitation): select in GUI → "Export block as XML", or
Openness `block.Export(FileInfo, ExportOptions.WithDefaults)`.
