# Backends: the plugin contract

A backend renders the **neutral statement AST** (never raw IR elements —
semantics are locked in lowering before a backend ever runs) into one
vendor's artifacts. A new vendor is a single self-contained module; the
five in-tree backends are each a few hundred lines.

## The contract

```python
from ladder.backends.base import Backend, register

@register
class AcmeBackend(Backend):
    name = "acme"                      # registry key and target name
    description = "Acme PLC Studio 9"  # shown by `ladder targets`
    target = "Acme Studio 9"

    def emit(self, project, lowered, outdir, iomap=None) -> list[Path]:
        ...
```

- `lowered` is `{program_name: LoweredProgram}` — statements
  (`SAssign/SIf/SCase/STimerCall/SComment/SRaw`) plus synthesized
  variables (timer instances, edge memories). Render these; never
  reinterpret IR elements.
- Reuse the ST dialect machinery (`backends/dialects.py`) for text
  targets, and the rung model (`backends/rungs.py`) for graphic ones —
  `to_rungs` converts the V11-checked subset to coils/moves/timer rungs.
- `iomap` hands you your own section of the IO map (`iomap.section(name)`);
  ignore other vendors' syntax entirely.
- `self.version` carries the `name@version` request (`ladder build -t
  acme@9`); key version quirks on it rather than forking the backend.
- `self.hints(project)` returns your `vendor: acme: {...}` block — hints
  are never required; the IR must stand alone.
- Raise `BackendError` with an actionable message for anything your
  target cannot express; never emit silently-wrong artifacts.

## In-tree vs plugin

In-tree backends register via the `@register` decorator and an import in
`backends/__init__.py`. **Third-party backends ship as their own package**
and register through the `ladder.backends` entry-point group:

```toml
# pyproject.toml of ladder-acme
[project.entry-points."ladder.backends"]
acme = "ladder_acme:AcmeBackend"
```

`pip install ladder-acme` and `ladder targets` lists it; a plugin that
fails to import is reported and skipped, never fatal.

## What earns a merge (or a conformance claim)

1. **Clean-room formats only**: emit from public documentation, never
   from decompiled vendor output. No vendor binaries in any repo.
2. Tests that pin the emitted artifact shape (see `tests/test_build.py`
   and friends), and — where an open toolchain exists — a CI check that
   *compiles or schema-validates* the output (matiec for IEC text, the
   tc6 XSD for PLCopen XML).
3. Every example in `examples/` must emit without `BackendError`, or the
   backend must document which elements it rejects and why.
4. Determinism: identical input → byte-identical output (no timestamps
   beyond the designated header fields, no iteration-order surprises).
