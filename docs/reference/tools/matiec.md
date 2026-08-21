# matiec — the open IEC 61131-3 compiler (working notes)

> Source: https://github.com/beremiz/matiec (the Beremiz project's
> compiler, `iec2c`). LADDER's CI uses it as a vendor-free proof that
> emitted ST/IL/SFC is real IEC 61131-3, not "looks like it".

## Invocation

```bash
iec2c -f -l -p -I /path/to/matiec/lib -T outdir program.st
```

- Input must be a **complete configuration**: POUs alone don't compile —
  you need `CONFIGURATION`/`RESOURCE`/`TASK`/`PROGRAM ... WITH` at the
  bottom (LADDER's iec backend always emits one).
- Exit code 0 + generated C files = accepted. The C output is only a
  byproduct for us; acceptance is the point.
- The standard library (TON, CTU, R_TRIG...) comes from `-I .../lib` —
  forget it and every timer reference is an undefined POU.

## Grammar strictness worth knowing (found the hard way)

1. **IL formal CAL syntax**: the parenthesized parameter list must start
   with a **newline after `(`** and take **one parameter per line**:

   ```
   CAL t1 (
       IN := start,
       PT := T#5s
   )
   ```

   A single-line `CAL t1(IN := start, PT := T#5s)` is rejected — most
   IL references show it single-line; matiec's grammar (and the
   standard's EBNF, read carefully) wants the line breaks.
2. IL operators are line-oriented; labels end with `:`; the accumulator
   ("current result") types must chain — no implicit conversions.
3. ST: no vendor extensions — no `REGION`, no Siemens `#var` prefixes,
   no `AT %` inside FB bodies (only in VAR blocks); `_` in numeric
   literals is fine; direct bit access `x.3` on words is not portable.
4. SFC in textual form: `INITIAL_STEP s0: END_STEP`,
   `TRANSITION FROM s0 TO s1 := cond; END_TRANSITION`, actions attach
   with qualifiers (`ACTION a0: ... END_ACTION`, step body
   `s1: a0(N); END_STEP`). matiec accepts this inside a PROGRAM.
5. Reserved-word collisions: matiec reserves everything the standard
   does *including* the standard FB names — don't name a variable `TON`,
   `SR`, `IN`, `PT`, `Q`, `ET`.

## Using it in CI (LADDER's pattern)

Build once per CI run (autoreconf + make, it's small), then per project:

```bash
ladder build ir.yaml -t iec -o out
iec2c -f -l -p -I $MATIEC/lib -T /tmp/c out/iec/Project.st
```

Any grammar drift in the emitter fails the pipeline with matiec's
line-numbered error — far cheaper than discovering it in a vendor IDE.

## Limits

matiec proves *syntax + static semantics* (types, declarations, POU
wiring), not behavior — behavior is the simulator's and nuXmv's job.
It implements IEC 61131-3 ed. 2 with parts of ed. 3: no classes/
interfaces/namespaces, partial `VAR_CONFIG`; fine for LADDER's emitted
subset, which is deliberately edition-2-conservative.
