"""`ladder diff` - what changed, in design language.

A YAML diff says lines moved; a reviewer needs "IL_motor gained
permissive guard_closed". This compares two IR documents (files or
modular directories) semantically: tags, types, programs, and per-
element field changes, keyed by element id so reordering unrelated
elements doesn't drown the real change.
"""

from __future__ import annotations

from pathlib import Path


def _key(el: dict, index: int) -> str:
    return el.get("id") or f"{el.get('element', '?')}#{index}"


def _fmt(v) -> str:
    if isinstance(v, dict) and len(v) == 1:
        k, val = next(iter(v.items()))
        return f"{k}: {_fmt(val)}"
    if isinstance(v, list):
        return "[" + ", ".join(_fmt(x) for x in v) + "]"
    return str(v)


def _diff_element(where: str, old: dict, new: dict, out: list[str]) -> None:
    for field in sorted(set(old) | set(new)):
        a, b = old.get(field), new.get(field)
        if a == b:
            continue
        # list fields (permissive chains etc.): show membership deltas
        la = a.get("all") if isinstance(a, dict) and "all" in a else a
        lb = b.get("all") if isinstance(b, dict) and "all" in b else b
        if isinstance(la, list) and isinstance(lb, list):
            sa = {_fmt(x) for x in la}
            sb = {_fmt(x) for x in lb}
            for gone in sorted(sa - sb):
                out.append(f"  ~ {where}: {field} DROPPED {gone}")
            for came in sorted(sb - sa):
                out.append(f"  ~ {where}: {field} gained {came}")
            if sa == sb:
                out.append(f"  ~ {where}: {field} reordered")
            continue
        if a is None:
            out.append(f"  ~ {where}: {field} added ({_fmt(b)})")
        elif b is None:
            out.append(f"  ~ {where}: {field} removed (was {_fmt(a)})")
        else:
            out.append(f"  ~ {where}: {field}: {_fmt(a)} -> {_fmt(b)}")


def diff_ir(old_path: str | Path, new_path: str | Path) -> list[str]:
    from ladder.ir.loader import load_ir_data

    old, new = load_ir_data(old_path), load_ir_data(new_path)
    out: list[str] = []

    def named(items, key="name") -> dict:
        return {x[key]: x for x in (items or [])}

    # tags
    ot, nt = named(old.get("tags")), named(new.get("tags"))
    for name in sorted(ot.keys() - nt.keys()):
        out.append(f"  - tag {name} removed")
    for name in sorted(nt.keys() - ot.keys()):
        t = nt[name]
        out.append(f"  + tag {name} added ({t.get('type', 'BOOL')}"
                   f"{', ' + t['direction'] if t.get('direction') else ''})")
    for name in sorted(ot.keys() & nt.keys()):
        for f in ("type", "direction", "initial", "array"):
            if ot[name].get(f) != nt[name].get(f):
                out.append(f"  ~ tag {name}: {f}: {ot[name].get(f)} -> "
                           f"{nt[name].get(f)}")

    # types
    oty, nty = named(old.get("types")), named(new.get("types"))
    for name in sorted(oty.keys() - nty.keys()):
        out.append(f"  - type {name} removed")
    for name in sorted(nty.keys() - oty.keys()):
        out.append(f"  + type {name} added")
    for name in sorted(oty.keys() & nty.keys()):
        om = named(oty[name].get("members"))
        nm = named(nty[name].get("members"))
        for m in sorted(om.keys() - nm.keys()):
            out.append(f"  - type {name}.{m} removed")
        for m in sorted(nm.keys() - om.keys()):
            out.append(f"  + type {name}.{m} added")

    # programs / elements
    op, np_ = named(old.get("programs")), named(new.get("programs"))
    for name in sorted(op.keys() - np_.keys()):
        out.append(f"  - program {name} removed")
    for name in sorted(np_.keys() - op.keys()):
        out.append(f"  + program {name} added "
                   f"({len(np_[name].get('logic', []))} element(s))")
    for name in sorted(op.keys() & np_.keys()):
        oe = {_key(e, i): e for i, e in enumerate(op[name].get("logic", []))}
        ne = {_key(e, i): e for i, e in enumerate(np_[name].get("logic", []))}
        for k in sorted(oe.keys() - ne.keys()):
            out.append(f"  - {name}/{k} removed ({oe[k].get('element')})")
        for k in sorted(ne.keys() - oe.keys()):
            out.append(f"  + {name}/{k} added ({ne[k].get('element')})")
        for k in sorted(oe.keys() & ne.keys()):
            if oe[k] != ne[k]:
                _diff_element(f"{name}/{k}", oe[k], ne[k], out)
        okeys = [k for k in oe if k in ne]
        nkeys = [k for k in ne if k in oe]
        if okeys != nkeys:
            out.append(f"  ~ program {name}: element ORDER changed "
                       "(scan-order review required)")

    return out
