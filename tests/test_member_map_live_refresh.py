import importlib.util
import json
from pathlib import Path

import pytest

from api.collectors.member_map_live_refresh import (
    apply_result, due, overlay_sources, overlay_states, read_state, save_source, news_result)
from api.intelligence.portfolio_public_sources import project_public_sources

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("live_refresh_runner", ROOT / "scripts/member-map/run-live-refresh.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
NOW = "2026-10-12T01:00:00+00:00"
ROW = {"ticker": "005930", "name": "삼성전자", "title": "신규 공시",
       "date": "2026-10-12", "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20261012000001",
       "source": "DART", "date_precision": "date", "observed_at": NOW}


def result(status="success"):
    return {"status": status, "complete": status == "success", "records": [ROW],
            "cursor": {"through_date": "2026-10-12"}, "coverage": {"whole_market_coverage": False}}


def test_partial_retains_cursor_but_keeps_observed_facts():
    prior = {"cursor": {"old": True}, "last_success_at": "2026-10-12T00:00:00+00:00"}
    state = apply_result("DART", prior, result("partial"), NOW)
    assert state["cursor"] == prior["cursor"]
    assert state["last_success_at"] == prior["last_success_at"]
    assert state["feed"]["items"][0]["disclosures"][0]["title"] == "신규 공시"
    assert state["health"]["status"] == "delayed"
    assert not state["screen_delivery_verified"]


def test_empty_success_advances_health_not_document_date():
    state = apply_result("DART", {}, {**result(), "records": []}, NOW)
    assert state["feed"] == {"items": []}
    assert state["last_success_at"] == NOW
    assert state["health"]["status"] == "on-time"


def test_restart_cursor_feed_are_atomic_and_failure_preserves(tmp_path):
    path = tmp_path / "state.sqlite3"
    state = apply_result("DART", {}, result(), NOW)
    save_source(path, "DART", state)
    loaded = read_state(path)["DART"]
    assert loaded == state
    failed = apply_result("DART", loaded, {"status": "error", "complete": False}, NOW)
    assert failed["feed"] == loaded["feed"]
    assert failed["cursor"] == loaded["cursor"]
    assert path.stat().st_mode & 0o777 == 0o600


def test_independent_cadence_and_no_rapid_retry():
    assert due("SEC", {}, NOW)
    for source in ("DART", "SEC", "news"):
        assert not due(source, {"last_attempt_at": NOW}, NOW)
    prior = {"last_attempt_at": "2026-10-12T00:57:59+00:00"}
    assert due("SEC", prior, NOW)
    assert not due("news", prior, NOW)


def test_memory_and_sqlite_overlay_are_equivalent_and_leave_inputs_unchanged(tmp_path):
    path = tmp_path / "state.sqlite3"
    current = apply_result("DART", {}, result(), NOW)
    save_source(path, "DART", current)
    docs = {"public_disclosure_feed.json": {"items": []}}
    before = json.dumps(current, sort_keys=True)
    assert overlay_states(docs, {"DART": current}) == overlay_sources(docs, path)
    assert docs == {"public_disclosure_feed.json": {"items": []}}
    assert json.dumps(current, sort_keys=True) == before


def test_snapshot_merges_baseline_and_projects_as_disclosure_not_relation(tmp_path):
    path = tmp_path / "state.sqlite3"
    save_source(path, "DART", apply_result("DART", {}, result(), NOW))
    docs = {"universe_search.json": {"stocks": [{"ticker": "005930", "name": "삼성전자", "market": "KOSPI"}]},
            "stock_report_public.json": {"stocks": []}, "us_stock_report_public.json": {"stocks": []},
            "public_disclosure_feed.json": {"items": [{"ticker": "000660", "name": "SK하이닉스", "disclosures": []}]},
            "us_disclosure_feed.json": {"items": []}, "member_map_ai_candidates.json": {"sentinel": "unchanged"}}
    merged = overlay_sources(docs, path)
    assert len(merged["public_disclosure_feed.json"]["items"]) == 2
    assert len(docs["public_disclosure_feed.json"]["items"]) == 1
    assert merged["member_map_ai_candidates.json"] is docs["member_map_ai_candidates.json"]
    projected = project_public_sources(merged)
    row = next(c for c in projected["companies"] if c["ticker"] == "005930")
    assert row["documents"][0]["title"] == "신규 공시"
    assert row["documents"][0]["as_of"] == "2026-10-12"


@pytest.mark.skipif(
    not (ROOT / "api/intelligence/portfolio_market_context.py").is_file(),
    reason="뉴스 의존 모듈이 포함되지 않는 DART 전용 패키지에서는 뉴스 투영 검사를 생략한다.",
)
def test_news_projection_drops_sentiment_and_private_fields(monkeypatch):
    from api.collectors import news_headlines as news
    rows = [{"title": "삼성전자 공장 가동", "source": "Reuters", "time": NOW,
             "link": "https://www.reuters.com/test", "sentiment": "positive", "member_id": "secret"}]
    monkeypatch.setattr(news, "collect_headlines", lambda **_: rows)
    monkeypatch.setattr(news, "collect_bloomberg_google_news_rss", lambda **_: [])
    monkeypatch.setattr(news, "collect_us_headlines", lambda *_, **kw: [])
    actual = news_result()
    assert actual["status"] == "partial" and not actual["complete"]
    assert set(actual["feed"]["headlines"][0]) == {"title", "source", "time", "link"}


def test_cycle_source_failure_does_not_stop_other_source(tmp_path):
    def failure(*_):
        raise RuntimeError("do not expose remote message or key")
    summary = runner.cycle(tmp_path / "state.sqlite3", {"DART": lambda *_: result(), "SEC": failure}, NOW)
    assert summary["DART"]["status"] == "success"
    assert summary["SEC"]["error"] == "collection-failed"
    assert "do not expose" not in json.dumps(summary)


def test_symlink_state_rejected(tmp_path):
    target = tmp_path / "real"
    target.write_text("preserve")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        save_source(link, "DART", {})
    assert target.read_text() == "preserve"


@pytest.mark.skipif(
    not (ROOT / "scripts/member_map_local_server.py").is_file(),
    reason="로컬 검수 서버가 포함되지 않는 패키지에서는 로컬 화면 통합 검사를 생략한다.",
)
def test_map_consumer_hot_reload_new_facts_without_ai(tmp_path):
    from scripts.member_map_local_server import PublicReview
    html = '<html><head><meta content="connect-src blob: data:;"></head><body><iframe sandbox="allow-scripts"></iframe><script id="alphanest-local-public-data">{}</script></body></html>'
    path = tmp_path / "state.sqlite3"
    docs = {"universe_search.json": {"stocks": [{"ticker": "005930", "name": "삼성전자", "market": "KOSPI"}]}}
    review = PublicReview(html, docs, live_state_db=path)
    before = review.analyze({"positions": [{"ticker": "005930", "market": "KR"}]}, public_refresh=False)
    save_source(path, "DART", apply_result("DART", {}, result(), NOW))
    after = review.analyze({"positions": [{"ticker": "005930", "market": "KR"}]}, public_refresh=False)
    assert before["revision"] != after["revision"]
    assert "신규 공시" in json.dumps(after, ensure_ascii=False)
    assert review.sources["public_disclosure_feed.json"]["items"][0]["ticker"] == "005930"
    assert 'sandbox="allow-scripts"' in review.html.decode()
    old_revision = review.revision
    failed = apply_result("DART", read_state(path)["DART"], {"status": "error"}, "2026-10-12T01:02:00+00:00")
    save_source(path, "DART", failed)
    review.analyze({"positions": [{"ticker": "005930", "market": "KR"}]}, public_refresh=False)
    assert review.revision == old_revision
