"""Roadmap tests: the page runs, claims match the repository, and the documents agree."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.roadmap import (
    CURRENT,
    CURRENT_COMPONENTS,
    EDGES,
    FUTURE,
    LIMITATIONS,
    LONGER,
    NODES,
    PHASES,
    STATUSES,
    WORKSTREAMS,
    workflow_dot,
)


def test_every_component_marked_current_exists_in_the_repository():
    for component in CURRENT_COMPONENTS:
        assert (ROOT / component["file"]).is_file(), component["file"]


def test_nothing_unbuilt_is_presented_as_current():
    assert {w["id"]: w["status"] for w in WORKSTREAMS} == {
        "WS1": CURRENT, "WS2": FUTURE, "WS3": FUTURE, "WS4": FUTURE}
    for ws in WORKSTREAMS[1:3]:                       # segmentation and price guidance
        assert ws["coverage"] == "Not started"
        assert ws["built"][0].startswith("Not built")
    assert all(p["status"] in (FUTURE, LONGER) for p in PHASES)  # no phase is complete
    assert [p["status"] for p in PHASES][-1] == LONGER           # RAG is longer-term


def test_four_workstreams_and_phases_a_to_d_plus_later_extension():
    assert [w["id"] for w in WORKSTREAMS] == ["WS1", "WS2", "WS3", "WS4"]
    assert [p["phase"] for p in PHASES] == ["A", "B", "C", "D", "Later"]


def test_diagram_is_consistent_and_uses_all_three_statuses():
    ids = {n[0] for n in NODES}
    assert all(a in ids and b in ids for a, b, _ in EDGES)
    assert {n[2] for n in NODES} == set(STATUSES)
    dot = workflow_dot()
    assert dot.startswith("digraph") and dot.rstrip().endswith("}")
    assert "dashed" in dot and "dotted" in dot
    for _, label, _ in NODES:
        assert label.replace("\n", "\\n") in dot


def test_no_invented_results_in_the_roadmap_text():
    text = (ROOT / "PROJECT_ROADMAP.md").read_text() + (ROOT / "src" / "roadmap.py").read_text()
    assert not re.search(r"\d+(\.\d+)?\s?%\s+(saving|saved|uplift|improvement)", text, re.I)
    assert not re.search(r"R²|R-squared|RMSE|MAE", text)
    assert "approved by" not in text.lower()


def test_limitations_cover_the_required_points():
    joined = " ".join(LIMITATIONS).lower()
    for phrase in ("synthetic", "not** confirmed price leakage", "assumptions about customer behaviour",
                   "causal", "market, customer and operational", "human consultant judgment"):
        assert phrase in joined, phrase


def test_markdown_roadmap_matches_the_page_content():
    md = (ROOT / "PROJECT_ROADMAP.md").read_text()
    for ws in WORKSTREAMS:
        assert ws["name"] in md
    for phase in PHASES[:4]:
        assert phase["title"].split(":")[0].split("&")[0].strip().lower()[:12] in md.lower()
    for status in STATUSES:
        assert status in md
    assert "```mermaid" in md
    assert "not verified quotations" in md
    assert "Price Waterfall → Regression Diagnosis → Root Cause Investigation → What-if Simulation" in md


def test_readme_links_to_the_roadmap():
    assert "PROJECT_ROADMAP.md" in (ROOT / "README.md").read_text()


def test_roadmap_page_runs_and_shows_everything():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(ROOT / "app" / "dashboard.py"), default_timeout=120).run()
    assert not app.exception                      # the Waterfall page still works
    app.switch_page("pages/4_Project_Roadmap.py").run()
    assert not app.exception
    text = " ".join(m.value for m in app.markdown)
    for ws in WORKSTREAMS:
        assert ws["name"] in text
    for status in STATUSES:
        assert status in text
    assert "Executive summary" in [h.value for h in app.header]
    assert len(app.dataframe) >= 2                # phases table and repository table


def test_existing_pages_still_run():
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(ROOT / "app" / "dashboard.py"), default_timeout=120).run()
    for page in ("pages/2_Regression_Diagnosis.py", "pages/3_Root_Cause_Simulation.py"):
        app.switch_page(page).run()
        assert not app.exception, page
