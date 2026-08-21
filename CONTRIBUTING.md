# Contributing to LADDER

Thanks for your interest! LADDER is vendor-agnostic PLC program generation
run as an LLM-driven authoring loop under human oversight: an assistant
(any model) drafts a declarative IR, a deterministic LLM-free core
validates, simulates, proves, and builds it, and a human reviews and
signs off (humans can also author directly — same gates). You can contribute meaningfully **without owning any
vendor software** — the core and its tests are pure Python, and CI verifies
generated IEC 61131-3 ST with the open matiec compiler.

## Dev setup

```bash
python -m venv .venv
.venv/bin/pip install -e .[dev]        # Windows: .venv\Scripts\pip
pytest                                  # must stay green
ladder build examples/vacuum_interlock.yaml -t all -o out
ladder verify examples/vacuum_interlock.yaml -t iec   # if matiec installed
```

## Hard rules

1. **Never commit vendor binaries or proprietary files** — no
   `Siemens.Engineering.dll`, no Logix SDK bits, no vendor project files.
   Engines load vendor APIs from the *user's* licensed installation.
2. **Vendor knowledge lives in `src/ladder/backends/` only.** The IR and
   lowering stay vendor-neutral; if two vendors would disagree about what an
   element means, fix the lowering (`src/ladder/ir/lower.py`), never a backend.
3. **Fail-safe conventions**: inputs named `*_ok` are TRUE when healthy;
   interlock outputs are permits that trip immediately and re-arm only on a
   manual reset while healthy. Don't contribute patterns that invert this.
4. Emitted PowerShell must be **ASCII-only** (Windows PowerShell 5.1 reads
   BOM-less files as ANSI).
5. Generated logic is not certified safety logic — keep the safety
   disclaimer intact in READMEs and generated headers.

## Good first contributions

- **A new vendor backend**: a self-contained module implementing
  `Backend.emit()` over the documented statement AST
  (see `src/ladder/backends/beckhoff.py` for the smallest example, ~120 lines).
- **A library pattern**: a function returning structured IR elements
  (`src/ladder/patterns/library.py`) with simulation tests
  (`tests/test_patterns.py` shows the shape).
- **Adopters**: lift another vendor's export format into IR
  (`src/ladder/adopt/`).

## Changing the IR

The IR is a contract (LLMs generate against its JSON Schema), so changes to
`src/ladder/ir/model.py` need: a short written proposal in the PR
description (what, why, migration), schema-level and semantic validation,
lowering + all-backend support or an explicit per-backend `BackendError`,
and tests including a simulation scenario where behavior is involved.

## Tests

Every change needs tests. Scenario tests via `ladder.sim.Simulator` are the
preferred way to pin element semantics — they verify what the logic *does*,
scan by scan, with no vendor tool.
