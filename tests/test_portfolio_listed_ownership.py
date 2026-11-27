from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vercel-api" / "api"))
from portfolio_core import portfolio_listed_ownership as ownership
from portfolio_core.portfolio_engine import analyze_portfolio


def public_inputs():
    stocks = [{"market": "KR", "ticker": "123456", "name": "가람전자"},
              {"market": "KR", "ticker": "654321", "name": "새솔산업"}]
    row = {"issuer": "KR:123456", "party": "KR:654321", "issuer_name": "가람전자",
           "party_name": "새솔산업(주)", "endpoint": "hyslrSttus", "receipt": "20260813000001",
           "settled_on": "2026-06-30", "pct": 21.5, "row_index": 0}
    return {"universe_search.json": {"stocks": stocks},
            ownership.FILENAME: {"schema": ownership.SCHEMA, "rows": [row]}}


def query(docs, *tickers):
    return analyze_portfolio([{"market": "KR", "ticker": t} for t in tickers], docs)


def test_both_sides_and_joint_selection_return_the_same_filed_row_once():
    docs = public_inputs()
    before = deepcopy(docs)
    expected = {"schema": ownership.SCHEMA, "rows": docs[ownership.FILENAME]["rows"], "total": 1}
    for tickers in [("123456",), ("654321",), ("123456", "654321")]:
        result = query(docs, *tickers)
        assert result["listed_ownership"] == expected
        assert result["listed_ownership"]["rows"][0] is not expected["rows"][0]
    assert docs == before


@pytest.mark.parametrize("changes", [
    {"party_name": "새솔산업의 자회사"}, {"party": "KR:123456"}, {"pct": 0},
    {"pct": True}, {"settled_on": "2026-09-30"}, {"receipt": "20261399000001"},
    {"receipt": "29990813000001"}, {"endpoint": "unknown"}, {"row_index": -1}, {"extra": "ignored"},
])
def test_unbound_row_never_appears_in_an_analysis(changes):
    docs = public_inputs()
    docs[ownership.FILENAME]["rows"][0].update(changes)
    assert query(docs, "123456")["listed_ownership"]["total"] == 0


def test_conflicting_source_row_and_missing_feed_preserve_existing_analysis():
    docs = public_inputs()
    rows = docs[ownership.FILENAME]["rows"]
    rows.append({**rows[0], "pct": 80})
    assert "listed_ownership" not in query(docs, "123456")
    del docs[ownership.FILENAME]
    result = query(docs, "123456")
    assert result["companies"][0]["id"] == "KR:123456"
    assert "listed_ownership" not in result
    assert ownership.FILENAME not in result["coverage"]["missing_source_files"]


def test_name_collision_and_bounded_response():
    docs = public_inputs()
    stocks = docs["universe_search.json"]["stocks"]
    stocks.append({"market": "KR", "ticker": "777777", "name": "(주)새솔산업"})
    assert query(docs, "123456")["listed_ownership"]["total"] == 0
    stocks.pop()
    original = docs[ownership.FILENAME]["rows"][0]
    docs[ownership.FILENAME]["rows"] = [{**original, "row_index": i} for i in range(23)]
    subset = query(docs, "123456")["listed_ownership"]
    assert subset["total"] == 23
    assert len(subset["rows"]) == 20
