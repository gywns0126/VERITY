"""prediction_scoring 채점 엔진 테스트.

실 history snapshot(2026-05-28 ~ 05-30) 가격으로 realized_return 채점 검증 (integration).
spec docs/prediction_layer_spec_v0_2026_06_01.md §9.3/§9.4 정합.
"""
import json
import os

import pytest

from api.intelligence import prediction_scoring as PS
from api.workflows.archiver import load_snapshot
from api.intelligence.backtest_archive import _get_price_map_from_snapshot


def _snapshots_available() -> bool:
    a = load_snapshot("2026-05-28")
    b = load_snapshot("2026-05-30")
    if not a or not b:
        return False
    pa = _get_price_map_from_snapshot(a)
    pb = _get_price_map_from_snapshot(b)
    return len(set(pa) & set(pb)) >= 3


pytestmark = pytest.mark.skipif(
    not _snapshots_available(),
    reason="history snapshot(05-28/05-30) 부재 — integration 채점 테스트 skip",
)


def _common_tickers(n=5):
    pa = _get_price_map_from_snapshot(load_snapshot("2026-05-28"))
    pb = _get_price_map_from_snapshot(load_snapshot("2026-05-30"))
    return sorted(set(pa) & set(pb))[:n]


def _write_trail(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _base(ticker, direction, pred_score, conf=0.6, created="2026-05-28T09:00:00+09:00",
          eval_date="2026-05-30", target_type="stock", horizon="short", scored=False):
    return {
        "pred_id": f"20260528-{ticker}-{horizon}", "created_at": created, "spec_version": "v0",
        "target_type": target_type, "target": ticker, "horizon": horizon,
        "eval_date": eval_date, "direction": direction, "rank": None,
        "pred_score": pred_score, "confidence": conf, "low_confidence": False,
        "signals": {"source": "test"}, "scored": scored,
        "realized_return": None, "hit": None, "ic_contrib": None,
    }


def test_scores_reached_stock_predictions(tmp_path):
    tickers = _common_tickers(5)
    trail = tmp_path / "trail.jsonl"
    ic_hist = tmp_path / "ic.jsonl"

    # 도달 stock 예측 (eval 05-30 <= today) — 방향/score 섞기
    entries = [_base(t, "up" if i % 2 == 0 else "down", pred_score=0.9 - i * 0.1)
               for i, t in enumerate(tickers)]
    # 미도래(future eval) — pending, scored 안 됨
    entries.append(_base(tickers[0], "up", 0.5, eval_date="2026-12-31"))
    # 섹터 — 채점 보류(deferred)
    entries.append(_base("반도체", "up", 0.7, target_type="sector"))
    _write_trail(trail, entries)

    summary = PS.score_predictions(trail_path=str(trail), ic_history_path=str(ic_hist))

    assert summary["scored"] == len(tickers), summary
    assert summary["deferred_sector"] == 1, summary
    assert summary["groups"] >= 1, summary

    # trail rewrite — 도달분 scored=true + realized_return 채워짐
    rows = [json.loads(l) for l in open(trail, encoding="utf-8") if l.strip()]
    scored_stock = [r for r in rows if r["target_type"] == "stock" and r["scored"]]
    assert len(scored_stock) == len(tickers)
    for r in scored_stock:
        assert r["realized_return"] is not None
        assert r["hit"] in (True, False)  # up/down → 이항 모집단
    # future 예측은 미채점
    future = [r for r in rows if r["eval_date"] == "2026-12-31"][0]
    assert future["scored"] is False
    # 섹터는 채점 보류 (scored 유지 false)
    sector = [r for r in rows if r["target_type"] == "sector"][0]
    assert sector["scored"] is False

    # ic_history 집계 레코드 검증
    recs = [json.loads(l) for l in open(ic_hist, encoding="utf-8") if l.strip()]
    assert len(recs) >= 1
    g = recs[0]
    assert g["target_type"] == "stock"
    assert g["horizon"] == "short"
    assert g["n"] == len(tickers)
    assert g["overlap_k"] == 5
    assert g["effective_n"] == pytest.approx(len(tickers) / 5, abs=0.01)
    assert g["label"] == "Trail 누적 초기"  # N_eff 작음 → 강제
    assert g["hit_rate"] is not None
    assert g["expectancy"] is not None
    assert "stock only(sector deferred)" in g["_method"]


def test_unscoreable_after_grace(tmp_path):
    trail = tmp_path / "trail.jsonl"
    ic_hist = tmp_path / "ic.jsonl"
    # 존재하지 않는 ticker + eval_date 가 grace(14일) 초과 → unscoreable 종결
    entries = [_base("ZZZNOEXIST", "up", 0.8, created="2026-01-01T09:00:00+09:00",
                     eval_date="2026-01-08")]
    _write_trail(trail, entries)
    summary = PS.score_predictions(trail_path=str(trail), ic_history_path=str(ic_hist))
    assert summary["unscoreable"] == 1, summary
    rows = [json.loads(l) for l in open(trail, encoding="utf-8") if l.strip()]
    assert rows[0]["scored"] is True
    assert rows[0]["_skip_reason"] == "no_snapshot_within_grace"
    assert rows[0]["realized_return"] is None


def test_empty_trail(tmp_path):
    trail = tmp_path / "trail.jsonl"
    summary = PS.score_predictions(trail_path=str(trail), ic_history_path=str(tmp_path / "ic.jsonl"))
    assert summary["scored"] == 0


def test_hit_logic():
    assert PS._is_hit("up", 1.5) is True
    assert PS._is_hit("up", -1.5) is False
    assert PS._is_hit("down", -2.0) is True
    assert PS._is_hit("down", 2.0) is False
    assert PS._is_hit("neutral", 0.1) is None  # 이항 모집단 제외


def test_label_gate():
    assert PS._label_for(10, None) == "Trail 누적 초기"
    assert PS._label_for(50, 0.5) == "예비"
    assert PS._label_for(300, 0.01) == "유의"
    assert PS._label_for(300, 0.5) == "예비"  # N 충분해도 유의성 미달
