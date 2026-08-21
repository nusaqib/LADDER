# nuXmv — model checking LADDER's emitted SMV (working notes)

> Tool: https://nuxmv.fbk.eu (free for non-commercial use; binary
> download). LADDER emits one SMV module per program (`ladder model`)
> with auto-theorems per safety element plus any user properties, then
> `ladder verify -t smv` runs nuXmv via `NUXMV_BIN`.

## What LADDER's SMV looks like

- One `MODULE main` per program; every BOOL tag is a state var; inputs
  are unconstrained (`IVAR`-like via nondeterministic next), outputs are
  `next()` assignments produced by **symbolic execution of the lowered
  statement AST** — so the model is scan-accurate by construction.
- **Timers are over-approximated**: an elapsed timer output is a free
  boolean constrained only by its enable — a proof therefore holds for
  *every* preset value. (Consequence: properties that depend on exact
  durations are out of scope by design; test those in the simulator.)
- UDT members are flattened (`key1.Eval_OK` → `key1_Eval_OK`); arrays
  are rejected at the model boundary rather than mis-modeled.
- Properties are `INVARSPEC`s: auto-theorems (e.g. "interlock output
  implies every permissive", "no ack path can set a search latch") and
  user properties from the properties file:
  `INVARSPEC ((given) -> (always));`

## Running it

**BDD (default)** — fine to ~100 vars, exhaustive, gives shortest
counterexamples:

```bash
nuXmv -dcx model.smv          # -dcx: no counterexample printing (CI)
nuXmv model.smv               # with counterexamples
```

Look for `-- invariant ... is true` / `is false` lines; any `is false`
= a real reachable violation of that theorem (modulo the timer
over-approximation, which only ever *adds* behaviors — a proof is sound,
a counterexample involving timers needs a simulator re-check).

**IC3 (large models)** — the SR PPS certified layer (~250 vars) needs
this; BDD blows up. nuXmv's IC3 runs from an interactive command script:

```
read_model -i model.smv
flatten_hierarchy
encode_variables
build_boolean_model
check_invar_ic3
quit
```

```bash
nuXmv -source script.cmd
```

LADDER's `check_invar_ic3` path automates exactly this. IC3 proves or
refutes each INVARSPEC independently and scales far beyond BDD for
invariant checking (it's SAT-based, no global BDD to build).

## Reading counterexamples

A counterexample is a state sequence; each `-> State: 1.N <-` block
prints only variables that *changed*. Reconstruct the scan story by
carrying values forward. The practical workflow: identify the input
pattern in the trace, replay it as a scenario in `ladder`'s simulator
(same semantics, friendlier output), fix the design, re-prove.

## Discipline

- A theorem that *fails to parse* is worse than a missing one — CI runs
  nuXmv on every emitted model even when there's nothing new to prove.
- Keep models per-program small rather than one whole-plant model:
  composition happens at review time, tractability stays per-module.
- Record BDD-vs-IC3 choice per program in the project docs; "it proved
  once on my machine" is not a verification result.
