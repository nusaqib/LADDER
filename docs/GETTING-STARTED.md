# Getting started

Ten minutes, one working project, no theory. You need Python 3.11+ and
nothing else — no PLC, no vendor software.

One thing to know before you start: on real projects LADDER runs as an
**LLM-driven loop under your oversight** — an assistant interviews you,
drafts the design, and the machine gates every draft; you review and
decide (see [WORKFLOW](WORKFLOW.md)). This page walks the same loop *by
hand*, one small step at a time, so you know exactly what the assistant
drafts and what the gates catch — that's what makes your oversight
informed rather than ceremonial.

## 1. Install

```powershell
pip install git+https://github.com/nusaqib/LADDER.git
```

## 2. Create a project

```powershell
ladder init my-first-plc
cd my-first-plc
```

This is not an empty template. It is a small, complete, working **motor
station**: a start/stop motor with an emergency-stop interlock and an
overload alarm. Everything you will ever write lives in files that
already exist here, filled in.

## 3. Run the whole gate

```powershell
ladder check .
```

You should see:

```
validate   OK (9 tags, 1 program(s))
scenarios  OK (3/3 passed)
build      OK (8 file(s) -> out, targets: iec, plcopen, siemens, rockwell, beckhoff)
CHECK PASSED
```

Three things just happened: the design was checked for mistakes, the
logic was **executed in a simulator** against three acceptance tests, and
real vendor files (Siemens SCL, Rockwell L5X, PLCopen XML, ...) were
generated into `out/`. That is the entire workflow — everything else is
detail.

## 4. Read the one file that matters

Open `ir/my_first_plc.yaml`. Find this:

```yaml
- element: interlock
  id: IL_motor
  permissives: {all: [estop_ok, overload_ok]}
  output: run_permit
  reset: {signal: reset_pb}
```

Read it out loud: *the run permit requires e-stop OK and overload OK;
if either drops it trips and stays tripped until someone presses reset.*
That is the whole idea of LADDER — you write **what the logic means**,
one declarative element at a time, and every vendor artifact is derived
from it.

## 5. Break it, and watch the net catch you

Delete the `reset:` line from the interlock and run `ladder check .`:

```
V05 [programs/MotorStation/IL_motor] latching interlock requires a reset
```

Put it back. Now open `scenarios/my_first_plc.scenarios.yaml` and change
one expectation to something wrong (say `motor_run: true` right after the
e-stop trips). Run `ladder check .`:

```
FAIL estop_trips_and_stays_down_until_reset - step 7 ...: motor_run is False, expected True
scenarios  FAILED (2/3 passed)
```

The scenarios are the project's definition of done — the simulator runs
your logic scan by scan, with real timer behavior, and refuses the build
when behavior regresses. Undo your change.

## 6. Make a real change

Add a second permissive. In `ir/my_first_plc.yaml`, add a tag:

```yaml
- {name: guard_closed, type: BOOL, direction: input, comment: Guard door closed}
```

and extend the interlock:

```yaml
  permissives: {all: [estop_ok, overload_ok, guard_closed]}
```

Run `ladder check .` — one scenario now fails, because the simulator
starts every input at 0 (= fault: LADDER is fail-safe by default) and
nothing sets the guard healthy. Add `guard_closed: true` to each
scenario's first `set:` step. Green again — and your change is now
*pinned* by the tests that just caught it.

## 7. Where the vendor files went

```
out/siemens/    SCL sources + a build script for TIA Portal
out/rockwell/   an L5X you can import into Studio 5000
out/plcopen/    standard tc6 XML
out/iec/        plain IEC 61131-3 text
```

If you have TIA Portal on this machine, add `deploy: [siemens@21]` to
`ladder.yaml` and run `ladder deploy .` — it builds and compiles an
**openable TIA project** under `out/siemens/project/`. Everything under
`out/` is disposable: regenerate it, never edit it.

## 8. Now let an assistant drive the loop

```powershell
ladder prompt --intake
```

Paste the output into any chat model: it interviews **you** for the
ground truth only you have (signals and their senses, what trips what,
who may reset, the acceptance stories), then drafts the design map, IR,
and scenarios — and `ladder check .` judges the draft exactly as it
judged yours in steps 3–6. That loop — assistant drafts, machine gates,
you decide — is how real projects are built; the full contract is in
[WORKFLOW](WORKFLOW.md).

## Where next

- **[The workflow](WORKFLOW.md)** — the authoring loop: who provides
  what, and where your sign-off gates are.
- **[The tutorial](TUTORIAL.md)** — build a real project from a blank
  requirement: design map, interlocks, alarms, scenarios, documentation.
- **[The guide](GUIDE.md)** — "how do I…" recipes, one task each.
- Reference, when you need it: [IR-SPEC](IR-SPEC.md),
  [SCENARIOS](SCENARIOS.md), [PROJECT-LAYOUT](PROJECT-LAYOUT.md).
