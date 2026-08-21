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

## …show the logic to someone who doesn't read YAML?

`ladder render .` → `out/report.html`: every program as ladder rung art
(or ST pseudocode where logic isn't rung-shaped), beside the element
table, the acceptance scenarios, and the safety theorems. This is the
review artifact — regenerate it with every change, never edit it.

## …find out why deploy doesn't work on this machine?

`ladder doctor .` — a preflight checklist: toolchain, manifest gate,
vendored submodule, nuXmv/matiec/XSD, and each vendor tool your
`deploy:` list needs — each with the fix for anything missing.
`python tools/fetch_verifiers.py` fetches nuXmv (and clones matiec)
into `.tools/` where doctor and `ladder verify` find them.

## …know if my scenarios would catch real faults?

`ladder mutate .` injects single realistic faults (dropped permissive,
defeated 1oo2 channel, removed debounce/latch, dropped search station)
and runs your suite against each. SURVIVED lines are faults your
acceptance tests would wave through — each tells you which scenario to
add. The scaffold starter scores 100%; keep yours there.

## …prove a backend (mine or a plugin) supports the whole IR?

`ladder conformance -t <backend>` runs the packaged example+benchmark
corpus through the backend: every element, all five languages, emit +
non-empty output per project (plus the scenario baseline). Passing it
is the plugin compatibility contract from [BACKENDS](BACKENDS.md).

## …understand a failed proof?

When `ladder verify -t smv` finds a violated theorem it writes
`out/smv/<program>.replay.scenarios.yaml` — the nuXmv counterexample as
a runnable scenario. Run it with `ladder test`: a PASS means the
violation is concrete (step through it, fix the design, then invert the
final `expect` to keep it as a regression); a FAIL usually means the
trace rides on the timer over-approximation.

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
them as INVARSPECs beside the auto-theorems. Pattern sugar for
non-logicians (each desugars to the same invariant form):

```yaml
  - {program: Safety, never: horn AND NOT lamp}
  - {program: Safety, mutex: [fill_vlv_cmd, drain_vlv_cmd]}
  - {program: Safety, if: search_done, then: key1.Latched}
```

## …simulate one weird timing by hand?

Interactively — a commissioning panel in the terminal:

```
ladder sim .
> set estop_ok true          > pulse start_pb
> watch motor_run run_permit > run 1500 50
> state                      > help
```

Or scripted in Python (`ladder.sim.Simulator`: set/pulse/run/get).
Scenarios are the same thing, declarative and CI-run.

## …test a PID/analog loop without hardware?

Attach a plant model inside the scenario — the simulator closes the
loop and `expect_near` asserts with tolerance:

```yaml
steps:
  - model: {input: heater_out, output: temp_pv,
            gain: 1.0, tau_ms: 2000, ambient: 20.0}
  - set: {enable: true}
  - run: {ms: 60000, dt_ms: 100}
  - expect_near: {temp_pv: {value: 60.0, tol: 3.0}}
```

`model:` is a first-order lag (pv → ambient + gain·u, time constant
tau); attach several for multi-loop plants.

## …review what a change actually did?

`ladder diff old.yaml new.yaml` (files or modular dirs) — semantic
changes in design language: `IL_motor: permissives gained guard_closed`,
dropped tags, added elements, and an explicit warning when element
ORDER changed (scan-order review required).

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

## …bring an existing Studio 5000 program into LADDER?

Export the controller as L5X (File → Save As → L5X), then
`ladder adopt rockwell plant.L5X` — tags, UDTs, timers (presets
included), and RLL rungs come back as elements; anything untranslatable
is quarantined as a commented `st` block and listed in the report.
Prove fidelity behaviorally: write scenarios against the old program's
known behavior and run them on the adopted IR.

## …expose the PLC to EPICS?

Add `epics` to the manifest's `targets:`. The backend emits
`out/epics/<Name>.db` — one record per directional tag (bi/bo/ai/ao),
site prefix and transport as macros (`$(P)`, `$(LINK=)` — OPC UA,
s7plc, or Modbus is a load-time choice, not a design property), alarm
severities wired from the IR's alarm elements, fail-safe `_ok` inputs
alarming on 0 — plus `<Name>-alarms.csv` as the alarm-handler/archiver
seed. An `epics:` section in the iomap pins concrete links.

## …add a new vendor?

A backend is one self-contained module rendering the neutral statement
AST — see [BACKENDS](BACKENDS.md) for the contract, registration, and
the external plugin entry point.
