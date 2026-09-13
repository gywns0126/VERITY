"""ADR discovery is a search-only addition, not a trading-universe expansion."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from api.collectors import us_depositary_search as s


def reference(n=100):
    return [{"ticker": f"ADR{i}", "name": f"Company {i}", "locale": "us",
             "active": True, "type": "ADRC", "primary_exchange": "XNYS"}
            for i in range(n)]


def catalog(tmp_path):
    rows, counts = s.reference_rows("test", get=lambda url: {
        "status": "OK", "results": reference() if "type=ADRC" in url else []}, pause=lambda _: None)
    doc = {"_meta": {"scope": "search_only_not_trading_universe", "count": len(rows), "types": counts},
           "stocks": rows}
    p = tmp_path / "catalog.json"
    p.write_text(json.dumps(doc))
    return p, doc


def test_typed_reference_filters_non_us_inactive_and_non_shares():
    extras = [dict(reference(1)[0], ticker=f"BAD{i}", **change) for i, change in enumerate([
        {"active": False}, {"locale": "gb"}, {"type": "CS"}, {"primary_exchange": "OTC"}, {"name": ""}])]
    rows, counts = s.reference_rows("test", get=lambda url: {"status": "OK", "results":
        reference() + extras if "type=ADRC" in url else []}, pause=lambda _: None)
    assert len(rows) == counts["ADRC"] == 100
    assert counts["NYRS"] == 0
    assert all(not r["ticker"].startswith("BAD") for r in rows)


def test_complete_pagination():
    responses = iter([{"status": "OK", "results": reference(50), "next_url": "https://api.polygon.io/page2"},
                      {"status": "OK", "results": reference()[50:]}, {"status": "OK", "results": []}])
    rows, _ = s.reference_rows("test", get=lambda _: next(responses), pause=lambda _: None)
    assert len(rows) == 100


@pytest.mark.parametrize("response,error", [
    ({"status": "OK", "results": []}, "coverage_below_floor"),
    ({"status": "ERROR", "results": []}, "invalid_reference_response"),
    ({"status": "OK", "results": reference(), "next_url": "https://example.org/page"}, "untrusted_reference_page"),
    ({"status": "OK", "results": reference(), "next_url": "https://api.polygon.io/loop"}, "incomplete_reference_pages"),
])
def test_rejects_incomplete_or_untrusted_reference(response, error):
    with pytest.raises(ValueError, match=error):
        s.reference_rows("test", get=lambda _: response, pause=lambda _: None)


def test_exact_us_display_name_accepts_latin():
    assert s.display_name("TSM", get=lambda _: {"items": [
        {"code": "TSM", "nationCode": "KOR", "name": "Wrong"},
        {"code": "TSMC", "nationCode": "USA", "name": "Wrong"},
        {"code": "TSM", "nationCode": "USA", "name": "TSMC ADR"}]}) == "TSMC ADR"


def test_merge_preserves_old_rows_and_strips_non_search_fields(tmp_path):
    p, doc = catalog(tmp_path)
    doc["stocks"][0].update(name_ko="테스트 ADR", price=123, cik="private-extra")
    p.write_text(json.dumps(doc))
    old = [{"ticker": "005930", "market": "KOSPI", "name": "삼성전자"},
           {"ticker": "QQQ", "market": "US", "name": "QQQ", "type": "ETF"},
           {"ticker": "CMD_GOLD", "market": "원자재", "type": "commodity"}]
    uni = copy.deepcopy(old)
    added, _ = s.append_catalog(uni, p)
    assert added == 100 and uni[:3] == old
    assert "price" not in uni[3] and "cik" not in uni[3]
    assert uni[3]["name_ko"] == "테스트 ADR"
    assert s.append_catalog(uni, p)[0] == 0


@pytest.mark.parametrize("bad", ["scope", "count", "duplicate", "row", "small"])
def test_invalid_catalog_never_mutates_index(tmp_path, bad):
    p, doc = catalog(tmp_path)
    if bad == "scope": doc["_meta"]["scope"] = "trading"
    if bad == "count": doc["_meta"]["count"] = 1
    if bad == "duplicate": doc["stocks"][-1] = doc["stocks"][0]
    if bad == "row": doc["stocks"][-1]["market"] = "OTC"
    if bad == "small": doc["stocks"] = []; doc["_meta"]["count"] = 0
    p.write_text(json.dumps(doc))
    uni = [{"ticker": "TSM", "name": "preserve"}]
    with pytest.raises(ValueError): s.append_catalog(uni, p)
    assert uni == [{"ticker": "TSM", "name": "preserve"}]


def test_failed_refresh_preserves_previous_file_and_timestamp(tmp_path):
    p, _ = catalog(tmp_path)
    before = p.read_bytes()
    with patch.object(s, "reference_rows", side_effect=ValueError("incomplete")):
        with pytest.raises(ValueError): s.refresh_catalog("test", p)
    assert p.read_bytes() == before


def test_builder_holds_last_index_when_catalog_unavailable(tmp_path):
    from api.builders import krx_mktcap_snapshot as builder
    target = tmp_path / "search.json"
    target.write_text('{"stocks": [{"ticker": "TSM"}]}')
    before = target.read_bytes()
    with patch.object(builder, "_ROOT", str(tmp_path)), patch.object(builder, "UNIVERSE_SEARCH_ALL_PATH", str(target)), \
            patch.object(s, "append_catalog", side_effect=ValueError("missing")):
        builder._build_unified_universe([])
    assert target.read_bytes() == before


def test_monthly_persistence_and_no_new_cron():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/us_smallcap.yml").read_text()
    assert "git add data/us_depositary_search.json" in workflow
    assert "checkout\\n" not in workflow
    assert "cron: '0 2 6 * *'" in workflow
    assert "group: verity-us-smallcap" in workflow
    assert "${{ secrets.POLYGON_API_KEY }}" in workflow
