"""
test_regime_predictions.py — 국면(regime) forward 예측 로깅 + 시계열 채점 단위 검증.

사전등록 spec (docs/regime_validation_spec_v0_2026_06_13.md) 정합:
regime→방향 매핑(§3c 강제값) / forward-only / 별도 trail(REGIME_PATH) / market-level schema /
시계열 scorer(ic_stats Newey-West 재사용, cross-section 미적용) / 관측 only(RULE 7) / graceful.
"""
import json
import os

import pytest

from api.intelligence import regime_prediction as RG
from api.metadata import prediction_trail as PT


def _load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


# ── 1. 방향 매핑 (spec §3c 강제값) ──────────────────────────────────────────


def test_direction_defensive_override_is_down():
    # 방어 cap (max_grade WATCH/CAUTION/AVOID, contrarian 아님) → 'down'
    for g in ("WATCH", "CAUTION", "AVOID"):
        mo = {"mode": "panic", "max_grade": g}
        assert RG.regime_direction(mo, None) == "down"


def test_direction_contrarian_upgrade_is_up():
    # 패닉 역발상(바닥 매수) → 'up'
    mo = {"mode": "panic_stage4", "max_grade": "WATCH", "contrarian_upgrade": True}
    assert RG.regime_direction(mo, None) == "up"


def test_direction_overheat_cap_is_down():
    # euphoria/greed cap (BUY/STRONG_BUY max_grade) → 'down' (평균회귀 가설)
    for g in ("BUY", "STRONG_BUY"):
        mo = {"mode": "euphoria", "max_grade": g}
        assert RG.regime_direction(mo, None) == "down"


def test_direction_cycle_stage_fallback():
    assert RG.regime_direction(None, "early_bull") == "up"
    assert RG.regime_direction(None, "mid_bull") == "up"
    assert RG.regime_direction(None, "euphoria") == "down"
    assert RG.regime_direction(None, "bear") == "down"
    assert RG.regime_direction(None, "late_bull") == "neutral"
    assert RG.regime_direction(None, "unknown") == "neutral"


def test_override_precedes_cycle_stage():
    # macro_override 존재 시 cycle_stage 무시 (우선순위 §3c)
    mo = {"mode": "panic", "max_grade": "AVOID"}
    assert RG.regime_direction(mo, "early_bull") == "down"


# ── 2. signal_score 부호 (시계열 IC 입력) ───────────────────────────────────


def test_signal_score_sign():
    assert RG.regime_signal_score({"mode": "panic", "max_grade": "AVOID"}, None) < 0     # 방어=음
    assert RG.regime_signal_score({"mode": "p", "max_grade": "WATCH", "contrarian_upgrade": True}, None) > 0
    assert RG.regime_signal_score(None, "early_bull") > 0   # 강세=양
    assert RG.regime_signal_score(None, "bear") < 0
    # 심각도 클수록 더 강한 음(하락 예측)
    assert (RG.regime_signal_score({"mode": "x", "max_grade": "AVOID"}, None)
            < RG.regime_signal_score({"mode": "x", "max_grade": "WATCH"}, None))


# ── 3. forward 로깅 ─────────────────────────────────────────────────────────


def test_log_emits_three_horizons(tmp_path):
    p = str(tmp_path / "regime.jsonl")
    mo = {"mode": "panic_stage3", "max_grade": "WATCH", "contrarian_upgrade": True,
          "secondary_signals": [{"mode": "yield_defense", "max_grade": "WATCH"}]}
    out = RG.log_regime_prediction(mo, "bear", {"kospi": 2500.0, "sp500": 5000.0}, path=p)
    rows = _load(p)
    assert len(out) == 3 and len(rows) == 3
    assert {r["horizon"] for r in rows} == {"short", "mid", "long"}
    assert all(r["target_type"] == "market" for r in rows)
    assert all(r["source"] == "regime_macro_override.v0" for r in rows)


def test_forward_only(tmp_path):
    p = str(tmp_path / "regime.jsonl")
    RG.log_regime_prediction({"mode": "panic", "max_grade": "AVOID"}, "bear",
                             {"kospi": 2500.0, "sp500": None}, path=p)
    for r in _load(p):
        assert r["created_at"][:10] < r["eval_date"]   # forward-only 강제


