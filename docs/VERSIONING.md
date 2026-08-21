# IR versioning and the road to 1.0

The IR is a contract three parties rely on: humans authoring designs,
models generating them, and backends rendering them. Contracts change by
process, not by drive-by edit.

## Semver on `ir_version`

- **Patch** (0.2.x): clarifications, new *optional* fields with defaults
  that preserve behavior, new validation that only rejects designs that
  were already wrong. Old documents load unchanged.
- **Minor** (0.x): new elements or fields; old documents still load and
  mean the same thing. Backends may reject new elements they cannot
  express (that is what `BackendError` and V11 are for).
- **Major**: anything that changes the meaning or validity of an existing
  document. Requires an RFC and a migration note; does not happen
  casually, and after 1.0 requires a deprecation cycle.

The loader accepts any document whose major.minor is ≤ the library's and
whose constructs validate; `ladder schema` always exports the current
contract.

## The RFC process (lightweight on purpose)

A change to the IR is proposed as an issue titled `RFC: <element/field>`
containing: the design problem (with a real plant example), the proposed
YAML, the **locked semantics** in prose (what lowering will guarantee on
every vendor), what each backend renders, what the simulator and model
checker do with it, and the validation rules. New elements land with:
model + validation + lowering + simulator behavior + at least one
auto-theorem or an explicit statement why none applies + docs + tests —
the same bar `alarm_group`, `dual_channel`, and `search_chain` met.

## What 1.0 will mean

- The element set and field names in [IR-SPEC](IR-SPEC.md) are frozen
  under the rules above.
- A **conformance suite** (the `examples/` + scenario corpus, run
  against a backend) lets third-party backends claim support levels:
  *core* (assign/interlock/alarm/timer), *structured* (+state machines,
  UDTs, scale), *safety* (+dual_channel, search_chain, alarm_group),
  *languages* (per-program language preferences honored or cleanly
  refused).
- Remaining before declaring it: field-name review against real adopted
  programs from at least two facilities, and the outstanding element
  RFCs (PID, motion axis) either landed or explicitly deferred.

## Tool versions are a different axis

`ir_version` versions the *design contract*. Vendor tool generations are
selected per build with `name@version` targets (`siemens@21`) and never
leak into the IR — a design does not change because a vendor shipped a
new IDE.
