"""Regression cases for September 2026 source migration and silent local failures."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.collectors import ReportScout as scout


ROOT = Path(__file__).resolve().parents[1]


def load_script(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def response(payload=None, url="https://stock.naver.com/research/company"):
    return SimpleNamespace(url=url, raise_for_status=lambda: None, json=lambda: payload)


def test_redirected_research_preserves_dates_codes_and_pdf_identity(monkeypatch):
    calls = []
    pages = [
        {"hasNext": True, "items": [
            {"nid": "101", "writeDate": "2026-09-11", "itemCode": "0017J0",
             "itemName": "Example", "title": "Research", "brokerName": "Broker",
             "goalPrice": "88,000", "readCount": "25"},
            {"nid": "102", "writeDate": "2026-08-01", "itemCode": "005930"},
        ]},
        {"hasNext": False, "items": [
            {"nid": "101", "writeDate": "2026-09-11", "itemCode": "0017J0"},
            {"nid": "103", "writeDate": "2026-09-10", "itemCode": "005930"},
        ]},
    ]

    def get(url, **kwargs):
        calls.append((url, kwargs))
        if url == scout.NAVER_COMPANY_LIST:
            return response()
        if url.endswith("/company"):
            return response(pages[kwargs["params"]["index"]])
        nid = url.rsplit("/", 1)[-1]
        return response({"nid": nid, "attachUrl": (
            "https://stock.pstatic.net/research/example.pdf?download=1"
            if nid == "101" else "https://broker.example/report-view")})

    monkeypatch.setattr(scout._SESSION, "get", get)
    monkeypatch.setattr(scout.time, "sleep", lambda _: None)
    monkeypatch.setattr(scout, "_resolve_ticker_to_yf", lambda _: None)
    rows = scout.fetch_naver_company_reports("2026-09-06", "2026-09-12", 5)
    assert len(rows) == 2
    assert rows[0]["date"] == "2026-09-11"
    assert rows[0]["ticker"] == "0017J0"
    assert rows[0]["pdf_url"].endswith(".pdf?download=1")
    assert rows[0]["target_price"] == 88000
    assert rows[1]["pdf_url"] is None
    assert rows[1]["read_url"].endswith("/103")
    assert not any(url.endswith("/102") for url, _ in calls)
    assert len(calls) == 5  # redirect, two pages, two in-window unique details


def test_industry_uses_published_sector_and_rejects_wrong_detail(monkeypatch):
    def get(url, **kwargs):
        if url == scout.NAVER_INDUSTRY_LIST:
            return response(url="https://stock.naver.com/research/industry")
        if url.endswith("/industry"):
            return response({"hasNext": False, "items": [{
                "nid": "20", "writeDate": "2026-09-11", "industryKoreanName": "기계",
            }]})
        return response({"nid": "21", "attachUrl": "https://example.com/wrong.pdf"})

    monkeypatch.setattr(scout._SESSION, "get", get)
    monkeypatch.setattr(scout.time, "sleep", lambda _: None)
    rows = scout.fetch_naver_industry_reports("2026-09-06", "2026-09-12", 1)
    assert rows[0]["sector"] == "기계"
    assert rows[0]["pdf_url"] is None


def test_scout_outage_preserves_prior_input(monkeypatch, tmp_path):
    artifact = tmp_path / "analyst_reports.json"
    original = '{"updated_at":"old","company_reports":[{"ticker":"005930"}]}'
    artifact.write_text(original)
    monkeypatch.setattr(scout, "OUTPUT_PATH", str(artifact))
    for name in ("fetch_naver_company_reports", "fetch_naver_industry_reports", "fetch_kirs_reports"):
        monkeypatch.setattr(scout, name, lambda *a, **k: [])
    monkeypatch.setattr(scout, "fetch_hankyung_reports", lambda *a, **k: pytest.fail("retired source called"))
    result = scout.scout_reports.__wrapped__("2026-09-06", "2026-09-12", 1)
    assert result["collection_status"] == "failed_no_company_reports"
    assert artifact.read_text() == original


def test_runner_does_not_summarize_preserved_stale_input(monkeypatch):
    runner = load_script("incident_reports", "scripts/analyst_reports_cron.py")
    monkeypatch.setattr(runner, "VERITY_MODE", "prod")
    monkeypatch.setattr(runner, "_collect_with_retry", lambda: ({}, {}, 0))
    monkeypatch.setattr(runner, "run_report_summarizer", lambda **k: pytest.fail("old input reused"))
    assert runner.main() == 1


def test_sparse_corner_reads_canonical_git_blob_without_checkout(monkeypatch, tmp_path):
    runner = load_script("incident_corner", "scripts/kr/smallcap_corner_daily.py")
    monkeypatch.setattr(runner, "DATA_DIR", str(tmp_path))
    calls = []

    def read(cmd, **kwargs):
        calls.append(cmd)
        return json.dumps({"stocks": [{"ticker": "005930"}]})

    monkeypatch.setattr(runner.subprocess, "check_output", read)
    assert runner._corner_stocks() == [{"ticker": "005930"}]
    assert calls[0][-2:] == ["show", "origin/main:data/smallcap_corner.json"]
    assert not (tmp_path / "smallcap_corner.json").exists()


def test_failed_lake_update_cannot_generate_stale_forward_predictions(monkeypatch):
    runner = load_script("incident_lake", "scripts/kr/smallcap_corner_daily.py")
    monkeypatch.setattr(runner.sys, "argv", ["smallcap_corner_daily.py"])
    monkeypatch.setattr(runner, "_corner_stocks", lambda: [{"ticker": "005930"}])

    def fail(*args):
        raise RuntimeError("source unavailable")

    monkeypatch.setattr(runner, "update_lake_incremental", fail)
    monkeypatch.setattr(runner, "generate_trail", lambda: pytest.fail("stale trail generated"))
    monkeypatch.setattr(runner, "_mark_run", lambda: pytest.fail("failed run marked successful"))
    assert runner.main() == 1


@pytest.mark.parametrize("published, expected", [(True, 0), (False, 1)])
def test_heartbeat_propagates_publish_outcome(monkeypatch, tmp_path, published, expected):
    runner = load_script("incident_heartbeat", "scripts/local_lake_heartbeat.py")
    monkeypatch.setattr(runner, "OUT", str(tmp_path / "health.json"))
    monkeypatch.setattr(runner.sys, "argv", ["local_lake_heartbeat.py", "--publish"])
    monkeypatch.setattr(runner, "build", lambda: {"artifacts": []})
    monkeypatch.setattr(runner, "_publish_to_main", lambda: published)
    assert runner.main() == expected
