"""
모닝 브리핑 Claude 전략 코멘트 신선도 게이트 회귀 테스트.

2026-06-05 사고: generate_morning_strategy 가 None 을 반환하면 STEP 10.7 이 옛 blob 을
덮어쓰지 못하고, load_portfolio() carry-forward 로 stale 환각 blob (삼성 65,000원 지지선
/ VIX 19.23 / 환율 1482.7) 이 매 아침 재전송됨 — 동일 환각 3차 surface.

게이트: send_morning_briefing 은 generated_at 가 없거나 20h 초과면 전략 코멘트 섹션을 생략.
"""
from datetime import timedelta
from datetime import datetime
from copy import deepcopy

import pytest

from api.config import now_kst
import api.notifications.telegram as tg
from api.builders import daily_briefing_builder as builder
from api.builders import briefing_timeline as timeline


def _capture(monkeypatch):
    sent = {}

    def fake_send(text, *a, **k):
        sent["text"] = text
        return True

    monkeypatch.setattr(tg, "send_message", fake_send)
    return sent


def _portfolio_with_strategy(generated_at):
    ms = {
        "scenario": "삼성전자 70점 고점신호 속 65,000원 지지선 테스트 후 반등 가능성",
        "watch_points": ["삼성전자 수급 변화", "환율 민감도"],
        "risk_note": "보유 삼성전자 -2.1% 손실 부담",
        "top_pick_comment": "삼성전자 메모리 업사이클 기대감",
    }
    if generated_at is not None:
        ms["generated_at"] = generated_at
    return {
        "macro": {"market_mood": {"label": "중립", "score": 50}, "usd_krw": {}, "vix": {}},
        "vams": {"total_return_pct": 0, "holdings": []},
        "claude_morning_strategy": ms,
    }


def test_stale_strategy_no_generated_at_is_suppressed(monkeypatch):
    """gen_at=None (pre-fix / 재생성 실패 carry-forward) — 코멘트 섹션 생략."""
    sent = _capture(monkeypatch)
    tg.send_morning_briefing(_portfolio_with_strategy(generated_at=None))
    assert "Claude 전략 코멘트" not in sent["text"]
    assert "65,000원" not in sent["text"]


def us_macro_rows():
    return {"macro": {
        "sp500": {"value": 7773.95, "change_pct": 0.66, "status": "ok", "source": "fred",
                  "as_of": "2026-10-06T23:32:57+09:00"},
        "nasdaq": {"value": 27477.31, "change_pct": 1.05, "status": "ok", "source": "fred",
                   "as_of": "2026-10-06T23:32:57+09:00"},
        "dji": {"value": 51267.9, "change_pct": 0.18, "status": "ok", "source": "fred",
                "as_of": "2026-10-06T23:32:58+09:00"},
        "sox": {"value": 13313.28, "change_pct": 1.07, "status": "ok", "source": "yfinance",
                "data_date": "20261006", "as_of": "2026-10-06T23:32:58+09:00"},
    }}


def test_us_index_observations_do_not_infer_a_close_or_date_from_session(monkeypatch):
    doc = us_macro_rows()
    original = deepcopy(doc)
    monkeypatch.setattr(builder, "_load", lambda *args: doc)
    observed = builder._us_market_item(datetime.fromisoformat("2026-10-06T23:40:00+09:00"))
    assert observed["country"] == "US" and "as_of" not in observed
    assert len(observed["values"]) == 8
    assert observed["values"]["sox_close"] == 13313.28
    assert observed["index_meta"]["sox"]["data_date"] == "2026-10-06"
    for key in ("sp500", "nasdaq", "dji"):
        meta = observed["index_meta"][key]
        assert "data_date" not in meta
        assert meta["collected_at"] == meta["as_of"] == doc["macro"][key]["as_of"]
    # The observation is during NY core hours, and is still only an index value.
    for at in ("2026-10-06T23:40:00+09:00", "2026-10-07T08:00:00+09:00"):
        assert builder._us_market_item(datetime.fromisoformat(at)) == observed
    assert doc == original


