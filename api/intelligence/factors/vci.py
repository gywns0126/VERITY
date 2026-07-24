"""VCI v2.0 — Verity Contrarian Index + Cohen 1987 역발상 체크리스트.

원본: api/intelligence/verity_brain.py:1517-1684 (분해 전).
"""
from __future__ import annotations

import json
import os
import statistics
from typing import Any, Dict, Optional, Tuple

from api.config import CRYPTO_FUNDING_OVERHEAT, DATA_DIR
from api.intelligence.factors._common import _load_constitution

# 2026-07-24 VCI median-centering 캘리브레이션 캐시 (프로세스당 1회 로드).
# grounded 기본: median 0(중립=fact·sentiment 정렬), σ 5(robust MAD 근사, Perplexity 권고).
_VCI_CALIB_CACHE: Dict[str, Any] = {"loaded": False, "median": 0.0, "sigma": 5.0}


def _load_vci_calibration() -> Tuple[float, float]:
    """직전 portfolio.json 의 fact−sentiment gap 분포 → (median, robust_sigma=1.4826·MAD).

    2026-07-24 median-centering(Perplexity grounding): 옛 σ=15 고정 가정은 실측 gap 분포([-7,15],
    σ≈4.1, mean +2.9)와 3.6배 불일치 → 전 신호밴드 사장. robust median/MAD 로 표준화하면 체계 tilt
    제거(mean-shift) + 개월/스케일 무관 + 극단치 robust(Hampel MAD, N≈50 신뢰구간 양호). VCI 가 종목
    채점 도중 계산돼 현 유니버스 미지(chicken-egg) → 직전-run 발행 분포 사용(1-run lag, 분포 안정).
    cold-start/데이터부족(N<20) 시 grounded 기본(median 0, σ 5). 프로세스당 1회 캐시.
    """
    if _VCI_CALIB_CACHE["loaded"]:
        return _VCI_CALIB_CACHE["median"], _VCI_CALIB_CACHE["sigma"]
    _VCI_CALIB_CACHE["loaded"] = True
    try:
        with open(os.path.join(DATA_DIR, "portfolio.json"), encoding="utf-8") as f:
            pf = json.load(f)
        gaps = []
        for r in pf.get("recommendations", []):
            vb = r.get("verity_brain") or {}
            fscore = (vb.get("fact_score") or {}).get("score")
            sscore = (vb.get("sentiment_score") or {}).get("score")
            if isinstance(fscore, (int, float)) and isinstance(sscore, (int, float)):
                gaps.append(fscore - sscore)
        if len(gaps) >= 20:  # feedback_threshold_calibration_overfit_guard: N 충분 시만 재캘리
            med = statistics.median(gaps)
            mad = statistics.median([abs(g - med) for g in gaps])
            sigma = max(1.4826 * mad, 3.0)  # floor: 퇴화 분포서 tiny σ(과민) 방지
            _VCI_CALIB_CACHE["median"] = round(med, 2)
            _VCI_CALIB_CACHE["sigma"] = round(sigma, 2)
    except (OSError, ValueError, KeyError):
        pass  # 기본값 유지
    return _VCI_CALIB_CACHE["median"], _VCI_CALIB_CACHE["sigma"]


def _cohen_contrarian_checks(
    fact_score: float,
    stock: Dict[str, Any],
    portfolio: Dict[str, Any],
) -> Dict[str, Any]:
    """Steve Cohen 1987 역발상 체크리스트.
    패닉 구간에서 팩트가 좋은 종목의 역발상 매수 근거를 정량화한다."""
    macro = portfolio.get("macro", {})
    vix = macro.get("vix", {}).get("value", 0)
    mood = macro.get("market_mood", {}).get("score", 50)
    crypto = portfolio.get("crypto_macro", {})

    checks = []
    passed = 0

    # 1. 하락 원인: 수급(강제 청산) vs 펀더멘털 붕괴
    is_supply_driven = fact_score >= 60 and mood < 30
    checks.append({
        "name": "수급발 하락 (펀더멘털 아닌 강제 청산)",
        "passed": is_supply_driven,
    })
    if is_supply_driven:
        passed += 1

    # 2. VIX 역사적 극단
    vix_extreme = vix >= 40
    checks.append({
        "name": f"VIX 역사적 극단 ({vix})",
        "passed": vix_extreme,
    })
    if vix_extreme:
        passed += 1

    # 3. 크립토 디커플링 (BTC가 나스닥과 분리 움직임 = 독자적 헤지 신호)
    btc_corr = 0.5
    if crypto.get("available"):
        corr_data = crypto.get("btc_nasdaq_corr", {})
        if corr_data.get("ok"):
            btc_corr = corr_data.get("correlation", 0.5)
    crypto_decoupled = btc_corr < 0.3
    checks.append({
        "name": f"크립토 디커플링 (상관 {btc_corr:.2f})",
        "passed": crypto_decoupled,
    })
    if crypto_decoupled:
        passed += 1

    # 4. 기관 흡수(Absorption) 신호 — 외인+기관 순매수 + 가격 변동 안정
    flow = stock.get("flow", {})
    fg_net = flow.get("kis_foreign_net", 0)
    inst_net = flow.get("kis_institution_net", 0)
    # US: Finnhub 내부자 + 기관 보유 변화로 대체
    if stock.get("currency") == "USD":
        insider = stock.get("insider_sentiment") or {}
        inst_own = stock.get("institutional_ownership") or {}
        absorption = insider.get("mspr", 0) > 0 and inst_own.get("change_pct", 0) > 0
    else:
        absorption = fg_net > 0 and inst_net > 0
    checks.append({
        "name": "기관 흡수 신호 (순매수 + 가격 안정)",
        "passed": absorption,
    })
    if absorption:
        passed += 1

    const = _load_constitution()
    cohen_cfg = const.get("panic_stages", {}).get("cohen_checklist", {})
    bonus_per = cohen_cfg.get("bonus_per_check", 3)
    max_bonus = cohen_cfg.get("max_bonus", 12)

    bonus = min(passed * bonus_per, max_bonus)

    return {
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "bonus": bonus,
    }


