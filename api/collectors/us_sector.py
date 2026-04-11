"""
US 섹터 분석 모듈
- yfinance에서 종목별 GICS 섹터 수집
- 섹터별 등락률 집계 → KR get_sector_rankings()과 동일 출력
- S&P 11개 GICS 섹터 한글 매핑
"""
import json
import os
import logging
import time
from typing import Any, Dict, List, Optional

import yfinance as yf

logger = logging.getLogger(__name__)

GICS_KR = {
    "Technology": "기술",
    "Communication Services": "커뮤니케이션",
    "Consumer Cyclical": "경기소비재",
    "Consumer Defensive": "필수소비재",
    "Financial Services": "금융",
    "Healthcare": "헬스케어",
    "Industrials": "산업재",
    "Energy": "에너지",
    "Basic Materials": "소재",
    "Real Estate": "부동산",
    "Utilities": "유틸리티",
}

GICS_SECTOR_ID = {
    "Technology": "SEC_TECH",
    "Communication Services": "SEC_COMM",
    "Consumer Cyclical": "SEC_CYCL",
    "Consumer Defensive": "SEC_DEFE",
    "Financial Services": "SEC_FIN",
    "Healthcare": "SEC_HLTH",
    "Industrials": "SEC_INDU",
    "Energy": "SEC_ENGY",
    "Basic Materials": "SEC_MATL",
    "Real Estate": "SEC_REAL",
    "Utilities": "SEC_UTIL",
}

KR_NAME_TO_SECTOR_ID = {
    "기술": "SEC_TECH",
    "커뮤니케이션": "SEC_COMM",
    "경기소비재": "SEC_CYCL",
    "필수소비재": "SEC_DEFE",
    "금융": "SEC_FIN",
    "헬스케어": "SEC_HLTH",
    "산업재": "SEC_INDU",
    "에너지": "SEC_ENGY",
    "소재": "SEC_MATL",
    "부동산": "SEC_REAL",
    "유틸리티": "SEC_UTIL",
    "반도체": "SEC_TECH",
    "IT": "SEC_TECH",
    "자동차": "SEC_CYCL",
    "건설": "SEC_INDU",
    "철강": "SEC_MATL",
    "조선": "SEC_INDU",
    "화학": "SEC_MATL",
    "기계": "SEC_INDU",
    "운송": "SEC_INDU",
    "통신": "SEC_COMM",
    "보험": "SEC_FIN",
    "은행": "SEC_FIN",
    "증권": "SEC_FIN",
}

_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "us_sector_cache.json",
)


def _load_sector_cache() -> Dict[str, str]:
    try:
        with open(_CACHE_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_sector_cache(cache: Dict[str, str]):
    try:
        os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
        with open(_CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def get_ticker_sector(ticker: str, cache: Dict[str, str]) -> Optional[str]:
    """yfinance에서 종목의 GICS 섹터를 가져옴. 캐시 우선."""
    if ticker in cache:
        return cache[ticker]
    try:
        info = yf.Ticker(ticker).info
        sector = info.get("sector")
        if sector:
            cache[ticker] = sector
        return sector
    except Exception:
        return None


def get_us_sector_rankings(candidates: Optional[List[Dict]] = None) -> List[Dict[str, Any]]:
    """
    US 종목의 섹터별 등락률 집계.
    candidates가 주어지면 해당 종목 리스트 기반, 아니면 US_MAJOR 전체.

    Returns: KR get_sector_rankings()과 동일 구조
        [{"name": "기술", "market": "US", "change_pct": 1.5, "heat": "hot", "top_stocks": [...], "rank": 1}, ...]
    """
    cache = _load_sector_cache()

    if candidates:
        stocks = []
        for s in candidates:
            if s.get("currency") != "USD":
                continue
            ticker = s.get("ticker", "")
            sector_en = get_ticker_sector(ticker, cache)
            if sector_en:
                stocks.append({
                    "ticker": ticker,
                    "name": s.get("name", ticker),
                    "sector_en": sector_en,
                    "sector_kr": GICS_KR.get(sector_en, sector_en),
                    "sector_id": GICS_SECTOR_ID.get(sector_en, "SEC_OTHER"),
                    "change_pct": s.get("technical", {}).get("price_change_pct", 0) or 0,
                    "price": s.get("price", 0),
                })
    else:
        from api.collectors.stock_data import US_MAJOR
        stocks = []
        for ticker, name in US_MAJOR.items():
            sector_en = get_ticker_sector(ticker, cache)
            if not sector_en:
                time.sleep(0.2)
                continue
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period="2d")
                if len(hist) >= 2:
                    chg = (hist["Close"].iloc[-1] / hist["Close"].iloc[-2] - 1) * 100
                else:
                    chg = 0
            except Exception:
                chg = 0
            stocks.append({
                "ticker": ticker,
                "name": name,
                "sector_en": sector_en,
                "sector_kr": GICS_KR.get(sector_en, sector_en),
                "sector_id": GICS_SECTOR_ID.get(sector_en, "SEC_OTHER"),
                "change_pct": round(chg, 2),
                "price": 0,
            })
            time.sleep(0.1)

    _save_sector_cache(cache)

    sector_groups: Dict[str, List[dict]] = {}
    for s in stocks:
        kr = s["sector_kr"]
        sector_groups.setdefault(kr, []).append(s)

    results = []
    for sector_kr, members in sector_groups.items():
        avg_chg = sum(m["change_pct"] for m in members) / len(members) if members else 0
        top = sorted(members, key=lambda x: x["change_pct"], reverse=True)[:3]
        sid = members[0].get("sector_id", "SEC_OTHER") if members else "SEC_OTHER"
        results.append({
            "name": sector_kr,
            "name_en": members[0]["sector_en"] if members else "",
            "sector_id": sid,
            "market": "US",
            "change_pct": round(avg_chg, 2),
            "top_stocks": [
                {"name": t["name"], "ticker": t["ticker"], "change_pct": t["change_pct"]}
                for t in top
            ],
            "stock_count": len(members),
        })

    results.sort(key=lambda x: x["change_pct"], reverse=True)

    for i, s in enumerate(results):
        if s["change_pct"] > 1.5:
            s["heat"] = "hot"
        elif s["change_pct"] > 0.3:
            s["heat"] = "warm"
        elif s["change_pct"] > -0.3:
            s["heat"] = "neutral"
        elif s["change_pct"] > -1.5:
            s["heat"] = "cool"
        else:
            s["heat"] = "cold"
        s["rank"] = i + 1

    return results
