"""September 2026 research migration and outage regression tests (no network/LLM)."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from api.collectors import ReportScout as scout
from api.collectors import dividend_ksd as ksd
from scripts import freshness_shadow_monitor as freshness
from scripts import cron_health_monitor as health

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 16, 13, tzinfo=KST)


def response(payload=None, url="https://stock.naver.com/research/company"):
    return SimpleNamespace(url=url, json=lambda: payload, raise_for_status=lambda: None)


def item(nid="96155", **extra):
    return {"nid": nid, "itemCode": "373220", "itemName": "LG에너지솔루션",
            "writeDate": "2026-09-15", "title": "실적 리포트", "brokerName": "증권사",
            "goalPrice": "510000", "opinionText": "매수", **extra}


@pytest.fixture
def fast_scout(monkeypatch):
    monkeypatch.setattr(scout.time, "sleep", lambda _: None)
    monkeypatch.setattr(scout, "_resolve_ticker_to_yf", lambda tk: tk + ".KS")


@pytest.mark.parametrize("kind", ["company", "industry"])
def test_redirect_routes_to_new_api(kind, monkeypatch, fast_scout):
    pdf = "https://stock.pstatic.net/stock-research/company/example.pdf"
    get = Mock(side_effect=[response(), response({"items": [item()], "hasNext": False}),
                           response({"nid": "96155", "attachUrl": pdf})])
    monkeypatch.setattr(scout, "_SESSION", SimpleNamespace(get=get))
    records = getattr(scout, f"fetch_naver_{kind}_reports")("2026-09-09", "2026-09-16")
    assert len(records) == 1
    assert records[0]["pdf_url"] == pdf
    assert records[0]["date"] == "2026-09-15"
    assert records[0]["read_url"].endswith(f"/{kind}/96155")
    if kind == "company":
        assert records[0]["ticker"] == "373220"
        assert records[0]["target_price"] == 510000
    assert get.call_args_list[1].kwargs["params"]["index"] == 0


def test_pagination_dedup_dates_and_cap(monkeypatch, fast_scout):
    get = Mock(side_effect=[
        response({"items": [item(), item(), item("2", writeDate="2020-01-01"),
                             item("3", writeDate="bad"), None], "hasNext": True}),
        response({"nid": "96155", "attachUrl": "https://example.com/a.pdf"}),
        response({"items": [item(), item("4")], "hasNext": True}),
        response({"nid": "4", "attachUrl": "https://example.com/b.pdf"}),
    ])
    monkeypatch.setattr(scout, "_SESSION", SimpleNamespace(get=get))
    rows = scout._fetch_naver_research_api("company", "2026-09-09", "2026-09-16", 2)
    assert [r["source_record_id"] for r in rows] == ["96155", "4"]
    assert get.call_count == 4
    assert get.call_args_list[2].kwargs["params"]["index"] == 1


@pytest.mark.parametrize("detail", [
    {"nid": "wrong", "attachUrl": "https://example.com/a.pdf"},
    {"nid": "96155", "attachUrl": "https://example.com/landing"},
    {"nid": "96155", "attachUrl": "file:///tmp/a.pdf"},
    requests.Timeout(),
])
def test_bad_detail_is_not_a_pdf(detail, monkeypatch, fast_scout):
    get = Mock(side_effect=[response({"items": [item()], "hasNext": False}),
                           detail if isinstance(detail, Exception) else response(detail)])
    monkeypatch.setattr(scout, "_SESSION", SimpleNamespace(get=get))
    rows = scout._fetch_naver_research_api("company", "2026-09-09", "2026-09-16", 1)
    assert len(rows) == 1 and rows[0]["pdf_url"] is None


def test_empty_collection_keeps_prior_input(tmp_path, monkeypatch):
    path = tmp_path / "input.json"
    path.write_text('{"old":true}')
    monkeypatch.setattr(scout, "OUTPUT_PATH", str(path))
    for name in ("fetch_naver_company_reports", "fetch_naver_industry_reports", "fetch_kirs_reports"):
        monkeypatch.setattr(scout, name, lambda *args: [])
    forbidden = Mock(side_effect=AssertionError("retired source must not be polled"))
    monkeypatch.setattr(scout, "fetch_hankyung_reports", forbidden)
    result = scout.scout_reports.__wrapped__()
    assert result["collection_status"] == "failed_no_company_reports"
    assert path.read_text() == '{"old":true}'
    forbidden.assert_not_called()


def test_retired_summary_stream_is_not_monitored(tmp_path, monkeypatch):
    manifest = ROOT / "data" / "freshness_sla.json"
    monkeypatch.setattr(freshness, "MANIFEST", str(manifest))
    monkeypatch.setattr(freshness, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(freshness, "now_kst", lambda: NOW)
    (tmp_path / "report_summaries.json").write_text(json.dumps({
        "updated_at": "2026-09-10T18:10:51+09:00"}))
    obs = freshness.build_observations()
    row = next(r for r in obs["rows"] if r["id"] == "report_summaries")
    assert row["status"] == "skip_inactive"
    monkeypatch.setattr(health, "_SLA_PATH", str(manifest))
    assert "analyst_reports.yml" not in health._workflow_stream_map()


@pytest.mark.parametrize("state", ["transport_error", "transient_http_error"])
def test_ksd_page_retries_without_duplicate_rows(state, monkeypatch):
    calls = []
    def call(bas_dt, page, rows, tmo=None):
        calls.append(page)
        if calls == [1, 2]:
            monkeypatch.setattr(ksd, "_LAST_CALL_STATE", state)
            return None, []
        return (3, [{"id": 1}, {"id": 2}]) if page == 1 else (3, [{"id": 3}])
    monkeypatch.setattr(ksd, "_PAGE_SIZE", 2)
    monkeypatch.setattr(ksd, "_call", call)
    monkeypatch.setattr(ksd.time, "sleep", lambda _: None)
    assert ksd.fetch_all("20260915") == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert calls == [1, 2, 2]


@pytest.mark.parametrize("state,attempts", [("transport_error", 3), ("auth_or_parse_error", 1)])
def test_ksd_persistent_error_preserves_ledger(state, attempts, tmp_path, monkeypatch):
    path = tmp_path / "ledger.json"
    path.write_text('{"prior":"ledger"}')
    monkeypatch.setattr(ksd, "_LEDGER_PATH", str(path))
    monkeypatch.setattr(ksd, "PUBLIC_DATA_API_KEY", "test-only")
    monkeypatch.setattr(ksd, "discover_bas_dt", lambda: "20260915")
    monkeypatch.setattr(ksd, "_LAST_CALL_STATE", state)
    monkeypatch.setattr(ksd.time, "sleep", lambda _: None)
    call = Mock(return_value=(None, []))
    monkeypatch.setattr(ksd, "_call", call)
    with pytest.raises(RuntimeError, match="페이징 중단"):
        ksd.collect()
    assert call.call_count == attempts
    assert path.read_text() == '{"prior":"ledger"}'


def test_ksd_retry_budget_is_bounded(monkeypatch):
    clock = iter([0, 0, 0, 539])
    monkeypatch.setattr(ksd.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(ksd, "_BUDGET_SEC", 540)
    monkeypatch.setattr(ksd, "_LAST_CALL_STATE", "transport_error")
    call = Mock(return_value=(None, []))
    monkeypatch.setattr(ksd, "_call", call)
    sleep = Mock()
    monkeypatch.setattr(ksd.time, "sleep", sleep)
    with pytest.raises(RuntimeError, match="페이징 중단"):
        ksd.fetch_all("20260915")
    assert call.call_count == 1
    sleep.assert_not_called()
