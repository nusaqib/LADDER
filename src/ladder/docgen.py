"""Documentation package generator: IR -> a complete controls doc set.

`ladder docs <project-dir | ir-file>` renders the documentation package a
controls project is normally required to deliver, derived from the same
single source of truth as the code:

    docs/01-requirements.md            normative SHALL statements, one per element
    docs/02-software-specification.md  architecture, specified behavior, data dictionary
    docs/03-conventions.md             naming, fail-safe sense, change process
    docs/04-developer-manual.md        regenerate / build / verify / extend
    docs/05-operator-manual.md         what operators see and what their actions do
    docs/06-verification-report.md     scenario inventory, formal theorems, lint state

Because every document is generated from the IR (plus the manifest,
scenarios, and IO map when present), the package can never drift from the
program - regenerating is part of `the` change process, and a reviewer
diffs documents like code. Prose quality goal: what a senior automation
engineer would hand to a review board, not a data dump.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from ladder.ir.model import (
    AlarmEl,
    AlarmGroupEl,
    AssignEl,
    Cond,
    CondAll,
    CondAny,
    CondNot,
    DualChannelEl,
    InterlockEl,
    Program,
    Project,
    ScaleEl,
    SearchChainEl,
    StateMachineEl,
    TimerEl,
    RawStEl,
)

# ------------------------------------------------------------- helpers


def _cond_text(c: Cond) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, CondAll):
        return "(" + " AND ".join(_cond_text(x) for x in c.all) + ")"
    if isinstance(c, CondAny):
        return "(" + " OR ".join(_cond_text(x) for x in c.any) + ")"
    if isinstance(c, CondNot):
        return f"NOT {_cond_text(c.not_)}"
    return str(c)


def _el_id(el) -> str:
    return getattr(el, "id", None) or el.element


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


@dataclass
class DocInputs:
    project: Project
    manifest: Optional[object] = None      # ladder.scaffold.Manifest
    scenarios: Optional[dict] = None       # parsed scenarios yaml
    iomap: Optional[object] = None         # ladder.iomap.IoMap
    design_map: Optional[str] = None       # path text reference, if present


# --------------------------------------------------------- requirements


def _requirement(prog: Program, el) -> tuple[str, str]:
    """(requirement id, normative statement)."""
    rid = f"REQ-{prog.name}-{_el_id(el)}"
    d = f" ({el.description})" if getattr(el, "description", None) else ""
    if isinstance(el, InterlockEl):
        r = (f"The permit `{el.output}` SHALL be TRUE only while "
             f"{_cond_text(el.permissives)} holds. On loss of any permissive "
             f"the permit SHALL drop within the same program cycle"
             + (f", SHALL remain down after the permissives return, and SHALL "
                f"re-arm only on a rising edge of `{el.reset.signal}` while "
                f"all permissives are healthy" if el.latching and el.reset
                else " and SHALL follow the permissives directly (non-latching)")
             + ".")
    elif isinstance(el, AlarmEl):
        r = (f"The alarm `{el.output}` SHALL become active when "
             f"{_cond_text(el.condition)} persists"
             + (f" for {el.on_delay}" if el.on_delay else "")
             + (f"; it SHALL latch and clear only on a rising edge of "
                f"`{el.ack}` after the condition has cleared" if el.latching
                else "; it SHALL follow the (delayed) condition")
             + f". Severity: {el.severity}.")
    elif isinstance(el, AlarmGroupEl):
        legend = ", ".join(f"{i}={m.name}" for i, m in enumerate(el.alarms, 1))
        r = (f"The annunciator group SHALL latch each member on the rising "
             f"edge of its (debounced) condition; `{el.active}` SHALL be TRUE "
             f"while any member is latched"
             + (f"; `{el.unacked}` SHALL sound for unacknowledged members and "
                f"SHALL re-sound on every new member" if el.unacked else "")
             + f"; acknowledge is `{el.ack}` and SHALL clear only members "
             f"whose condition is gone"
             + (f"; `{el.first_out}` SHALL record the first member to trip "
                f"(0=none, {legend}) and reset when the group clears"
                if el.first_out else "") + ".")
    elif isinstance(el, DualChannelEl):
        r = (f"`{el.output}` SHALL be TRUE only while both `{el.channel_a}` "
             f"and `{el.channel_b}` are TRUE (1oo2)"
             + (f". Channels disagreeing for longer than {el.discrepancy_time} "
                f"SHALL latch a discrepancy fault forcing the output FALSE "
                f"until a rising edge of `{el.ack}` with the channels in "
                f"agreement" if el.discrepancy_time else "") + ".")
    elif isinstance(el, SearchChainEl):
        walk = " -> ".join(s.name for s in el.stations)
        r = (f"The search chain SHALL complete only by operating the station "
             f"keys in walk order ({walk}), each on a rising edge, while "
             f"{_cond_text(el.precondition)} holds. Loss of the precondition "
             f"or of any predecessor SHALL clear all downstream stations and "
             f"`{el.complete}` within one program cycle. No acknowledge or "
             f"reset signal SHALL restore a cleared search.")
    elif isinstance(el, TimerEl):
        r = (f"Timer {el.kind} with preset {el.preset} on "
             f"{_cond_text(el.input)}"
             + (f"; `{el.done}` SHALL follow the done bit" if el.done else "")
             + ".")
    elif isinstance(el, StateMachineEl):
        r = (f"The sequence SHALL start in state `{el.initial}` and follow "
             f"the transition table exactly (first matching transition "
             f"wins); `{el.state_tag}` SHALL always hold the current state "
             f"code.")
    elif isinstance(el, ScaleEl):
        r = (f"`{el.output}` SHALL be the linear scaling of `{el.input}` "
             f"from raw [{el.raw_min}..{el.raw_max}] to engineering "
             f"[{el.eu_min}..{el.eu_max}]"
             + (", clamped to the engineering range" if el.clamp else "") + ".")
    elif isinstance(el, AssignEl):
        r = f"`{el.target}` SHALL equal {_cond_text(el.value)} every cycle."
    elif isinstance(el, RawStEl):
        r = ("Raw structured-text element - behavior specified by its code "
             "body; OUTSIDE the checked subset (no lint/model coverage).")
    else:
        r = el.description or "(see software specification)"
    return rid, r + d


def doc_requirements(di: DocInputs) -> str:
    p = di.project
    out = [f"# {p.name} - Requirements", "",
           f"> Generated from the IR - the single source of truth. "
           f"Every requirement below is implemented by a named logic "
           f"element and verified per the verification report. "
           f"Regenerate with `ladder docs`; never edit by hand.", ""]
    if p.description:
        out += [f"**System purpose:** {p.description}", ""]
    out += ["## Global conventions (normative)", "",
            "- Fail-safe sense: every BOOL input SHALL read 1 = OK/healthy/"
            "closed; a de-energized input SHALL read as a fault.",
            "- Latching protective functions SHALL require a deliberate "
            "manual action to re-arm; no protective function SHALL re-arm "
            "on signal restoration alone.",
            "- Hardware addresses SHALL live in the IO map document, never "
            "in the logic.", ""]
    for prog in p.programs:
        out += [f"## {prog.name}", ""]
        if prog.description:
            out += [prog.description, ""]
        for el in prog.logic:
            rid, text = _requirement(prog, el)
            out += [f"**{rid}**  {text}", ""]
    return "\n".join(out) + "\n"


# ----------------------------------------------- software specification


_SEMANTICS = {
    "interlock": "Latching permissive: trips the scan a permissive drops; "
                 "re-arms only on a reset rising edge while healthy.",
    "alarm": "Optional on-delay debounce (TON); latching alarms clear on an "
             "ack rising edge only after the (delayed) condition is gone.",
    "alarm_group": "ISA-18.1-style annunciator: per-member latch, common "
                   "ack, horn re-sounds per new alarm, first-out capture.",
    "dual_channel": "1oo2 evaluation with optional discrepancy window; a "
                    "latched discrepancy forces the output FALSE until "
                    "acknowledged with channels in agreement.",
    "search_chain": "Stations latch on the rising edge of their key in walk "
                    "order while the precondition holds; a breach cascades "
                    "within one scan; nothing else clears a station.",
    "state_machine": "CASE on the state tag; per-state actions run every "
                     "scan, transitions evaluate in order (first match wins).",
    "timer": "IEC timer semantics (TON/TOF/TP).",
    "scale": "Linear raw-to-engineering conversion with optional clamping.",
    "assign": "Unconditional assignment, every scan.",
    "pattern": "Library pattern (expanded before validation).",
    "st": "Raw structured text - outside the checked subset.",
}


def doc_software_spec(di: DocInputs) -> str:
    p = di.project
    out = [f"# {p.name} - Software Specification", ""]
    out += ["## Architecture", "",
            "Programs execute in the order listed - the order is "
            "load-bearing (later programs read what earlier ones wrote "
            "this scan):", ""]
    rows = [[i + 1, pr.name, pr.execution + (f" ({pr.interval})" if pr.interval else ""),
             pr.language, len(pr.logic), pr.description or ""]
            for i, pr in enumerate(p.programs)]
    out += _table(["#", "program", "execution", "language", "elements",
                   "purpose"], rows) + [""]
    out += ["Element semantics are locked once in the LADDER lowering and "
            "are identical on every target:", ""]
    used = {el.element for pr in p.programs for el in pr.logic}
    out += _table(["element", "locked semantics"],
                  [[e, _SEMANTICS.get(e, "")] for e in sorted(used)]) + [""]

    if p.types:
        out += ["## Data types", ""]
        for t in p.types:
            out += [f"### {t.name}" + (f" - {t.comment}" if t.comment else ""), ""]
            out += _table(["member", "type", "comment"],
                          [[m.name, m.type, m.comment or ""] for m in t.members])
            out += [""]

    out += ["## Tag dictionary", ""]
    rows = [[t.name, t.type + (f"[{t.array}]" if t.array else ""),
             t.direction, t.comment or ""] for t in p.tags]
    out += _table(["tag", "type", "direction", "meaning"], rows) + [""]

    if di.iomap is not None:
        out += ["## Hardware bindings (from the IO map document)", ""]
        for backend in ("siemens", "rockwell", "beckhoff", "plcopen", "iec"):
            section = di.iomap.section(backend)
            if not section:
                continue
            out += [f"### {backend}", ""]
            out += _table(["tag", "binding"],
                          [[n, b.address or b.alias] for n, b in
                           sorted(section.items())]) + [""]

    out += ["## Specified behavior (per element)", ""]
    for prog in p.programs:
        out += [f"### {prog.name}", ""]
        for el in prog.logic:
            rid, text = _requirement(prog, el)
            out += [f"- **{_el_id(el)}** ({el.element}): {text} "
                    f"[traces to {rid}]"]
        out += [""]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------- conventions


def doc_conventions(di: DocInputs) -> str:
    p = di.project
    langs = {pr.name: pr.language for pr in p.programs}
    out = [f"# {p.name} - Conventions", "",
           "## Signals",
           "",
           "- **Fail-safe sense**: BOOL inputs read `1 = OK / healthy / "
           "closed / present`; momentary action inputs (pushbuttons, keys) "
           "rest at 0 and are read on their rising edge.",
           "- **Permits, not inhibits**: interlock outputs are TRUE = "
           "permitted, so a dead CPU, a broken wire, or a dropped rung all "
           "fail toward the safe state.",
           "",
           "## Naming",
           "",
           "- Identifiers: letter first, single underscores, no trailing "
           "underscore, max 40 characters (the strictest target's limit).",
           "- Element ids carry their class: `IL_*` interlocks, `ALM_*` "
           "alarms, `GRP_*` annunciator groups, `DC_*` dual-channel "
           "evaluations, `SRCH_*` search chains, `SEQ_*` sequences.",
           "- `OK` means the result of the final protective evaluation and "
           "nothing more; `Eval_OK` means a channel evaluation only.",
           "",
           "## Languages",
           ""]
    out += _table(["program", "language", "why"],
                  [[n, l, "reviewed as rungs by plant electricians"
                    if l == "ladder" else
                    ("sequence chart" if l == "sfc" else "structured text")]
                   for n, l in langs.items()]) + [""]
    out += ["## Change process",
            "",
            "1. The design map / design data changes first - never the "
            "generated artifacts.",
            "2. The IR mirrors the design; scenarios change in the same "
            "commit as the behavior they pin.",
            "3. `ladder check` gates every change: validation (V01-V11), "
            "lint (W01-W06 are design smells - fix the design), scenario "
            "simulation, artifact builds.",
            "4. Everything under `out/` (including vendor IDE projects) is "
            "a disposable build product: regenerate, never hand-edit.",
            "5. This documentation package is regenerated with `ladder "
            "docs` in the same commit as any logic change."]
    return "\n".join(out) + "\n"


# ------------------------------------------------------ developer manual


def doc_developer_manual(di: DocInputs) -> str:
    p = di.project
    m = di.manifest
    ir_ref = m.ir if m else "<ir file>"
    out = [f"# {p.name} - Developer Manual", "",
           "## Toolchain",
           "",
           "```",
           "pip install git+https://github.com/nusaqib/LADDER.git",
           "ladder check .          # the full acceptance gate",
           f"ladder docs .           # regenerate this documentation package",
           f"ladder model {ir_ref} -o out   # SMV + auto safety theorems (nuXmv)",
           "```",
           "",
           "## Build artifacts",
           "",
           "| target | artifact | proves |",
           "|---|---|---|",
           "| siemens | SCL/UDT/DB sources + build.ps1; openable TIA "
           "project under `out/siemens/project/` | live TIA compile |",
           "| rockwell | controller-scoped L5X (RLL rungs for ladder "
           "programs) | Studio 5000 import/verify |",
           "| plcopen | tc6 XML incl. LD/FBD/SFC/IL bodies | validates "
           "against the official tc6 XSD |",
           "| iec | strict IEC 61131-3 ST/IL/SFC text | compiles with "
           "matiec (vendor-free CI) |",
           "",
           "## Validation issue codes",
           "",
           "V01 identifier - V02 duplicate - V03 unresolved read - V04 bad "
           "write target - V05 missing reset/ack - V06 wrong type - V07 "
           "state machine - V08 periodic interval - V09 unexpanded pattern "
           "- V10 UDT/array misuse - V11 language cannot express. "
           "W01-W06 are non-fatal but are design smells: unwritten outputs, "
           "multi-writer hazards, unread inputs, trap/unreachable states.",
           "",
           "## Extending",
           "",
           "- New behavior: prefer a library pattern or structured element; "
           "raw `st` is the last resort and suppresses lint/model coverage.",
           "- New vendor: a backend is a self-contained module rendering "
           "the neutral statement AST (see the LADDER repo's AGENTS.md).",
           ""]
    return "\n".join(out) + "\n"


# ------------------------------------------------------- operator manual


def doc_operator_manual(di: DocInputs) -> str:
    p = di.project
    out = [f"# {p.name} - Operator Manual", "",
           "What you see, what it means, and exactly what your controls do. "
           "Nothing in this system re-arms by itself: restoring a signal "
           "never restores a permit or a completed search.", ""]
    for prog in p.programs:
        section: list[str] = []
        for el in prog.logic:
            if isinstance(el, InterlockEl) and el.latching and el.reset:
                section += [
                    f"### Permit: {_el_id(el)}",
                    "",
                    (el.description or "") and f"{el.description}", "",
                    f"- **Healthy**: `{el.output}` is on while "
                    f"{_cond_text(el.permissives)}.",
                    f"- **Trip**: any permissive loss drops the permit "
                    f"immediately and it STAYS down.",
                    f"- **To restore**: clear the cause, then press "
                    f"`{el.reset.signal}` (a new press is required - "
                    f"holding it from before the trip does nothing).", ""]
            elif isinstance(el, AlarmGroupEl):
                legend = ", ".join(f"**{i}** = {m.name}"
                                   + (f" ({m.description})" if m.description else "")
                                   for i, m in enumerate(el.alarms, 1))
                section += [
                    f"### Annunciator: {_el_id(el)}", "",
                    f"- Lamp `{el.active}`: at least one alarm is standing.",
                    *([f"- Horn `{el.unacked}`: a NEW alarm arrived; "
                       f"`{el.ack}` silences it. The horn re-sounds for "
                       f"every new alarm even while others stand."]
                      if el.unacked else []),
                    *([f"- First-out `{el.first_out}` shows WHICH window "
                       f"tripped first: {legend}. It resets when the panel "
                       f"clears."] if el.first_out else []),
                    f"- Acknowledging clears only windows whose cause is "
                    f"gone; a standing cause keeps its window lit.", ""]
            elif isinstance(el, AlarmEl) and el.latching:
                section += [
                    f"### Alarm: {_el_id(el)} ({el.severity})", "",
                    (el.description or ""), "",
                    f"- Trips when {_cond_text(el.condition)}"
                    + (f" persists for {el.on_delay}" if el.on_delay else "") + ".",
                    f"- `{el.ack}` clears it ONLY after the cause is gone; "
                    f"acknowledging a standing alarm leaves it lit.", ""]
            elif isinstance(el, SearchChainEl):
                walk = " -> ".join(s.name for s in el.stations)
                section += [
                    f"### Area search: {_el_id(el)}", "",
                    f"- Walk order: **{walk}**. Turn each station key as "
                    f"you reach it; keys already held do not count - the "
                    f"turn itself is what registers.",
                    f"- The chain arms only while "
                    f"{_cond_text(el.precondition)}; any door opening or "
                    f"trip clears the ENTIRE search instantly.",
                    f"- A cleared search means a full re-walk. No reset or "
                    f"acknowledge can restore it - by design.", ""]
            elif isinstance(el, DualChannelEl) and el.discrepancy_time:
                section += [
                    f"### Channel fault: {_el_id(el)}", "",
                    f"- If the two channels of this device disagree longer "
                    f"than {el.discrepancy_time}, it locks out as a fault.",
                    f"- To clear: both channels must read the same again, "
                    f"then press `{el.ack}`. Expect a maintenance check - "
                    f"a discrepancy usually means a wiring or switch "
                    f"problem, not an operational event.", ""]
        if section:
            out += [f"## {prog.name}", ""] + section
    return "\n".join(x for x in out if x is not None) + "\n"


# --------------------------------------------------- verification report


def doc_verification(di: DocInputs) -> str:
    p = di.project
    out = [f"# {p.name} - Verification Report", "",
           "Four independent layers, weakest to strongest. Regenerate this "
           "report (and re-run the layers) after every change.", ""]
    out += ["## 1. Static validation and lint", "",
            "`ladder validate` / `ladder check`: schema, semantic rules "
            "V01-V11, design-smell lint W01-W06.", ""]
    out += ["## 2. Scenario simulation (scan-accurate)", ""]
    if di.scenarios:
        rows = [[s["name"], len(s.get("steps", [])),
                 s.get("description", "")] for s in di.scenarios.get("scenarios", [])]
        out += _table(["scenario", "steps", "notes"], rows)
        out += ["", f"{len(rows)} scenarios pin the acceptance behavior; "
                "`ladder check` fails if any regresses.", ""]
    else:
        out += ["No scenario suite declared - **add one**; scenarios are "
                "the definition of done.", ""]
    out += ["## 3. Formal verification (nuXmv)", "",
            "`ladder model` emits one SMV model per checkable program with "
            "auto-generated theorems; timers are soundly over-approximated "
            "so a proved property holds for EVERY preset and scan rate:", ""]
    theorems: list[list[str]] = []
    for prog in p.programs:
        for el in prog.logic:
            if isinstance(el, InterlockEl):
                theorems.append([_el_id(el), f"{el.output} -> permissives",
                                 "permit never TRUE with a permissive down"])
            elif isinstance(el, DualChannelEl):
                theorems.append([_el_id(el), f"{el.output} -> chA AND chB",
                                 "never evaluates OK with a channel down"])
            elif isinstance(el, SearchChainEl):
                theorems.append([_el_id(el), f"{el.complete} -> precondition",
                                 "search never complete while inputs down"])
                theorems.append([_el_id(el), "station_i -> station_i-1",
                                 f"walk-order monotonicity "
                                 f"({len(el.stations) - 1} pairs)"])
            elif isinstance(el, AlarmGroupEl):
                if el.unacked:
                    theorems.append([_el_id(el), f"{el.unacked} -> {el.active}",
                                     "horn never sounds without the lamp"])
                if el.first_out:
                    theorems.append([_el_id(el),
                                     f"{el.active} <-> {el.first_out} != 0",
                                     "first-out consistency"])
    if theorems:
        out += _table(["element", "theorem", "meaning"], theorems) + [""]
    else:
        out += ["No auto-theorem-bearing elements in this project.", ""]
    out += ["## 4. Vendor toolchain", "",
            "- matiec compiles the emitted IEC text (CI, vendor-free).",
            "- The emitted PLCopen XML validates against the official "
            "tc6_0201 XSD (CI).",
            "- The Siemens build compiles the generated project live "
            "(0 errors required).", "",
            "## Statement of limits", "",
            "Simulation and proofs cover the modeled logic - not sensors, "
            "wiring, the F-runtime, or the operator. Nothing in this "
            "package is a functional-safety certification.", ""]
    return "\n".join(out) + "\n"


# ----------------------------------------------------------------- main


DOCS = {
    "01-requirements.md": doc_requirements,
    "02-software-specification.md": doc_software_spec,
    "03-conventions.md": doc_conventions,
    "04-developer-manual.md": doc_developer_manual,
    "05-operator-manual.md": doc_operator_manual,
    "06-verification-report.md": doc_verification,
}


def generate_docs(di: DocInputs, outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    written = []
    index = [f"# {di.project.name} - Documentation package", "",
             "Generated by `ladder docs` from the IR; regenerate with every "
             "change - never edit these files by hand.", ""]
    for name, fn in DOCS.items():
        path = outdir / name
        path.write_text(fn(di), encoding="utf-8")
        written.append(path)
        title = name.split("-", 1)[1].removesuffix(".md").replace("-", " ")
        index.append(f"- [{title}]({name})")
    (outdir / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    written.append(outdir / "README.md")
    return written


def load_doc_inputs(path: str | Path) -> DocInputs:
    """Accept a project dir (with ladder.yaml) or a bare IR file/dir."""
    from ladder.ir.loader import load_project

    p = Path(path)
    manifest = None
    scenarios = None
    iomap = None
    if (p / "ladder.yaml").exists():
        from ladder.scaffold import load_manifest

        manifest, root = load_manifest(p)
        project = load_project(root / manifest.ir)
        if manifest.scenarios:
            scenarios = yaml.safe_load(
                (root / manifest.scenarios).read_text(encoding="utf-8"))
        if manifest.iomap:
            from ladder.iomap import load_iomap

            iomap = load_iomap(root / manifest.iomap)
    else:
        project = load_project(p)
    return DocInputs(project=project, manifest=manifest,
                     scenarios=scenarios, iomap=iomap)
