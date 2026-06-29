"""코인 universe — CoinGecko 시총 상위 N 코인 (히트맵용).

무인증 무료 API. 사실만(시총/가격/변동%/sparkline) — RULE 7 점수·등급 비노출.
sparkline 168포인트(7일 시간봉) → 28포인트 다운샘플(payload 경량). 단일 호출(rate-limit 대비).
실패 시 예외 raise(빈 리스트 금지 — builder가 last-good 유지). 스키마 실호출 검증 완료(2026-06).
"""
from __future__ import annotations

from typing import Any, Dict, List

import requests

_TIMEOUT = 12
_HEADERS = {"User-Agent": "Verity-Terminal/1.0", "Accept": "application/json"}
_URL = "https://api.coingecko.com/api/v3/coins/markets"


def _downsample(arr: List[float], target: int = 28) -> List[float]:
    if not arr:
        return []
    if len(arr) <= target:
        return [round(float(x), 4) for x in arr]
    step = len(arr) / float(target)
    return [round(float(arr[int(i * step)]), 4) for i in range(target)]


def collect_crypto_universe(per_page: int = 50) -> List[Dict[str, Any]]:
    """CoinGecko 시총 상위 per_page 코인. 실패 시 예외."""
    r = requests.get(
        _URL,
        params={
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": 1,
            "sparkline": "true",
            "price_change_percentage": "24h,7d",
        },
        headers=_HEADERS, timeout=_TIMEOUT,
    )
    r.raise_for_status()
    rows = r.json()
    if not isinstance(rows, list) or not rows:
        raise ValueError("coingecko_empty")

    coins: List[Dict[str, Any]] = []
    for c in rows:
        if not isinstance(c, dict) or not c.get("market_cap"):
            continue
        spark = ((c.get("sparkline_in_7d") or {}).get("price")) or []
        mc = c.get("market_cap")
        fdv = c.get("fully_diluted_valuation")
        circ = c.get("circulating_supply")
        total = c.get("total_supply")
        mx = c.get("max_supply")
        # 희석 포렌식(AlphaNest 희석공시 코인판): FDV/MC overhang + 유통비율. 사실만(RULE 7).
        fdv_mc = round(fdv / mc, 3) if (fdv and mc and mc > 0) else None
        denom = mx or total
        circ_ratio = round(circ / denom * 100, 1) if (circ and denom and denom > 0) else None
        coins.append({
            "id": c.get("id"),
            "symbol": (c.get("symbol") or "").upper(),
            "name": c.get("name"),
            "market_cap": mc,
            "current_price": c.get("current_price"),
            "change_pct": c.get("price_change_percentage_24h"),
            "change_pct_7d": c.get("price_change_percentage_7d_in_currency"),
            "sparkline": _downsample(spark),
            # 희석 포렌식
            "fdv": fdv,
            "fdv_mc_ratio": fdv_mc,          # >1 = 미유통 물량 overhang (희석 압력)
            "circulating_supply": circ,
            "total_supply": total,
            "max_supply": mx,
            "circulating_ratio": circ_ratio,  # 유통비율% (낮을수록 미유통 희석 overhang 큼)
        })
    if not coins:
        raise ValueError("no_valid_coins")
    return coins
