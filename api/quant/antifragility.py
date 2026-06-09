"""
Antifragility 측정 인프라 v0.1 (2026-05-17, Perplexity Q6 학계 자문 적용).

2028 Vision Anti-fragile + Anti-FOMO 산식 코드. docs/GOLDEN_GOOSE_VISION_2028_v0.1.md SSOT.

산식 4종:
1. Antifragility Index (AI) = E[Gain|Shock] / E[Loss|Shock] > 1
2. Convexity: Skewness > 0, Kurtosis > 3
3. Volatility Benefit Ratio (VBR) = avg_ret_high_vol / avg_ret_low_vol > 1.5
4. Delta-adjusted Stress P&L: 시장 -10% 시 portfolio P&L

입력: 일별 portfolio return series + market benchmark series.
산출: dict + jsonl entry.

호출 위치: cron_health_monitor 분기별 또는 weekly_admin_pdf chap7.

NOTE: 운영 누적 데이터 부족 (2027~ 측정 가능). 본 모듈 = 산식 구현 인프라.
"""
from __future__ import annotations

import json
import math
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

KST = timezone(timedelta(hours=9))

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ANTIFRAGILITY_LEDGER_PATH = REPO_ROOT / "data" / "metadata" / "antifragility_ledger.jsonl"


def compute_skewness(returns: List[float]) -> Optional[float]:
    """Pearson skewness (3rd standardized moment).

    Anti-fragile 목표: Skewness > 0 (오른쪽 꼬리 두꺼움 = 큰 이익 비대칭 발생).
    """
    n = len(returns)
    if n < 3:
        return None
    mean = statistics.mean(returns)
    sd = statistics.stdev(returns)
    if sd == 0:
        return 0.0
    skew = sum((r - mean) ** 3 for r in returns) / (n * sd ** 3)
    return round(skew, 4)


def compute_kurtosis(returns: List[float]) -> Optional[float]:
    """Pearson kurtosis (4th standardized moment). 정규분포 = 3.

    Anti-fragile 목표: Kurtosis > 3 (꼬리가 정규분포보다 두꺼움 = tail event 비중 ↑).
    """
    n = len(returns)
    if n < 4:
        return None
    mean = statistics.mean(returns)
    sd = statistics.stdev(returns)
    if sd == 0:
        return 0.0
    kurt = sum((r - mean) ** 4 for r in returns) / (n * sd ** 4)
    return round(kurt, 4)


def compute_volatility_benefit_ratio(
    returns: List[float],
    vol_threshold_percentile: float = 0.7,
) -> Optional[Dict[str, Any]]:
    """VBR = avg_return_high_vol / avg_return_low_vol.

    Anti-fragile 목표: VBR > 1.5 (변동성 높을 때 수익 ↑ = 충격에서 이익).
    rolling 5d std 로 high/low vol 분류.
    """
    n = len(returns)
    if n < 30:
        return None
    # 5일 rolling vol
    vols = []
    for i in range(4, n):
        window = returns[i - 4 : i + 1]
        vols.append((i, statistics.stdev(window) if len(window) >= 2 else 0))
    if not vols:
        return None

    # 70 percentile = high vol cutoff
    vol_values = sorted(v for _, v in vols)
    cutoff_idx = int(len(vol_values) * vol_threshold_percentile)
    vol_cutoff = vol_values[min(cutoff_idx, len(vol_values) - 1)]

    high_vol_returns = [returns[i] for i, v in vols if v >= vol_cutoff]
    low_vol_returns = [returns[i] for i, v in vols if v < vol_cutoff]

    if not high_vol_returns or not low_vol_returns:
        return None

    avg_high = statistics.mean(high_vol_returns)
    avg_low = statistics.mean(low_vol_returns)

    if avg_low <= 0:
        # low vol 음수 / 0 = VBR 무한대. high 가 양수면 antifragile.
        vbr = None
        interpretation = "low_vol_avg_non_positive"
    else:
        vbr = round(avg_high / avg_low, 3)
        interpretation = "antifragile_confirmed" if vbr > 1.5 else "fragile_or_robust"

    return {
        "vbr": vbr,
        "avg_return_high_vol": round(avg_high, 5),
        "avg_return_low_vol": round(avg_low, 5),
        "n_high_vol": len(high_vol_returns),
        "n_low_vol": len(low_vol_returns),
        "vol_cutoff": round(vol_cutoff, 5),
        "interpretation": interpretation,
    }


