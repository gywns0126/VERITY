"""매매 밴드 tier 스케일러 — 총액 기반 밴드폭 배율 (갭1).

사전등록 = docs/PREREG_TRADING_BANDS_REBALANCE_2026_08_02.md Part A (private repo).
PM 승인 2026-08-02 ("매매밴드 tier 승인. 3갭 빌드"). RULE 7 임계 1회 — 재조정 = 신규 사전등록.

🚨 신규 flat % 산식 아님 — 기존 밴드(ATR 동적 손절 trade_planner / BB 진입존)에 "배율만" 적용.
근거(원전 ≥2): Davis & Norman(1990)·Leland(2000) 무거래 밴드 — 유효 거래비용↑ → 최적 밴드폭↑.
소액 = 매도세 0.20%(2026)+최소수수료+정수주 그래뉼래리티의 %드래그↑ → 밴드 넓게(덜 거래).
XL 은 시장충격으로 재확대(U자). 자동 액션 없음 — trade_plan v0 "표시값" 철학 유지.
"""
from __future__ import annotations

from typing import Dict, Tuple

# (상한 KRW exclusive, tier, band_mult, drift_band_rel_pct, min_trade_krw, slice_required)
# PM 승인 배율: S ×1.4 / M ×1.0 / L ×0.8 / XL ×1.2 · 드리프트(상대) ±30/±20/±12/±18%
_TIERS: Tuple[Tuple[float, str, float, float, int, bool], ...] = (
    (10_000_000, "S", 1.4, 30.0, 300_000, False),
    (100_000_000, "M", 1.0, 20.0, 500_000, False),
    (1_000_000_000, "L", 0.8, 12.0, 1_000_000, False),
    (float("inf"), "XL", 1.2, 18.0, 1_000_000, True),
)


def band_profile(total_value_krw: float) -> Dict[str, object]:
    """총액 → tier 프로파일. 입력 비정상(<=0/NaN)은 M(중립 ×1.0) 반환."""
    try:
        v = float(total_value_krw)
    except (TypeError, ValueError):
        v = -1.0
    if not (v > 0):
        return {"tier": "M", "band_mult": 1.0, "drift_band_rel_pct": 20.0,
                "min_trade_krw": 500_000, "slice_required": False, "fallback": True}
    for upper, tier, mult, drift, min_trade, slice_req in _TIERS:
        if v < upper:
            return {"tier": tier, "band_mult": mult, "drift_band_rel_pct": drift,
                    "min_trade_krw": min_trade, "slice_required": slice_req, "fallback": False}
    raise AssertionError("unreachable")  # inf 상한이 흡수


def scaled_stop_pct(base_stop_pct: float, total_value_krw: float) -> float:
    """ATR 동적 손절 %(음수, trade_planner 산출)에 tier 배율 적용.

    예: base -6.2% · S tier(×1.4) → -8.68% (소액=넓게, 노이즈 손절 감소).
    base 가 양수로 오면 부호 정규화(항상 음수 반환).
    """
    prof = band_profile(total_value_krw)
    return -abs(float(base_stop_pct)) * float(prof["band_mult"])


def scaled_entry_zone(low: float, high: float, total_value_krw: float) -> Tuple[float, float]:
    """진입존(BB하단~MA20) 폭에 tier 배율 — 상단(high) 고정, 하단만 확장/축소.

    폭' = (high-low)×mult. S(×1.4)=더 깊은 하락에서만 진입 시작(덜 거래),
    L(×0.8)=좁게(정밀 진입). low>=high 등 비정상 입력은 원값 반환.
    """
    lo, hi = float(low), float(high)
    if not (hi > lo > 0):
        return lo, hi
    mult = float(band_profile(total_value_krw)["band_mult"])
    return hi - (hi - lo) * mult, hi
