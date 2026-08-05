# -*- coding: utf-8 -*-
"""B3 F-Score/Accrual shadow IC trail — PREREG_FSCORE_ACCRUAL_B3_2026_07_12 집행 검증.

핵심 계약(등록 동결분):
  · brain-input 0 — 관측 전용 (어떤 점수에도 입력 금지)
  · 결측 철학 — available_n < 9 → 관측 제외 (부분 점수 금지)
  · accrual 방향 −1 (低=양호) 로 정렬해야 H1(IC>0)이 양쪽 신호에 성립
  · horizon 3종 전부 paired 산출 (cherry-pick 금지)
  · 지표 paired 병기 — IC 단독/hit 단독/expectancy 단독 게재 금지 (RULE 7)
  · 게이트 N≥252 ∧ IC>0.03 ∧ ICIR>0.3
  · forward-only (과거 backfill 금지 — survivorship 무편의 조건)
"""
import json

import api.intelligence.fscore_shadow as FS


def _iso(monkeypatch, tmp_path):
    monkeypatch.setattr(FS, "TRAIL_PATH", str(tmp_path / "trail.jsonl"))
    monkeypatch.setattr(FS, "HISTORY_PATH", str(tmp_path / "hist.jsonl"))


def _stock(ticker, eps=1000.0, shares=1000.0, cfo=900_000.0, ta=10_000_000.0):
    return {"ticker": ticker, "eps": eps, "shares_outstanding": shares,
            "operating_cashflow": cfo,
            "dart_financials": {"financials": {"total_assets": ta}}}


# ── accrual 산식 ────────────────────────────────────────────────────────

def test_accrual_matches_sloan_definition():
    # NI = eps×shares = 1,000,000 · CFO = 900,000 · TA = 10,000,000 → 0.01
    assert FS.compute_accrual(_stock("A")) == 0.01


def test_accrual_none_when_any_input_missing():
    for k in ("eps", "shares_outstanding", "operating_cashflow"):
        s = _stock("A")
        s[k] = None
        assert FS.compute_accrual(s) is None
    s = _stock("A")
    s["dart_financials"] = {"financials": {"total_assets": 0}}
    assert FS.compute_accrual(s) is None  # 0 나눗셈 방지 + 부분 추정 금지


def test_accrual_direction_is_negative():
    """低 accrual = 양호 → 방향 −1 이어야 H1(IC>0) 이 성립한다."""
    assert FS.SIGNAL_DIRECTION["accrual"] == -1
    assert FS.SIGNAL_DIRECTION["fscore"] == 1


# ── 관측 ────────────────────────────────────────────────────────────────