def _compute_vci(
    fact: float,
    sentiment: float,
    stock: Optional[Dict[str, Any]] = None,
    portfolio: Optional[Dict[str, Any]] = None,
    *,
    gap_median: Optional[float] = None,
    robust_sigma: Optional[float] = None,
) -> Dict[str, Any]:
    """팩트와 심리의 괴리율 계산 — median-centered robust z (2026-07-24 재캘리).

    gap = fact − sentiment 를 유니버스 분포의 robust median/MAD 로 표준화. 옛 σ=15 고정 가정은 실측
    gap 분포([-7,15], σ≈4.1)와 3.6배 불일치로 전 밴드 사장했음(Perplexity grounding). 밴드 = robust z
    ±1(mild)/±2(strong). test 는 gap_median·robust_sigma override 로 결정론."""
    base_vci = round(fact - sentiment)

    if gap_median is None or robust_sigma is None:
        gap_median, robust_sigma = _load_vci_calibration()
    _z_base = (base_vci - gap_median) / robust_sigma  # base gap 의 robust z

    # V4: Cohen 체크리스트 (robust z ≥ 2 = 극단 저평가 territory). 옛 base_vci≥20 은 gap[-7,15]서 미발화.
    cohen = None
    cohen_bonus = 0
    if _z_base >= 2.0 and stock is not None and portfolio is not None:
        cohen = _cohen_contrarian_checks(fact, stock, portfolio)
        cohen_bonus = cohen["bonus"]

    # 버블 경계 (robust z ≤ -2)
    bubble_penalty = 0
    if _z_base <= -2.0 and stock is not None:
        # Soros 반사성: 심리만 좋고 팩트 나쁜 경우 추가 패널티
        funding_overheat = False
        if portfolio:
            crypto = portfolio.get("crypto_macro", {})
            if crypto.get("available"):
                fr = crypto.get("funding_rate", {})
                if fr.get("ok") and fr.get("rate_pct", 0) >= CRYPTO_FUNDING_OVERHEAT:
                    funding_overheat = True
        if funding_overheat:
            bubble_penalty = -5

    vci = base_vci + cohen_bonus + bubble_penalty

    # signal: 조정된 vci 의 robust z 밴드 (Perplexity 표준 robust z: |z|≥2 강 / ≥1 약).
    _z = (vci - gap_median) / robust_sigma
    if _z >= 2.0:
        signal = "STRONG_CONTRARIAN_BUY"
        label = "팩트 좋은데 심리 과도 비관 → 역발상 매수"
    elif _z >= 1.0:
        signal = "CONTRARIAN_BUY"
        label = "팩트 우위 — 시장이 아직 미반영"
    elif _z > -1.0:
        signal = "ALIGNED"
        label = "팩트·심리 정렬 — 추세 추종 유효"
    elif _z > -2.0:
        signal = "CONTRARIAN_SELL"
        label = "심리 과열 — 팩트 대비 고평가 주의"
    else:
        signal = "STRONG_CONTRARIAN_SELL"
        label = "심리만 좋고 팩트 나쁨 → 버블 경계"

    # ── Mispricing = base gap 의 median-centered robust z (2026-07-24 재캘리) ──
    # 옛 base_vci/15(σ=15 가정)은 gap 최대 15 라 |z| 최대 1.0 → extreme(≥2) 영구 미발화. robust z 로 정정.
    # (옛 'Baker-Wurgler 2006 정합' 표기는 오귀속 — B-W 는 시장단 심리지수, 여긴 종목단 fact−sentiment 괴리.)
    mispricing_z = round(_z_base, 2)
    if mispricing_z >= 2.0:
        mispricing_signal = "extreme_undervalued"  # fact > sentiment 2σ — 강 매수
    elif mispricing_z >= 1.0:
        mispricing_signal = "mild_undervalued"
    elif mispricing_z <= -2.0:
        mispricing_signal = "extreme_overvalued"  # sentiment > fact 2σ — 강 매도
    elif mispricing_z <= -1.0:
        mispricing_signal = "mild_overvalued"
    else:
        mispricing_signal = "fair_value"

    result = {
        "vci": vci,
        "base_vci": base_vci,
        "signal": signal,
        "label": label,
        "mispricing_z": mispricing_z,
        "mispricing_signal": mispricing_signal,
        "robust_z": round(_z, 2),
        "gap_median": gap_median,
        "robust_sigma": robust_sigma,
    }
    if cohen is not None:
        result["cohen_checklist"] = cohen
    if bubble_penalty:
        result["bubble_penalty"] = bubble_penalty
    return result
