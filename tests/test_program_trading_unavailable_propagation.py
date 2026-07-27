"""프로그램 매매 소스 불가 상태의 하류 전파 — 죽은 소스가 중립 신호로 새는 것 차단.

2026-07-27. collector 는 2026-06-17 부터 소스 불가 시 unavailable=True 로 정직 반환하는데,
_apply_market_structure_override 가 signal/net_bn 만 복사해 market_brain 에는 "NEUTRAL · 0억"
만 남았음 → 프론트/브레인이 실측 중립과 구분 불가. KRX MDCSTAT06401 은 KDM 개편(2025-12-26)
이후 LOGOUT 반환 = 사실상 상시 불가라, 매 run 죽은 0 이 중립 신호로 유입되던 상태.
"""
import pytest

import api.intelligence.verity_brain as VB
from api.collectors.program_trading_collector import _fallback


_EXPIRY = {
    "position_size_cap": 1.0, "watch_level": "NORMAL", "reason": "",
    "days_to_kr_option": 17, "days_to_kr_futures": 45, "days_to_us_quad": 53,
    "next_kr_option": "", "next_kr_futures": "", "next_us_quad": "",
    "chase_buy_allowed": True,
}


@pytest.fixture(autouse=True)
def _stub_expiry(monkeypatch):
    import api.collectors.expiry_calendar as EC
    monkeypatch.setattr(EC, "get_expiry_status", lambda: dict(_EXPIRY))


def _run(program: dict) -> dict:
    result = {"market_brain": {}, "stocks": []}
    VB._apply_market_structure_override(result, {"program_trading": program})
    return result["market_brain"]["program_trading"]


def test_unavailable_propagates_to_market_brain():
    mb = _run(_fallback("20260727", note="KRX bld 거부 (LOGOUT)"))
    assert mb["unavailable"] is True
    # 죽은 소스가 실측 중립으로 위장하지 않아야 함
    assert mb["signal"] != "NEUTRAL"
    assert mb["total_net_bn"] is None
    assert mb["arb_net_bn"] is None and mb["non_arb_net_bn"] is None
    assert mb["status_note"]


def test_ok_false_also_treated_unavailable():
    mb = _run({"ok": False, "signal": "NEUTRAL", "arb_net_bn": 0,
               "non_arb_net_bn": 0, "total_net_bn": 0, "sell_bomb": False})
    assert mb["unavailable"] is True
    assert mb["total_net_bn"] is None


def test_real_reading_passes_through_unchanged():
    mb = _run({"ok": True, "signal": "SELL_PRESSURE", "arb_net_bn": -120,
               "non_arb_net_bn": -800, "total_net_bn": -920,
               "sell_bomb": False, "sell_bomb_reason": None})
    assert mb["unavailable"] is False
    assert mb["signal"] == "SELL_PRESSURE"
    assert mb["total_net_bn"] == -920
    assert mb["arb_net_bn"] == -120


def test_real_neutral_reading_is_distinguishable_from_unavailable():
    """실측 중립(0억)은 그대로 0 — unavailable(None)과 구분 가능해야 함."""
    mb = _run({"ok": True, "signal": "NEUTRAL", "arb_net_bn": 0,
               "non_arb_net_bn": 0, "total_net_bn": 0, "sell_bomb": False})
    assert mb["unavailable"] is False
    assert mb["signal"] == "NEUTRAL"
    assert mb["total_net_bn"] == 0      # None 아님 — 실측 0
