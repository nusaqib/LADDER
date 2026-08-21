---
name: lad-programming
description: Author and review ladder logic (LAD/LD/RLL) - rung idioms, latch discipline, edge detection, branch structure, per-vendor rendering, F-LAD constraints. Use when logic must be delivered or reviewed as ladder.
---

# Ladder (LAD/LD/RLL): the language plant electricians review

Choose `language: ladder` when the people signing off think in rungs.
It is a *presentation* choice: in LADDER the semantics come from the
element (interlock, alarm...), lowering is language-neutral, and the
rung form is generated - Rockwell RLL text, PLCopen LD bodies, and the
`ladder render` report's ASCII art all from the same statements.

## Rung idioms (the vocabulary)

- **Permissive chain**: series NO contacts -> coil. Read as "all of
  these must be true". 1=OK senses make the healthy plant a closed row.
- **Seal-in (motor start)**:
  `[permit]--[stop_ok]--+--[start_pb]--+--(run)` with `[run]` as the
  parallel branch. Stop or permit loss opens the row; the branch holds
  it in.
- **Latch pairs**: `(S x)` on the set condition, `(R x)` on the reset
  condition, **reset rung last** so reset dominates within the scan -
  the safe direction for trips and faults. Never mix a latched coil
  with an OTE of the same tag.
- **Edge (one-shot)**: prefer an explicit previous-value bit
  (`[sig]--[/sig_prev]` then `[sig]--(sig_prev)`) over vendor one-shot
  contacts - it renders identically everywhere and the model checker
  sees it. This is exactly what LADDER lowers edges to.
- **Timers in-rung**: enable contacts -> timer box; consume `.Q` (or
  DN) on a separate rung. Don't bury a timer inside a branch.

## Discipline

1. One decision per rung. A rung needing a paragraph to explain is two
   rungs.
2. Branches are OR - keep them shallow (2-3 wide); deep nesting means
   the condition wants a named intermediate bit on its own rung.
3. NC contact `[/x]` means "when x is false" - with 1=OK senses, a NC
   contact on an `_ok` tag reads "when unhealthy": correct for alarm
   conditions, suspicious in a permissive chain (double negation -
   rewrite).
4. Rung comments carry the *why* ("manual reset after trip per spec
   §4.2"), not a narration of the contacts.
5. Order-safety: flattening IF-shaped logic to rungs re-evaluates the
   condition per action rung; if a body action writes what the
   condition reads, semantics change. LADDER's rung converter rejects
   that case (RungError) - if a vendor tool tempts you into it by hand,
   don't.

## Vendor rendering notes

- **Rockwell RLL**: text grammar `XIC/XIO` contacts, `[ , ]` branches,
  `OTE/OTL/OTU` coils, `TON(timer,?,?)` with PRE in ms on the TIMER
  tag; rungs end `;`. See `docs/reference/vendors/rockwell-l5x.md`.
- **PLCopen LD**: positioned elements wired by refLocalId; LADDER emits
  tc6-XSD-valid bodies - the exchange form for CODESYS/Beckhoff.
- **Siemens F-LAD**: the safety compiler accepts LAD/FBD only (no
  F-SCL). Generated F-LAD goes in as SimaticML FlgNet: every pin wired
  or explicitly OpenCon, one power rail per network, certified
  instructions (ESTOP1, SFDOOR, EV1oo2DI) called with their exact
  pin sets and instance DBs. See
  `docs/reference/vendors/siemens-simatic-ml.md`.

## Review shortcuts

`ladder render .` draws every program as rung art next to its
scenarios - review that, not the XML. V11 tells you at validate time if
an element can't be expressed as rungs; believe it and either change
the program's language or restructure the logic.
