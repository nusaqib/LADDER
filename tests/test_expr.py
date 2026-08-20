import pytest

from ladder.ir import expr as X


def test_parse_bool_chain():
    e = X.parse_expr("a AND b OR NOT c")
    assert isinstance(e, X.Bin) and e.op == "OR"
    assert isinstance(e.right, X.Un) and e.right.op == "NOT"


def test_parse_comparison_arith():
    e = X.parse_expr("fill_level >= setpoint - 2.5")
    assert isinstance(e, X.Bin) and e.op == ">="
    assert isinstance(e.right, X.Bin) and e.right.op == "-"
    assert e.right.right == X.Lit(2.5, "real")


def test_parse_member_access():
    e = X.parse_expr("motor.running AND T1.Q")
    refs = list(X.refs(e))
    assert refs[0].path == ("motor", "running")
    assert refs[1].path == ("T1", "Q")


@pytest.mark.parametrize("text,ms", [
    ("T#5s", 5000),
    ("T#500ms", 500),
    ("T#1m30s", 90000),
    ("TIME#2.5s", 2500),
    ("t#1h", 3600000),
])
def test_time_literals(text, ms):
    assert X.parse_time_literal(text) == ms


def test_time_format_roundtrip():
    assert X.format_time_ms(90000) == "T#1m30s"
    assert X.parse_time_literal(X.format_time_ms(3723000)) == 3723000


@pytest.mark.parametrize("bad", ["", "AND b", "a AND", "a ++ b", "T#xyz", "(a"])
def test_parse_errors(bad):
    with pytest.raises(X.ExprError):
        X.parse_expr(bad)


def test_render_precedence_parens():
    from ladder.backends.dialects import Iec61131Dialect, RenderContext

    d, ctx = Iec61131Dialect(), RenderContext()
    e = X.parse_expr("(a OR b) AND NOT c")
    assert d.expr(e, ctx) == "(a OR b) AND NOT c"
    e2 = X.parse_expr("a OR b AND c")
    assert d.expr(e2, ctx) == "a OR b AND c"


def test_render_siemens_decoration():
    from ladder.backends.dialects import RenderContext, SiemensSclDialect

    d = SiemensSclDialect()
    ctx = RenderContext(local_names={"t1"})
    e = X.parse_expr("go AND t1.Q")
    assert d.expr(e, ctx) == '"go" AND #t1.Q'


def test_render_rockwell_timer_members():
    from ladder.backends.dialects import RenderContext, RockwellStDialect

    d = RockwellStDialect()
    ctx = RenderContext(local_names={"t1"})
    assert d.expr(X.parse_expr("t1.Q"), ctx) == "t1.DN"
    assert d.expr(X.parse_expr("t1.ET"), ctx) == "t1.ACC"
