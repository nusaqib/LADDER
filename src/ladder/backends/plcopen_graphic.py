"""PLCopen tc6 XML graphic bodies: LD, FBD, and SFC.

Renders the neutral rung model (ladder.backends.rungs) as real graphic
networks - contacts/coils for LD, function-block graphs for FBD - and a
state_machine element as an SFC chart. Everything carries localIds,
positions (simple grid layout), and executionOrderIds in statement order
so importing tools execute networks exactly like the lowered ST.

Semantic notes locked here:

  LD    one rung per model rung; set/reset coils use the tc6 `storage`
        attribute; compare sub-expressions render as function blocks and
        are reordered to the head of their AND chain (safe: conditions
        are pure), because a block output cannot be fed from a contact.
  FBD   coils have no FBD equivalent, so each written variable becomes
        one network: consecutive set/reset rungs fold into the standard
        latch idiom (later rung dominant, matching ST statement order):
            set-dominant   out := set OR (out AND NOT reset)
            reset-dominant out := (set OR out) AND NOT reset
        Conditional moves become MOVE blocks gated by EN.
  SFC   steps mirror the state machine 1:1; each step's action (qualifier
        N) performs the state's `do` assigns plus `state_tag := code` so
        the tag stays truthful for other programs; transition order is
        selection-divergence priority = first-match-wins.
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from ladder.backends.rungs import (
    CoilAction,
    MoveAction,
    Rung,
    RungError,
    TimerAction,
    push_not_down,
)
from ladder.ir import expr as X
from ladder.ir.model import StateMachineEl, compile_cond
from ladder.ir.lower import state_codes

_CMP_BLOCKS = {"=": "EQ", "<>": "NE", "<": "LT", "<=": "LE", ">": "GT", ">=": "GE"}


def _fmt_lit(lit: X.Lit) -> str:
    if lit.kind == "bool":
        return "TRUE" if lit.value else "FALSE"
    if lit.kind == "time":
        return X.format_time_ms(int(lit.value))
    if lit.kind == "real":
        s = repr(float(lit.value))
        return s if ("." in s or "e" in s) else s + ".0"
    return str(lit.value)


def _expr_text(e: X.Expr) -> str:
    if isinstance(e, X.Lit):
        return _fmt_lit(e)
    if isinstance(e, X.Ref):
        return ".".join(e.path)
    raise RungError(f"expected a plain operand, got {e!r}")


class _Body:
    """localId allocator + line collector + grid layout."""

    def __init__(self, indent: str):
        self.lines: list[str] = []
        self.indent = indent
        self._id = 0
        self._exec = 0
        self.row = 0

    def nid(self) -> int:
        self._id += 1
        return self._id

    def eid(self) -> int:
        self._exec += 1
        return self._exec

    def pos(self, col: int) -> str:
        return f'<position x="{col * 90}" y="{self.row * 70}"/>'

    def add(self, text: str) -> None:
        self.lines.append(self.indent + text)


def _cpi(sources: list[tuple[int, str | None]]) -> str:
    conns = "".join(
        f'<connection refLocalId="{rid}"'
        + (f' formalParameter="{fp}"' if fp else "") + "/>"
        for rid, fp in sources)
    return f'<connectionPointIn><relPosition x="0" y="0"/>{conns}</connectionPointIn>'


_CPO = '<connectionPointOut><relPosition x="0" y="0"/></connectionPointOut>'


def _in_var(b: _Body, expression: str, col: int) -> int:
    vid = b.nid()
    b.add(f'<inVariable localId="{vid}">{b.pos(col)}{_CPO}'
          f"<expression>{escape(expression)}</expression></inVariable>")
    return vid


# ------------------------------------------------------------------- LD


def _ld_and_operands(e: X.Expr) -> list[X.Expr]:
    if isinstance(e, X.Bin) and e.op == "AND":
        return _ld_and_operands(e.left) + _ld_and_operands(e.right)
    return [e]


def _ld_contact(b: _Body, name: str, negated: bool, col: int,
                sources: list[tuple[int, str | None]]) -> int:
    cid = b.nid()
    b.add(f'<contact localId="{cid}" negated={quoteattr("true" if negated else "false")}>'
          f"{b.pos(col)}{_cpi(sources)}{_CPO}"
          f"<variable>{escape(name)}</variable></contact>")
    return cid


def _ld_cmp_block(b: _Body, e: X.Bin, col: int) -> int:
    bid = b.nid()
    in1 = _in_var(b, _expr_text(e.left), col - 1)
    in2 = _in_var(b, _expr_text(e.right), col - 1)
    b.add(f'<block localId="{bid}" typeName="{_CMP_BLOCKS[e.op]}" '
          f'executionOrderId="{b.eid()}">{b.pos(col)}'
          "<inputVariables>"
          f'<variable formalParameter="IN1">{_cpi([(in1, None)])}</variable>'
          f'<variable formalParameter="IN2">{_cpi([(in2, None)])}</variable>'
          "</inputVariables><inOutVariables/><outputVariables>"
          f'<variable formalParameter="OUT">{_CPO}</variable>'
          "</outputVariables></block>")
    return bid


def _ld_chain(b: _Body, e: X.Expr, col: int,
              sources: list[tuple[int, str | None]],
              head: bool) -> tuple[list[tuple[int, str | None]], int]:
    """Render expression e fed from `sources` (head = fed straight from the
    power rail); return (out points, next col)."""
    if isinstance(e, X.Ref):
        cid = _ld_contact(b, ".".join(e.path), False, col, sources)
        return [(cid, None)], col + 1
    if isinstance(e, X.Un) and e.op == "NOT" and isinstance(e.x, X.Ref):
        cid = _ld_contact(b, ".".join(e.x.path), True, col, sources)
        return [(cid, None)], col + 1
    if isinstance(e, X.Bin):
        if e.op == "AND":
            ops = _ld_and_operands(e)
            # a compare block's output is the rung signal and it takes no
            # boolean input, so it must sit at the head; AND is commutative
            # and conditions are pure, so hoisting is safe
            cmps = [o for o in ops if isinstance(o, X.Bin) and o.op in _CMP_BLOCKS]
            rest = [o for o in ops if not (isinstance(o, X.Bin) and o.op in _CMP_BLOCKS)]
            if len(cmps) > 1:
                raise RungError("more than one comparison in an LD rung")
            cur, at_head = sources, head
            if cmps:
                if not at_head:
                    raise RungError("comparison not at the head of an LD rung")
                bid = _ld_cmp_block(b, cmps[0], col)
                cur, at_head = [(bid, "OUT")], False
                col += 1
            for o in rest:
                cur, col = _ld_chain(b, o, col, cur, at_head)
                at_head = False
            return cur, col
        if e.op == "OR":
            left_out, lcol = _ld_chain(b, e.left, col, sources, head)
            b.row += 1
            right_out, rcol = _ld_chain(b, e.right, col, sources, head)
            b.row -= 1
            return left_out + right_out, max(lcol, rcol)
        if e.op in _CMP_BLOCKS:
            if not head:
                raise RungError("comparison not at the head of an LD rung")
            bid = _ld_cmp_block(b, e, col)
            return [(bid, "OUT")], col + 1
    raise RungError(f"no LD form for expression {e!r}")


def ld_body(rungs: list[Rung], indent: str = "            ") -> list[str]:
    b = _Body(indent)
    rail = b.nid()
    b.add(f'<leftPowerRail localId="{rail}"><position x="0" y="0"/>'
          '<connectionPointOut formalParameter="">'
          '<relPosition x="0" y="0"/></connectionPointOut></leftPowerRail>')
    coil_ids: list[int] = []
    for r in rungs:
        b.row += 1
        if r.comment:
            cid = b.nid()
            b.add(f'<comment localId="{cid}" height="20" width="400">{b.pos(0)}'
                  f'<content><xhtml xmlns="http://www.w3.org/1999/xhtml">'
                  f"{escape(r.comment)}</xhtml></content></comment>")
            b.row += 1
        src: list[tuple[int, str | None]] = [(rail, None)]
        col = 1
        cond = push_not_down(r.cond) if r.cond is not None else None
        if cond is not None and not (isinstance(cond, X.Lit) and cond.value):
            src, col = _ld_chain(b, cond, col, src, head=True)
        a = r.action
        if isinstance(a, CoilAction):
            cid = b.nid()
            storage = {"out": "none", "set": "set", "reset": "reset"}[a.mode]
            b.add(f'<coil localId="{cid}" storage={quoteattr(storage)} '
                  f'executionOrderId="{b.eid()}">{b.pos(col)}{_cpi(src)}{_CPO}'
                  f"<variable>{escape('.'.join(a.target.path))}</variable></coil>")
            coil_ids.append(cid)
        elif isinstance(a, MoveAction):
            bid = b.nid()
            in_id = _in_var(b, _expr_text(a.value), col)
            b.add(f'<block localId="{bid}" typeName="MOVE" '
                  f'executionOrderId="{b.eid()}">{b.pos(col + 1)}'
                  "<inputVariables>"
                  f'<variable formalParameter="EN">{_cpi(src)}</variable>'
                  f'<variable formalParameter="IN">{_cpi([(in_id, None)])}</variable>'
                  "</inputVariables><inOutVariables/><outputVariables>"
                  f'<variable formalParameter="OUT">{_CPO}</variable>'
                  "</outputVariables></block>")
            oid = b.nid()
            b.add(f'<outVariable localId="{oid}" executionOrderId="{b.eid()}">'
                  f"{b.pos(col + 2)}{_cpi([(bid, 'OUT')])}"
                  f"<expression>{escape('.'.join(a.target.path))}</expression></outVariable>")
        elif isinstance(a, TimerAction):
            pt = _in_var(b, X.format_time_ms(a.preset_ms), col)
            bid = b.nid()
            b.add(f'<block localId="{bid}" typeName="{a.kind}" '
                  f'instanceName={quoteattr(a.instance)} '
                  f'executionOrderId="{b.eid()}">{b.pos(col + 1)}'
                  "<inputVariables>"
                  f'<variable formalParameter="IN">{_cpi(src)}</variable>'
                  f'<variable formalParameter="PT">{_cpi([(pt, None)])}</variable>'
                  "</inputVariables><inOutVariables/><outputVariables>"
                  f'<variable formalParameter="Q">{_CPO}</variable>'
                  "</outputVariables></block>")
    b.row += 1
    if coil_ids:
        b.add(f'<rightPowerRail localId="{b.nid()}">{b.pos(12)}'
              + _cpi([(c, None) for c in coil_ids]) + "</rightPowerRail>")
    return b.lines


# ------------------------------------------------------------------ FBD


def _fbd_expr(b: _Body, e: X.Expr, col: int) -> tuple[int, str | None]:
    """Render an expression; return (localId, formalParameter) of its output."""
    if isinstance(e, (X.Lit, X.Ref)):
        return _in_var(b, _expr_text(e), col), None
    if isinstance(e, X.Un):
        src = _fbd_expr(b, e.x, col - 1)
        name = "NOT" if e.op == "NOT" else "NEG"
        bid = b.nid()
        b.add(f'<block localId="{bid}" typeName="{name}" '
              f'executionOrderId="{b.eid()}">{b.pos(col)}'
              "<inputVariables>"
              f'<variable formalParameter="IN">{_cpi([src])}</variable>'
              "</inputVariables><inOutVariables/><outputVariables>"
              f'<variable formalParameter="OUT">{_CPO}</variable>'
              "</outputVariables></block>")
        return bid, "OUT"
    if isinstance(e, X.Bin):
        name = {"AND": "AND", "OR": "OR", "XOR": "XOR", "+": "ADD", "-": "SUB",
                "*": "MUL", "/": "DIV", "MOD": "MOD"}.get(e.op) or _CMP_BLOCKS.get(e.op)
        if name is None:
            raise RungError(f"no FBD block for operator {e.op!r}")
        left = _fbd_expr(b, e.left, col - 1)
        b.row += 1
        right = _fbd_expr(b, e.right, col - 1)
        b.row -= 1
        bid = b.nid()
        b.add(f'<block localId="{bid}" typeName="{name}" '
              f'executionOrderId="{b.eid()}">{b.pos(col)}'
              "<inputVariables>"
              f'<variable formalParameter="IN1">{_cpi([left])}</variable>'
              f'<variable formalParameter="IN2">{_cpi([right])}</variable>'
              "</inputVariables><inOutVariables/><outputVariables>"
              f'<variable formalParameter="OUT">{_CPO}</variable>'
              "</outputVariables></block>")
        return bid, "OUT"
    if isinstance(e, X.Conv):
        src = _fbd_expr(b, e.x, col - 1)
        bid = b.nid()
        b.add(f'<block localId="{bid}" typeName="{e.frm}_TO_{e.to}" '
              f'executionOrderId="{b.eid()}">{b.pos(col)}'
              "<inputVariables>"
              f'<variable formalParameter="IN">{_cpi([src])}</variable>'
              "</inputVariables><inOutVariables/><outputVariables>"
              f'<variable formalParameter="OUT">{_CPO}</variable>'
              "</outputVariables></block>")
        return bid, "OUT"
    raise RungError(f"no FBD form for expression {e!r}")


def _fold_latch(target: X.Ref, group: list[Rung]) -> X.Expr:
    """Fold set/reset/out rungs on one target into a single expression,
    preserving ST statement-order dominance."""
    expr: X.Expr = X.Ref(target.path)
    for r in group:
        cond = r.cond if r.cond is not None else X.Lit(True, "bool")
        if r.action.mode == "out":
            expr = cond
        elif r.action.mode == "set":
            expr = X.Bin("OR", cond, expr)
        else:  # reset
            expr = X.Bin("AND", X.Un("NOT", cond), expr)
    return expr


def fbd_body(rungs: list[Rung], indent: str = "            ") -> list[str]:
    # group coil rungs per target; validate the fold is order-safe
    groups: dict[tuple[str, ...], list[int]] = {}
    for i, r in enumerate(rungs):
        if isinstance(r.action, CoilAction):
            groups.setdefault(r.action.target.path, []).append(i)
    for path, idxs in groups.items():
        group = [rungs[i] for i in idxs]
        modes = {r.action.mode for r in group}
        if modes == {"out"} and len(group) > 1:
            raise RungError(f"{'.'.join(path)}: multiple plain coils in FBD")
        between = [rungs[i] for i in range(idxs[0], idxs[-1] + 1) if i not in idxs]
        written = {r.action.target.root for r in between
                   if isinstance(r.action, (CoilAction, MoveAction))}
        for r in group:
            reads = {ref.root for ref in X.refs(r.cond)} if r.cond is not None else set()
            if reads & written:
                raise RungError(f"{'.'.join(path)}: latch fold would reorder a "
                                "read past a write; use st for this program")
            if path[0] in reads and modes != {"out"}:
                raise RungError(f"{'.'.join(path)}: set/reset condition reads its "
                                "own target; use st for this program")

    b = _Body(indent)
    done: set[tuple[str, ...]] = set()
    for i, r in enumerate(rungs):
        b.row += 2
        a = r.action
        if isinstance(a, CoilAction):
            if a.target.path in done or i != groups[a.target.path][-1]:
                continue  # rendered at the group's last rung position
            done.add(a.target.path)
            group = [rungs[j] for j in groups[a.target.path]]
            src = _fbd_expr(b, _fold_latch(a.target, group), 4)
            oid = b.nid()
            b.add(f'<outVariable localId="{oid}" executionOrderId="{b.eid()}">'
                  f"{b.pos(6)}{_cpi([src])}"
                  f"<expression>{escape('.'.join(a.target.path))}</expression></outVariable>")
        elif isinstance(a, MoveAction):
            en = (_fbd_expr(b, r.cond, 4) if r.cond is not None else
                  (_in_var(b, "TRUE", 4), None))
            in_id = _in_var(b, _expr_text(a.value), 4)
            bid = b.nid()
            b.add(f'<block localId="{bid}" typeName="MOVE" '
                  f'executionOrderId="{b.eid()}">{b.pos(5)}'
                  "<inputVariables>"
                  f'<variable formalParameter="EN">{_cpi([en])}</variable>'
                  f'<variable formalParameter="IN">{_cpi([(in_id, None)])}</variable>'
                  "</inputVariables><inOutVariables/><outputVariables>"
                  f'<variable formalParameter="OUT">{_CPO}</variable>'
                  "</outputVariables></block>")
            oid = b.nid()
            b.add(f'<outVariable localId="{oid}" executionOrderId="{b.eid()}">'
                  f"{b.pos(6)}{_cpi([(bid, 'OUT')])}"
                  f"<expression>{escape('.'.join(a.target.path))}</expression></outVariable>")
        elif isinstance(a, TimerAction):
            en = (_fbd_expr(b, r.cond, 4) if r.cond is not None else
                  (_in_var(b, "TRUE", 4), None))
            pt = _in_var(b, X.format_time_ms(a.preset_ms), 4)
            bid = b.nid()
            b.add(f'<block localId="{bid}" typeName="{a.kind}" '
                  f'instanceName={quoteattr(a.instance)} '
                  f'executionOrderId="{b.eid()}">{b.pos(5)}'
                  "<inputVariables>"
                  f'<variable formalParameter="IN">{_cpi([en])}</variable>'
                  f'<variable formalParameter="PT">{_cpi([(pt, None)])}</variable>'
                  "</inputVariables><inOutVariables/><outputVariables>"
                  f'<variable formalParameter="Q">{_CPO}</variable>'
                  "</outputVariables></block>")
    return b.lines


# ------------------------------------------------------------------ SFC


def sfc_body(el: StateMachineEl, st_expr, indent: str = "            ") -> list[str]:
    """SFC chart for a state_machine element. `st_expr` renders an
    expression AST to ST text (dialect-bound by the caller)."""
    codes = state_codes(el)
    b = _Body(indent)
    step_ids: dict[str, int] = {}
    for st in el.states:
        b.row += 3
        sid = b.nid()
        step_ids[st.name] = sid
        initial = ' initialStep="true"' if st.name == el.initial else ""
        b.add(f'<step localId="{sid}" name={quoteattr(st.name)}{initial}>'
              f"{b.pos(1)}{_cpi([])}"
              '<connectionPointOut formalParameter="">'
              "<relPosition x=\"0\" y=\"0\"/></connectionPointOut></step>")
        # action: state's do-assigns + keep the state tag truthful
        lines = [f"{el.state_tag} := {codes[st.name]};"]
        for act in st.do:
            lines.append(f"{act.target} := {st_expr(compile_cond(act.value))};")
        aid = b.nid()
        b.add(f'<actionBlock localId="{aid}">{b.pos(3)}{_cpi([(sid, None)])}'
              f'<action localId="{b.nid()}" qualifier="N">'
              '<relPosition x="0" y="0"/><inline>'
              '<ST><xhtml xmlns="http://www.w3.org/1999/xhtml">'
              f'{escape(" ".join(lines))}</xhtml></ST>'
              "</inline></action></actionBlock>")
        for k, tr in enumerate(st.transitions):
            b.row += 1
            tid = b.nid()
            b.add(f'<transition localId="{tid}" priority="{k + 1}">{b.pos(1)}'
                  f"{_cpi([(sid, None)])}{_CPO}"
                  f'<condition><inline name="cond_{tid}">'
                  '<ST><xhtml xmlns="http://www.w3.org/1999/xhtml">'
                  f"{escape(st_expr(compile_cond(tr.when)))}</xhtml></ST>"
                  "</inline></condition></transition>")
            b.row += 1
            jid = b.nid()
            b.add(f'<jumpStep localId="{jid}" targetName={quoteattr(tr.goto)}>'
                  f"{b.pos(1)}{_cpi([(tid, None)])}</jumpStep>")
    return b.lines
