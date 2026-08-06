# -*- coding: utf-8 -*-
"""공매도 규칙 관측 trail + 결측 판정 보류 (2026-08-06).

사전등록 = docs/PREREG_SHORT_SALE_AUTO_AVOID_2026_08_06.md
  PM 승인 "권고대로 ㄱㄱ" — 안 (가) 확정.

계약: ① 결측을 clean(무혐의)과 분리 ② KR·US 를 합산하지 않음(지표·임계·강도가 다름)
③ 🚨 의사복제 통제 — 1차 수치는 종목 단위, 게이트도 종목 수 기준
④ 점수·집행 입력 0 ⑤ 임계·강도 무변경(관측 대상으로만 명시).
"""
import json

import pytest

import api.observability.short_sale_trail as ST
from api.intelligence.factors.red_flags import _detect_red_flags as detect_red_flags


# ── 결측 = 판정 보류 (clean 아님) ────────────────────────────────────

def _kr(**kw):
    s = {"ticker": "000001", "currency": "KRW"}
    s.update(kw)
    return s


def test_kr_missing_records_gap_not_pass():
    """🚨 핵심 — 결측이 조용히 통과하지 않고 data_gaps 에 남는다."""
    r = detect_red_flags(_kr(), {})
    gaps = [g["rule"] for g in r["data_gaps"]]
    assert "short_sale_kr" in gaps
    assert not any("공매도" in t for t in r["auto_avoid"] + r["downgrade"])


def test_kr_present_value_produces_no_gap():
    r = detect_red_flags(_kr(kis_short_sale={"avg_short_ratio_5d": 3.0}), {})
    assert not any(g["rule"] == "short_sale_kr" for g in r["data_gaps"])


def test_kr_thresholds_unchanged():
    """등록 §7-3 — 임계 15/8·강도 무변경. 본 등록은 결측 처리만 다룬다."""
    hi = detect_red_flags(_kr(kis_short_sale={"avg_short_ratio_5d": 15.1}), {})
    mid = detect_red_flags(_kr(kis_short_sale={"avg_short_ratio_5d": 8.1}), {})
    lo = detect_red_flags(_kr(kis_short_sale={"avg_short_ratio_5d": 8.0}), {})
    assert any("과다" in t for t in hi["auto_avoid"])
    assert any("주의" in t for t in mid["downgrade"])
    assert not any("공매도" in t for t in lo["auto_avoid"] + lo["downgrade"])


def test_kr_zero_is_clean_not_missing():
    """0% 는 실측값이다 — 결측과 구분된다."""
    r = detect_red_flags(_kr(kis_short_sale={"avg_short_ratio_5d": 0.0}), {})
    assert not r["data_gaps"]


def test_us_missing_records_gap():
    r = detect_red_flags({"ticker": "AAPL", "currency": "USD"}, {})
    assert any(g["rule"] == "short_interest_us" for g in r["data_gaps"])


def test_us_threshold_unchanged_and_no_auto_avoid():
    """미장은 downgrade 만 — KR 과 강도가 다르다(합산 금지의 근거)."""
    r = detect_red_flags({"ticker": "AAPL", "currency": "USD",
                          "short_interest": {"short_pct": 25.0}}, {})
    assert any("공매도" in t for t in r["downgrade"])
    assert not any("공매도" in t for t in r["auto_avoid"])


# ── tier 분류 ────────────────────────────────────────────────────────

@pytest.mark.parametrize("v,want", [(20.0, "auto_avoid"), (15.1, "auto_avoid"),
                                    (15.0, "downgrade"), (8.1, "downgrade"),
                                    (8.0, "clean"), (0.0, "clean"), (None, "missing")])
def test_tier_kr(v, want):
    rec = {"ticker": "000001", "kis_short_sale": ({"avg_short_ratio_5d": v} if v is not None else {})}
    assert ST._tier(rec)[0] == want


@pytest.mark.parametrize("v,want", [(25.0, "downgrade"), (20.0, "clean"), (None, "missing")])
def test_tier_us(v, want):
    rec = {"ticker": "AAPL", "short_interest": ({"short_pct": v} if v is not None else {})}
    t, _, market = ST._tier(rec)
    assert t == want and market == "US"


# ── 수익률 ──────────────────────────────────────────────────────────

def _bars(closes, start=20260601):
    return [[start + i, 0, 0, 0, c, 0] for i, c in enumerate(closes)]


def test_forward_return_math():
    b = _bars([100, 101, 102, 110])
    assert ST._forward(b, "2026-06-01", 3) == 10.0


def test_forward_none_when_horizon_not_elapsed():
    """구간이 아직 안 지났으면 None — 외삽·부분구간 금지."""
    assert ST._forward(_bars([100, 101]), "2026-06-01", 20) is None


