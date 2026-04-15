"""
etfscreener.py — ETF 멀티팩터 스크리닝 엔진
의존: api/collectors/etfdata.py, api/collectors/etfus.py
역할: 모멘텀·밸류·퀄리티·유동성 4팩터 기반 ETF 순위 산출
      → VAMS 엔진의 ETF 추천 리스트 생성에 사용
팩터 가중치: 모멘텀 0.35 / 밸류 0.30 / 퀄리티 0.25 / 유동성 0.10
"""

import logging
import json
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FACTOR_WEIGHTS = {
    "momentum": 0.35,
    "value": 0.30,
    "quality": 0.25,
    "liquidity": 0.10,
}

TER_BENCHMARK = {
    "equity_domestic": 0.30,
    "equity_foreign": 0.50,
    "equity_us_large": 0.10,
    "equity_us_tech": 0.20,
    "equity_us_small": 0.20,
    "equity_us_total": 0.10,
    "equity_intl": 0.40,
    "equity_em": 0.50,
    "bond_kr": 0.20,
    "bond_us": 0.30,
    "bond_us_long": 0.20,
    "bond_us_mid": 0.20,
    "bond_us_short": 0.20,
    "bond_us_agg": 0.10,
    "bond_us_total": 0.10,
    "bond_us_ig": 0.20,
    "bond_us_hy": 0.40,
    "bond_us_tips": 0.20,
    "bond_em": 0.50,
    "bond_domestic": 0.20,
    "bond_foreign": 0.30,
    "sector": 0.50,
    "sector_financial": 0.20,
    "sector_tech": 0.20,
    "sector_energy": 0.30,
    "commodity": 0.60,
    "commodity_gold": 0.40,
    "commodity_silver": 0.50,
    "commodity_oil": 0.60,
    "thematic": 0.60,
    "thematic_innovation": 0.75,
    "dividend": 0.30,
    "leverage": 0.70,
    "inverse": 0.70,
    "alternative": 0.60,
}


# ──────────────────────────────────────────────
# 1. 개별 팩터 점수 계산 (0~100 정규화)
# ──────────────────────────────────────────────

def score_momentum(returns: Dict[str, Optional[float]]) -> Optional[float]:
    """
    모멘텀 팩터 점수.
    1M(10%), 3M(20%), 6M(30%), 1Y(40%) — 중장기 모멘텀 중시.
    """
    weights = {"1M": 0.10, "3M": 0.20, "6M": 0.30, "1Y": 0.40}
    total_w, total_score = 0.0, 0.0

    for period, w in weights.items():
        val = returns.get(period)
        if val is not None:
            total_score += val * w
            total_w += w

    if total_w < 0.3:
        return None

    raw = total_score / total_w
    normalized = (raw + 30) / 60 * 100
    return round(max(0.0, min(100.0, normalized)), 2)


def score_value(expense_ratio: Optional[float], category: str) -> Optional[float]:
    """밸류 팩터 — ETF에서 '밸류' = 비용 효율성 (TER 낮을수록 고점수)."""
    if expense_ratio is None:
        return 50.0

    benchmark = TER_BENCHMARK.get(category, 0.50) / 100
    if benchmark <= 0:
        benchmark = 0.005
    ratio = expense_ratio / benchmark
    score = (1 - min(ratio, 2.0) / 2.0) * 100
    return round(max(0.0, min(100.0, score)), 2)


def score_quality(
    tracking_error: Optional[float] = None,
    aum: Optional[float] = None,
    dividend_yield: Optional[float] = None,
    category: str = "",
) -> Optional[float]:
    """
    퀄리티 팩터.
    추적오차(40%), AUM 규모(40%), 배당수익률(20%).
    """
    scores: List[tuple] = []

    if tracking_error is not None:
        te_score = max(0, 100 - tracking_error * 50)
        scores.append(("te", te_score, 0.4))

    if aum is not None and aum > 0:
        if "domestic" in category or "kr" in category.lower():
            aum_score = min(100, math.log10(max(aum, 1)) / math.log10(10000) * 100)
        else:
            aum_score = min(100, math.log10(max(aum, 1)) / math.log10(10_000_000_000) * 100)
        scores.append(("aum", aum_score, 0.4))

    if dividend_yield is not None:
        if "bond" in category:
            div_score = min(100, dividend_yield / 0.03 * 100)
        else:
            div_score = min(100, 50 + dividend_yield / 0.02 * 25)
        scores.append(("div", div_score, 0.2))

    if not scores:
        return None

    total_w = sum(s[2] for s in scores)
    total_score = sum(s[1] * s[2] for s in scores) / total_w
    return round(max(0.0, min(100.0, total_score)), 2)


def score_liquidity(volume: Optional[float], trading_value: Optional[float] = None) -> Optional[float]:
    """유동성 팩터 — 일평균 거래량·거래대금 기준."""
    if volume is None and trading_value is None:
        return None

    score = 0.0
    if volume is not None and volume > 0:
        score = min(100, math.log10(max(volume, 1)) / math.log10(100_000) * 100)
    if trading_value is not None and trading_value > 0:
        tv_score = min(100, math.log10(max(trading_value, 1)) / math.log10(10_000_000_000) * 100)
        score = max(score, tv_score)

    return round(max(0.0, min(100.0, score)), 2)


