# LADDER benchmark: spec → IR

Machine-checkable PLC generation tasks. Each task is a folder:

```
taskNN_name/
  requirement.md    what to build (the ONLY thing the model sees)
  scenarios.yaml    acceptance scenarios, run in the LADDER simulator
  reference.yaml    a known-good solution (passes all scenarios; CI-verified)
```

A submission passes a task when its IR validates (`ladder validate`) and
**all acceptance scenarios pass** (`ladder test`). No vendor software is
involved anywhere — scoring is pure Python.

## Running

```bash
# score an existing IR document against a task
ladder test my_solution.yaml benchmarks/task01_conveyor_jam/scenarios.yaml

# run the full loop with any model (the command reads the prompt on stdin)
ladder generate benchmarks/task01_conveyor_jam/requirement.md \
    --cmd "your-llm-cli" \
    --accept benchmarks/task01_conveyor_jam/scenarios.yaml \
    -o solution.yaml
```

## Why this exists

Published LLM-PLC benchmarks (e.g. Agents4PLC's) score generated
*Structured Text*. This benchmark scores at the IR level: behavior is
checked by simulation scenarios, which means acceptance is about what the
program *does* — trip timing, latching, sequence order — not how its text
looks. Reference solutions double as semantics documentation.

## Contributing a task

- The requirement must be self-contained prose (no LADDER jargon), the way
  a controls engineer would receive it.
- Scenarios must pin the behaviors that matter, including at least one
  timing behavior and one failure/recovery path.
- Provide a reference solution; CI verifies it stays green.
- Fail-safe conventions apply (inputs `*_ok`: TRUE = healthy).
