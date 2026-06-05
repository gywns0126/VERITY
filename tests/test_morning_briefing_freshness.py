"""
모닝 브리핑 Claude 전략 코멘트 신선도 게이트 회귀 테스트.

2026-06-05 사고: generate_morning_strategy 가 None 을 반환하면 STEP 10.7 이 옛 blob 을
덮어쓰지 못하고, load_portfolio() carry-forward 로 stale 환각 blob (삼성 65,000원 지지선
/ VIX 19.23 / 환율 1482.7) 이 매 아침 재전송됨 — 동일 환각 3차 surface.

게이트: send_morning_briefing 은 generated_at 가 없거나 20h 초과면 전략 코멘트 섹션을 생략.
"""
from datetime import timedelta

from api.config import now_kst
import api.notifications.telegram as tg


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
