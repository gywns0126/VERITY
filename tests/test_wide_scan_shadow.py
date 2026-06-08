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


class TestProductionGate:
    """SHADOW→PRODUCTION 게이트 (2026-05-22 PM 65→90)."""

    def test_min_required_is_90(self):
        from api.analyzers.wide_scan import production_gate_status
        s = production_gate_status(Path("/nonexistent.jsonl"))
        assert s["min_required"] == 90
        assert s["days_accumulated"] == 0
        assert s["ready"] is False

    def test_counts_distinct_dates_and_ready(self, tmp_path):
        from api.analyzers.wide_scan import production_gate_status
        p = tmp_path / "wide_scan_log.jsonl"
        lines = []
        # 90 distinct dates × 2 step/day = 180 행 → days=90, ready True
        for i in range(90):
            d = f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}"
            lines.append(json.dumps({"ts": f"{d}T19:00:00+09:00", "step": "c"}))
            lines.append(json.dumps({"ts": f"{d}T19:01:00+09:00", "step": "f"}))
        p.write_text("\n".join(lines))
        s = production_gate_status(p)
        assert s["days_accumulated"] == 90  # 중복 일자 dedupe
        assert s["ready"] is True

    def test_not_ready_below_min(self, tmp_path):
        from api.analyzers.wide_scan import production_gate_status
        p = tmp_path / "wide_scan_log.jsonl"
        p.write_text("\n".join(
            json.dumps({"ts": f"2026-05-{i + 1:02d}T19:00:00+09:00", "step": "c"})
            for i in range(20)
        ))
        s = production_gate_status(p)
        assert s["days_accumulated"] == 20
        assert s["ready"] is False