def compute_antifragility_index(
    portfolio_returns: List[float],
    market_returns: List[float],
    shock_threshold_pct: float = -0.02,  # -2% 일별 = shock day
) -> Optional[Dict[str, Any]]:
    """AI = E[Gain|Shock] / E[Loss|Shock].

    market_returns 의 shock day (≤ shock_threshold_pct) 식별 후 portfolio 의
    같은 날 수익률 평균. shock 시 portfolio 가 양수 평균 = antifragile.

    AI > 1: 충격에서 이익 비대칭 우위. Anti-fragile 핵심 지표.
    AI = 1: 충격 영향 중립.
    AI < 1: 충격에서 손실 비대칭. fragile.
    """
    if len(portfolio_returns) != len(market_returns):
        return {"_error": "len mismatch"}
    if len(portfolio_returns) < 30:
        return None

    shock_days_pnl = []
    for p_r, m_r in zip(portfolio_returns, market_returns):
        if m_r <= shock_threshold_pct:
            shock_days_pnl.append(p_r)

    if len(shock_days_pnl) < 5:
        return {
            "_warning": f"shock days {len(shock_days_pnl)} 건 (<5) — AI 신뢰도 낮음",
            "ai": None,
            "n_shock_days": len(shock_days_pnl),
        }

    gains = [r for r in shock_days_pnl if r > 0]
    losses = [r for r in shock_days_pnl if r < 0]

    avg_gain = statistics.mean(gains) if gains else 0.0
    avg_loss = statistics.mean(losses) if losses else 0.0

    if avg_loss == 0:
        ai = None  # 손실 case 0 = 완벽 antifragile (정의상)
        interpretation = "no_loss_in_shock"
    else:
        ai = round(avg_gain / abs(avg_loss), 3)
        interpretation = (
            "antifragile_strong" if ai > 1.5
            else "antifragile" if ai > 1.0
            else "robust" if ai > 0.5
            else "fragile"
        )

    return {
        "ai": ai,
        "n_shock_days": len(shock_days_pnl),
        "n_gains_in_shock": len(gains),
        "n_losses_in_shock": len(losses),
        "avg_gain_in_shock": round(avg_gain, 5),
        "avg_loss_in_shock": round(avg_loss, 5),
        "shock_threshold_pct": shock_threshold_pct,
        "interpretation": interpretation,
    }


def compute_delta_adjusted_stress_pnl(
    portfolio_returns: List[float],
    market_returns: List[float],
    market_drop_threshold_pct: float = -0.10,  # -10% 일별
) -> Optional[Dict[str, Any]]:
    """시장 -10% 시 portfolio P&L. Anti-fragile 목표: 양수 또는 벤치마크 초과.

    한국 일별 -10% 는 매우 드묾 (서킷브레이커). 5일 누적 -10% 도 같이 측정.
    """
    if len(portfolio_returns) != len(market_returns):
        return {"_error": "len mismatch"}

    # 일별 -10%
    daily_drop_pnl = [
        p_r for p_r, m_r in zip(portfolio_returns, market_returns)
        if m_r <= market_drop_threshold_pct
    ]

    # 5일 rolling -10%
    rolling_drop_pnl = []
    for i in range(4, len(market_returns)):
        m_5d = sum(market_returns[i - 4 : i + 1])
        if m_5d <= market_drop_threshold_pct:
            p_5d = sum(portfolio_returns[i - 4 : i + 1])
            rolling_drop_pnl.append(p_5d - m_5d)  # excess return

    return {
        "n_daily_drops_10pct": len(daily_drop_pnl),
        "avg_portfolio_pnl_on_daily_drop": (
            round(statistics.mean(daily_drop_pnl), 5)
            if daily_drop_pnl else None
        ),
        "n_rolling_5d_drops_10pct": len(rolling_drop_pnl),
        "avg_excess_return_on_5d_drop": (
            round(statistics.mean(rolling_drop_pnl), 5)
            if rolling_drop_pnl else None
        ),
        "interpretation": (
            "no_drops_in_window" if not daily_drop_pnl and not rolling_drop_pnl
            else "antifragile" if (rolling_drop_pnl and statistics.mean(rolling_drop_pnl) > 0)
            else "fragile"
        ),
    }