def test_observe_writes_three_horizons_per_signal(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    out = FS.observe([_stock("000001")], base_date="2026-08-05")
    assert out["appended"] == 3          # accrual × 3 horizon
    rows = FS._load_jsonl(FS.TRAIL_PATH)
    assert sorted(r["horizon"] for r in rows) == ["21d", "252d", "63d"]
    assert all(r["scored"] is False and r["realized_return"] is None for r in rows)


def test_observe_is_idempotent_per_date(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    FS.observe([_stock("000001")], base_date="2026-08-05")
    again = FS.observe([_stock("000001")], base_date="2026-08-05")
    assert again.get("skipped") == "already_observed"
    assert len(FS._load_jsonl(FS.TRAIL_PATH)) == 3


def test_partial_fscore_is_excluded(monkeypatch, tmp_path):
    """available_n < 9 = 전체 무효 (부분 점수 금지). 실운영 실측이 이 경로다."""
    _iso(monkeypatch, tmp_path)
    monkeypatch.setattr("api.analyzers.wide_scan._piotroski_f_score",
                        lambda s: {"score": 3, "available_n": 3})
    out = FS.observe([_stock("000001")], base_date="2026-08-05")
    assert out["fscore_n"] == 0
    assert all(r["signal"] == "accrual" for r in FS._load_jsonl(FS.TRAIL_PATH))


def test_full_fscore_is_recorded(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    monkeypatch.setattr("api.analyzers.wide_scan._piotroski_f_score",
                        lambda s: {"score": 7, "available_n": 9})
    out = FS.observe([_stock("000001")], base_date="2026-08-05")
    assert out["fscore_n"] == 1 and out["appended"] == 6   # (fscore+accrual) × 3


def test_eval_date_skips_weekends():
    # 2026-08-05(수) + 21거래일 → 달력 4주 이상 뒤, 반드시 평일
    from datetime import datetime
    d = FS._add_trading_days("2026-08-05", 21)
    assert datetime.strptime(d, "%Y-%m-%d").weekday() < 5
    assert d > "2026-08-31"


# ── 집계 ────────────────────────────────────────────────────────────────

def _scored_row(date, ticker, val, ret, sig="accrual", hz="21d"):
    return {"base_date": date, "ticker": ticker, "signal": sig, "horizon": hz,
            "value": val, "realized_return": ret, "scored": True}


def test_aggregate_orients_accrual_so_low_is_good(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    # 低 accrual 종목이 高 수익 → 방향 반영 후 IC 는 양수여야 한다
    rows = [_scored_row("2026-07-01", f"{i:06d}", val=i / 100, ret=-i)
            for i in range(1, 7)]
    FS._append_jsonl(FS.TRAIL_PATH, rows)
    agg = {(a["signal"], a["horizon"]): a for a in FS.aggregate()}
    a = agg[("accrual", "21d")]
    assert a["n_cross_sections"] == 1
    assert a["ic_mean"] is not None and a["ic_mean"] > 0
    assert a["expectancy_spread_pp"] is not None and a["expectancy_spread_pp"] > 0


def test_aggregate_emits_all_paired_metrics(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    FS._append_jsonl(FS.TRAIL_PATH, [_scored_row("2026-07-01", f"{i:06d}", i / 100, -i)
                                     for i in range(1, 7)])
    a = FS.aggregate()[0]
    for k in ("n_cross_sections", "ic_mean", "icir", "ic_hit_rate",
              "expectancy_spread_pp", "ci95_ic", "label", "gate"):
        assert k in a, f"{k} 누락 — RULE 7 paired 병기 위반"
    assert a["brain_input"] is False


def test_all_six_signal_horizon_pairs_always_emitted(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    keys = {(a["signal"], a["horizon"]) for a in FS.aggregate()}
    assert keys == {(s, h) for s in FS.SIGNALS for h in FS.HORIZONS}  # cherry-pick 차단


def test_thin_cross_section_is_discarded(monkeypatch, tmp_path):
    _iso(monkeypatch, tmp_path)
    FS._append_jsonl(FS.TRAIL_PATH, [_scored_row("2026-07-01", f"{i:06d}", i / 100, -i)
                                     for i in range(1, 4)])   # 3종목 < MIN_CROSS_SECTION
    a = {(x["signal"], x["horizon"]): x for x in FS.aggregate()}[("accrual", "21d")]
    assert a["n_cross_sections"] == 0


def test_gate_constants_match_registration():
    assert (FS.GATE_N, FS.GATE_IC, FS.GATE_ICIR) == (252, 0.03, 0.3)


def test_labels_follow_registered_n_thresholds():
    assert "무의미" in FS._label(29)
    assert "예비" in FS._label(30)
    assert "누적" in FS._label(100)
    assert "게이트" in FS._label(252)


def test_ci95_zero_inclusion_is_flagged(monkeypatch, tmp_path):
    """실패 조항 — 게이트 시점 CI95 가 0 을 포함하면 재보정 금지 판정이 필요하다."""
    _iso(monkeypatch, tmp_path)
    rows = []
    for d in range(1, 6):   # 부호가 섞인 단면 5일 → CI 가 0 을 포함
        sign = 1 if d % 2 else -1
        rows += [_scored_row(f"2026-07-0{d}", f"{i:06d}", i / 100, sign * i)
                 for i in range(1, 7)]
    FS._append_jsonl(FS.TRAIL_PATH, rows)
    a = {(x["signal"], x["horizon"]): x for x in FS.aggregate()}[("accrual", "21d")]
    assert a["ci95_ic"] is not None
    assert a["ci95_includes_zero"] is True
