import pytest

from app.models.schemas import Finding
from scripts.evaluate_run import evaluate


def finding(category, page):
    return Finding(run_id="run", category=category, page=page, severity="low", personas=[], evidence=[], observed="Fixture")


@pytest.mark.parametrize("page", ["/demo/", "/demo/index.html", "index.html", "https://test/demo/index.html?q=1#x"])
def test_evaluation_index_aliases(page):
    result = evaluate([finding("backtrack", page)])
    assert result["found"] == ["D1"]
    assert result["recall"] == 1 / 12
    assert len(result["missed"]) == 11
    assert result["unmatched_findings"] == []


def test_evaluation_global_signals_and_page_mismatch():
    result = evaluate([finding("long_path", None), finding("invalid_input_accepted", "/wrong.html")])
    assert result["found"] == ["D1", "D8"]
    assert result["unmatched_findings"] == ["invalid_input_accepted@/wrong.html"]


def test_evaluation_duplicate_findings_count_issue_once_and_exclude_visual():
    result = evaluate([finding("dead_end", "/demo/learn.html"), finding("dead_end", "/learn.html"), finding("stuck_on_page", "/demo/")])
    assert result["found"] == ["D2"]
    assert result["recall"] == 1 / 12
    assert result["unmatched_findings"] == ["stuck_on_page@/demo/"]


def test_evaluation_empty():
    result = evaluate([])
    assert result["recall"] == 0.0 and not result["found"] and not result["unmatched_findings"]
    assert len(result["missed"]) == 12
