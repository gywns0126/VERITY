# -*- coding: utf-8 -*-
"""심층분석 지명 로테이션 (PREREG_ANALYSIS_ROTATION_2026_08_12)."""
import json

from api.analyzers import stock_filter as SF


def _pool(n, currency="KRW", pct=0.5, prefix="T"):
    return [{"ticker": f"{prefix}{i:03d}", "name": f"{prefix}{i}", "currency": currency,
             "safety_score": i, "safety_pct": pct, "per": 10, "debt_ratio": 30,
             "operating_margin": 10} for i in range(n)]


def _wire(tmp_path, monkeypatch, state=None):
    sp = tmp_path / "state.json"
    lp = tmp_path / "log.jsonl"
    if state is not None:
        sp.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(SF, "_ROTATION_STATE_PATH", str(sp))
    monkeypatch.setattr(SF, "_ROTATION_LOG_PATH", str(lp))
    return sp


def test_cold_start_ticker_asc_and_state_written(tmp_path, monkeypatch):
    sp = _wire(tmp_path, monkeypatch)
    kr = _pool(30)
    top = SF.nominate_for_analysis(kr, market_scope="all")
    assert len(top) == SF.FILTER_KR_TOP_N
    assert [s["ticker"] for s in top] == sorted(s["ticker"] for s in kr)[:SF.FILTER_KR_TOP_N]
    doc = json.loads(sp.read_text(encoding="utf-8"))
    assert len(doc["tickers"]) == SF.FILTER_KR_TOP_N        # 지명분만 기록


def test_staleness_rotation_cycles(tmp_path, monkeypatch):
    """어제 지명된 종목은 미분석 종목보다 뒤로 — 순환이 실제로 돈다."""
    kr = _pool(30)
    yesterday = {s["ticker"]: "2026-08-11" for s in kr[:SF.FILTER_KR_TOP_N]}
    _wire(tmp_path, monkeypatch, {"updated_at": "2026-08-11", "tickers": yesterday})
    top = SF.nominate_for_analysis(kr, market_scope="all")
    assert not ({s["ticker"] for s in top} & set(yesterday))   # 어제 본 것 재지명 0


def test_gate_respected(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    kr = _pool(30)
    for s in kr[:20]:
        s["safety_pct"] = 0.05          # 하위 20% — 게이트 컷
    top = SF.nominate_for_analysis(kr, market_scope="all")
    assert all(s["safety_pct"] >= 0.20 for s in top)
    assert len(top) == SF.FILTER_KR_TOP_N


def test_dead_state_falls_back_to_legacy(tmp_path, monkeypatch):
    """상태 파일 미갱신 = 배선 사망 → 구 지명(안심상위) 자동 복귀 (§4)."""
    _wire(tmp_path, monkeypatch, {"updated_at": "2026-01-01", "tickers": {}})
    kr = _pool(30)
    top = SF.nominate_for_analysis(kr, market_scope="all")
    scores = [s["safety_score"] for s in top]
    assert scores == sorted(scores, reverse=True)              # 안심상위 = 구 지명
    assert scores[0] == 29


def test_market_quotas(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    both = _pool(30) + _pool(30, currency="USD", prefix="U")
    top = SF.nominate_for_analysis(both, market_scope="all")
    kr = [s for s in top if s["currency"] != "USD"]
    us = [s for s in top if s["currency"] == "USD"]
    assert len(kr) == SF.FILTER_KR_TOP_N and len(us) == SF.FILTER_US_TOP_N


def test_no_pct_pool_falls_back(tmp_path, monkeypatch):
    """게이트 판정 불가(pct 전부 None) — 지어내지 않고 구 지명 폴백."""
    _wire(tmp_path, monkeypatch)
    kr = _pool(30, pct=None)
    for s in kr:
        s["safety_pct"] = None
    top = SF.nominate_for_analysis(kr, market_scope="all")
    scores = [s["safety_score"] for s in top]
    assert scores == sorted(scores, reverse=True)
