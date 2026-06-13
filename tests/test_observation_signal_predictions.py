"""
test_observation_signal_predictions.py — 관측-only 신호 forward 예측 생성+로깅 단위 검증.

사전등록 spec (docs/observation_signal_trails_spec_v0_2026_06_13.md) 정합:
4 source(aaii/naaim/finra_short/insider_form4) → market-level forward 예측 / 강제 매핑 /
방향 = sign(pred_score) / target='sp500' / source 분리 태그 / forward-only / 별 trail(OBS_PATH) /
관측 only. + market-level scorer(observation_scoring) 채점 단위 검증.
"""
import json
import os

import pytest

from api.intelligence import prediction_layer as PL
from api.intelligence import observation_scoring as OS


@pytest.fixture
def obs_latest():
    # us_market_observations.latest_per_source() 출력 형태
    return {
        "aaii": {"period": "2026-06-10",
                 "metrics": {"bullish": 30.4, "neutral": 22.0, "bearish": 47.7, "bull_bear_spread": -17.3}},
        "naaim": {"period": "2026-06-10", "metrics": {"exposure_mean": 79.27}},
        "finra_short": {"period": "2026-06-11", "metrics": {"market_short_volume_pct": 47.34, "n_symbols": 11595}},
        "insider_form4": {"period": "2026-06-12",
                          "metrics": {"net_buy_minus_sell": 5, "buy_ratio": 0.6, "universe_covered": 15}},
    }


def _load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def test_four_sources_three_horizons(tmp_path, obs_latest):
    p = str(tmp_path / "obs.jsonl")
    PL.generate_observation_predictions(obs_latest, path=p)
    rows = _load(p)
    # 4 source × 3 horizon = 12. 메타 신호(n_symbols/universe_covered 등) skip = 자유 surface 0.
    assert len(rows) == 12
    assert {r["signals"]["obs_source"] for r in rows} == {"aaii", "naaim", "finra_short", "insider_form4"}


def test_forced_direction_mapping(tmp_path, obs_latest):
    """강제 매핑: aaii spread<0→down / naaim 79>50→up / finra 47<50→up(반전) / form4 +5→up."""
    p = str(tmp_path / "obs.jsonl")
    PL.generate_observation_predictions(obs_latest, path=p)
    by_src = {r["signals"]["obs_source"]: r["direction"] for r in _load(p)}
    assert by_src["aaii"] == "down"          # bull_bear_spread -17.3 < 0
    assert by_src["naaim"] == "up"           # exposure 79.27 - 50 > 0
    assert by_src["finra_short"] == "up"     # -(47.34 - 50) = +2.66 > 0 (공매도 50 미만 = bullish)
    assert by_src["insider_form4"] == "up"   # net_buy_minus_sell +5 > 0


def test_pred_score_is_centered_signed(tmp_path, obs_latest):
    """pred_score = (metric - center) * sign (강제값)."""
    p = str(tmp_path / "obs.jsonl")
    PL.generate_observation_predictions(obs_latest, path=p)
    by_src = {r["signals"]["obs_source"]: r["pred_score"] for r in _load(p)}
    assert by_src["aaii"] == -17.3           # (-17.3 - 0) * 1
    assert by_src["naaim"] == round(79.27 - 50.0, 4)   # 29.27
    assert by_src["finra_short"] == round(-(47.34 - 50.0), 4)  # +2.66
    assert by_src["insider_form4"] == 5.0


def test_target_is_market_sp500(tmp_path, obs_latest):
    p = str(tmp_path / "obs.jsonl")
    PL.generate_observation_predictions(obs_latest, path=p)
    for r in _load(p):
        assert r["target_type"] == "market"
        assert r["target"] == "sp500"


def test_source_tag_and_spec_version(tmp_path, obs_latest):
    p = str(tmp_path / "obs.jsonl")
    PL.generate_observation_predictions(obs_latest, path=p)
    rows = _load(p)
    # source = obs_us_market.v0.<src> (소스별 IC 분리 + pred_id 충돌 회피)
    assert all(r["source"].startswith("obs_us_market.v0.") for r in rows)
    assert all(r["spec_version"] == "obs.v0" for r in rows)
    # pred_id 가 source suffix 로 프로덕션/소스간 충돌 회피
    assert all("-obs_us_market" in r["pred_id"] for r in rows)


