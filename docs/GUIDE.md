# Guide — how do I…

Task-sized recipes. Each stands alone; each assumes you've seen
[Getting started](GETTING-STARTED.md). Reference detail lives in
[IR-SPEC](IR-SPEC.md).

## …start a brand-new machine?

`ladder init <dir>` → edit `design/DESIGN.md` first → mirror it in `ir/`
→ keep `scenarios/` in the same commit → `ladder check .` until green.
The [tutorial](TUTORIAL.md) walks this end-to-end.

## …make a project self-contained (no LADDER install needed)?

`ladder init` already scaffolds it: `tools/bootstrap.ps1` (or `.sh`) pins
LADDER as a git submodule at `vendor/LADDER` and installs it into a
project-local `.venv`. A colleague needs only:

```bash
git clone --recursive <project> && cd <project>
tools/bootstrap.sh          # Windows: tools\bootstrap.ps1
.venv/bin/ladder check .
```

The manifest's `requires: ">=0.2,<0.3"` refuses to run under any other
toolchain version. To upgrade: `git -C vendor/LADDER pull`, re-run
bootstrap, `ladder check`, commit the new pin only when green.

## …look up a standard or vendor API offline?

`docs/reference/` in the LADDER repo (so `vendor/LADDER/docs/reference/`
inside any project) holds original-authored reference notes: IEC 61131-3,
PLCopen tc6 XML, PROFIsafe, alarm-management (ISA-18.2) on the standards
side; TIA Openness, SimaticML, Rockwell L5X, matiec and nuXmv on the API
side. Search there first; go online only for normative text.

## …split a big IR into reviewable files?

Point the manifest at a directory (`ir: ir`) and split:

```
ir/project.yaml            name, description, vendor hints
ir/types.yaml              UDTs
ir/tags.yaml               signal list (or tags/*.yaml fragments)
ir/programs/10_inputs.yaml one program per file — the numeric prefix
ir/programs/20_logic.yaml  fixes the SCAN ORDER
```

## …model a device with two redundant switches?

`dual_channel`. Never hand-AND the channels — the element carries the
1oo2 semantics, discrepancy monitoring, and the ack contract:

```yaml
- element: dual_channel
  id: DC_gate
  channel_a: gate_sw1
  channel_b: gate_sw2
  output: gate_ok
  discrepancy_time: T#500ms
  fault: gate_disc_flt
  ack: area_reset
```

## …build an annunciator with first-out?

One `alarm_group` (see the tutorial, step 4). Three or more alarms
sharing an ack or horn is the signal you want it.

## …write a search/arming sequence (PPS-style)?

`search_chain`: stations latch on the **rising edge** of their key, in
walk order, only while the precondition holds; any breach cascades and
clears everything in one scan; no ack can restore a search. That last
property is structural — the element has nowhere to wire a reset, on
purpose.

## …choose ladder / SFC / IL for a program?

`language:` on the program is a *communication* choice, not semantics:
`ladder` when plant electricians review it as rungs (renders as native
RLL on Rockwell and LD in PLCopen), `sfc` for a program that is exactly
one state machine, `il` for legacy runtimes, default `st`. V11 tells you
when logic doesn't fit the chosen language.

## …put hardware addresses on my tags?

Never in the IR. Write an IO map and pass it everywhere:

```yaml
# iomaps/plant.iomap.yaml
project: Plant
siemens:  {flow_ok: {address: "%I8.0"}}
rockwell: {flow_ok: {alias: "Local:1:I.Data.0"}}
```

The manifest wires it into `ladder check`; located variables, alias
tags, and AT declarations come out per vendor.

## …target a specific tool version?

`name@version`, everywhere a target is named: `targets: [siemens@21,
rockwell@36]`, `ladder build -t siemens@19`. One backend serves several
tool generations; version quirks live behind that switch.

## …get an openable TIA / Studio 5000 project?

Declare intent in the manifest and run deploy on a machine that has the
tool:

```yaml
deploy: [siemens@21]
```

`ladder deploy .` → `out/siemens/project/<Name>/<Name>.ap21`, compiled.
Rockwell: import the L5X (SDK 2.x automates this when installed).
Everything under `out/` is disposable — regenerate, never hand-edit.

## …prove a safety property, not just test it?

`ladder model <ir> -o out` emits SMV with auto-theorems per interlock /
dual_channel / search_chain / alarm_group; `ladder verify -t smv` runs
nuXmv (`NUXMV_BIN`). Timers are over-approximated, so proofs hold for
every preset. For big models use IC3 (`check_invar_ic3`) instead of the
default BDD engine. Add your own invariants in a properties file:

```yaml
properties:
  - program: Safety
    description: a completed search implies the first station
    given: search_done
    always: key1.Latched
```

`ladder model <ir> --properties props.yaml` (also on `verify`) appends
them as INVARSPECs beside the auto-theorems.

## …simulate one weird timing by hand?

```python
from ladder.ir.loader import load_project
from ladder.sim import Simulator
sim = Simulator(load_project("ir/plant.yaml"))
sim.set("water_flow_ok", True); sim.pulse("reset_pb")
sim.run(2500, dt_ms=50)
print(sim.get("pump_permit"))
```

Scenarios are this, declarative and CI-run.

## …generate the documentation package?

`ladder docs .` → `docs/generated/`: requirements (one SHALL per
element), software spec, conventions, developer + operator manuals,
verification report. Regenerate in the same commit as any logic change.

## …use an LLM to draft the design?

The recommended loop for real projects — see [WORKFLOW](WORKFLOW.md) for
who provides what. `ladder prompt --intake` prints an interview contract
for any chat model: it asks *you* for the ground truth (signals, senses,
safety philosophy, acceptance stories), then drafts the map, IR, and
scenarios for `ladder check` to judge. With a requirement text already
in hand: `ladder prompt "<requirement>"` for one-shot drafting, or
`ladder generate "<requirement>" --cmd "<llm-cli>" --accept scenarios.yaml`
for the mechanically closed loop — validator issue codes and your
scenarios are the feedback, and a human reviews the result like any
other change. The pipeline itself never needs a model: the same gates
run standalone. The `skills/` folder holds the deeper workflows (intake,
authoring, deploy, verification, documentation) for agent frameworks.

## …bring an existing TIA program into LADDER?

Export it with the TiaOpenness module (`Export-TiaToSpec`), then
`ladder adopt siemens <spec-dir>` — you get IR plus a structure report.
Diff round-trips (IR → SCL → TIA → export → IR) to prove fidelity.

## …add a new vendor?

A backend is one self-contained module rendering the neutral statement
AST — see [BACKENDS](BACKENDS.md) for the contract, registration, and
the external plugin entry point.
