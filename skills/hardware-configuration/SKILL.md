---
name: hardware-configuration
description: Configure PLC hardware - CPU selection, racks/stations, IO modules, PROFINET/EtherNet-IP topology, PROFIsafe parameters - as reviewable design data that generators consume. Use when a project needs its controller/IO defined or an existing rack must be captured.
---

# Hardware configuration: racks as design data, not clicks

Hardware belongs in **tables the build consumes**, never in undocumented
IDE clicks: a station list and a module list (CSV/sheet), from which the
project is generated and against which the as-built is verified. LADDER
projects keep addresses in `iomaps/` and hardware inventory beside the
design map; the Siemens path feeds a sheet-driven pipeline
(tia-autocode's `Invoke-TiaSheetPipeline`), Rockwell embeds `<Modules>`
in L5X.

## The stance

1. **Exact part numbers or nothing.** A module is an order number +
   firmware (`6ES7 131-6BF01-0BA0` + `V2.1`), not "an 8ch DI". Catalog
   acceptance differs per tool version - the generator must probe
   (`CanPlugNew`-style) rather than assume, and the sheet must record
   what was actually accepted.
2. **Derived values never get authored.** IO start addresses, tag
   safety-class prefixes, and device counts are read back from the
   built project into report files; anything stated twice will
   eventually disagree.
3. **The inventory is the coverage claim.** Every physical module
   appears in the table even if unused - "nobody considered it" must
   not look like "considered and excluded".

## Procedure

1. Fix the CPU first: family and safety variant decide everything
   downstream (an F-CPU for personnel protection: e.g. 1515F-2 PN; a
   GuardLogix for Rockwell safety). Record firmware.
2. Stations: name, rack/slot or PROFINET device name + IP, one row
   each. PROFINET device names are lowercase, hyphenated, and must
   match commissioning (`iod-bta`); IPs from a documented plan.
3. Modules: per station, slot-ordered rows - order number, firmware,
   channel count, and for F-modules the PROFIsafe columns (see below).
   Terminal/base info where the platform needs it (ET200SP BaseUnits;
   point IO wiring bases).
4. Generate, compile, then export the address map (`%I/%Q` starts,
   `Local:n:I` layouts) into a report the iomap can cite.
5. Any change repeats the loop: edit table -> regenerate -> compile ->
   re-export -> diff.

## PROFIsafe / safety IO (the part that bites)

- `F_Dest_Address` is unique per F-module and must match the physical
  DIP/coding switches. TIA Openness cannot write it (V19 and V21,
  tested - GUI-only); the compiler accepts catalogue defaults, so
  "compiles clean" is NOT "deployable". Record intended addresses in
  the sheet, enter them in the GUI, and read back to verify.
- `F_WD_Time`: start conservative (default 150 ms); too tight causes
  spurious passivation under network load.
- On passivation all F-IO reads as 0: with the 1=OK convention every
  fault is a trip, which is the point. Design reintegration (ACK_REI)
  as an explicit operator action.
- A simulated F-CPU has no PROFIsafe partners - everything passivates.
  Bench builds that stub this must never leave the bench.

## Vendor notes

- **Siemens**: catalog IDs are `OrderNumber:<MLFB>/<FW>`; F-parameters
  live on child DeviceItems; see `docs/reference/vendors/siemens-openness.md`
  and the hardware-parameters PDF in `docs/reference/downloads/`.
- **Rockwell**: modules are `<Module>` entries in L5X (catalog number,
  slot, connection); IO tags materialize as `Local:slot:I/O` and logic
  binds via alias tags - keep aliases in the iomap.
- **Beckhoff**: IO is the EtherCAT scan in the .tsproj; POUs use
  `AT %I*` deferred addresses and the linker maps them - generate link
  names, not offsets.

Gate: hardware compiles clean AND the exported address map matches the
iomap AND (safety) F-addresses verified against the switches - three
different checks, all needed.
