"""`ladder render` - a human-readable HTML report of a project.

The review artifact for people who don't read YAML: every program shown
as ladder rungs (ASCII art, the lingua franca of plant floors) or ST
pseudocode where logic isn't rung-shaped, beside the element summary,
the acceptance scenarios, and the safety theorems. Self-contained HTML,
no scripts, printable.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path

from ladder.backends.rungs import (
    CoilAction,
    MoveAction,
    Rung,
    RungError,
    TimerAction,
    bool_roots_for,
    push_not_down,
    to_rungs,
)
from ladder.ir import expr as X
from ladder.ir.lower import LoweredProgram, lower_project
from ladder.ir.model import Project

# ------------------------------------------------------- expression text


def expr_text(e: X.Expr) -> str:
    if isinstance(e, X.Lit):
        if e.kind == "bool":
            return "TRUE" if e.value else "FALSE"
        return str(e.value)
    if isinstance(e, X.Ref):
        return ".".join(e.path)
    if isinstance(e, X.Un):
        return f"NOT {expr_text(e.x)}" if e.op == "NOT" else f"-{expr_text(e.x)}"
    if isinstance(e, X.Bin):
        return f"{expr_text(e.left)} {e.op} {expr_text(e.right)}"
    return "?"


# --------------------------------------------------- ASCII ladder layout
#
# A block is a rectangle of equal-width lines whose row 0 is the
# conductive row. Series lays blocks left to right on row 0; parallel
# stacks branches between '+' junctions with '|' rails.


@dataclass
class _Block:
    lines: list[str]

    @property
    def width(self) -> int:
        return len(self.lines[0])

    @property
    def height(self) -> int:
        return len(self.lines)


def _leaf(text: str) -> _Block:
    return _Block([f"[ {text} ]"])


def _series(blocks: list[_Block]) -> _Block:
    if len(blocks) == 1:
        return blocks[0]
    height = max(b.height for b in blocks)
    rows = ["" for _ in range(height)]
    for i, b in enumerate(blocks):
        joint = "--" if i else ""
        for r in range(height):
            if r < b.height:
                rows[r] += (joint if r == 0 else " " * len(joint)) + b.lines[r]
            else:
                rows[r] += " " * (len(joint) + b.width)
    return _Block(rows)


def _parallel(blocks: list[_Block]) -> _Block:
    maxw = max(b.width for b in blocks)
    rows: list[str] = []
    row0_of: list[int] = []
    for b in blocks:
        row0_of.append(len(rows))
        pad0 = "-" * (maxw - b.width)
        rows.append("+" + b.lines[0] + pad0 + "+")
        for line in b.lines[1:]:
            rows.append(" " + line + " " * (maxw - b.width) + " ")
    last0 = row0_of[-1]
    fixed = []
    for r, line in enumerate(rows):
        if r in row0_of or r > last0:
            fixed.append(line)
        else:  # rails between the first and last branch entry
            fixed.append("|" + line[1:-1] + "|")
    return _Block(fixed)


def _cond_block(e: X.Expr) -> _Block:
    if isinstance(e, X.Bin) and e.op == "AND":
        parts: list[X.Expr] = []

        def flat(x: X.Expr) -> None:
            if isinstance(x, X.Bin) and x.op == "AND":
                flat(x.left), flat(x.right)
            else:
                parts.append(x)

        flat(e)
        return _series([_cond_block(p) for p in parts])
    if isinstance(e, X.Bin) and e.op == "OR":
        parts = []

        def flat_or(x: X.Expr) -> None:
            if isinstance(x, X.Bin) and x.op == "OR":
                flat_or(x.left), flat_or(x.right)
            else:
                parts.append(x)

        flat_or(e)
        return _parallel([_cond_block(p) for p in parts])
    if isinstance(e, X.Un) and e.op == "NOT" and isinstance(e.x, X.Ref):
        return _Block([f"[/{'.'.join(e.x.path)} ]"])
    if isinstance(e, X.Ref):
        return _leaf(".".join(e.path))
    if isinstance(e, X.Lit) and e.kind == "bool":
        return _Block(["-------"]) if e.value else _leaf("FALSE")
    return _leaf(expr_text(e))  # comparison as a compare contact


def _action_text(a) -> str:
    if isinstance(a, CoilAction):
        name = ".".join(a.target.path)
        return {"out": f"( {name} )", "set": f"(S {name} )",
                "reset": f"(R {name} )"}[a.mode]
    if isinstance(a, MoveAction):
        return f"[MOVE {expr_text(a.value)} -> {'.'.join(a.target.path)}]"
    if isinstance(a, TimerAction):
        return f"[{a.kind} {a.instance}, {a.preset_ms} ms]"
    return "(?)"


def rung_art(rung: Rung) -> str:
    """One rung as ASCII ladder art between power rails."""
    if rung.cond is None:
        body = _Block(["-" * 4])
    else:
        body = _cond_block(push_not_down(rung.cond))
    act = _action_text(rung.action)
    rows = []
    for r, line in enumerate(body.lines):
        if r == 0:
            rows.append(f"|--{line}--{act}--|")
        else:
            rows.append(f"|  {line}" + " " * (len(act) + 4) + "|")
    return "\n".join(rows)


def program_art(lp: LoweredProgram, project: Project) -> tuple[str, str]:
    """(kind, text): kind 'ladder' with rung art, or 'st' pseudocode."""
    try:
        rungs = to_rungs(lp, bool_roots_for(lp, project))
        parts = []
        for i, r in enumerate(rungs):
            head = f"Network {i + 1}"
            if r.comment:
                head += f" - {r.comment.splitlines()[0]}"
            parts.append(head + "\n" + rung_art(r))
        return "ladder", "\n\n".join(parts)
    except RungError:
        from ladder.backends.dialects import Iec61131Dialect

        return "st", Iec61131Dialect().body(lp)


# ------------------------------------------------------------- the report

_CSS = """
body { font-family: Georgia, 'Times New Roman', serif; margin: 2rem auto;
       max-width: 62rem; padding: 0 1rem; color: #1c2b33; background: #fbfaf7; }
h1 { border-bottom: 3px solid #1c2b33; padding-bottom: .3rem; }
h2 { margin-top: 2.2rem; border-bottom: 1px solid #b9b3a6; padding-bottom: .2rem; }
h3 { margin-bottom: .3rem; }
pre { background: #10231d; color: #d7e8dc; padding: .8rem 1rem; overflow-x: auto;
      border-radius: 4px; font-size: .82rem; line-height: 1.35; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; }
th, td { border: 1px solid #cdc7ba; padding: .3rem .55rem; text-align: left;
         vertical-align: top; }
th { background: #efeadf; }
.badge { display: inline-block; background: #35594a; color: #fff;
         border-radius: 3px; padding: .05rem .45rem; font-size: .75rem;
         font-family: Consolas, monospace; }
.muted { color: #6d675c; font-size: .85rem; }
.pass { color: #1d6b3c; font-weight: bold; }
.warn { color: #8a5a00; }
details summary { cursor: pointer; margin: .4rem 0; }
footer { margin-top: 3rem; font-size: .8rem; color: #6d675c;
         border-top: 1px solid #b9b3a6; padding-top: .5rem; }
@media print { pre { background: #fff; color: #000; border: 1px solid #999; } }
"""


def _esc(s) -> str:
    return html.escape(str(s or ""))


def _element_rows(prog) -> str:
    rows = []
    for el in prog.logic:
        kind = getattr(el, "element", type(el).__name__)
        eid = getattr(el, "id", "") or ""
        desc = getattr(el, "description", "") or ""
        out = (getattr(el, "output", None) or getattr(el, "target", None)
               or getattr(el, "active", None) or "")
        rows.append(f"<tr><td><span class=badge>{_esc(kind)}</span></td>"
                    f"<td>{_esc(eid)}</td><td>{_esc(out)}</td>"
                    f"<td>{_esc(desc)}</td></tr>")
    return "\n".join(rows)


def _theorems_html(project: Project, lowered) -> str:
    from ladder.model_check import ModelError, emit_smv

    items = []
    for name, lp in lowered.items():
        try:
            smv = emit_smv(project, lp)
        except ModelError as e:
            items.append(f"<li class=warn>{_esc(name)}: not model-checkable "
                         f"({_esc(e)}) - covered by scenarios only</li>")
            continue
        lines = smv.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("INVARSPEC"):
                desc = lines[i - 1][3:] if i and lines[i - 1].startswith("--") else ""
                items.append(f"<li><b>{_esc(name)}</b>: {_esc(desc)} "
                             f"<code class=muted>{_esc(line)}</code></li>")
    return "<ul>" + "\n".join(items) + "</ul>" if items else \
        "<p class=muted>no auto-theorems (no safety elements).</p>"


def _scenarios_html(scenarios_path: Path | None) -> str:
    if not scenarios_path or not Path(scenarios_path).exists():
        return "<p class=muted>no scenario suite declared.</p>"
    import yaml

    data = yaml.safe_load(Path(scenarios_path).read_text(encoding="utf-8"))
    out = []
    for sc in data.get("scenarios", []):
        steps = []
        for step in sc.get("steps", []):
            for verb, arg in step.items():
                steps.append(f"<tr><td><span class=badge>{_esc(verb)}</span></td>"
                             f"<td>{_esc(arg)}</td></tr>")
        out.append(f"<details open><summary><b>{_esc(sc.get('name'))}</b>"
                   "</summary><table><tr><th>step</th><th>detail</th></tr>"
                   + "\n".join(steps) + "</table></details>")
    return "\n".join(out)


def render_html(project: Project, scenarios_path: Path | None = None) -> str:
    lowered = lower_project(project)
    sections = []
    for prog in project.programs:
        lp = lowered[prog.name]
        kind, art = program_art(lp, project)
        label = ("ladder view (generated from the IR)" if kind == "ladder"
                 else "logic as structured text (not rung-shaped)")
        sections.append(f"""
<h2>Program: {_esc(prog.name)} <span class=badge>{_esc(prog.language)}</span></h2>
<p>{_esc(prog.description)}</p>
<table><tr><th>element</th><th>id</th><th>output</th><th>description</th></tr>
{_element_rows(prog)}</table>
<h3>{label}</h3>
<pre>{_esc(art)}</pre>""")

    tag_rows = "\n".join(
        f"<tr><td>{_esc(t.name)}</td><td>{_esc(t.type)}</td>"
        f"<td>{_esc(t.direction)}</td><td>{_esc(t.comment)}</td></tr>"
        for t in project.tags)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(project.name)} - logic report</title>
<style>{_CSS}</style></head><body>
<h1>{_esc(project.name)}</h1>
<p>{_esc(project.description)}</p>
<p class=muted>Generated by <code>ladder render</code> from the IR - the
single source of truth. Regenerate after any change; never edit.</p>
<details><summary><b>Signals</b> ({len(project.tags)} tags)</summary>
<table><tr><th>name</th><th>type</th><th>direction</th><th>comment</th></tr>
{tag_rows}</table></details>
{''.join(sections)}
<h2>Acceptance scenarios (the definition of done)</h2>
{_scenarios_html(scenarios_path)}
<h2>Safety theorems (proved by nuXmv via <code>ladder verify -t smv</code>)</h2>
{_theorems_html(project, lowered)}
<footer>LADDER logic report - generated logic must be reviewed by a
qualified controls engineer; not certified for SIL/PL-rated safety
functions.</footer>
</body></html>
"""
