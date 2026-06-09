"""
MarketHorizon V0 — "남이 시장 어디까지 가냐 물을 때 답"

핵심 4축:
  1. Probit 침체확률 (Estrella-Mishkin 1996, yield curve 단일 변수)
  2. CAPE percentile (Shiller 1881- 분포 위치)
  3. Cycle stage (rule-based 5단계 분류)
  4. Horizon median return (regime 기반 historical lookup)

정직 패턴: 분포 + 가정 노출. 단정 X. self-attribution 명시.
계획 docs/MARKET_HORIZON_V0_PLAN.md
"""

from __future__ import annotations

import json
import logging
import math
import os
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst  # 시점 기록 (메모리 feedback_macro_timestamp_policy)

logger = logging.getLogger(__name__)
_STATE_PATH = os.path.join(DATA_DIR, "metadata", "market_horizon_state.json")


# ──────────────────────────────────────────────────────────────
# 1) Probit 침체확률 (Estrella-Mishkin 1996)
# ──────────────────────────────────────────────────────────────
# P(recession in 12M) = Φ(α + β × spread_3m_10y)
# 미국 1968- 칼리브레이션, hit 6/7 (1971 false positive 1번)
PROBIT_ALPHA = -0.546
PROBIT_BETA = -0.690


def _phi(x: float) -> float:
    """표준정규 누적분포 (math.erf 활용)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def recession_prob_12m(spread_3m_10y: Optional[float]) -> Optional[float]:
    if spread_3m_10y is None:
        return None
    return _phi(PROBIT_ALPHA + PROBIT_BETA * spread_3m_10y)


# ──────────────────────────────────────────────────────────────
# 2) CAPE percentile (Shiller 1881-2024 분포)
# ──────────────────────────────────────────────────────────────
# monthly CAPE 분포 근사 (Shiller online dataset 기반).
# V0 hardcoded; V1 에서 actual historical series 동적 계산.
_CAPE_PERCENTILE_TABLE: List[tuple] = [
    (5, 6.5), (10, 8.5), (25, 11.0), (50, 16.0),
    (75, 22.0), (85, 26.5), (90, 30.0), (95, 33.0), (99, 40.0),
]


def cape_percentile(cape: Optional[float]) -> Optional[int]:
    if cape is None:
        return None
    prev_p, prev_v = 0, 5.0
    for p, v in _CAPE_PERCENTILE_TABLE:
        if cape <= v:
            # 선형 보간
            if v == prev_v:
                return p
            frac = (cape - prev_v) / (v - prev_v)
            return int(prev_p + frac * (p - prev_p))
        prev_p, prev_v = p, v
    return 99


# ──────────────────────────────────────────────────────────────
# 3) Cycle stage 분류 (rule-based, 5변수 — V1 2026-05-06)
# ──────────────────────────────────────────────────────────────
# V1 = spread / hy_oas / unemployment / consumer_sentiment / vix 5변수 rule-based.
# unknown 반환 = spread 또는 hy_oas 결손 시 (= 데이터 결손 센티넬, 국면 X).
#   주의: unknown 은 시장 국면이 아님 — caller 에서 carry-forward 로 직전 known
#   stage 유지 + alert 차단 (FRED 결손 run 이 euphoria 를 덮어쓰는 깜빡임 방지,
#   2026-06-06 fix). CAPE/PMI refinement 는 V2 에서 보강.
def classify_cycle_stage(
    spread_2y_10y: Optional[float],
    hy_oas: Optional[float],
    unemployment: Optional[float],
    consumer_sent: Optional[float],
    vix: Optional[float],
    fred_recession_now: Optional[float] = None,
    cape_pctile: Optional[int] = None,
) -> str:
    """5단계 분류 — early_bull / mid_bull / late_bull / euphoria / bear.

    핵심 2변수 (spread + hy_oas) 만 있으면 진행. CAPE/실업/소비심리 etc 는 refinement.
    """
    if spread_2y_10y is None or hy_oas is None:
        return "unknown"

    # bear: NBER 침체 또는 실업 급등 + 신용 스트레스 + VIX 패닉
    if (fred_recession_now or 0) > 0.4:
        return "bear"
    if (unemployment or 0) > 5.5 and hy_oas > 5 and (vix or 0) > 28:
        return "bear"

    # euphoria — 강화 (2026-05-07): CAPE 95+ 단독 또는 옛 조합
    if cape_pctile is not None and cape_pctile >= 95:
        # 1929/2000/2021 류 극단 valuation. spread/VIX 무관 trigger
        return "euphoria"
    if cape_pctile is not None and cape_pctile >= 90 and (spread_2y_10y < 0.5 or (vix or 99) < 16):
        return "euphoria"
    if spread_2y_10y < 0 and hy_oas < 3 and (vix or 99) < 14:
        return "euphoria"

    # late_bull: CAPE 75+ 또는 spread 평탄 + HY 정상
    if cape_pctile is not None and cape_pctile >= 75:
        return "late_bull"
    if spread_2y_10y < 0.5 and hy_oas < 4 and (unemployment is None or unemployment < 5):
        return "late_bull"

    # early_bull: CAPE 50- + spread 가파름 + consumer_sent 회복
    if cape_pctile is not None and cape_pctile < 50 and spread_2y_10y > 1.5:
        return "early_bull"
    if spread_2y_10y > 1.8 and hy_oas < 4 and (consumer_sent or 0) > 75:
        return "early_bull"

    # 기본 = mid_bull
    return "mid_bull"


# ──────────────────────────────────────────────────────────────
# 4) Horizon return lookup (regime 기반)
# ──────────────────────────────────────────────────────────────
# S&P 500 1928-2024 historical regime별 forward return 분포 (대략).
# V0 hardcoded reasonable estimates — V1 에서 actual backtest 보정.
# 구조: stage → horizon → (median, p25, p75, p5, p95)
_HORIZON_RETURN_LOOKUP: Dict[str, Dict[str, tuple]] = {
    "early_bull": {
        "1m":  (0.018, -0.020, 0.050, -0.060, 0.085),
        "3m":  (0.045, -0.030, 0.110, -0.090, 0.180),
        "6m":  (0.085, -0.020, 0.180, -0.110, 0.290),
        "12m": (0.150,  0.050, 0.250, -0.100, 0.400),
    },
    "mid_bull": {
        "1m":  (0.012, -0.025, 0.040, -0.070, 0.080),
        "3m":  (0.030, -0.045, 0.090, -0.120, 0.150),
        "6m":  (0.055, -0.060, 0.140, -0.180, 0.240),
        "12m": (0.100,  0.000, 0.200, -0.150, 0.300),
    },
    "late_bull": {
        "1m":  (0.005, -0.040, 0.035, -0.090, 0.070),
        "3m":  (0.015, -0.070, 0.080, -0.150, 0.130),
        "6m":  (0.025, -0.090, 0.120, -0.220, 0.200),
        "12m": (0.050, -0.080, 0.150, -0.250, 0.300),
    },
    "euphoria": {
        "1m":  (-0.010, -0.080, 0.030, -0.180, 0.060),
        "3m":  (-0.030, -0.130, 0.050, -0.280, 0.110),
        "6m":  (-0.060, -0.200, 0.060, -0.400, 0.130),
        "12m": (-0.050, -0.250, 0.050, -0.500, 0.150),
    },
    "bear": {
        "1m":  (-0.015, -0.080, 0.040, -0.180, 0.090),
        "3m":  (-0.030, -0.140, 0.080, -0.280, 0.180),
        "6m":  (-0.020, -0.180, 0.130, -0.350, 0.250),
        "12m": ( 0.030, -0.150, 0.220, -0.300, 0.400),  # 평균회귀 시작
    },
    "unknown": {
        "1m":  (0.008, -0.030, 0.045, -0.080, 0.080),
        "3m":  (0.025, -0.060, 0.100, -0.140, 0.170),
        "6m":  (0.045, -0.080, 0.150, -0.200, 0.260),
        "12m": (0.080, -0.050, 0.200, -0.200, 0.330),
    },
}


def horizon_returns(stage: str) -> Dict[str, Dict[str, float]]:
    table = _HORIZON_RETURN_LOOKUP.get(stage, _HORIZON_RETURN_LOOKUP["unknown"])
    out: Dict[str, Dict[str, float]] = {}
    for h, (med, p25, p75, p5, p95) in table.items():
        out[h] = {"median": med, "p25": p25, "p75": p75, "p5": p5, "p95": p95}
    return out


# ──────────────────────────────────────────────────────────────
# 4.5) Historical Analog Matching (V2, 2026-05-07)
# ──────────────────────────────────────────────────────────────
# Robert Shiller 데이터 + 시장 사료 기반 hardcoded analog. V3 에서 동적 매칭.
# distance = sqrt(sum((current - analog) / scale)^2) 정규화 5변수.
# 변수: CAPE / 10Y-3M spread / HY OAS / unemployment / VIX
# scale: 각 변수 historical std 근사
HISTORICAL_ANALOGS: List[Dict[str, Any]] = [
    {
        "name": "1929 9월 — 대공황 직전",
        "date": "1929-09",
        "cape": 32.6, "spread_3m_10y": 0.5, "hy_oas": 4.0, "unemployment": 3.2, "vix": None,
        "after_pct": {"1m": -19, "3m": -35, "6m": -47, "12m": -55, "24m": -83},
    },
    {
        "name": "1987 8월 — Black Monday 직전",
        "date": "1987-08",
        "cape": 18.0, "spread_3m_10y": 1.5, "hy_oas": 3.0, "unemployment": 6.1, "vix": 18.0,
        "after_pct": {"1m": -3, "3m": -22, "6m": -10, "12m": +12, "24m": +35},
    },
    {
        "name": "1996 12월 — Greenspan 'irrational exuberance' 발언",
        "date": "1996-12",
        "cape": 28.3, "spread_3m_10y": 1.0, "hy_oas": 3.4, "unemployment": 5.4, "vix": 16.4,
        "after_pct": {"1m": +6, "3m": +5, "6m": +18, "12m": +31, "24m": +57},
    },
    {
        "name": "2000 3월 — 닷컴 버블 정점",
        "date": "2000-03",
        "cape": 44.2, "spread_3m_10y": -0.3, "hy_oas": 5.5, "unemployment": 4.0, "vix": 24.5,
        "after_pct": {"1m": -10, "3m": -2, "6m": -7, "12m": -25, "24m": -40},
    },
    {
        "name": "2007 10월 — GFC 직전",
        "date": "2007-10",
        "cape": 27.5, "spread_3m_10y": 0.6, "hy_oas": 4.5, "unemployment": 4.7, "vix": 19.5,
        "after_pct": {"1m": -4, "3m": -8, "6m": -10, "12m": -38, "24m": -45},
    },
    {
        "name": "2018 1월 — Volmageddon 직전",
        "date": "2018-01",
        "cape": 33.3, "spread_3m_10y": 1.3, "hy_oas": 3.4, "unemployment": 4.1, "vix": 11.0,
        "after_pct": {"1m": -3, "3m": -8, "6m": +2, "12m": -2, "24m": +14},
    },
    {
        "name": "2021 12월 — 코로나 후 정점",
        "date": "2021-12",
        "cape": 38.6, "spread_3m_10y": 1.4, "hy_oas": 3.1, "unemployment": 3.9, "vix": 17.2,
        "after_pct": {"1m": -5, "3m": -5, "6m": -20, "12m": -19, "24m": -8},
    },
    {
        "name": "2024 12월 — 2024 후반 강세",
        "date": "2024-12",
        "cape": 38.0, "spread_3m_10y": 0.4, "hy_oas": 2.8, "unemployment": 4.1, "vix": 16.0,
        "after_pct": {"1m": -2, "3m": -8, "6m": None, "12m": None, "24m": None},  # 미완
    },
]

# 정규화 scale (historical std 근사)
_ANALOG_SCALE = {
    "cape": 8.0,
    "spread_3m_10y": 1.0,
    "hy_oas": 1.5,
    "unemployment": 1.5,
    "vix": 5.0,
}


def find_nearest_analogs(
    current: Dict[str, Optional[float]],
    n: int = 5,
) -> List[Dict[str, Any]]:
    """현재 5변수 vector 와 가장 가까운 historical N 시점.

    distance = sqrt(sum((cur_v - hist_v)/scale)^2). 둘 중 하나 None 이면 그 변수 skip.
    """
    scored: List[tuple] = []
    for analog in HISTORICAL_ANALOGS:
        sq_sum = 0.0
        used = 0
        for k, scale in _ANALOG_SCALE.items():
            cv = current.get(k)
            hv = analog.get(k)
            if cv is None or hv is None:
                continue
            diff = (cv - hv) / scale
            sq_sum += diff * diff
            used += 1
        if used == 0:
            continue
        # 사용한 변수 수로 정규화 (변수 누락된 analog 도 비교 가능)
        dist = (sq_sum / used) ** 0.5
        scored.append((dist, analog))
    scored.sort(key=lambda x: x[0])
    out: List[Dict[str, Any]] = []
    for dist, a in scored[:n]:
        out.append({
            "name": a["name"],
            "date": a["date"],
            "distance": round(dist, 2),
            "cape": a["cape"],
            "spread_3m_10y": a["spread_3m_10y"],
            "hy_oas": a["hy_oas"],
            "unemployment": a["unemployment"],
            "vix": a["vix"],
            "after_pct": a["after_pct"],
        })
    return out


def aggregate_analog_horizons(analogs: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """nearest-N analog 의 1/3/6/12/24M 분포 집계 (median / p25 / p75)."""
    out: Dict[str, Dict[str, float]] = {}
    for h in ("1m", "3m", "6m", "12m", "24m"):
        values = [a["after_pct"].get(h) for a in analogs if a["after_pct"].get(h) is not None]
        if not values:
            continue
        sorted_v = sorted(values)
        n = len(sorted_v)
        median = sorted_v[n // 2] if n > 0 else 0
        p25_idx = max(0, int(n * 0.25))
        p75_idx = min(n - 1, int(n * 0.75))
        out[h] = {
            "n_samples": n,
            "median_pct": median,
            "p25_pct": sorted_v[p25_idx],
            "p75_pct": sorted_v[p75_idx],
            "min_pct": sorted_v[0],
            "max_pct": sorted_v[-1],
        }
    return out


# ──────────────────────────────────────────────────────────────
# 5) Verdict 한 줄
# ──────────────────────────────────────────────────────────────
_STAGE_LABEL_KO: Dict[str, str] = {
    "early_bull": "초기 강세장",
    "mid_bull":   "중기 강세장",
    "late_bull":  "후기 강세장",
    "euphoria":   "과열 (Euphoria)",
    "bear":       "약세장",
    "unknown":    "데이터 부족",
}


def build_verdict(
    stage: str,
    recession_p: Optional[float],
    cape_pctile: Optional[int],
    horizon_12m_median: Optional[float],
) -> str:
    parts = [_STAGE_LABEL_KO.get(stage, stage)]
    if recession_p is not None:
        parts.append(f"12M 침체확률 {recession_p * 100:.0f}%")
    if cape_pctile is not None:
        parts.append(f"CAPE {cape_pctile}%ile")
    if horizon_12m_median is not None:
        sign = "+" if horizon_12m_median >= 0 else ""
        parts.append(f"12M median {sign}{horizon_12m_median * 100:.0f}%")
    return " · ".join(parts)


# ──────────────────────────────────────────────────────────────
# 6) Signal stack
# ──────────────────────────────────────────────────────────────
def classify_new_listing_quality(
    recent_listings_count: Optional[float],
    avg_first_day_return_pct: Optional[float],
    baseline_listings_count: Optional[float],
    baseline_first_day_return_pct: Optional[float],
    baseline_listings_sigma: Optional[float] = None,
    baseline_return_sigma: Optional[float] = None,
) -> Dict[str, Any]:
    """막스 5번째 사이클 신호 — 신규 딜 품질 (Quality of New Issues, V2.3 2026-05-09).

    입력 (직전 3M 추정):
      - recent_listings_count: 직전 3M IPO 상장사 수
      - avg_first_day_return_pct: 같은 기간 평균 첫날 수익률 (%)
      - baseline_*: 5년 lookback baseline (count + return + 각 sigma)

    Output verdict (5단계):
      - speculative_extreme (광기): z+1.5 둘 다 — "모두가 확신" 막스 강세장 3단계
      - speculative (과열): z+0.7~+1.5
      - normal: -0.5~+0.7
      - cautious (위축): -1.5~-0.5
      - starved (기근): z-1.5 이하 — "소수만 아는" 막스 강세장 1단계 = 매수 기회
    """
    if recent_listings_count is None or baseline_listings_count is None:
        return {"verdict": None, "value": None, "z_count": None, "z_return": None}

    sigma_count = baseline_listings_sigma if baseline_listings_sigma else max(1.0, baseline_listings_count * 0.3)
    z_count = (recent_listings_count - baseline_listings_count) / sigma_count

    z_return: Optional[float] = None
    if avg_first_day_return_pct is not None and baseline_first_day_return_pct is not None:
        sigma_return = baseline_return_sigma if baseline_return_sigma else max(2.0, abs(baseline_first_day_return_pct) * 0.5)
        z_return = (avg_first_day_return_pct - baseline_first_day_return_pct) / sigma_return

    # combined z = mean(z_count, z_return). z_return 없으면 z_count only
    if z_return is not None:
        combined = (z_count + z_return) / 2.0
    else:
        combined = z_count

    if combined >= 1.5:
        verdict = "speculative_extreme"
    elif combined >= 0.7:
        verdict = "speculative"
    elif combined >= -0.5:
        verdict = "normal"
    elif combined >= -1.5:
        verdict = "cautious"
    else:
        verdict = "starved"

    return {
        "verdict": verdict,
        "value": round(combined, 2),
        "z_count": round(z_count, 2),
        "z_return": round(z_return, 2) if z_return is not None else None,
    }


def build_signals(
    spread_3m_10y: Optional[float],
    cape: Optional[float],
    cape_pctile: Optional[int],
    pmi: Optional[float],
    hy_oas: Optional[float],
    vix: Optional[float],
    fred_recession_now: Optional[float] = None,
    unemployment: Optional[float] = None,
    consumer_sent: Optional[float] = None,
    fear_greed: Optional[float] = None,
    pcr: Optional[float] = None,
    pcr_signal: Optional[str] = None,
    fund_rotation: Optional[str] = None,
    cot_signal: Optional[str] = None,
    cot_conviction: Optional[float] = None,
    new_listing_quality: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    sigs: List[Dict[str, Any]] = []

    if spread_3m_10y is not None:
        direction = "warn" if spread_3m_10y < 0 else "neutral" if spread_3m_10y < 1 else "ok"
        sigs.append({
            "name": "yield_spread_3m_10y",
            "value": round(spread_3m_10y, 2),
            "lead_months": [6, 18],
            "direction": direction,
            "note": "Estrella-Mishkin probit 입력 (12M lead)",
        })

    if fred_recession_now is not None:
        direction = "warn" if fred_recession_now > 0.3 else "neutral" if fred_recession_now > 0.1 else "ok"
        sigs.append({
            "name": "fred_recession_now",
            "value": round(fred_recession_now * 100, 1),  # fraction → %
            "direction": direction,
            "note": "FRED smoothed 침체 확률 % (현재, NBER 정의)",
        })

    if cape is not None:
        direction = "warn" if (cape_pctile or 0) > 85 else "neutral" if (cape_pctile or 50) > 50 else "ok"
        sigs.append({
            "name": "cape",
            "value": round(cape, 1),
            "percentile": cape_pctile,
            "direction": direction,
            "note": "Shiller PE, 1881- 분포 위치",
        })

    if pmi is not None:
        direction = "warn" if pmi < 50 else "ok"
        sigs.append({
            "name": "pmi",
            "value": round(pmi, 1),
            "direction": direction,
            "note": "ISM 제조업 PMI, 50 = 확장/수축 경계",
        })

    if unemployment is not None:
        direction = "warn" if unemployment > 5 else "neutral" if unemployment > 4 else "ok"
        sigs.append({
            "name": "unemployment",
            "value": round(unemployment, 2),
            "direction": direction,
            "note": "미국 실업률 (Sahm rule = 3M 평균 - 12M 최저 > 0.5)",
        })

    if hy_oas is not None:
        direction = "warn" if hy_oas > 5 else "neutral" if hy_oas > 3.5 else "ok"
        sigs.append({
            "name": "hy_oas",
            "value": round(hy_oas, 2),
            "direction": direction,
            "note": "BAML HY OAS, 신용 스트레스 (5%+ 위험)",
        })

    if consumer_sent is not None:
        direction = "warn" if consumer_sent < 70 else "neutral" if consumer_sent < 85 else "ok"
        sigs.append({
            "name": "consumer_sentiment",
            "value": round(consumer_sent, 1),
            "direction": direction,
            "note": "미시간대 소비자심리 (70 미만 = 침체심리)",
        })

    if vix is not None:
        direction = "warn" if vix > 30 else "neutral" if vix > 20 else "ok"
        sigs.append({
            "name": "vix",
            "value": round(vix, 1),
            "direction": direction,
            "note": "S&P 500 implied volatility (30+ 패닉)",
        })

    # Sentiment 신호 — euphoria 검증용 (contrarian)
    if fear_greed is not None:
        direction = "warn" if fear_greed >= 75 else "neutral" if fear_greed >= 55 else "ok" if fear_greed >= 25 else "warn"
        sigs.append({
            "name": "cnn_fear_greed",
            "value": round(fear_greed, 0),
            "direction": direction,
            "note": "CNN F&G 0-100 (75+ 극단 탐욕 = 매도 contrarian, 25- 극단 공포 = 매수)",
        })

    if pcr is not None:
        direction = "warn" if pcr >= 1.3 else "ok" if pcr <= 0.7 else "neutral"
        note = "Put/Call ratio (1.0+ 풋 우세 = 공포)"
        if pcr_signal:
            note += f" · 신호: {pcr_signal}"
        sigs.append({
            "name": "cboe_pcr",
            "value": round(pcr, 2),
            "direction": direction,
            "note": note,
        })

    if fund_rotation:
        direction = "ok" if fund_rotation == "risk_on" else "warn" if fund_rotation == "risk_off" else "neutral"
        sigs.append({
            "name": "fund_flow_rotation",
            "value": fund_rotation,
            "direction": direction,
            "note": "ETF 자금흐름 (risk_on / risk_off / neutral)",
        })

    if cot_signal:
        # CFTC COT 는 1주 lag 데이터. positioning extreme 도 contrarian 신호.
        direction = "neutral"
        if cot_signal == "bullish" and (cot_conviction or 0) > 75:
            direction = "warn"  # 극단 bullish positioning = contrarian sell signal
        elif cot_signal == "bearish" and (cot_conviction or 0) > 75:
            direction = "ok"    # 극단 bearish = contrarian buy
        elif cot_signal == "bullish":
            direction = "ok"
        elif cot_signal == "bearish":
            direction = "warn"
        note = f"비상업 longs positioning (1주 lag)"
        if cot_conviction is not None:
            note += f" · 확신 {cot_conviction:.0f}/100"
        sigs.append({
            "name": "cot_overall",
            "value": cot_signal,
            "direction": direction,
            "note": note,
        })

    # 신규 딜 품질 — 막스 5번째 사이클 신호 (V2.3, 2026-05-09)
    # speculative_extreme = 광기 (강세장 3단계 / 매도 contrarian)
    # starved = 기근 (강세장 1단계 / 매수 contrarian)
    if new_listing_quality and new_listing_quality.get("verdict"):
        v = new_listing_quality["verdict"]
        if v == "speculative_extreme":
            direction = "warn"
        elif v == "speculative":
            direction = "warn"
        elif v == "starved":
            direction = "ok"  # contrarian 매수 신호
        elif v == "cautious":
            direction = "neutral"
        else:
            direction = "neutral"
        note = "Howard Marks 5번째 사이클 신호 — 신규 딜 품질 (3M IPO 상장 + 첫날 수익률 z-score)"
        z_c = new_listing_quality.get("z_count")
        z_r = new_listing_quality.get("z_return")
        if z_c is not None or z_r is not None:
            parts = []
            if z_c is not None:
                parts.append(f"z_count {z_c:+.1f}")
            if z_r is not None:
                parts.append(f"z_return {z_r:+.1f}")
            note += " · " + " / ".join(parts)
        sigs.append({
            "name": "new_listing_quality",
            "value": new_listing_quality.get("value"),
            "direction": direction,
            "note": note,
        })

    return sigs


def _us_sentiment_signals(us: Dict[str, Any]) -> List[Dict[str, Any]]:
    """미장 sentiment/positioning priors → market_horizon informational signals.

    사전등록 spec(docs/PREREG_US_SENTIMENT_SIGNALS_2026_06_07.md) 임계 lock.
    ⚠️ informational ONLY — cycle_stage/verdict 가중 0 (N≥50 엣지 검증 전 → brain 불간섭).
    가설 labeling(RULE 7). 데이터 = data/observations/us_market_signals.jsonl 최신.
    two-track([[feedback_priors_vs_validation_two_track]]): 문헌 prior 있는 established 신호 → 지금 modest 사용 정당.
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(us, dict):
        return out

    def _m(src: str) -> Dict[str, Any]:
        v = us.get(src)
        return v.get("metrics", {}) if isinstance(v, dict) else {}

    # 1) AAII bull-bear spread — contrarian (Fisher-Statman 2000)
    spr = _m("aaii").get("bull_bear_spread")
    if spr is not None:
        direction = "ok" if spr < -10 else "warn" if spr > 20 else "neutral"
        out.append({"name": "aaii_sentiment", "value": spr, "direction": direction,
                    "note": f"AAII 개인심리 bull-bear {spr:+.1f}p (contrarian, Fisher-Statman 2000) · 가설 informational, verdict 가중 0"})

    # 2) NAAIM 매니저 노출 — positioning (practitioner 약 prior)
    exp = _m("naaim").get("exposure_mean")
    if exp is not None:
        direction = "warn" if exp > 90 else "ok" if exp < 30 else "neutral"
        out.append({"name": "naaim_exposure", "value": exp, "direction": direction,
                    "note": f"NAAIM 매니저 노출 {exp:.0f} (positioning, practitioner 약 prior) · 가설 informational, 가중 0"})

    # 3) FINRA 시장 공매도 비중 — daily short VOLUME(≠interest), 약 prior·관측 위주
    sv = _m("finra_short").get("market_short_volume_pct")
    if sv is not None:
        direction = "warn" if sv > 52 else "neutral"
        out.append({"name": "short_volume", "value": sv, "direction": direction,
                    "note": f"시장 공매도 비중 {sv:.1f}% (daily volume, 약 prior·관측 위주) · 가설 informational, 가중 0"})

    # 4) SEC Form4 내부자 순매수 — Cohen-Malloy-Pomorski 2012 (aggregate proxy)
    ins = _m("insider_form4")
    net, br = ins.get("net_buy_minus_sell"), ins.get("buy_ratio")
    if net is not None:
        direction = "ok" if net > 0 else "warn" if (br is not None and br < 0.10) else "neutral"
        out.append({"name": "insider_net", "value": net, "direction": direction,
                    "note": f"내부자 순매수 {net:+d} (buy_ratio {br if br is not None else 'n/a'}, Cohen-Malloy-Pomorski 2012, aggregate proxy) · 가설 informational, 가중 0"})

    return out


