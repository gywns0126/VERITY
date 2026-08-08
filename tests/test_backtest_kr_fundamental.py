# -*- coding: utf-8 -*-
"""kr_fundamental 백테스트 엔진 계약 테스트.

이 엔진의 결함은 조용하다 — 숫자가 나오고, 그 숫자가 틀렸다는 신호가 없다.
그래서 결과를 왜곡하는 4가지 경로를 각각 고정한다:
  ① look-ahead (미공시 재무로 매수)
  ② 상폐 손실 지우기 (last_bar 이후 채우기)
  ③ 겹침 표본 t 부풀리기
  ④ 결측을 실패로 채점
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.quant.backtest import kr_fundamental as bt  # noqa: E402


# ── ① look-ahead 차단 ──────────────────────────────────────────────────────
def test_pit_snapshot_blocks_unpublished_quarter():
    """분기말 직후는 아직 공시 전 — 45일 지나야 쓸 수 있다."""
    snaps = [
        {"quarter_end": "2023-12-31", "roa": 1.0},
        {"quarter_end": "2024-03-31", "roa": 2.0},
    ]
    # 2024-04-05 = 1Q 종료 5일 후 → 1Q 는 아직 못 쓴다. 직전 연간(12/31)도 45일 경과분만.
    got = bt.pit_snapshot(snaps, "20240405")
    assert got is not None and got["quarter_end"] == "2023-12-31"

    # 2024-05-20 = 3/31 + 50일 → 이제 1Q 사용 가능
    got2 = bt.pit_snapshot(snaps, "20240520")
    assert got2 is not None and got2["quarter_end"] == "2024-03-31"


def test_pit_snapshot_none_when_nothing_published_yet():
    snaps = [{"quarter_end": "2024-03-31", "roa": 2.0}]
    assert bt.pit_snapshot(snaps, "20240401") is None


# ── ② 상폐 처리 ────────────────────────────────────────────────────────────
def _series(days, closes):
    return {"d": list(days), "c": [float(c) for c in closes]}


def test_forward_return_normal():
    s = _series([20240102, 20240202, 20240302], [100, 110, 121])
    r = bt.forward_return(s, 20240102, 20240302, delisted=False, haircut=False)
    assert r is not None
    ret, mode = r
    assert mode == "normal"
    assert ret == pytest.approx(0.21, abs=1e-9)


def test_forward_return_delisted_uses_last_bar_not_fabricated():
    """🚨 상폐 종목은 마지막 체결가로 청산. 0 이나 진입가로 채우면 손실이 지워진다."""
    s = _series([20240102, 20240202], [100, 40])
    opt = bt.forward_return(s, 20240102, 20240402, delisted=True, haircut=False)
    con = bt.forward_return(s, 20240102, 20240402, delisted=True, haircut=True)
    assert opt is not None and con is not None
    assert opt[1] == "delisted" and con[1] == "delisted"
    assert opt[0] == pytest.approx(-0.60)                 # 40/100 − 1
    assert con[0] == pytest.approx(40 * 0.70 / 100 - 1)   # 정리매매 할인 가정
    assert con[0] < opt[0]                                # 보수 시나리오가 반드시 더 나쁘다


def test_forward_return_drops_plain_data_gap():
    """소멸 확정이 아닌 단순 공백은 관측을 버린다 — 결측 ≠ 실패."""
    s = _series([20240102, 20240202], [100, 40])
    assert bt.forward_return(s, 20240102, 20240402, delisted=False, haircut=False) is None


def test_forward_return_rejects_stale_entry_price():
    """진입 시점 근처에 가격이 없으면 그 관측을 만들지 않는다."""
    s = _series([20230102, 20240202], [100, 110])
    assert bt.forward_return(s, 20240102, 20240202, delisted=False, haircut=False) is None


# ── ③ 겹침 통제 ────────────────────────────────────────────────────────────
def test_non_overlap_selection_respects_horizon():
    """거래일 간격이 지평보다 좁으면 건너뛴다 (t 부풀림 차단)."""
    entry = [0, 10, 20, 30, 40, 50]
    assert bt._select_non_overlapping(entry, 20) == [0, 2, 4]     # 0·20·40
    assert bt._select_non_overlapping(entry, 60) == [0]
    assert bt._select_non_overlapping(entry, 10) == [0, 1, 2, 3, 4, 5]


def test_non_overlap_never_exceeds_naive():
    entry = list(range(0, 200, 21))
    for h in (20, 60):
        assert len(bt._select_non_overlapping(entry, h)) <= len(entry)


# ── ④ 결측 채점 금지 ───────────────────────────────────────────────────────
_FULL = {
    "quarter_end": "2024-03-31", "roa": 5.0, "debt_ratio": 50.0,
    "current_ratio": 2.0, "gross_margin": 30.0, "asset_turnover": 1.0,
    "operating_cashflow": 1000.0, "net_income": 500.0,
}
_PRIOR = dict(_FULL, quarter_end="2023-03-31", roa=1.0, debt_ratio=60.0,
              current_ratio=1.5, gross_margin=25.0, asset_turnover=0.8)


def test_fscore8_full_marks():
    """개선 전면 + CFO 양수 + CFO>NI = 8/8."""
    assert bt.axis_fscore8(_FULL, [_PRIOR, _FULL]) == 8


def test_fscore8_none_without_prior():
    """YoY 비교 대상이 없으면 채점하지 않는다 — 부분 채점은 결측을 실패로 만든다."""
    assert bt.axis_fscore8(_FULL, [_FULL]) is None


def test_fscore8_none_without_cashflow():
    cur = dict(_FULL)
    cur.pop("operating_cashflow")
    assert bt.axis_fscore8(cur, [_PRIOR, cur]) is None


def test_fscore8_zero_cfo_is_scored_not_dropped():
    """CFO=0 은 결측이 아니라 실측이다 — falsy-zero 로 버리면 안 된다.

    F2(0 > 0)만 탈락하고 F4 는 통과한다: 0 > −10 = 현금흐름이 순이익보다 낫다
    (발생주의 품질). 운영 `compute_piotroski_f_score` 의 분기 그대로다.
    """
    cur = dict(_FULL, operating_cashflow=0.0, net_income=-10.0)
    s = bt.axis_fscore8(cur, [_PRIOR, cur])
    assert s is not None and s == 7      # F2 만 탈락


def test_fscore8_deteriorating_company_scores_low():
    """전면 악화 기업 = 1/8. 유일한 득점이 F4 인 것이 정상이다.

    🚨 CFO(−100) > 순이익(−200) → 적자지만 현금흐름이 손실보다 덜 나쁘다 = Piotroski
       원논문의 발생주의 품질 신호. 적자라고 0점으로 만들면 그건 다른 산식이다.
    """
    cur = dict(_FULL, roa=-5.0, operating_cashflow=-100.0, net_income=-200.0)
    prior = dict(_PRIOR, roa=10.0, debt_ratio=20.0, current_ratio=3.0,
                 gross_margin=40.0, asset_turnover=2.0)
    assert bt.axis_fscore8(cur, [prior, cur]) == 1


def test_fscore8_matches_production_branch_for_loss_maker():
    """운영 `compute_piotroski_f_score` 와 F2/F4 판정이 같아야 한다 (재현 정합)."""
    from api.quant.factors.quality import compute_piotroski_f_score
    cur = dict(_FULL, operating_cashflow=500.0, net_income=-100.0)
    prod, details = compute_piotroski_f_score({
        "roa": cur["roa"], "operating_cashflow": cur["operating_cashflow"],
        "net_income": cur["net_income"], "sector": "제조",
    })
    assert prod >= 0
    assert any("F2" in d for d in details) and any("F4" in d for d in details)
    # 백테스트 축도 같은 두 항목을 득점해야 한다
    assert bt.axis_fscore8(cur, [_PRIOR, cur]) == 8


# ── GP/A ───────────────────────────────────────────────────────────────────
def test_gpa_identity():
    """매출총이익률(%) × 자산회전율 = 매출총이익/총자산."""
    assert bt.axis_gpa({"gross_margin": 40.0, "asset_turnover": 0.5}) == pytest.approx(0.20)


def test_gpa_none_on_missing():
    assert bt.axis_gpa({"gross_margin": 40.0}) is None


def test_gpa_zero_margin_is_value_not_missing():
    assert bt.axis_gpa({"gross_margin": 0.0, "asset_turnover": 1.0}) == 0.0


# ── 유니버스 제외 ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("ticker,name,expect", [
    ("005930", "삼성전자", None),
    ("005935", "삼성전자우", "preferred"),
    ("417790", "교보14호스팩", "spac"),
    ("330590", "롯데리츠", "reit"),
    ("069500", "KODEX 200", "etf"),
    ("123457", None, "preferred"),          # 이름 없어도 끝자리로 걸러낸다
    ("123450", None, None),
])
def test_exclusion_rules(ticker, name, expect):
    assert bt.exclusion_reason(ticker, name) == expect


# ── 통계 ───────────────────────────────────────────────────────────────────
def test_spearman_monotonic():
    assert bt.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert bt.spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)


def test_spearman_none_on_constant_input():
    """전 종목 같은 점수 = 순위 정보 0. 상관이 아니라 None 이어야 한다."""
    assert bt.spearman([5, 5, 5, 5], [1, 2, 3, 4]) is None


def test_t_stat_shape():
    r = bt.t_stat([0.1, 0.2, 0.15, 0.05])
    assert r["n"] == 4 and r["t"] is not None and r["positive_rate"] == 1.0


def test_t_stat_no_t_for_single_sample():
    assert bt.t_stat([0.1])["t"] is None


# ── 사전등록 상수 고정 ─────────────────────────────────────────────────────
def test_prereg_constants_locked():
    """사전등록에 고정한 값들 — 바뀌면 그건 다른 검정이다."""
    assert bt.HORIZONS == (20, 60)
    assert bt.PIT_LAG_DAYS == 45
    assert bt.DELIST_HAIRCUT == 0.70
    assert bt.SELL_TAX == 0.0020
    assert bt.COMMISSION == 0.00015
    assert bt.N_QUANTILE == 10
    assert bt.AXES == ("fscore8", "gpa")
    assert bt.SCENARIOS == ("optimistic", "conservative")
