import json

import pytest

from analyst.__main__ import main
from analyst.analyzer import analyze, to_markdown

GREENFIELD = "Build a scalable URL shortener service with APIs, persistence, and analytics."
BROWNFIELD = "Improve the existing analytics: bot traffic such as Googlebot is currently counted in click totals. Exclude bots from totals, with tests."
AMBIGUOUS = "Make the system faster and better, with some improvements etc."


def test_greenfield_covers_url_shortener_capabilities():
    """Greenfield requirement yields core capabilities/tasks and flags a missing scale target."""
    a = analyze(GREENFIELD)
    assert a.classification["type"] == "greenfield"
    assert {"api", "persistence", "analytics", "scalability"} <= set(a.capabilities)
    ids = {t["id"] for t in a.tasks}
    assert {"clarify", "design", "scaffold", "persistence", "core_logic", "analytics", "tests", "docs", "summary"} <= ids
    assert not a.needs_clarification
    # scalability without numbers must be called out
    assert any(x["topic"] == "scale target" for x in a.ambiguities)


def test_brownfield_pins_behaviour_before_changing_it():
    """Brownfield plan skips scaffolding and orders understand, characterize, then change."""
    a = analyze(BROWNFIELD)
    assert a.classification["type"] == "brownfield"
    ids = [t["id"] for t in a.tasks]
    assert "scaffold" not in ids and "characterize" in ids
    assert ids.index("understand_code") < ids.index("characterize") < ids.index("change")


def test_ambiguous_requirement_is_flagged_and_blocks_on_clarification():
    """Vague requirement is classified ambiguous, lists questions, and blocks on a clarify task."""
    a = analyze(AMBIGUOUS)
    assert a.classification["type"] == "ambiguous" and a.needs_clarification
    assert len(a.ambiguities) >= 3
    assert all(x["clarifying_question"] for x in a.ambiguities)
    clarify = next(t for t in a.tasks if t["id"] == "clarify")
    assert "BLOCKING" in clarify["description"]


def test_gibberish_is_ambiguous():
    """A vague non-requirement string is classified as ambiguous."""
    assert analyze("do the thing").classification["type"] == "ambiguous"


def test_task_graph_is_valid_and_ordered():
    """Task order equals execution order, dependencies come first, and waves cover all tasks."""
    for req in (GREENFIELD, BROWNFIELD, AMBIGUOUS):
        a = analyze(req)
        ids = [t["id"] for t in a.tasks]
        assert ids == a.execution_order
        position = {i: n for n, i in enumerate(ids)}
        for t in a.tasks:
            assert all(position[d] < position[t["id"]] for d in t["depends_on"]), t
        assert [i for wave in a.parallel_waves for i in wave] == ids


def test_risks_cover_all_required_categories():
    """Risk register includes functional, design, and ai categories."""
    cats = {r["category"] for r in analyze(GREENFIELD).risks}
    assert {"functional", "design", "ai"} <= cats


def test_deterministic():
    """Analyzing the same requirement twice yields identical output."""
    assert analyze(GREENFIELD).to_dict() == analyze(GREENFIELD).to_dict()


def test_empty_requirement_rejected():
    """A whitespace-only requirement raises ValueError."""
    with pytest.raises(ValueError):
        analyze("   ")


def test_context_scan_finds_relevant_files(tmp_path):
    """Scanning a context dir detects tests, frameworks, and files relevant to the requirement."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "analytics.py").write_text("def click_totals(): pass\n")
    (tmp_path / "requirements.txt").write_text("fastapi\npytest\n")
    (tmp_path / "test_x.py").write_text("")
    a = analyze(BROWNFIELD, context_dir=str(tmp_path))
    assert a.context["has_tests"] and "fastapi" in a.context["frameworks"]
    assert any("analytics.py" in f for f in a.context["likely_relevant_files"])


def test_cli_json_and_markdown(tmp_path, capsys):
    """CLI writes JSON to a file, prints Markdown by default, and exits 2 on empty input."""
    out = tmp_path / "o.json"
    assert main([GREENFIELD, "--format", "json", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["classification"]["type"] == "greenfield"
    assert main([GREENFIELD]) == 0
    assert "# Requirement Analysis" in capsys.readouterr().out
    assert main(["   "]) == 2
    assert "Task breakdown" in to_markdown(analyze(GREENFIELD))
