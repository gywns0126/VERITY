"""
wide_scan step (a) 회귀 테스트.

검증:
- DISABLED 모드: 호출 자체 skip (skipped=True), jsonl 미적재
- SHADOW 모드: jsonl 1줄 적재 + decision 영향 0 보장
- 7차원 stub 함수 import 가능 (step b 진입 전 시그니처 고정)
- F-Score / Altman Z stub 함수 import 가능 (step c 진입 전 시그니처 고정)

메모리 원칙 5 (회귀 테스트 의무) 정합.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sample_stocks() -> list[dict]:
    """get_all_stock_data 결과 흉내 — 5종목."""
    return [
        {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "currency": "KRW",
         "price": 70000, "per": 12.5, "pbr": 1.3, "roe": 12.0, "debt_ratio": 25.0},
        {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI", "currency": "KRW",
         "price": 200000, "per": 15.0, "pbr": 1.8, "roe": 15.0, "debt_ratio": 35.0},
        {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "currency": "USD",
         "price": 180.0, "per": 28.0, "pbr": 5.5, "roe": 150.0, "debt_ratio": 200.0},
        {"ticker": "316140", "name": "우리금융지주", "market": "KOSPI", "currency": "KRW",
         "price": 13000, "per": 6.0, "pbr": 0.5, "roe": 8.0, "debt_ratio": 80.0},
        {"ticker": "251270", "name": "넷마블", "market": "KOSPI", "currency": "KRW",
         "price": 43000, "per": 0, "pbr": 1.0, "roe": -5.0, "debt_ratio": 50.0},
    ]


def test_disabled_mode_skips(tmp_path, monkeypatch):
    """WIDE_SCAN_MODE=DISABLED → run_wide_scan_shadow 가 jsonl 미적재 + skipped=True."""
    log_path = tmp_path / "wide_scan_log.jsonl"
    monkeypatch.setenv("WIDE_SCAN_MODE", "DISABLED")
    # config 모듈 reload 후 wide_scan reload — env 반영 보장
    import importlib
    import api.config as _cfg
    importlib.reload(_cfg)
    import api.analyzers.wide_scan as ws
    importlib.reload(ws)
    monkeypatch.setattr(ws, "WIDE_SCAN_LOG_PATH", log_path)

    result = ws.run_wide_scan_shadow(_sample_stocks())
    assert result["mode"] == "DISABLED"
    assert result["skipped"] is True
    assert result["logged"] is False
    assert not log_path.exists(), "DISABLED 모드는 jsonl 적재 금지"


def test_shadow_mode_appends_jsonl(tmp_path, monkeypatch):
    """WIDE_SCAN_MODE=SHADOW → jsonl 1줄 append + decision 영향 0."""
    log_path = tmp_path / "wide_scan_log.jsonl"
    monkeypatch.setenv("WIDE_SCAN_MODE", "SHADOW")
    import importlib
    import api.config as _cfg
    importlib.reload(_cfg)
    import api.analyzers.wide_scan as ws
    importlib.reload(ws)
    monkeypatch.setattr(ws, "WIDE_SCAN_LOG_PATH", log_path)

    stocks = _sample_stocks()
    result = ws.run_wide_scan_shadow(stocks, run_at_iso="2026-05-10T13:00:00+09:00")

    assert result["mode"] == "SHADOW"
    assert result["skipped"] is False
    assert result["logged"] is True
    assert result["input_n"] == 5
    assert result["target_n"] == 1  # 5 × 0.22 = 1.1 → int 1
    assert result["passed_n"] == 1  # step (b2) — 7차원 absolute scoring → 22% cut

    # jsonl schema 검증
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["label"] == "v0_heuristic"
    assert entry["mode"] == "SHADOW"
    assert entry["step"] == "c_gate_prep"
    assert entry["input_n"] == 5
    assert entry["target_n"] == 1
    assert entry["passed_n"] == 1
    assert entry["ts"] == "2026-05-10T13:00:00+09:00"
    assert "dim_weights" in entry and abs(sum(entry["dim_weights"].values()) - 1.0) < 1e-9
    assert "dim_avg" in entry and set(entry["dim_avg"]) == set(entry["dim_weights"])
    assert isinstance(entry["top10_tickers"], list)
    assert len(entry["top10_tickers"]) == 1  # passed_n=1 이라 top10 도 1개


def test_decision_impact_zero(tmp_path, monkeypatch):
    """SHADOW 모드 호출이 입력 stocks 리스트를 mutate 하지 않음 보장."""
    log_path = tmp_path / "wide_scan_log.jsonl"
    monkeypatch.setenv("WIDE_SCAN_MODE", "SHADOW")
    import importlib
    import api.config as _cfg
    importlib.reload(_cfg)
    import api.analyzers.wide_scan as ws
    importlib.reload(ws)
    monkeypatch.setattr(ws, "WIDE_SCAN_LOG_PATH", log_path)

    stocks = _sample_stocks()
    snapshot = json.dumps(stocks, sort_keys=True, ensure_ascii=False)
    ws.run_wide_scan_shadow(stocks)
    after = json.dumps(stocks, sort_keys=True, ensure_ascii=False)
    assert snapshot == after, "wide_scan SHADOW 가 production stocks 를 mutate 함 — decision 영향 0 위반"


def test_seven_dimension_scoring_in_range():
    """step (b2) — 7차원 함수 모두 [0, 100] 범위 반환."""
    from api.analyzers import wide_scan as ws
    samsung = _sample_stocks()[0]  # 삼성전자: per=12.5, pbr=1.3, roe=12, debt=25
    bucket = "IT"
    for fn, args in [
        (ws._score_liquidity, (samsung,)),
        (ws._score_value, (samsung, bucket)),
        (ws._score_profitability, (samsung,)),
        (ws._score_growth, (samsung, bucket)),
        (ws._score_safety, (samsung,)),
        (ws._score_payout, (samsung,)),
        (ws._score_momentum, (samsung,)),
    ]:
        score = fn(*args)
        assert 0.0 <= score <= 100.0, f"{fn.__name__} score={score} out of [0,100]"


def test_value_scoring_uses_sector_thresholds():
    """Q2 정합 — sector_thresholds 의무 적용. 미국 임계값 사용 절대 금지.
    바이오 PER 65 (한국 Q2) → 50점 (정상). IT PER 65 → 0~40점 (Q3 24 초과)."""
    from api.analyzers import wide_scan as ws
    bio_stock = {"per": 65, "pbr": 3.2}
    it_stock = {"per": 65, "pbr": 3.2}
    bio_score = ws._score_value(bio_stock, "바이오")
    it_score = ws._score_value(it_stock, "IT")
    assert bio_score > it_score, f"바이오 65 PER (Q2) 가 IT 65 PER (Q3 초과) 보다 점수 높아야 함"


def test_cyclical_growth_penalty():
    """Q6 정합 — 경기민감재 (조선/화학/철강) Growth 점수 30% 페널티."""
    from api.analyzers import wide_scan as ws
    base = {"revenue_growth": 30.0}  # max score 100
    normal_score = ws._score_growth(base, "IT")
    cyclical = {"revenue_growth": 30.0, "company_type": "조선"}
    cyclical_score = ws._score_growth(cyclical, "제조")
    assert cyclical_score < normal_score, "경기민감재 Growth 페널티 미적용"
    assert abs(cyclical_score - normal_score * 0.7) < 0.01, "Q6 페널티 30% 정확도 위반"


def test_financial_safety_neutralized():
    """Q1 + sector_aware — 금융업 debt_ratio 점수 무효화 (50점 = 모름)."""
    from api.analyzers import wide_scan as ws
    bank = {"company_type": "은행", "debt_ratio": 800, "current_ratio": 1.5}
    safety = ws._score_safety(bank)
    # debt 점수가 50 (무효), cr 점수 50 → 평균 50
    assert 40 <= safety <= 60, f"금융업 debt 무효화 위반 (safety={safety})"


def test_fscore_returns_explicit_dict():
    """step (c) — F-Score 가 9 항목 explicit dict 반환. 현재 가용 = c1 (ROE proxy) 만."""
    from api.analyzers import wide_scan as ws
    samsung = _sample_stocks()[0]  # roe=12 → c1=True
    result = ws._piotroski_f_score(samsung)
    assert isinstance(result, dict)
    assert "score" in result and "available_n" in result and "criteria" in result
    assert result["data_source"] == "stock_dict_v0"
    assert len(result["criteria"]) == 9
    # ROE 12 > 0 → c1_roa_positive = True
    assert result["criteria"]["c1_roa_positive"] is True
    # 나머지 8 항목 모두 None (단년 데이터 한계)
    none_count = sum(1 for v in result["criteria"].values() if v is None)
    assert none_count == 8
    # available_n < 7 이라 score = None (전체 무효)
    assert result["score"] is None
    assert "missing_fields" in result and len(result["missing_fields"]) >= 8


def test_fscore_handles_missing_roe():
    """ROE 미가용 시 c1 도 None — score=None + available_n=0."""
    from api.analyzers import wide_scan as ws
    no_roe = {"ticker": "X", "name": "X"}
    result = ws._piotroski_f_score(no_roe)
    assert result["score"] is None
    assert result["available_n"] == 0
    assert result["criteria"]["c1_roa_positive"] is None


def test_altman_z_manufacturing_only():
    """step (c) — Altman Z 가 제조업에만 applicable=True 반환."""
    from api.analyzers import wide_scan as ws
    manuf = {"company_type": "철강", "market_cap": 1e12}
    bank = {"company_type": "은행", "market_cap": 1e12}
    bio = {"company_type": "바이오", "market_cap": 1e12}

    z_manuf = ws._altman_z_score(manuf)
    z_bank = ws._altman_z_score(bank)
    z_bio = ws._altman_z_score(bio)

    assert z_manuf["applicable"] is True
    assert z_bank["applicable"] is False  # Q3 — 비제조업 부채비율 대체
    assert z_bio["applicable"] is False
    # 데이터 미가용 → z_value = None (모두)
    assert z_manuf["z_value"] is None
    assert len(z_manuf["ratios"]) == 5


def test_jsonl_includes_gate_stats(tmp_path, monkeypatch):
    """step (c) — jsonl 에 gate_stats 필드 + step='c_gate_prep'."""
    log_path = tmp_path / "wide_scan_log.jsonl"
    monkeypatch.setenv("WIDE_SCAN_MODE", "SHADOW")
    import importlib
    import api.config as _cfg
    importlib.reload(_cfg)
    import api.analyzers.wide_scan as ws
    importlib.reload(ws)
    monkeypatch.setattr(ws, "WIDE_SCAN_LOG_PATH", log_path)

    stocks = _sample_stocks()
    ws.run_wide_scan_shadow(stocks, run_at_iso="2026-05-10T18:00:00+09:00")
    entry = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert entry["step"] == "c_gate_prep"
    assert "gate_stats" in entry
    gs = entry["gate_stats"]
    assert "fscore_available_n" in gs
    assert "altman_applicable_n" in gs
    assert gs["data_source"] == "stock_dict_v0"
    # 5 sample 중 ROE 가진 종목 = 5 (모두 roe 필드 있음, 음수 포함) → fscore_available_n=5
    assert gs["fscore_available_n"] == 5
    # full_n = 0 (available_n < 7 이라 score 박히지 않음)
    assert gs["fscore_full_n"] == 0


def test_invalid_mode_falls_back_to_disabled(monkeypatch):
    """알 수 없는 WIDE_SCAN_MODE 값 → DISABLED 강제 정합 (config 가드)."""
    monkeypatch.setenv("WIDE_SCAN_MODE", "MAYBE_LATER")
    import importlib
    import api.config as _cfg
    importlib.reload(_cfg)
    assert _cfg.WIDE_SCAN_MODE == "DISABLED"
