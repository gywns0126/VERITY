"""집행 직전 실시간가 참조 배선 (PM 승인 2026-08-26) — 규칙 무변경 검증.

- check_live_band: E2 밴드(0.02, 등록값) 판정의 가격 입력만 실시간으로 — 임계 불변.
- _live_quotes: 조회 실패 시 빈 dict = 스냅샷 폴백 (집행이 멎지 않는다, 가짜 0 없음).
"""
from __future__ import annotations

from api.trading import auto_trader as at
from api.execution import paper_track as pt


def test_band_constant_is_registered_value():
    # 🚨 E2 = 사전등록 임계. 이 값이 바뀌면 재등록 사안이다.
    assert at.E2_FILL_BAND == 0.02


def test_live_in_band_submits_live_price():
    r = at.check_live_band(101.0, 100.0)
    assert r["ok"] and r["submit_price"] == 101.0 and r["source"] == "live_quote"
    assert abs(r["band_pct"] - 0.01) < 1e-9


def test_live_out_of_band_blocks_no_chase():
    r = at.check_live_band(103.0, 100.0)   # +3% > 2% — 추격 금지
    assert not r["ok"] and r["submit_price"] is None and r["source"] == "live_quote"


def test_live_unavailable_falls_back_to_signal():
    r = at.check_live_band(None, 100.0)
    assert r["ok"] and r["submit_price"] == 100.0
    assert r["source"] == "signal_price_fallback" and r["band_pct"] is None


def test_invalid_signal_blocks():
    assert not at.check_live_band(100.0, 0)["ok"]
    assert not at.check_live_band(100.0, -1)["ok"]


def test_band_boundary_exact_2pct_passes():
    # 경계 포함(≤) — 초과만 차단. 등록 문언 "±2% 밴드" 정합.
    r = at.check_live_band(102.0, 100.0)
    assert r["ok"] and r["submit_price"] == 102.0


def test_live_quotes_failure_returns_empty(monkeypatch):
    # KIS 미구성/예외 = 빈 dict → 호출부 스냅샷 폴백 (Number||0 류 가짜 값 금지)
    class _Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("no token")
    import api.trading.kis_broker as kb
    monkeypatch.setattr(kb, "KISBroker", _Boom)
    assert pt._live_quotes(["005930"]) == {}
    assert pt._live_quotes([]) == {}


def test_live_quotes_reads_configured_property(monkeypatch):
    """KISBroker.is_configured is a property, not a callable."""
    class _Configured:
        def __init__(self, *a, **k):
            self.is_configured = True

        def get_current_price(self, ticker):
            return {"stck_prpr": "71200" if ticker == "005930" else "0"}

    import api.trading.kis_broker as kb
    monkeypatch.setattr(kb, "KISBroker", _Configured)
    assert pt._live_quotes(["005930", "003550"]) == {"005930": 71200.0}