def test_forward_only_and_confidence_neutral(tmp_path, obs_latest):
    p = str(tmp_path / "obs.jsonl")
    PL.generate_observation_predictions(obs_latest, path=p)
    rows = _load(p)
    assert {r["horizon"] for r in rows} == {"short", "mid", "long"}
    assert all(r["created_at"][:10] < r["eval_date"] for r in rows)  # forward-only
    # 관측 신호 = 캘리브레이션된 확률 미보유 → confidence 0.5 고정 (Brier 중립)
    assert all(r["confidence"] == 0.5 for r in rows)


def test_obs_period_frozen_in_signals(tmp_path, obs_latest):
    """관측 데이터 as_of(period) 가 signals 에 동결 (PIT)."""
    p = str(tmp_path / "obs.jsonl")
    PL.generate_observation_predictions(obs_latest, path=p)
    by_src = {r["signals"]["obs_source"]: r["signals"]["obs_period"] for r in _load(p)}
    assert by_src["aaii"] == "2026-06-10"
    assert by_src["finra_short"] == "2026-06-11"


def test_unscored_schema(tmp_path, obs_latest):
    p = str(tmp_path / "obs.jsonl")
    PL.generate_observation_predictions(obs_latest, path=p)
    for r in _load(p):
        assert r["scored"] is False
        assert r["realized_return"] is None and r["hit"] is None and r["ic_contrib"] is None


def test_graceful_empty(tmp_path):
    p = str(tmp_path / "obs.jsonl")
    out = PL.generate_observation_predictions({}, path=p)
    assert out == []
    assert not os.path.exists(p)  # 빈 입력 = 파일 미생성


def test_graceful_partial_source_missing(tmp_path):
    """일부 source 결손 = 그 source 만 skip (graceful), 나머지는 진행."""
    p = str(tmp_path / "obs.jsonl")
    out = PL.generate_observation_predictions(
        {"naaim": {"period": "2026-06-10", "metrics": {"exposure_mean": 60.0}}}, path=p
    )
    assert len(out) == 3  # naaim 만 × 3 horizon
    assert {r["signals"]["obs_source"] for r in _load(p)} == {"naaim"}


def test_graceful_metric_missing(tmp_path):
    """매핑 metric 결손 = skip (KeyError 없이)."""
    p = str(tmp_path / "obs.jsonl")
    out = PL.generate_observation_predictions(
        {"aaii": {"period": "2026-06-10", "metrics": {"bullish": 30.0}}}, path=p  # bull_bear_spread 없음
    )
    assert out == []


def test_zero_score_neutral(tmp_path):
    """metric == center → pred_score 0 → neutral."""
    p = str(tmp_path / "obs.jsonl")
    PL.generate_observation_predictions(
        {"naaim": {"period": "2026-06-10", "metrics": {"exposure_mean": 50.0}}}, path=p
    )
    assert all(r["direction"] == "neutral" and r["pred_score"] == 0.0 for r in _load(p))


# ─── market-level scorer (observation_scoring) ──────────────────────────


def test_scorer_index_value_extraction():
    """snapshot market_summary[idx]['value'] 절대 level 추출."""
    snap = {"market_summary": {"sp500": {"value": 6000.0, "change_pct": 1.2}}}
    assert OS._index_value_from_snapshot(snap, "sp500") == 6000.0
    assert OS._index_value_from_snapshot(snap, "kospi") is None  # 결손 → None
    assert OS._index_value_from_snapshot({}, "sp500") is None
    assert OS._index_value_from_snapshot(None, "sp500") is None