# ──────────────────────────────────────────────────────────────
# 7) 메인 진입점
# ──────────────────────────────────────────────────────────────
def _load_horizon_state() -> Dict[str, Any]:
    """이전 cycle_stage 상태 read."""
    if not os.path.exists(_STATE_PATH):
        return {}
    try:
        with open(_STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_horizon_state(state: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    try:
        with open(_STATE_PATH, "w") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"horizon state save 실패: {e}")


def _classify_signal_thresholds(
    recession_p: Optional[float],
    vix: Optional[float],
    cape_p: Optional[int],
    hy_oas: Optional[float],
    consumer_sent: Optional[float],
    pcr: Optional[float],
    fund_rotation: Optional[str],
) -> Dict[str, str]:
    """각 신호의 임계 status. 변경 시 텔레그램 alert."""
    out: Dict[str, str] = {}
    if recession_p is not None:
        out["recession_prob"] = "high" if recession_p >= 0.30 else "normal"
    if vix is not None:
        out["vix"] = "panic" if vix >= 30 else "elevated" if vix >= 25 else "normal"
    if cape_p is not None:
        out["cape_pctile"] = "extreme" if cape_p >= 95 else "high" if cape_p >= 75 else "normal"
    if hy_oas is not None:
        out["hy_oas"] = "stress" if hy_oas >= 5 else "elevated" if hy_oas >= 3.5 else "normal"
    if consumer_sent is not None:
        out["consumer"] = "panic" if consumer_sent < 30 else "weak" if consumer_sent < 60 else "normal"
    if pcr is not None:
        out["pcr"] = "fear" if pcr >= 1.3 else "normal"
    if fund_rotation:
        out["fund_rotation"] = fund_rotation
    return out


_SIGNAL_LABELS_KO = {
    "recession_prob": "FRED 침체확률",
    "vix": "VIX",
    "cape_pctile": "CAPE percentile",
    "hy_oas": "HY OAS 신용 스프레드",
    "consumer": "소비자심리",
    "pcr": "Put/Call Ratio",
    "fund_rotation": "ETF 자금흐름",
}

_SIGNAL_STATUS_EMOJI = {
    "panic": "🚨", "stress": "🚨", "extreme": "⚠️",
    "elevated": "⚠️", "high": "⚠️", "fear": "⚠️", "weak": "⚠️",
    "normal": "✅", "risk_on": "✅", "risk_off": "🚨",
}


def _alert_signal_cross(curr: Dict[str, str], prev: Dict[str, str]) -> List[str]:
    """임계 cross 변경 감지. 변경된 신호 list 반환 (alert 메시지용)."""
    changes: List[str] = []
    for key, val in curr.items():
        prev_val = prev.get(key)
        if prev_val is None or prev_val == val:
            continue
        # 의미 있는 변경만 (normal ↔ 비정상 또는 비정상 → 다른 비정상)
        emoji = _SIGNAL_STATUS_EMOJI.get(val, "📊")
        label = _SIGNAL_LABELS_KO.get(key, key)
        changes.append(f"  {emoji} <b>{label}</b>: {prev_val} → {val}")
    return changes


def _alert_signal_thresholds(curr: Dict[str, str]) -> None:
    """신호 임계 cross 시 텔레그램 alert. state 의 thresholds 와 비교."""
    state = _load_horizon_state()
    prev_thresholds = state.get("signal_thresholds") or {}
    if not prev_thresholds:
        # 첫 산출 — state 만 박고 alert 안 보냄
        state["signal_thresholds"] = curr
        _save_horizon_state(state)
        return

    changes = _alert_signal_cross(curr, prev_thresholds)
    if not changes:
        return

    text = "📊 <b>MarketHorizon Signal 변경</b>\n\n" + "\n".join(changes)
    try:
        from api.notifications.telegram import send_message
        send_message(text)
        logger.info(f"signal threshold alert: {len(changes)}건 변경")
    except Exception as e:
        logger.warning(f"signal alert 실패: {e}")

    # state 갱신 (변경된 신호만 반영됨 — cycle_stage / changed_at 보존)
    state["signal_thresholds"] = curr
    state["signal_changed_at"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    _save_horizon_state(state)


def _alert_stage_change(
    new_stage: str,
    recession_p: Optional[float],
    cape_p: Optional[int],
    horizon_12m_med: Optional[float],
    verdict: str,
) -> None:
    """cycle_stage 변경 시 텔레그램 1회 alert (dedupe)."""
    state = _load_horizon_state()
    prev_stage = state.get("cycle_stage")
    if prev_stage == new_stage:
        return  # 변경 없음

    # 첫 산출이면 alert 안 보냄 (state 초기화)
    if prev_stage is None:
        state["cycle_stage"] = new_stage
        state["first_seen_at"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
        _save_horizon_state(state)
        return

    # unknown = 데이터 결손 센티넬 (국면 X). caller carry-forward 가 1차 방어지만,
    # 직전 known stage 부재 (최초 분류 전) 등 carry-forward 불가 시엔 unknown 이 통과.
    # in/out unknown 전이는 spurious cycle 변경 alert → state 만 갱신, 텔레그램 차단
    # (2026-06-06 fix, defense-in-depth).
    if prev_stage == "unknown" or new_stage == "unknown":
        state["cycle_stage"] = new_stage
        state["previous_stage"] = prev_stage
        state["changed_at"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
        _save_horizon_state(state)
        return

    # 변경 감지 → 텔레그램 alert
    direction_arrow = "→"
    severity_emoji = "📊"
    if new_stage == "euphoria":
        severity_emoji = "⚠️"
    elif new_stage == "bear":
        severity_emoji = "🚨"
    elif new_stage in ("late_bull",) and prev_stage in ("mid_bull", "early_bull"):
        severity_emoji = "⚠️"
    elif new_stage in ("mid_bull", "early_bull") and prev_stage in ("bear",):
        severity_emoji = "✅"

    horizon_str = f"{horizon_12m_med * 100:+.0f}%" if horizon_12m_med is not None else "—"
    cape_str = f"{cape_p}%ile" if cape_p is not None else "?"
    rec_str = f"{recession_p * 100:.0f}%" if recession_p is not None else "?"

    text = (
        f"{severity_emoji} <b>MarketHorizon Cycle 변경</b>\n\n"
        f"  <code>{prev_stage}</code> {direction_arrow} <code>{new_stage}</code>\n\n"
        f"  CAPE: {cape_str}\n"
        f"  12M 침체확률: {rec_str}\n"
        f"  12M median: {horizon_str}\n\n"
        f"  {verdict}"
    )

    try:
        from api.notifications.telegram import send_message
        send_message(text)
        logger.info(f"market_horizon stage 변경 alert: {prev_stage} → {new_stage}")
    except Exception as e:
        logger.warning(f"market_horizon alert 실패: {e}")

    # state 갱신 (signal_thresholds 보존)
    state["cycle_stage"] = new_stage
    state["previous_stage"] = prev_stage
    state["changed_at"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    _save_horizon_state(state)


def _safe_get(d: dict, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


def compute_market_horizon(portfolio: dict) -> Dict[str, Any]:
    """portfolio.json 읽고 market_horizon 산출.

    Returns dict (위 V0 schema). 실패 시 partial 또는 minimal dict 반환 — Brain 처럼
    fallback graceful (메모리 feedback_ai_fallback_sanitization 정신).
    """
    macro = portfolio.get("macro") or {}
    bonds = portfolio.get("bonds") or {}

    # 1) 입력 추출
    us_10y = _safe_get(macro, "us_10y", "value")
    us_2y = _safe_get(macro, "us_2y", "value")
    spread_2y_10y = (us_10y - us_2y) if (us_10y is not None and us_2y is not None) else None
    spread_3m_10y = _safe_get(bonds, "yield_curves", "us", "spread_3m_10y")

    cape = _safe_get(macro, "fred", "cape", "value")
    pmi = _safe_get(macro, "fred", "ism_pmi", "value")
    hy_oas_raw = _safe_get(bonds, "credit_spreads", "us_hy_oas")
    # us_hy_oas schema 변동: 옛=fraction(0.034) / 신=percent(2.78). 둘 다 % 단위로 정규화
    if isinstance(hy_oas_raw, (int, float)):
        hy_oas = hy_oas_raw * 100 if abs(hy_oas_raw) < 1 else hy_oas_raw
    else:
        hy_oas = None

    vix = _safe_get(macro, "vix", "value")

    # FRED 자체 신호 (probit 보강용) — schema 가 dict 별로 다름 (pct/value)
    _fred = macro.get("fred") or {}
    _rec_dict = _fred.get("us_recession_smoothed_prob") or {}
    _rec_raw = _rec_dict.get("pct") if isinstance(_rec_dict, dict) else None
    # FRED 의 pct 는 0-100 percentage. 0-1 fraction 으로 정규화
    fred_recession_now = (_rec_raw / 100.0) if isinstance(_rec_raw, (int, float)) else None
    _u_dict = _fred.get("unemployment_rate") or {}
    unemployment = _u_dict.get("pct") if isinstance(_u_dict, dict) else None
    _cs_dict = _fred.get("consumer_sentiment") or {}
    consumer_sent = _cs_dict.get("value") if isinstance(_cs_dict, dict) else None

    # Sentiment 5종 (이미 수집된 데이터, 2026-05-07 활용 추가)
    _fg = portfolio.get("market_fear_greed") or {}
    fear_greed = _fg.get("value") if isinstance(_fg, dict) else None
    _pcr = portfolio.get("cboe_pcr") or {}
    pcr = _pcr.get("total_pcr_latest") if isinstance(_pcr, dict) else None
    pcr_signal = _pcr.get("signal") if isinstance(_pcr, dict) else None
    _ff = portfolio.get("fund_flows") or {}
    fund_rotation = _ff.get("rotation_signal") if isinstance(_ff, dict) else None
    _cot = portfolio.get("cftc_cot") or {}
    _cot_summary = _cot.get("summary") if isinstance(_cot, dict) else None
    cot_signal = _cot_summary.get("overall_signal") if isinstance(_cot_summary, dict) else None
    cot_conviction = _cot_summary.get("conviction_level") if isinstance(_cot_summary, dict) else None

    # 신규 딜 품질 (V2.3, 2026-05-09 — 막스 5번째 사이클 신호)
    # portfolio.new_listings schema (collector 큐잉, source 연결된 후 자동 합류):
    #   recent_3m_count, recent_3m_avg_first_day_pct, baseline_5y_count, baseline_5y_first_day_pct,
    #   baseline_count_sigma, baseline_return_sigma
    _nl = portfolio.get("new_listings") or {}
    new_listing_quality = classify_new_listing_quality(
        recent_listings_count=_nl.get("recent_3m_count") if isinstance(_nl, dict) else None,
        avg_first_day_return_pct=_nl.get("recent_3m_avg_first_day_pct") if isinstance(_nl, dict) else None,
        baseline_listings_count=_nl.get("baseline_5y_count") if isinstance(_nl, dict) else None,
        baseline_first_day_return_pct=_nl.get("baseline_5y_first_day_pct") if isinstance(_nl, dict) else None,
        baseline_listings_sigma=_nl.get("baseline_count_sigma") if isinstance(_nl, dict) else None,
        baseline_return_sigma=_nl.get("baseline_return_sigma") if isinstance(_nl, dict) else None,
    )

    # 2) 산출
    recession_p = recession_prob_12m(spread_3m_10y)
    cape_p = cape_percentile(cape)
    stage = classify_cycle_stage(
        spread_2y_10y, hy_oas, unemployment, consumer_sent, vix,
        fred_recession_now=fred_recession_now,
        cape_pctile=cape_p,
    )
    # carry-forward (2026-06-06 fix): spread/hy_oas 결손 run = unknown 반환.
    # unknown = 데이터 결손 센티넬이지 국면 변경 X. 매크로 국면은 run 단위로 안 바뀜 —
    # FRED 미적재 라이트 run 이 직전 known stage (euphoria 등) 를 unknown 으로 덮어쓰면
    # euphoria↔unknown 깜빡임 + 매 왕복마다 spurious cycle 변경 alert. 직전 known stage 유지.
    if stage == "unknown":
        _prev_stage = _load_horizon_state().get("cycle_stage")
        if _prev_stage and _prev_stage != "unknown":
            logger.info(
                f"market_horizon: 입력 결손 (spread/hy_oas) → carry-forward "
                f"직전 stage '{_prev_stage}' 유지 (unknown 무시)"
            )
            stage = _prev_stage
    horizons = horizon_returns(stage)
    horizon_12m_med = horizons.get("12m", {}).get("median")

    verdict = build_verdict(stage, recession_p, cape_p, horizon_12m_med)
    signals = build_signals(
        spread_3m_10y, cape, cape_p, pmi, hy_oas, vix,
        fred_recession_now=fred_recession_now,
        unemployment=unemployment,
        consumer_sent=consumer_sent,
        fear_greed=fear_greed,
        pcr=pcr,
        pcr_signal=pcr_signal,
        fund_rotation=fund_rotation,
        cot_signal=cot_signal,
        cot_conviction=cot_conviction,
        new_listing_quality=new_listing_quality,
    )

    # 미장 sentiment/positioning priors — modest informational (cycle_stage 무관 → brain 불간섭).
    # 사전등록 lock(docs/PREREG_US_SENTIMENT_SIGNALS_2026_06_07.md). verdict 가중 0 (N≥50 엣지 검증 전).
    signals.extend(_us_sentiment_signals(portfolio.get("us_sentiment") or {}))

    # cycle_stage 변경 감지 + 텔레그램 alert (V2, 2026-05-07)
    _alert_stage_change(stage, recession_p, cape_p, horizon_12m_med, verdict)

    # signal 임계 cross alert (V2.1, 2026-05-07) — cycle 변경 외 작은 신호 변동
    curr_thresholds = _classify_signal_thresholds(
        recession_p=recession_p,
        vix=vix,
        cape_p=cape_p,
        hy_oas=hy_oas,
        consumer_sent=consumer_sent,
        pcr=pcr,
        fund_rotation=fund_rotation,
    )
    _alert_signal_thresholds(curr_thresholds)

    # Historical analog matching (V2, 2026-05-07)
    current_vec = {
        "cape": cape,
        "spread_3m_10y": spread_3m_10y,
        "hy_oas": hy_oas,
        "unemployment": unemployment,
        "vix": vix,
    }
    analogs = find_nearest_analogs(current_vec, n=5)
    analog_horizons = aggregate_analog_horizons(analogs)

    # Black Swan event ledger 직전 24h top 3 (V2.2, 2026-05-08)
    # tail_risk_digest 가 적재한 ledger 에서 가장 최근/심각한 이벤트만 노출.
    # ledger 비어있으면 frontend 가 "목업" 라벨 표시 (사용자 결정 5/8).
    recent_swan_events: List[Dict[str, Any]] = []
    try:
        from api.intelligence.tail_risk_digest import load_black_swan_ledger
        _swan_raw = load_black_swan_ledger(hours=24)
        _swan_sorted = sorted(
            _swan_raw,
            key=lambda e: (int(e.get("severity") or 0), str(e.get("ts_kst") or "")),
            reverse=True,
        )
        for e in _swan_sorted[:3]:
            recent_swan_events.append({
                "ts_kst": e.get("ts_kst"),
                "severity": e.get("severity"),
                "category": e.get("category"),
                "summary_ko": e.get("summary_ko"),
                "primary_title": e.get("primary_title") or "",
                "link": e.get("link") or "",
                "portfolio_angle": e.get("portfolio_angle") or "",
            })
    except Exception as e:
        logger.warning(f"swan ledger 로드 실패: {e}")

    return {
        "verdict": verdict,
        "recession_prob_12m": round(recession_p, 3) if recession_p is not None else None,
        "cape_percentile": cape_p,
        "cape_value": round(cape, 1) if cape is not None else None,
        "cycle_stage": stage,
        "cycle_stage_label_ko": _STAGE_LABEL_KO.get(stage),
        "horizons": horizons,
        "analogs": analogs,
        "analog_horizons": analog_horizons,
        "recent_black_swan_events": recent_swan_events,
        "signals": signals,
        "model_meta": {
            "probit": {
                "source": "Estrella-Mishkin 1996",
                "calibration": "미국 1968-",
                "hit_rate": "6/7 since 1968 (1971 false positive)",
            },
            "cape_percentile": {
                "source": "Shiller 1881- monthly distribution",
                "version": "v0_hardcoded",
            },
            "horizon_returns": {
                "source": "S&P 500 1928-2024 regime lookup (V0 approximation)",
                "version": "v0_hardcoded",
                "note": "V1 에서 actual historical backtest 로 보정",
            },
        },
        "as_of": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }
