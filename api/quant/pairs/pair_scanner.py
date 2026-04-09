"""
페어 트레이딩 스캐너 — 통계적 차익거래 실행 모듈

동일 섹터 내에서 공적분 관계가 확인되는 종목 쌍을 자동 발굴하고,
실시간 스프레드 Z-Score를 모니터링하여 매매 시그널을 생성한다.

파이프라인:
  1. 섹터별 종목 그룹핑
  2. 그룹 내 모든 페어 조합의 상관관계 프리필터 (|corr| > 0.6)
  3. 통과 페어에 Engle-Granger 공적분 검정
  4. 공적분 확인된 페어의 스프레드 Z-Score 모니터링
  5. 반감기 기반 보유기간 제안
"""
from __future__ import annotations

import itertools
from typing import Any, Dict, List, Optional

import numpy as np
import yfinance as yf

from api.quant.pairs.cointegration import (
    compute_spread_zscore,
    engle_granger_test,
)

SECTOR_GROUPS = {
    "반도체": ["005930.KS", "000660.KS", "042700.KS", "058470.KS"],
    "2차전지": ["373220.KS", "006400.KS", "051910.KS", "003670.KS"],
    "자동차": ["005380.KS", "000270.KS", "012330.KS"],
    "금융": ["105560.KS", "055550.KS", "086790.KS", "316140.KS"],
    "바이오": ["207940.KS", "068270.KS", "326030.KS"],
    "인터넷": ["035420.KS", "035720.KS", "263750.KS"],
    "철강": ["005490.KS", "004020.KS"],
    "화학": ["051910.KS", "010950.KS", "096770.KS"],
    "통신": ["017670.KS", "030200.KS"],
}

TICKER_NAMES = {
    "005930.KS": "삼성전자", "000660.KS": "SK하이닉스",
    "042700.KS": "한미반도체", "058470.KS": "리노공업",
    "373220.KS": "LG에너지솔루션", "006400.KS": "삼성SDI",
    "051910.KS": "LG화학", "003670.KS": "포스코퓨처엠",
    "005380.KS": "현대차", "000270.KS": "기아",
    "012330.KS": "현대모비스",
    "105560.KS": "KB금융", "055550.KS": "신한지주",
    "086790.KS": "하나금융", "316140.KS": "우리금융",
    "207940.KS": "삼성바이오로직스", "068270.KS": "셀트리온",
    "326030.KS": "SK바이오팜",
    "035420.KS": "NAVER", "035720.KS": "카카오",
    "263750.KS": "펄어비스",
    "005490.KS": "POSCO홀딩스", "004020.KS": "현대제철",
    "010950.KS": "S-Oil", "096770.KS": "SK이노베이션",
    "017670.KS": "SK텔레콤", "030200.KS": "KT",
}

MIN_CORRELATION = 0.6
MIN_DATA_DAYS = 120


