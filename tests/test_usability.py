"""The usability layer: render, replay, apply, doctor, friendly errors."""

from pathlib import Path

import pytest

from ladder.cli import main
from ladder.scaffold import init_project


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "plant"
    init_project(root, name="Plant")
    return root


# ------------------------------------------------------------- render


def test_render_report(project, capsys):
    assert main(["render", str(project)]) == 0
    html = (project / "out" / "report.html").read_text(encoding="utf-8")
    # rung art: NO/NC contacts, latch coils, timer instruction, branches
    assert "[ estop_ok ]" in html and "[/overload_ok ]" in html
    assert "(S run_permit )" in html and "(R run_permit )" in html
    assert "[TON ALM_overload_ton, 1000 ms]" in html
    assert "+[ start_pb ]" in html         # OR branch junction
    # scenarios + theorems made it in
    assert "start_seals_in_and_stop_drops_it" in html
    assert "INVARSPEC (run_permit" in html


def test_render_st_fallback(tmp_path):
    ir = tmp_path / "p.yaml"
    ir.write_text("""\
ir_version: "0.2"
name: StFall
tags:
  - {name: a, type: BOOL, direction: input}
  - {name: x, type: REAL}
programs:
  - name: P
    logic:
      - element: st
        id: RAW_x
        code: "IF a THEN x := x + 0.5; END_IF;"
""", encoding="utf-8")
    assert main(["render", str(ir), "-o", str(tmp_path / "r.html")]) == 0
    html = (tmp_path / "r.html").read_text(encoding="utf-8")
    assert "structured text" in html and "x + 0.5" in html


# ------------------------------------------------------------- replay

_NUXMV_OUT = """\
-- invariant (search_done -> FALSE) is false
-- as demonstrated by the following execution sequence
Trace Description: BDD Counterexample
Trace Type: Counterexample
  -> State: 1.1 <-
    search_done = FALSE
    k1a = FALSE
    k1b = FALSE
    door_ok = FALSE
  -> Input: 1.2 <-
    T_choice = FALSE
  -> State: 1.2 <-
    k1a = TRUE
    k1b = TRUE
    door_ok = TRUE
  -> State: 1.3 <-
    search_done = TRUE
"""


def test_parse_nuxmv_output():
    from ladder.replay import parse_nuxmv_output

    traces = parse_nuxmv_output(_NUXMV_OUT)
    assert len(traces) == 1
    t = traces[0]
    assert t.spec == "(search_done -> FALSE)"
    assert len(t.states) == 3
    assert t.states[0]["search_done"] is False
    assert t.states[1]["k1a"] is True          # change applied
    assert t.states[1]["search_done"] is False  # carried forward
    assert t.states[2]["search_done"] is True


def test_replay_end_to_end(tmp_path):
    """A deliberately false property yields a replay scenario that PASSES
    in the simulator (the violation is concrete, timer-free)."""
    import os
    import shutil

    from ladder.verify import find_nuxmv

    if not find_nuxmv():
        pytest.skip("nuXmv not available")
    from tests_support_replay import make_project  # local helper below

    project = make_project()
    props = tmp_path / "props.yaml"
    props.write_text(
        "properties:\n  - program: Safety\n    always: NOT search_done\n",
        encoding="utf-8")
    from ladder.verify import verify_smv

    res = verify_smv(project, tmp_path, properties=str(props))
    assert res.status == "fail"
    replay = tmp_path / "smv" / "Safety.replay.scenarios.yaml"
    assert replay.exists()
    from ladder.scenario import run_suite

    results = run_suite(project, replay)
    assert results and all(r.passed for r in results), \
        [str(r) for r in results]


# -------------------------------------------------------------- apply


def test_apply_lands_blocks_and_checks(project, capsys):
    ir_text = (project / "ir" / "plant.yaml").read_text(encoding="utf-8")
    sc_text = (project / "scenarios" / "plant.scenarios.yaml").read_text(encoding="utf-8")
    response = (
        "Here is the design.\n\n```markdown\n# Plant - Design Inputs Map\n"
        "content\n```\n\nThe IR:\n\n```yaml\n" + ir_text +
        "```\n\nScenarios:\n\n```yaml\n" + sc_text + "```\n")
    resp = project / "response.md"
    resp.write_text(response, encoding="utf-8")
    assert main(["apply", str(resp), str(project)]) == 0
    out = capsys.readouterr().out
    assert "CHECK PASSED" in out
    assert (project / "design" / "DESIGN.md").read_text(encoding="utf-8")\
        .startswith("# Plant - Design Inputs Map")


def test_apply_rejects_blockless_response(project, capsys):
    resp = project / "r.md"
    resp.write_text("no fences here", encoding="utf-8")
    assert main(["apply", str(resp), str(project)]) == 1
    assert "no recognizable" in capsys.readouterr().err


# ------------------------------------------------- friendly IR errors


def test_schema_error_carries_line_number(tmp_path, capsys):
    ir = tmp_path / "bad.yaml"
    ir.write_text("""\
ir_version: "0.2"
name: Bad
tags:
  - {name: a, type: BOOL, direction: input}
programs:
  - name: P
    logic:
      - element: interlock
        id: IL_x
        permissives: {all: [a]}
""", encoding="utf-8")  # interlock missing required `output`
    assert main(["validate", str(ir)]) == 1
    err = capsys.readouterr().err
    assert "does not match the schema" in err
    assert "bad.yaml:" in err            # a real line number was found
    assert "ladder schema" in err        # the hint


# -------------------------------------------------------------- doctor


def test_doctor_reports(project, capsys):
    assert main(["doctor", str(project)]) == 0
    out = capsys.readouterr().out
    assert "ladder doctor" in out
    assert "manifest: Plant" in out
    assert "nuXmv" in out and "matiec" in out
