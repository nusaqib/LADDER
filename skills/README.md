# Skills — expert workflows for agents (and humans)

Tool-agnostic, principal-engineer-level playbooks. Each `SKILL.md` is
canonical here; `.claude/skills/` holds discovery stubs (kept in sync
by `tests/test_skills.py`). They compose with the authoring loop
(`docs/WORKFLOW.md`): the human owns ground truth and sign-off, the
assistant follows these, the machine gates everything.

## Workflow skills (the loop, end to end)

| skill | when |
|---|---|
| [design-intake](design-intake/SKILL.md) | prose requirement → filled Design Inputs Map |
| [design-documents](design-documents/SKILL.md) | maintaining the authored package: map, decisions, assumptions |
| [ir-authoring](ir-authoring/SKILL.md) | design map → validated IR + scenarios |
| [verification](verification/SKILL.md) | what each check proves — simulator, lint, matiec, nuXmv |
| [documentation](documentation/SKILL.md) | the generated package: requirements → operator manual |

## Vendor deployment

| skill | target |
|---|---|
| [siemens-deploy](siemens-deploy/SKILL.md) | TIA Portal (incl. the F-system path) |
| [rockwell-deploy](rockwell-deploy/SKILL.md) | Studio 5000 / L5X |
| [beckhoff-deploy](beckhoff-deploy/SKILL.md) | TwinCAT 3 |

## Engineering-domain skills

| skill | covers |
|---|---|
| [hardware-configuration](hardware-configuration/SKILL.md) | CPUs, stations, modules, PROFIsafe parameters as design data |
| [tags-and-io](tags-and-io/SKILL.md) | signal lists, BOOL senses, iomaps, per-vendor binding |
| [udt-design](udt-design/SKILL.md) | types/structs, vendor mapping, F-compliance |
| [block-architecture](block-architecture/SKILL.md) | OB/FB/DB · programs/routines · POUs, layering, scan order |
| [safety-matrix](safety-matrix/SKILL.md) | cause-and-effect (CEM) matrices → interlock elements |
| [hmi-design](hmi-design/SKILL.md) | screens, alarm presentation, write contracts, generation |

## Language skills

| skill | language |
|---|---|
| [lad-programming](lad-programming/SKILL.md) | ladder (LAD/LD/RLL), incl. F-LAD constraints |
| [fbd-programming](fbd-programming/SKILL.md) | function block diagram |
| [scl-programming](scl-programming/SKILL.md) | ST/SCL + the raw-`st` escape-hatch discipline |
| [stl-programming](stl-programming/SKILL.md) | STL/IL: reading legacy, migrating, strict-IL emission |
| [sfc-graph-programming](sfc-graph-programming/SKILL.md) | sequences: SFC, Siemens GRAPH, state machines |

Offline references these skills lean on: [docs/reference/](../docs/reference/README.md).