# ──────────────────────────────────────────────
# 2. 종합 Verity ETF Score 계산
# ──────────────────────────────────────────────

def calc_verity_etf_score(etf: Dict[str, Any]) -> Dict[str, Any]:
    """ETF 1개에 대한 멀티팩터 종합점수 계산."""
    category = etf.get("category", "")
    returns = etf.get("returns", {})

    m_score = score_momentum(returns)
    v_score = score_value(etf.get("expense_ratio"), category)
    q_score = score_quality(
        tracking_error=etf.get("tracking_diff"),
        aum=etf.get("aum"),
        dividend_yield=etf.get("dividend_yield"),
        category=category,
    )
    l_score = score_liquidity(etf.get("volume"), etf.get("trading_value"))

    factor_scores: Dict[str, Optional[float]] = {
        "momentum": m_score,
        "value": v_score,
        "quality": q_score,
        "liquidity": l_score,
    }

    available = {k: v for k, v in factor_scores.items() if v is not None}
    if not available:
        verity_score: Optional[float] = None
    else:
        total_w = sum(FACTOR_WEIGHTS[k] for k in available)
        verity_score = sum(available[k] * FACTOR_WEIGHTS[k] for k in available) / total_w
        verity_score = round(verity_score, 2)

    signal = "UNKNOWN"
    if verity_score is not None:
        if verity_score >= 75:
            signal = "STRONG_BUY"
        elif verity_score >= 60:
            signal = "BUY"
        elif verity_score >= 45:
            signal = "WATCH"
        elif verity_score >= 30:
            signal = "CAUTION"
        else:
            signal = "AVOID"

    return {
        **etf,
        "factor_scores": factor_scores,
        "verity_etf_score": verity_score,
        "signal": signal,
        "screened_at": datetime.now().isoformat(),
    }


# ──────────────────────────────────────────────
# 3. 스크리닝 필터 + 랭킹
# ──────────────────────────────────────────────

def screen_etfs(
    etf_list: List[Dict[str, Any]],
    category_filter: Optional[str] = None,
    min_aum: Optional[float] = None,
    top_n: int = 20,
    exclude_leverage: bool = True,
) -> List[Dict[str, Any]]:
    """ETF 리스트를 멀티팩터 스크리닝 후 상위 N개 반환."""
    filtered = list(etf_list)

    if category_filter:
        filtered = [e for e in filtered if category_filter in e.get("category", "")]

    if exclude_leverage:
        filtered = [e for e in filtered
                    if "leverage" not in e.get("category", "")
                    and "inverse" not in e.get("category", "")]

    if min_aum is not None:
        filtered = [e for e in filtered
                    if e.get("aum") is None or e.get("aum", 0) >= min_aum]

    scored = [calc_verity_etf_score(e) for e in filtered]
    scored.sort(key=lambda x: x.get("verity_etf_score") or 0, reverse=True)

    return scored[:top_n]


def get_bond_etf_picks(etf_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """채권형 ETF 전용 스크리닝 — 채권 대시보드 'ETF 추천' 위젯용."""
    kr_bond = screen_etfs(etf_list, category_filter="bond_kr", top_n=5)
    us_bond = screen_etfs(etf_list, category_filter="bond_us", top_n=5)
    foreign_bond = screen_etfs(etf_list, category_filter="bond_foreign", top_n=5)

    return {
        "kr_bond_top5": kr_bond,
        "us_bond_top5": us_bond,
        "foreign_bond_top5": foreign_bond,
        "screened_at": datetime.now().isoformat(),
    }


def run_full_etf_screening(
    kr_etfs: List[Dict[str, Any]],
    us_etfs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """전체 ETF 스크리닝 실행 — portfolio.json etfs 섹션 업데이트용 메인 함수."""
    all_etfs = kr_etfs + us_etfs

    return {
        "overall_top20": screen_etfs(all_etfs, top_n=20),
        "kr_equity_top10": screen_etfs(kr_etfs, category_filter="equity_domestic", top_n=10),
        "kr_bond_top10": screen_etfs(kr_etfs, category_filter="bond_kr", top_n=10),
        "us_bond_top10": screen_etfs(us_etfs, category_filter="bond_us", top_n=10),
        "us_equity_top10": screen_etfs(us_etfs, category_filter="equity_us", top_n=10),
        "bond_picks": get_bond_etf_picks(all_etfs),
        "total_screened": len(all_etfs),
        "screened_at": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_etfs = [
        {
            "ticker": "069500", "name": "KODEX 200",
            "category": "equity_domestic",
            "returns": {"1M": 2.1, "3M": 5.3, "6M": 8.2, "1Y": 12.4},
            "expense_ratio": 0.0015, "volume": 3000000,
            "aum": 52000, "tracking_diff": 0.05,
        },
        {
            "ticker": "148070", "name": "KOSEF 국고채10년",
            "category": "bond_kr",
            "returns": {"1M": 0.5, "3M": 1.2, "6M": 2.1, "1Y": 4.3},
            "expense_ratio": 0.0015, "volume": 500000,
            "aum": 8000, "tracking_diff": 0.02,
        },
    ]
    result = screen_etfs(test_etfs, top_n=10)
    print(json.dumps(result, ensure_ascii=False, indent=2))