# ── 🚨 의사복제 통제 ─────────────────────────────────────────────────

def _wire(monkeypatch, tmp_path, days):
    monkeypatch.setattr(ST, "TRAIL_PATH", str(tmp_path / "t.jsonl"))
    monkeypatch.setattr(ST, "SUMMARY_PATH", str(tmp_path / "s.json"))
    hist = tmp_path / "history"
    hist.mkdir()
    for day, recs in days.items():
        (hist / f"{day}.json").write_text(json.dumps({"recommendations": recs}),
                                          encoding="utf-8")
    monkeypatch.setattr(ST, "HISTORY_GLOB", str(hist / "20??-??-??.json"))


def test_ticker_level_aggregation_beats_observation_count(monkeypatch, tmp_path):
    """같은 종목이 매일 재등장해도 N 은 종목 수다.

    실측에서 auto_avoid 관측 31건이 고유 종목 9개였고, 종목 단위로 접자 tier 순서가
    뒤집혔다(downgrade 관측 −1.97% → 종목 −4.34%). 관측 수를 N 으로 쓰면 유의성을 지어낸다.
    """
    aa = {"ticker": "000001", "kis_short_sale": {"avg_short_ratio_5d": 20.0}}
    days = {f"2026-06-{d:02d}": [dict(aa)] for d in range(1, 11)}   # 한 종목 10일 반복
    _wire(monkeypatch, tmp_path, days)
    monkeypatch.setattr(ST, "_load_bars", lambda: {"000001": _bars([100] * 40)})
    s = ST.build()
    ent = s["KR"]["auto_avoid"]["fwd_20d"]
    assert ent["n_observations"] > ent["n_tickers"]     # 부풀려진 쪽
    assert ent["n_tickers"] == 1                        # 유효 표본
    assert any("통계 무의미" in x and "N=1" in x for x in s["labels"])


def test_failure_clause_gated_on_ticker_count(monkeypatch, tmp_path):
    """표본 미달이면 경보(🚨)가 아니라 판정 보류로 표기된다."""
    days = {}
    for d in range(1, 11):
        days[f"2026-06-{d:02d}"] = [
            {"ticker": "000001", "kis_short_sale": {"avg_short_ratio_5d": 20.0}},
            {"ticker": "000002", "kis_short_sale": {"avg_short_ratio_5d": 1.0}},
        ]
    _wire(monkeypatch, tmp_path, days)
    monkeypatch.setattr(ST, "_load_bars", lambda: {
        "000001": _bars([100] * 20 + [110] * 20),      # auto_avoid 가 더 잘 감
        "000002": _bars([100] * 20 + [90] * 20)})
    s = ST.build()
    joined = " ".join(s["labels"])
    assert "판정 보류" in joined and "🚨" not in joined


def test_missing_tier_separated_from_clean(monkeypatch, tmp_path):
    days = {"2026-06-01": [{"ticker": "000001"},                      # 결측
                           {"ticker": "000002", "kis_short_sale": {"avg_short_ratio_5d": 1.0}}]}
    _wire(monkeypatch, tmp_path, days)
    monkeypatch.setattr(ST, "_load_bars", lambda: {})
    s = ST.build()
    assert s["KR"]["missing"]["n_tickers"] == 1
    assert s["KR"]["clean"]["n_tickers"] == 1


def test_observation_only_and_idempotent(monkeypatch, tmp_path):
    days = {"2026-06-01": [{"ticker": "000001", "kis_short_sale": {"avg_short_ratio_5d": 20.0}}]}
    _wire(monkeypatch, tmp_path, days)
    monkeypatch.setattr(ST, "_load_bars", lambda: {})
    s = ST.build()
    assert s["brain_input"] is False
    ST.build()
    assert sum(1 for _ in open(ST.TRAIL_PATH, encoding="utf-8")) == 1


def test_markets_not_summed(monkeypatch, tmp_path):
    """KR·US 는 별도 집계 — 측정 대상이 달라 합산이 의미 없다."""
    days = {"2026-06-01": [{"ticker": "000001", "kis_short_sale": {"avg_short_ratio_5d": 20.0}},
                           {"ticker": "AAPL", "short_interest": {"short_pct": 25.0}}]}
    _wire(monkeypatch, tmp_path, days)
    monkeypatch.setattr(ST, "_load_bars", lambda: {})
    s = ST.build()
    assert s["KR"]["auto_avoid"]["n_tickers"] == 1
    assert s["US"]["downgrade"]["n_tickers"] == 1
    assert s["US"]["auto_avoid"]["n_tickers"] == 0      # 미장엔 이 tier 자체가 없다