def test_pit_index_levels_frozen(tmp_path):
    p = str(tmp_path / "regime.jsonl")
    RG.log_regime_prediction({"mode": "euphoria", "max_grade": "BUY"}, "euphoria",
                             {"kospi": 8123.62, "sp500": 7394.3}, path=p)
    for r in _load(p):
        lv = r["signals"]["index_levels"]
        assert lv["kospi"] == 8123.62 and lv["sp500"] == 7394.3   # 동결(PIT)


def test_unscored_schema(tmp_path):
    p = str(tmp_path / "regime.jsonl")
    RG.log_regime_prediction({"mode": "panic", "max_grade": "AVOID"}, "bear",
                             {"kospi": 2500.0, "sp500": 5000.0}, path=p)
    for r in _load(p):
        assert r["scored"] is False
        assert r["realized_return"] is None and r["hit"] is None
        assert r["realized_return_by_index"] is None
        assert "direction" in r and "signal_score" in r and "confidence" in r


# ── 4. graceful skip ────────────────────────────────────────────────────────


def test_no_regime_signal_skips(tmp_path):
    # macro_override 부재 + cycle_stage unknown/없음 → 빈 list, 파일 미생성
    p = str(tmp_path / "regime.jsonl")
    assert RG.log_regime_prediction(None, "unknown", {"kospi": 2500.0}, path=p) == []
    assert RG.log_regime_prediction(None, None, {"kospi": 2500.0}, path=p) == []
    assert RG.log_regime_prediction({}, "", {}, path=p) == []
    assert not os.path.exists(p)


def test_run_regime_layer_from_portfolio(tmp_path):
    p = str(tmp_path / "regime.jsonl")
    portfolio = {
        "verity_brain": {"macro_override": {"mode": "panic", "max_grade": "AVOID"}},
        "market_horizon": {"cycle_stage": "bear"},
        "market_summary": {"kospi": {"value": 2500.0}},
        "macro": {"sp500": {"value": 5000.0}},
    }
    out = RG.run_regime_layer(portfolio, path=p)
    assert out["regime_predictions"] == 3
    rows = _load(p)
    assert rows[0]["signals"]["index_levels"]["kospi"] == 2500.0
    assert rows[0]["signals"]["index_levels"]["sp500"] == 5000.0


def test_run_regime_layer_graceful_missing(tmp_path):
    p = str(tmp_path / "regime.jsonl")
    # 국면 신호 전무 → 0건, 예외 없음
    out = RG.run_regime_layer({"market_summary": {}, "macro": {}}, path=p)
    assert out["regime_predictions"] == 0
    assert not os.path.exists(p)


# ── 5. 시계열 채점 (실현 수익률 + ic_stats Newey-West 재사용) ────────────────


def _write_entry(rows, **kw):
    base = {
        "pred_id": "x", "created_at": "2026-01-01T09:00:00+09:00", "spec_version": "regime.v0",
        "source": "regime_macro_override.v0", "target_type": "market", "target": "kospi",
        "horizon": "short", "eval_date": "2026-01-08", "regime_mode": "panic",
        "direction": "down", "signal_score": -5.0, "confidence": 0.6,
        "signals": {"index_levels": {"kospi": 2500.0, "sp500": 5000.0}},
        "scored": False, "realized_return": None, "realized_return_by_index": None, "hit": None,
    }
    base.update(kw)
    rows.append(base)