def test_scorer_realized_return_via_snapshots(tmp_path, monkeypatch):
    """base→eval snapshot index level diff 로 realized_return(%) 산출 (순환 antidote = 실제 level)."""
    snaps = {
        "2026-06-01": {"market_summary": {"sp500": {"value": 6000.0}}},
        "2026-06-08": {"market_summary": {"sp500": {"value": 6120.0}}},  # +2%
    }
    monkeypatch.setattr(OS, "load_snapshot", lambda d: snaps.get(d))
    avail = list(snaps.keys())
    ret = OS._realized_market_return("sp500", "2026-06-01", "2026-06-08", avail)
    assert ret == 2.0


def test_scorer_end_to_end_market(tmp_path, monkeypatch):
    """OBS_PATH 의 market 예측 채점 → scored=true + hit + (source,horizon) 집계."""
    trail = str(tmp_path / "obs_trail.jsonl")
    ic_hist = str(tmp_path / "obs_ic.jsonl")
    # eval_date 도달 + 방향 up 인 market 예측 1건 (created 가격 6000 → eval 6120 = +2% = up 적중)
    entry = {
        "pred_id": "x", "created_at": "2026-06-01T09:00:00+09:00", "spec_version": "obs.v0",
        "source": "obs_us_market.v0.naaim", "target_type": "market", "target": "sp500",
        "horizon": "short", "eval_date": "2026-06-08", "direction": "up", "rank": None,
        "pred_score": 29.27, "confidence": 0.5, "low_confidence": False,
        "signals": {"obs_source": "naaim"},
        "scored": False, "realized_return": None, "hit": None, "ic_contrib": None,
    }
    with open(trail, "w", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    snaps = {
        "2026-06-01": {"market_summary": {"sp500": {"value": 6000.0}}},
        "2026-06-08": {"market_summary": {"sp500": {"value": 6120.0}}},
    }
    monkeypatch.setattr(OS, "load_snapshot", lambda d: snaps.get(d))
    monkeypatch.setattr(OS, "list_available_dates", lambda: list(snaps.keys()))
    # eval_date(6/8) <= today 가정 — now_kst 를 6/20 으로 고정
    import datetime as _dt
    from api.config import KST
    monkeypatch.setattr(OS, "now_kst", lambda: _dt.datetime(2026, 6, 20, 12, 0, tzinfo=KST))

    summary = OS.score_observations(trail_path=trail, ic_history_path=ic_hist)
    assert summary["scored"] == 1
    rows = _load(trail)
    assert rows[0]["scored"] is True
    assert rows[0]["realized_return"] == 2.0
    assert rows[0]["hit"] is True       # direction up + realized +2% = 적중
    # 집계 레코드 (source, horizon) 기록
    ic_rows = _load(ic_hist)
    assert any(g["source"] == "naaim" and g["horizon"] == "short" for g in ic_rows)


def test_scorer_skips_nonmarket(tmp_path, monkeypatch):
    """OBS_PATH 에 비-market entry 혼입 시 무시 (market 전용 trail)."""
    trail = str(tmp_path / "obs_trail.jsonl")
    entry = {
        "created_at": "2026-06-01T09:00:00+09:00", "target_type": "stock", "target": "AAA",
        "horizon": "short", "eval_date": "2026-06-08", "direction": "up",
        "pred_score": 1.0, "confidence": 0.5, "scored": False,
        "realized_return": None, "hit": None,
    }
    with open(trail, "w", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    monkeypatch.setattr(OS, "list_available_dates", lambda: [])
    import datetime as _dt
    from api.config import KST
    monkeypatch.setattr(OS, "now_kst", lambda: _dt.datetime(2026, 6, 20, tzinfo=KST))
    summary = OS.score_observations(trail_path=trail, ic_history_path=str(tmp_path / "ic.jsonl"))
    assert summary["skipped_nonmarket"] == 1
    assert summary["scored"] == 0


def test_scorer_graceful_empty_trail(tmp_path):
    summary = OS.score_observations(
        trail_path=str(tmp_path / "nope.jsonl"), ic_history_path=str(tmp_path / "ic.jsonl")
    )
    assert summary["scored"] == 0 and summary["groups"] == 0