def assess_antifragility(
    portfolio_returns: List[float],
    market_returns: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """4 산식 통합 + 종합 verdict.

    Anti-fragile 달성 조건 (Perplexity Q6 학계 자문):
    1. Skewness > 0
    2. Kurtosis > 3
    3. VBR > 1.5
    4. AI > 1.0
    4 조건 중 3+ 충족 = "antifragile_confirmed".
    """
    skew = compute_skewness(portfolio_returns)
    kurt = compute_kurtosis(portfolio_returns)
    vbr_result = compute_volatility_benefit_ratio(portfolio_returns)
    ai_result = (
        compute_antifragility_index(portfolio_returns, market_returns)
        if market_returns else None
    )
    delta_stress_result = (
        compute_delta_adjusted_stress_pnl(portfolio_returns, market_returns)
        if market_returns else None
    )

    # 조건 카운트
    conditions_met = 0
    conditions_status = {}
    if skew is not None:
        c = skew > 0
        conditions_status["skewness_positive"] = c
        conditions_met += int(c)
    if kurt is not None:
        c = kurt > 3
        conditions_status["kurtosis_fat_tail"] = c
        conditions_met += int(c)
    if vbr_result and vbr_result.get("vbr") is not None:
        c = vbr_result["vbr"] > 1.5
        conditions_status["vbr_above_1_5"] = c
        conditions_met += int(c)
    if ai_result and ai_result.get("ai") is not None:
        c = ai_result["ai"] > 1.0
        conditions_status["ai_above_1"] = c
        conditions_met += int(c)

    if conditions_met >= 3:
        verdict = "antifragile_confirmed"
    elif conditions_met == 2:
        verdict = "partial_antifragile"
    elif conditions_met == 1:
        verdict = "robust"
    else:
        verdict = "fragile"

    return {
        "verdict": verdict,
        "conditions_met": conditions_met,
        "conditions_status": conditions_status,
        "skewness": skew,
        "kurtosis": kurt,
        "vbr": vbr_result,
        "antifragility_index": ai_result,
        "delta_stress_pnl": delta_stress_result,
        "n_observations": len(portfolio_returns),
        "assessed_at": datetime.now(KST).isoformat(timespec="seconds"),
    }


def append_ledger(entry: Dict[str, Any]) -> bool:
    """data/metadata/antifragility_ledger.jsonl 1줄 append. 분기 monitor 추세 추적."""
    try:
        ANTIFRAGILITY_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(ANTIFRAGILITY_LEDGER_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        print(f"[antifragility] ledger write fail: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    # CLI dry-run: synthetic 데이터로 산식 sanity test
    import random
    random.seed(42)

    # 60일 portfolio + market returns. portfolio = market 0.7 + noise + tail boost
    market = [random.gauss(0.0005, 0.012) for _ in range(60)]
    # tail event 추가 (market -3%~-8%)
    market[15] = -0.03
    market[42] = -0.06
    market[48] = -0.08

    # portfolio: shock day 에 positive (antifragile sim)
    portfolio = []
    for m in market:
        if m <= -0.02:
            p = abs(m) * 0.5 + random.gauss(0, 0.005)  # shock 시 positive
        else:
            p = m * 0.7 + random.gauss(0, 0.008)
        portfolio.append(p)

    result = assess_antifragility(portfolio, market)
    print(json.dumps(result, indent=2, ensure_ascii=False))
