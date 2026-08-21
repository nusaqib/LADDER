# Documentation

Pick your entry point by what you're doing — the slope is deliberate:

## Learn (in order)

1. **[Getting started](GETTING-STARTED.md)** — ten minutes, a working
   project, no theory.
2. **[Tutorial](TUTORIAL.md)** — build a real vacuum skid from a
   requirement: design map → interlock → patterns → annunciator →
   proofs → deliverables.
3. **[Guide](GUIDE.md)** — "how do I…" recipes, one task each.

## Reference (when you need it)

| | |
|---|---|
| [IR-SPEC](IR-SPEC.md) | every element, field, and validation rule |
| [SCENARIOS](SCENARIOS.md) | the acceptance-test format |
| [DESIGN-INPUTS](DESIGN-INPUTS.md) | the intake map a successful project starts from |
| [PROJECT-LAYOUT](PROJECT-LAYOUT.md) | user-project structure, manifest, targets vs deploy |
| [BACKENDS](BACKENDS.md) | writing a vendor backend / plugin |
| [VERSIONING](VERSIONING.md) | IR semver, the RFC process, the road to 1.0 |
| [ROADMAP](ROADMAP.md) | where the project is and what's next |
| [RELATED-WORK](RELATED-WORK.md) | prior-art survey, gap analysis, adopted best practices |
| [reference/](reference/README.md) | offline library: IEC/PLCopen/PROFIsafe/ISA notes + vendor API notes (TIA Openness, SimaticML, L5X, TwinCAT, matiec, nuXmv) — search here before searching online |

## For agents and LLMs

Tool-agnostic working notes in [AGENTS.md](../AGENTS.md); expert
workflows in [skills/](../skills/) (intake → authoring → deploy →
verification → documentation). The machine contract is one command away:
`ladder prompt "<requirement>"`.