def test_score_realizes_and_aggregates(tmp_path, monkeypatch):
    """eval 도달 + snapshot 가용 시 실현수익률 채점 + ic_history 집계."""
    trail = str(tmp_path / "regime.jsonl")
    ich = str(tmp_path / "regime_ic.jsonl")

    rows = []
    # 3 run (시계열 N=3) — down 신호 후 KOSPI 하락(2500→2400) = hit
    evals = ("2026-01-08", "2026-01-09", "2026-01-10")
    for i, day in enumerate(("2026-01-01", "2026-01-02", "2026-01-03")):
        _write_entry(rows, pred_id=f"r{i}", created_at=f"{day}T09:00:00+09:00",
                     eval_date=evals[i], signals={"index_levels": {"kospi": 2500.0, "sp500": 5000.0}})
    with open(trail, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # archiver / nearest 를 deterministic stub 으로 (실 snapshot 무의존)
    import api.intelligence.regime_prediction as RGM

    def fake_imports():
        pass

    # score_regime_predictions 내부 lazy import 를 monkeypatch — 모듈 함수로 주입
    import sys
    import types
    arch = types.ModuleType("api.workflows.archiver")
    arch.list_available_dates = lambda: ["2026-01-08", "2026-01-09", "2026-01-10"]
    snaps = {
        "2026-01-08": {"market_summary": {"kospi": {"value": 2400.0}}, "macro": {"sp500": {"value": 4900.0}}},
        "2026-01-09": {"market_summary": {"kospi": {"value": 2400.0}}, "macro": {"sp500": {"value": 4900.0}}},
        "2026-01-10": {"market_summary": {"kospi": {"value": 2400.0}}, "macro": {"sp500": {"value": 4900.0}}},
    }
    arch.load_snapshot = lambda d: snaps.get(d)
    bka = types.ModuleType("api.intelligence.backtest_archive")
    bka._find_nearest_snapshot = lambda td, avail: td if td in avail else None
    monkeypatch.setitem(sys.modules, "api.workflows.archiver", arch)
    monkeypatch.setitem(sys.modules, "api.intelligence.backtest_archive", bka)

    # today 를 채점 도달 이후로 (eval_date <= today)
    import api.config as cfg
    from datetime import datetime, timezone, timedelta as td
    kst = timezone(td(hours=9))
    monkeypatch.setattr(RGM, "now_kst", lambda: datetime(2026, 1, 11, tzinfo=kst))

    summary = RGM.score_regime_predictions(trail_path=trail, ic_history_path=ich)
    assert summary["scored"] == 3
    scored_rows = _load(trail)
    assert all(r["scored"] for r in scored_rows)
    # down 예측 + KOSPI -4% → hit True
    assert all(r["hit"] is True for r in scored_rows)
    assert all(r["realized_return"] < 0 for r in scored_rows)
    assert all(r["realized_return_by_index"]["sp500"] is not None for r in scored_rows)
    # ic_history 집계 산출 (N=3 → 라벨 'Trail 누적 초기')
    agg = _load(ich)
    assert agg and agg[0]["target_type"] == "market"
    assert agg[0]["primary_index"] == "kospi"
    assert agg[0]["label"] == "Trail 누적 초기"
    assert agg[0]["hit_rate"] == 1.0


def test_score_empty_trail_graceful(tmp_path):
    out = RG.score_regime_predictions(trail_path=str(tmp_path / "none.jsonl"),
                                      ic_history_path=str(tmp_path / "ic.jsonl"))
    assert out["scored"] == 0 and out["groups"] == 0


def test_score_pending_when_not_due(tmp_path, monkeypatch):
    """eval_date 미도래 = pending/skip, 채점 안 함."""
    trail = str(tmp_path / "regime.jsonl")
    rows = []
    _write_entry(rows, eval_date="2099-01-01")
    with open(trail, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    import api.intelligence.regime_prediction as RGM
    import sys
    import types
    arch = types.ModuleType("api.workflows.archiver")
    arch.list_available_dates = lambda: []
    arch.load_snapshot = lambda d: None
    bka = types.ModuleType("api.intelligence.backtest_archive")
    bka._find_nearest_snapshot = lambda td, avail: None
    monkeypatch.setitem(sys.modules, "api.workflows.archiver", arch)
    monkeypatch.setitem(sys.modules, "api.intelligence.backtest_archive", bka)
    out = RGM.score_regime_predictions(trail_path=trail, ic_history_path=str(tmp_path / "ic.jsonl"))
    assert out["scored"] == 0
    assert all(not r["scored"] for r in _load(trail))


def test_scorer_separate_from_cross_section():
    """regime trail 은 prediction_scoring(cross-section) 과 물리/논리 분리 = 무오염."""
    assert RG.REGIME_PATH == PT.REGIME_PATH
    assert RG.REGIME_PATH != PT._PATH and RG.REGIME_PATH != PT.SHADOW_PATH and RG.REGIME_PATH != PT.ML_PATH