def _sample_stocks() -> list[dict]:
    """get_all_stock_data 결과 흉내 — 5종목 (Phase 2-B 보강 필드 포함)."""
    return [
        {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "currency": "KRW",
         "price": 70000, "per": 12.5, "pbr": 1.3, "roe": 12.0, "roa": 8.0,
         "debt_ratio": 25.0, "operating_cashflow": 5e9, "eps": 1000, "shares_outstanding": 1e6},
        {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI", "currency": "KRW",
         "price": 200000, "per": 15.0, "pbr": 1.8, "roe": 15.0, "roa": 10.0,
         "debt_ratio": 35.0, "operating_cashflow": 8e9, "eps": 5000, "shares_outstanding": 800_000},
        {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "currency": "USD",
         "price": 180.0, "per": 28.0, "pbr": 5.5, "roe": 150.0, "roa": 25.0,
         "debt_ratio": 200.0, "operating_cashflow": 1e11, "eps": 6.0, "shares_outstanding": 16e9},
        {"ticker": "316140", "name": "우리금융지주", "market": "KOSPI", "currency": "KRW",
         "price": 13000, "per": 6.0, "pbr": 0.5, "roe": 8.0, "roa": 0.5,
         "debt_ratio": 80.0, "operating_cashflow": 2e9, "eps": 2000, "shares_outstanding": 700_000},
        {"ticker": "251270", "name": "넷마블", "market": "KOSPI", "currency": "KRW",
         "price": 43000, "per": 0, "pbr": 1.0, "roe": -5.0, "roa": -3.0,
         "debt_ratio": 50.0, "operating_cashflow": -1e8, "eps": -500, "shares_outstanding": 100_000},
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

    # jsonl schema 검증 — 2026-05-17 funnel sprint Step 2-4 cascading 도입 후:
    # step 1 (c_gate_prep) + step 2 (d_precision_fallback) + step 3 (e_factor_rank) + step 4 (f_sector_diversified) = 4 entries
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 4  # cascading 4 단계 entry
    # Step 1 (c_gate_prep) 검증
    entry_c = json.loads(lines[0])
    assert entry_c["label"] == "v0_heuristic"
    assert entry_c["mode"] == "SHADOW"
    assert entry_c["step"] == "c_gate_prep"
    assert entry_c["input_n"] == 5
    assert entry_c["target_n"] == 1
    assert entry_c["passed_n"] == 1
    assert entry_c["ts"] == "2026-05-10T13:00:00+09:00"
    assert "dim_weights" in entry_c and abs(sum(entry_c["dim_weights"].values()) - 1.0) < 1e-9
    assert "dim_avg" in entry_c and set(entry_c["dim_avg"]) == set(entry_c["dim_weights"])
    assert isinstance(entry_c["top10_tickers"], list)
    assert len(entry_c["top10_tickers"]) == 1  # passed_n=1
    # Step 2-4 cascading entries — step 명 검증 (funnel sprint Step 2/3/4)
    steps_present = {json.loads(l).get("step") for l in lines}
    assert "c_gate_prep" in steps_present
    assert "d_precision_fallback" in steps_present
    assert "e_factor_rank" in steps_present
    assert "f_sector_diversified" in steps_present


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
    """step (c+) — F-Score 가 9 항목 explicit dict 반환. 가용 = c1 (ROA), c2 (CFO), c4 (CFO>NI)."""
    from api.analyzers import wide_scan as ws
    # ROA + CFO + EPS + shares 포함 sample
    rich = {
        "ticker": "RICH", "roa": 8.0, "operating_cashflow": 5_000_000_000,
        "eps": 1000, "shares_outstanding": 1_000_000,  # NI proxy = 1e9 < CFO
    }
    result = ws._piotroski_f_score(rich)
    assert isinstance(result, dict)
    assert "score" in result and "available_n" in result and "criteria" in result
    # ROA 8 > 0 → c1=True. CFO 5B > 0 → c2=True. CFO 5B > NI 1B → c4=True
    assert result["criteria"]["c1_roa_positive"] is True
    assert result["criteria"]["c2_cfo_positive"] is True
    assert result["criteria"]["c4_cfo_gt_ni"] is True
    # Δ 항목 5개 모두 None (시계열 jsonl 누적 후 가능)
    delta_keys = ["c3_delta_roa_positive", "c5_delta_leverage_negative",
                  "c6_delta_current_ratio_positive", "c7_no_new_shares",
                  "c8_delta_gross_margin_positive", "c9_delta_asset_turnover_positive"]
    for k in delta_keys:
        assert result["criteria"][k] is None
    # available_n = 3, score = 3 (모두 True)
    assert result["available_n"] == 3
    assert result["score"] == 3


def test_fscore_handles_missing_data():
    """ROA / CFO / EPS 모두 미가용 시 → score=None + available_n=0."""
    from api.analyzers import wide_scan as ws
    no_data = {"ticker": "X", "name": "X"}
    result = ws._piotroski_f_score(no_data)
    assert result["score"] is None
    assert result["available_n"] == 0


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
    # 2026-05-17 funnel sprint Step 2-4 cascading 적용 — jsonl 첫 줄 (c_gate_prep) 만 parse
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    entry = json.loads(lines[0])  # c_gate_prep
    assert entry["step"] == "c_gate_prep"
    assert "gate_stats" in entry
    gs = entry["gate_stats"]
    assert "fscore_available_n" in gs
    assert "altman_applicable_n" in gs
    assert gs["data_source"] == "stock_dict_v0"
    # 5 sample 중 ROE 가진 종목 = 5 (모두 roe 필드 있음, 음수 포함) → fscore_available_n=5
    assert gs["fscore_available_n"] == 5
    # 5 sample 모두 ROA + CFO + EPS + shares 포함됨 → c1+c2+c4 가용 → available_n=3 ≥ 3 → score 산출됨
    assert gs["fscore_full_n"] == 5


def test_invalid_mode_falls_back_to_disabled(monkeypatch):
    """알 수 없는 WIDE_SCAN_MODE 값 → DISABLED 강제 정합 (config 가드)."""
    monkeypatch.setenv("WIDE_SCAN_MODE", "MAYBE_LATER")
    import importlib
    import api.config as _cfg
    importlib.reload(_cfg)
    assert _cfg.WIDE_SCAN_MODE == "DISABLED"
