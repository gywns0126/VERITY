"""TimingSignalWatcher 전이 감지 + 쿨다운 테스트."""
from datetime import datetime, timedelta, timezone

from api.notifications.timing_signal_watcher import detect_transitions

KST = timezone(timedelta(hours=9))


def _rec(ticker, action, score=75, name=None, recommendation="BUY", safety=80):
    return {
        "ticker": ticker,
        "name": name or ticker,
        "recommendation": recommendation,
        "safety_score": safety,
        "price": 70000,
        "currency": "KRW",
        "timing": {
            "action": action,
            "timing_score": score,
            "reasons": [f"{action} reason1", f"{action} reason2"],
        },
    }


def test_hold_to_buy_triggers_alert():
    recs = [_rec("005930", "BUY", score=72)]
    state = {"005930": {"last_action": "HOLD", "last_score": 50, "last_sent_at": None}}

    transitions, new_state = detect_transitions(recs, state=state)

    assert len(transitions) == 1
    assert transitions[0]["ticker"] == "005930"
    assert transitions[0]["from_action"] == "HOLD"
    assert transitions[0]["to_action"] == "BUY"
    assert transitions[0]["significance"] == "enter_buy"
    assert new_state["005930"]["last_sent_at"] is not None


def test_same_action_no_alert():
    recs = [_rec("005930", "BUY", score=72)]
    state = {"005930": {"last_action": "BUY", "last_score": 70, "last_sent_at": None}}
    transitions, _ = detect_transitions(recs, state=state)
    assert transitions == []


def test_cooldown_blocks_repeat():
    now = datetime.now(KST)
    recent = (now - timedelta(hours=1)).isoformat()
    state = {"005930": {"last_action": "HOLD", "last_score": 40, "last_sent_at": recent}}
    recs = [_rec("005930", "BUY")]
    transitions, _ = detect_transitions(recs, state=state, now=now)
    assert transitions == []


def test_cooldown_expires_allows_alert():
    now = datetime.now(KST)
    old = (now - timedelta(hours=5)).isoformat()
    state = {"005930": {"last_action": "HOLD", "last_score": 40, "last_sent_at": old}}
    recs = [_rec("005930", "BUY")]
    transitions, _ = detect_transitions(recs, state=state, now=now)
    assert len(transitions) == 1


def test_held_stock_sell_signal_is_flagged():
    recs = [_rec("005930", "STRONG_SELL", recommendation="WATCH")]
    state = {"005930": {"last_action": "HOLD", "last_score": 50}}
    transitions, _ = detect_transitions(
        recs, held_tickers={"005930"}, state=state,
    )
    assert len(transitions) == 1
    assert transitions[0]["is_held"] is True
    assert transitions[0]["to_action"] == "STRONG_SELL"


def test_non_held_sell_signal_filtered():
    """미보유 종목의 HOLD→SELL은 노이즈로 필터링 (강한 매도가 아닌 경우)."""
    recs = [_rec("005930", "SELL", recommendation="WATCH")]
    state = {"005930": {"last_action": "HOLD", "last_score": 50}}
    transitions, _ = detect_transitions(recs, held_tickers=set(), state=state)
    assert transitions == []


def test_non_held_strong_sell_still_alerts():
    """미보유여도 STRONG_SELL 진입은 알림 (쇼트/워치리스트 감시용)."""
    recs = [_rec("005930", "STRONG_SELL", recommendation="WATCH")]
    state = {"005930": {"last_action": "HOLD", "last_score": 50}}
    transitions, _ = detect_transitions(recs, held_tickers=set(), state=state)
    assert len(transitions) == 1


def test_held_buy_signal_suppressed():
    """이미 보유중인데 BUY 시그널 뜨면 중복이므로 알림 안 함."""
    recs = [_rec("005930", "STRONG_BUY")]
    state = {"005930": {"last_action": "BUY", "last_score": 60}}
    transitions, _ = detect_transitions(recs, held_tickers={"005930"}, state=state)
    assert transitions == []


def test_fresh_state_first_cycle_no_alert_unless_buy():
    """상태 없는 신규 종목: HOLD(기본) → 현재 action 전이가 의미 있을 때만 알림."""
    recs = [_rec("005930", "HOLD")]
    transitions, _ = detect_transitions(recs, state={})
    assert transitions == []


def test_fresh_state_buy_alert():
    recs = [_rec("005930", "STRONG_BUY")]
    transitions, _ = detect_transitions(recs, state={})
    assert len(transitions) == 1
    assert transitions[0]["from_action"] == "HOLD"
    assert transitions[0]["to_action"] == "STRONG_BUY"