def _fetch_prices(ticker: str, period: str = "1y") -> Optional[np.ndarray]:
    """yfinance에서 종가 시계열 가져오기."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period)
        if hist.empty or len(hist) < MIN_DATA_DAYS:
            return None
        return hist["Close"].values
    except Exception:
        return None


def scan_sector_pairs(
    sector: Optional[str] = None,
    custom_tickers: Optional[List[str]] = None,
    period: str = "1y",
) -> Dict[str, Any]:
    """
    섹터 내 모든 페어 조합을 검사하여 공적분 페어를 발굴.

    Args:
        sector: SECTOR_GROUPS 키 (None이면 전체 스캔)
        custom_tickers: 직접 지정할 티커 리스트
        period: yfinance 데이터 기간

    Returns:
        {
            "pairs_found": [...],
            "total_tested": int,
            "sector": str,
        }
    """
    if custom_tickers:
        tickers = custom_tickers
        sector_name = "custom"
    elif sector and sector in SECTOR_GROUPS:
        tickers = SECTOR_GROUPS[sector]
        sector_name = sector
    else:
        tickers = []
        sector_name = "all"
        for grp in SECTOR_GROUPS.values():
            tickers.extend(grp)
        tickers = list(set(tickers))

    price_cache: Dict[str, np.ndarray] = {}
    for t in tickers:
        prices = _fetch_prices(t, period)
        if prices is not None:
            price_cache[t] = prices

    available = list(price_cache.keys())
    if len(available) < 2:
        return {
            "pairs_found": [],
            "total_tested": 0,
            "sector": sector_name,
            "reason": f"데이터 가용 종목 {len(available)}개 — 최소 2개 필요",
        }

    pairs_found: List[Dict[str, Any]] = []
    total_tested = 0

    for t1, t2 in itertools.combinations(available, 2):
        total_tested += 1
        p1 = price_cache[t1]
        p2 = price_cache[t2]

        min_len = min(len(p1), len(p2))
        p1_trim = p1[-min_len:]
        p2_trim = p2[-min_len:]

        corr = float(np.corrcoef(p1_trim, p2_trim)[0, 1])
        if abs(corr) < MIN_CORRELATION:
            continue

        eg = engle_granger_test(p1_trim, p2_trim)
        if not eg.get("is_cointegrated"):
            continue

        spread_info = compute_spread_zscore(
            p1_trim, p2_trim,
            eg["hedge_ratio"],
            eg.get("intercept", 0),
        )

        pair_result = {
            "ticker_a": t1,
            "ticker_b": t2,
            "name_a": TICKER_NAMES.get(t1, t1),
            "name_b": TICKER_NAMES.get(t2, t2),
            "correlation": round(corr, 4),
            "hedge_ratio": eg["hedge_ratio"],
            "half_life": eg.get("half_life"),
            "adf_stat": eg["adf_result"]["test_statistic"],
            "adf_p": eg["adf_result"]["p_value_approx"],
            "spread_zscore": spread_info["zscore"],
            "spread_signal": spread_info["signal"],
            "spread_label": spread_info.get("label", ""),
        }
        pairs_found.append(pair_result)

    pairs_found.sort(key=lambda x: abs(x["spread_zscore"]), reverse=True)

    return {
        "pairs_found": pairs_found,
        "total_tested": total_tested,
        "sector": sector_name,
        "available_tickers": len(available),
    }


def scan_all_sectors() -> Dict[str, Any]:
    """전체 섹터 그룹 순회하며 페어 발굴."""
    all_pairs: List[Dict[str, Any]] = []
    sector_results: Dict[str, int] = {}

    for sector_name in SECTOR_GROUPS:
        result = scan_sector_pairs(sector=sector_name)
        found = result.get("pairs_found", [])
        for p in found:
            p["sector"] = sector_name
        all_pairs.extend(found)
        sector_results[sector_name] = len(found)

    all_pairs.sort(key=lambda x: abs(x["spread_zscore"]), reverse=True)

    actionable = [p for p in all_pairs if abs(p["spread_zscore"]) >= 1.5]

    return {
        "total_pairs": len(all_pairs),
        "actionable_pairs": actionable,
        "all_pairs": all_pairs,
        "by_sector": sector_results,
    }


def monitor_pair(
    ticker_a: str,
    ticker_b: str,
    hedge_ratio: float,
    intercept: float = 0,
    period: str = "6mo",
) -> Dict[str, Any]:
    """
    기존에 발굴된 페어의 스프레드를 실시간 모니터링.
    realtime 모드에서 호출 가능한 경량 함수.
    """
    p1 = _fetch_prices(ticker_a, period)
    p2 = _fetch_prices(ticker_b, period)

    if p1 is None or p2 is None:
        return {"error": "가격 데이터 없음", "ticker_a": ticker_a, "ticker_b": ticker_b}

    spread_info = compute_spread_zscore(p1, p2, hedge_ratio, intercept)

    suggested_action = "HOLD"
    if spread_info["zscore"] <= -2.0:
        suggested_action = f"롱 {TICKER_NAMES.get(ticker_a, ticker_a)} / 숏 {TICKER_NAMES.get(ticker_b, ticker_b)}"
    elif spread_info["zscore"] >= 2.0:
        suggested_action = f"숏 {TICKER_NAMES.get(ticker_a, ticker_a)} / 롱 {TICKER_NAMES.get(ticker_b, ticker_b)}"
    elif abs(spread_info["zscore"]) < 0.5:
        suggested_action = "스프레드 정상화 — 청산 고려"

    return {
        "ticker_a": ticker_a,
        "ticker_b": ticker_b,
        "name_a": TICKER_NAMES.get(ticker_a, ticker_a),
        "name_b": TICKER_NAMES.get(ticker_b, ticker_b),
        **spread_info,
        "suggested_action": suggested_action,
    }
