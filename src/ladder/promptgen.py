"""Model-agnostic prompt bundle for IR generation (M5 seed).

`ladder prompt` packages everything an LLM needs to generate valid LADDER
IR - the element vocabulary, the pattern library, the fail-safe rules, and
the JSON Schema contract - into one self-contained markdown document you
can paste into ANY model (hosted chat, API, or local). The feedback loop
is `ladder validate`: its issue codes are written to be machine-actionable,
so generation loops iterate against the validator, not a vendor tool.

Nothing here is specific to one LLM provider, by design.
"""

from __future__ import annotations

import inspect
import json
import textwrap

from ladder.ir.loader import json_schema
from ladder.patterns import PATTERNS

_GUIDE = """\
You are writing a PLC program as **LADDER IR**: a vendor-neutral, declarative
YAML document. It will be validated, deterministically lowered, and rendered
into Siemens TIA Portal, Rockwell Studio 5000, PLCopen XML, Beckhoff TwinCAT,
and plain IEC 61131-3 artifacts. You never write vendor syntax.

## Rules

1. Output ONLY one YAML document conforming to the JSON Schema below - no
   prose, no code fences around vendor code, no explanations.
2. Fail-safe sense everywhere: at the PLC input `1 = OK / healthy / closed`,
   `0 = fault`. Interlock outputs are permits (`TRUE = permitted`).
3. Prefer, in order: a library **pattern**, then structured elements
   (interlock / alarm / timer / state_machine / assign), and only as a last
   resort the raw `st` escape hatch.
4. Prefer structured condition trees (`all:` / `any:` / `not:`) over long
   expression strings; expressions use neutral ST syntax
   (`AND OR XOR NOT`, `= <> < <= > >=`, `T#5s` time literals).
5. Declare every tag you reference, with direction (input/output/memory)
   and a comment. Identifiers: start with a letter, single underscores,
   max 40 chars, no IEC reserved words. Structured data: declare UDTs under
   `types:` and use `array: N` on tags; reference members and elements as
   `pump.run_cmd` / `temps[3]` (literal indices). UDT/array tags must be
   direction `memory` - IO stays scalar.
6. Latching interlocks require a `reset`; latching alarms require an `ack`.
7. Give every stateful element a unique, meaningful `id` (e.g. `IL_shutter`,
   `ALM_vacuum`), and every element a `description`.
8. Optionally set a program's `language` (st | il | ladder | fbd | sfc) as a
   rendering preference - e.g. `ladder` for simple boolean/interlock
   programs, `sfc` for a program that is exactly one state_machine. When
   unsure, omit it (defaults to st). V11 rejects logic the language cannot
   express.

## Element vocabulary

- `interlock` - fail-safe permissive; trips the scan a permissive drops,
  re-arms only on manual reset (rising edge) while healthy.
- `alarm` - condition TRUE = active; optional `on_delay` debounce (TON),
  optional latching with `ack`; severity info/warning/alarm/critical.
- `alarm_group` - annunciator: N latched alarms with a common `ack`, group
  `active` lamp, optional `unacked` horn (re-sounds on each new alarm) and
  `first_out` INT capture (1-based member index of the first trip; 0=none).
  Prefer this over N separate alarms whenever alarms share an ack/horn.
- `dual_channel` - 1oo2 two-channel evaluation (redundant safety inputs):
  output TRUE only while both channels are OK; optional `discrepancy_time`
  latches a `fault` needing `ack` (channels must agree again). Models the
  logic of certified evaluations; NOT itself certified safety.
- `search_chain` - sequential area-search chain (PPS practice): stations
  latch on the rising edge of their key in walk order while `precondition`
  holds; any breach cascades and clears `complete` within one scan; an
  ack/reset must never be wired to it.
- `timer` - standalone TON/TOF/TP with `preset`, optional `done`/`elapsed`.
- `state_machine` - named states with per-scan `do` assigns and ordered
  `transitions` (first match wins); lowered to a CASE statement.
- `scale` - linear analog scaling raw counts -> engineering units (REAL
  output), with raw/EU ranges and clamping.
- `assign` - unconditional `target := value` every scan.
- `pattern` - invoke a library pattern by `ref` with `params` (see below).
- `st` - raw neutral structured text; escape hatch only.

## Validation feedback

Validate with `ladder validate <file>`. Issue codes: V01 identifier not
portable, V02 duplicate/shadowed name, V03 unresolved reference, V04 write
to unknown target or an input, V05 missing reset/ack on latching element,
V06 wrong type (BOOL outputs, INT state tags), V07 state machine
inconsistency, V08 periodic program without interval, V09 unexpanded
pattern. Fix and re-emit until it passes.
"""


def _pattern_docs() -> str:
    lines = ["## Available patterns", ""]
    for name, fn in sorted(PATTERNS.items()):
        sig = str(inspect.signature(fn)).replace("el_id: str, *, ", "")
        doc = textwrap.dedent(fn.__doc__ or "").strip().splitlines()[0]
        lines.append(f"- **{name}**`({sig.strip('()')})` - {doc}")
    lines.append("")
    lines.append("Pattern params reference declared tag names; patterns never "
                 "create global tags, so declare the tags they use.")
    return "\n".join(lines)


def build_prompt(requirement: str) -> str:
    schema = json.dumps(json_schema(), separators=(",", ":"))
    return "\n".join([
        _GUIDE,
        _pattern_docs(),
        "",
        "## Output contract (JSON Schema)",
        "",
        "```json",
        schema,
        "```",
        "",
        "## Requirement",
        "",
        requirement.strip(),
        "",
        "Now emit the LADDER IR YAML document.",
    ])
