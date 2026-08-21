"""The packaged conformance suite: every built-in backend over the corpus."""

from ladder.conformance import corpus_projects, format_conformance, run_conformance


def test_corpus_is_nonempty_and_discovers_benchmarks():
    corpus = corpus_projects()
    names = {p.stem for p in corpus}
    assert "vacuum_interlock" in names and "languages_demo" in names
    assert len(corpus) >= 10  # examples + benchmark references


def test_all_builtin_backends_conform():
    results = run_conformance(["iec", "plcopen", "siemens", "rockwell",
                               "beckhoff"])
    failed = [str(r) for r in results if r.status == "fail"]
    assert not failed, "\n".join(failed)
    report = format_conformance(results)
    assert "CONFORMANCE PASSED" in report
