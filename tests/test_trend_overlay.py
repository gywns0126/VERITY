"""trend_overlay — A1 200MA 추세 게이트 SHADOW 테스트 (2026-06-15).

게이트 판정(close vs 200SMA) + shadow 격리 + caveat 박제 검증. yfinance 무의존(합성).
"""
import api.intelligence.trend_overlay as to


def test_gate_risk_on_above_sma():
    closes = [100.0] * 199 + [120.0]   # SMA≈100.1, 현재 120 > SMA
    g = to._gate_state(closes)
    assert g["status"] == "ok"
    assert g["gate"] == "risk_on"
    assert g["shadow_equity_exposure"] == 1.0
    assert g["gap_pct"] > 0


def test_gate_defensive_below_sma():
    closes = [100.0] * 199 + [80.0]    # 현재 80 < SMA
    g = to._gate_state(closes)
    assert g["gate"] == "defensive"
    assert g["shadow_equity_exposure"] == 0.0
    assert g["gap_pct"] < 0


def test_gate_insufficient_history():
    g = to._gate_state([100.0] * 150)
    assert g["status"] == "insufficient"
    assert g["need"] == 200


def test_sma_uses_last_200():
    # 오래된 값은 SMA 에 안 들어감 — 최근 200개만
    closes = [1.0] * 100 + [100.0] * 200 + [100.0]
    g = to._gate_state(closes)
    assert abs(g["sma200"] - 100.0) < 0.01  # 최근 200 = 전부 100


def test_compute_carries_caveat(monkeypatch):
    # fetch 를 합성으로 대체 (yfinance 무의존)
    monkeypatch.setattr(to, "_fetch_closes", lambda yf: [100.0] * 199 + [110.0])
    r = to.compute_overlay()
    assert "오버레이" in r["caveat"]
    assert "공짜 알파" in r["caveat"]  # 포지셔닝 명시 필수
    assert r["indices"]["kospi"]["gate"] == "risk_on"
    assert r["indices"]["sp500"]["gate"] == "risk_on"


def test_run_shadow_brain_input_false(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(to, "_fetch_closes", lambda yf: [100.0] * 199 + [90.0])
    monkeypatch.setattr(to, "SHADOW_OUT", str(tmp_path / "trend.jsonl"))
    to.run_shadow()
    entry = json.loads((tmp_path / "trend.jsonl").read_text().strip())
    assert entry["brain_input"] is False and entry["shadow"] is True
    # 둘 다 defensive (90 < 100)
    assert entry["gates"]["kospi"]["gate"] == "defensive"


def test_fetch_fail_graceful(monkeypatch):
    monkeypatch.setattr(to, "_fetch_closes", lambda yf: None)
    r = to.compute_overlay()
    assert r["indices"]["kospi"]["status"] == "fetch_fail"
