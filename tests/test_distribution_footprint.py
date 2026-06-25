"""분산매도 정황 관측 (distribution_footprint) 단위 test.

관측-only 불변식: 점수 None / observation_only True / disclaimer 병기 / flag>0만 적재.
플래그 정의 회귀 (외국인·기관 순매도·연속·대량보유 축소·overhang).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.intelligence.distribution_footprint import (  # noqa: E402
    compute_distribution_footprint,
    build_distribution_observations,
    CONSEC_SELL_MIN,
    MAJOR_HOLDER_CUT_PT,
    INST_OVERHANG_PCT,
)


def test_clean_stock_no_flags():
    s = {"ticker": "000000", "name": "클린", "flow": {"kis_foreign_net": 100, "kis_institution_net": 50}}
    fp = compute_distribution_footprint(s)
    assert fp["flags"] == []
    assert fp["flag_count"] == 0
    # 불변식
    assert fp["score"] is None
    assert fp["observation_only"] is True
    assert fp["lagged_incomplete"] is True
    assert "13F" in fp["disclaimer"]


def test_foreign_net_sell_flag():
    s = {"ticker": "T", "flow": {"kis_foreign_net": -5000, "kis_institution_net": 10}}
    fp = compute_distribution_footprint(s)
    assert "foreign_net_sell" in fp["flags"]
    assert "inst_net_sell" not in fp["flags"]


def test_consec_sell_streak_flag():
    s = {"ticker": "T", "flow": {"foreign_net": -1, "foreign_consec_sell": CONSEC_SELL_MIN, "inst_consec_sell": CONSEC_SELL_MIN - 1}}
    fp = compute_distribution_footprint(s)
    assert f"foreign_consec_sell_{CONSEC_SELL_MIN}d" in fp["flags"]
    # 미만이면 streak 플래그 없음
    assert not any(x.startswith("inst_consec_sell_") for x in fp["flags"])


def test_major_holder_reduction_flag():
    s = {
        "ticker": "T",
        "flow": {},
        "major_shareholder_changes": [
            {"delta_pct_pt": MAJOR_HOLDER_CUT_PT - 0.5, "hyslr_nm": "국민연금", "chnge_resn": "단순매도", "rcept_no": "1"},
            {"delta_pct_pt": 0.2, "hyslr_nm": "X"},  # 증가 → 제외
        ],
    }
    fp = compute_distribution_footprint(s)
    assert "major_holder_reduction" in fp["flags"]
    red = fp["detail"]["major_holder_reductions"]
    assert len(red) == 1 and red[0]["holder"] == "국민연금"


def test_institution_overhang_context_not_a_sell_flag():
    s = {"ticker": "T", "flow": {"kis_foreign_net": 1}, "held_pct_institutions": INST_OVERHANG_PCT + 5}
    fp = compute_distribution_footprint(s)
    assert fp["detail"]["institution_overhang"] is True
    # overhang 은 context — sell 플래그 아님
    assert fp["flags"] == []


def test_build_observations_only_flagged():
    stocks = [
        {"ticker": "A", "flow": {"kis_foreign_net": -1}},   # 발화
        {"ticker": "B", "flow": {"kis_foreign_net": 1}},    # 클린
        {"ticker": "", "flow": {"kis_foreign_net": -1}},    # ticker 없음 → 제외
    ]
    obs = build_distribution_observations(stocks, observed_at="2026-06-25T00:00:00+09:00")
    tickers = [o["ticker"] for o in obs]
    assert tickers == ["A"]
    assert obs[0]["source"] == "distribution_footprint.v0"
    assert obs[0]["observed_at"] == "2026-06-25T00:00:00+09:00"
    assert obs[0]["score"] is None
