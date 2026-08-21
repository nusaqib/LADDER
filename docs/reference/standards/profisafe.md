# PROFIsafe — F-communication over PROFINET (working notes)

> Normative sources: IEC 61784-3-3 (PROFIsafe), PI specification
> "PROFIsafe — Profile for Safety Technology" (profibus.com), Siemens
> "SIMATIC Safety — Configuring and Programming" manual (the practical
> authority for F-parameters in TIA). Original notes below; version-
> tagged claims were tested on TIA V19 and V21.

## The model

PROFIsafe runs a safety layer ("black channel") over standard PROFINET:
the transport is untrusted; integrity comes from the F-layer's CRC,
sequence numbering, and watchdog. Each F-device ↔ F-host relationship is
identified by **F-addresses**:

- **F_Source_Address** — the F-host (F-CPU) side.
- **F_Dest_Address** — unique per F-module; must match what the module
  itself believes. On ET200SP F-modules that belief is set by the
  **BaseUnit coding/DIP switches** — the project value and the physical
  switches must agree or the module never exchanges F-IO data.
- **F_WD_Time (F-monitoring time)** — watchdog for valid F-telegrams;
  too small → spurious passivation; the default (150 ms typical) is
  conservative for small networks.

## Passivation and reintegration

On any F-error (CRC, watchdog, discrepancy, channel fault) the module
**passivates**: safe substitute values (0) are delivered instead of
process values, and `QBAD`/`PASS_OUT` indicate it. Recovery requires the
fault to clear *and* an operator **reintegration** (ACK_REI /
ACK_NEC-gated). Design consequence LADDER inherits: every dual-channel
input's evaluation result must be treated as "0 = not safe", and
acknowledge paths are explicit, deliberate signals — never automatic.

## 1oo2 evaluation and discrepancy

F-DI modules evaluate paired channels (1oo2): the safe result is 1 only
while both channels agree on 1. Disagreement starts the **discrepancy
time**; if it expires before agreement, a discrepancy fault latches and
(configurably) needs acknowledgment after the channels re-agree.
LADDER's `dual_channel` element mirrors exactly this behavior in the
portable IR so the same semantics exist on non-Siemens targets and in
the model checker.

## What TIA Openness can and cannot configure (tested)

| item | V19 | V21 | notes |
|---|---|---|---|
| Place F-CPU / F-modules from catalog | yes | yes | normal `Devices`/`DeviceItems` API |
| Read `Failsafe_FDestinationAddress` | yes | yes | attribute lives on a *child* DeviceItem, not the module head |
| **Write** `Failsafe_FDestinationAddress` | no | no | `SetAttribute` throws on every CLR type/timing we tried, even where the attribute reports ReadWrite. GUI-only. Plan for a documented manual step matching the DIP switches. |
| Read `Failsafe_FMonitoringtime` | yes | yes | writable only after the manual-assignment flag is set |
| F-signature / safety program compile | via compiler | via compiler | compile reports it; not settable |

The compiler does **not** object to catalog-default F_Dest_Addresses
(all 65534-ish auto values) — the project compiles green and is still
undeployable against real hardware until the addresses match the
switches. Treat "compile clean" as necessary, never sufficient.

## Safety program structure (Siemens F-system)

- F-blocks (F-FB/F-FC/F-DB) live in a safety group under a **Main_Safety**
  called from an F-OB (cyclic interrupt, e.g. OB123 / RTG1).
- Certified library instructions (e.g. `EV1oo2DI`, `ESTOP1`, `SFDOOR`,
  versioned like 1.3/1.6) each take an instance in the safety group's
  instance DB; the F-compiler checksums the whole group (collective
  F-signature).
- F-LAD/F-FBD only — no F-ST in classic TIA safety. Generated logic
  therefore must be delivered as LAD networks (SimaticML FlgNet), which
  is why LADDER's Siemens F-path emits LAD XML rather than SCL.