@pytest.mark.parametrize("override", [
    {"status": "error"}, {"source": "unknown"}, {"value": True}, {"value": 0},
    {"value": float("nan")}, {"change_pct": float("inf")}, {"change_pct": None},
    {"as_of": "2026-10-06T23:00:00"}, {"as_of": "2026-10-07T23:00:00+09:00"},
    {"data_date": "20261007"}, {"data_date": "not-a-date"},
])
def test_invalid_us_measurements_are_omitted_without_filling_values(monkeypatch, override):
    row = {**us_macro_rows()["macro"]["sp500"], **override}
    monkeypatch.setattr(builder, "_load", lambda *args: {"macro": {"sp500": row}})
    assert builder._us_market_item(datetime.fromisoformat("2026-10-06T23:40:00+09:00")) is None


def test_us_date_is_only_shared_when_every_source_explicitly_supplies_it(monkeypatch):
    doc = us_macro_rows()
    for row in doc["macro"].values():
        row["data_date"] = "20261006"
    monkeypatch.setattr(builder, "_load", lambda *args: doc)
    now = datetime.fromisoformat("2026-10-06T23:40:00+09:00")
    assert builder._us_market_item(now)["as_of"] == "2026-10-06"
    doc["macro"]["sp500"]["data_date"] = "20261005"
    assert "as_of" not in builder._us_market_item(now)
    doc["macro"]["sp500"].pop("data_date")
    assert "as_of" not in builder._us_market_item(now)


def test_us_source_future_date_is_checked_against_ny_date_not_kst(monkeypatch):
    row = {**us_macro_rows()["macro"]["sox"], "data_date": "20261007"}
    monkeypatch.setattr(builder, "_load", lambda *args: {"macro": {"sox": row}})
    assert builder._us_market_item(datetime.fromisoformat("2026-10-07T00:10:00+09:00")) is None


def test_builder_actual_run_writes_separate_market_days_and_keeps_source_provenance(tmp_path, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat("2026-10-07T00:30:00+09:00").astimezone(tz)

    monkeypatch.setattr(builder, "datetime", Clock)
    monkeypatch.setattr(timeline, "ARCHIVE_DIR", tmp_path / "days")
    monkeypatch.setattr(builder, "OUT_PATH", str(tmp_path / "latest.json"))
    monkeypatch.setattr(builder, "HIST_PATH", str(tmp_path / "history.jsonl"))
    monkeypatch.setattr(builder, "_names", lambda: {"AAPL": "test"})
    monkeypatch.setattr(builder, "_load", lambda path, default: us_macro_rows() if path == builder.MACRO_PATH else {})
    for name in ("_sec_us_filings", "_sec_earnings", "_sec_disclosures", "_sec_insider", "_sec_flow"):
        monkeypatch.setattr(builder, name, lambda *args: {"title": "empty", "items": []})
    assert builder.main() == 0
    import json
    kr = json.loads((tmp_path / "days" / "2026-10-07.json").read_text())
    us = json.loads((tmp_path / "days" / "us" / "2026-10-06.json").read_text())
    latest = json.loads((tmp_path / "latest.json").read_text())
    assert kr["snapshots"][0]["phase"] == "pre"
    assert us["snapshots"][0]["phase"] == "open"
    assert latest["date"] == "2026-10-07"
    row = us["snapshots"][0]["items"][0]
    assert row["as_of"] == "" and row["country"] == "US"
    assert row["index_meta"]["sox"]["data_date"] == "2026-10-06"
    assert "data_date" not in row["index_meta"]["sp500"]


def test_stale_strategy_3days_old_is_suppressed(monkeypatch):
    """72h 전 frozen blob — 코멘트 섹션 생략."""
    sent = _capture(monkeypatch)
    old = (now_kst() - timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    tg.send_morning_briefing(_portfolio_with_strategy(generated_at=old))
    assert "Claude 전략 코멘트" not in sent["text"]


def test_fresh_strategy_last_evening_is_rendered(monkeypatch):
    """어젯밤 12h 전 정상 생성분 — 코멘트 섹션 포함."""
    sent = _capture(monkeypatch)
    fresh = (now_kst() - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    tg.send_morning_briefing(_portfolio_with_strategy(generated_at=fresh))
    assert "Claude 전략 코멘트" in sent["text"]


def test_future_timestamp_is_suppressed(monkeypatch):
    """미래 timestamp (시계 오류) — 코멘트 섹션 생략 (음수 age 거부)."""
    sent = _capture(monkeypatch)
    future = (now_kst() + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    tg.send_morning_briefing(_portfolio_with_strategy(generated_at=future))
    assert "Claude 전략 코멘트" not in sent["text"]
