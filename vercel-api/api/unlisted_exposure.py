"""
비상장 지분 조회 유틸.

portfolio.json → recommendations[].group_structure.subsidiaries 에서
is_listed === false 인 항목만 추출하여 unlisted_exposure 스키마로 반환.
"""
import json
import os
import time
import urllib.request

PORTFOLIO_URL = os.environ.get(
    "PORTFOLIO_URL",
    "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
)

_cache: dict = {}
_cache_ts: float = 0
_CACHE_TTL = 600


def _fetch_portfolio() -> dict:
    global _cache, _cache_ts
    if time.time() - _cache_ts < _CACHE_TTL and _cache:
        return _cache
    try:
        req = urllib.request.Request(PORTFOLIO_URL, headers={"User-Agent": "VERITY/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            txt = resp.read().decode("utf-8")
            txt = txt.replace("NaN", "null").replace("Infinity", "null").replace("-Infinity", "null")
            _cache = json.loads(txt)
            _cache_ts = time.time()
    except Exception:
        pass
    return _cache


def get_unlisted_exposure(ticker: str) -> dict:
    """ticker(6자리 코드)에 대한 비상장 지분 노출 정보를 반환.

    Returns:
        {
            "has_data": bool,
            "total_count": int,
            "total_stake_value_억": float,
            "items": [{ name, ownership_pct, stake_value_억, book_value_억,
                         revenue_억, profit_억 }, ...]
        }
    """
    data = _fetch_portfolio()
    if not data:
        return {"has_data": False, "total_count": 0, "total_stake_value_억": 0, "items": []}

    recs = data.get("recommendations") or []
    gs = None
    ticker_clean = ticker.strip().replace(".KS", "").replace(".KQ", "")
    for r in recs:
        t = str(r.get("ticker", "")).strip()
        if t == ticker_clean:
            gs = r.get("group_structure")
            break

    if not gs:
        return {"has_data": False, "total_count": 0, "total_stake_value_억": 0, "items": []}

    subs = gs.get("subsidiaries") or []
    unlisted = [s for s in subs if not s.get("is_listed", True)]

    if not unlisted:
        return {"has_data": True, "total_count": 0, "total_stake_value_억": 0, "items": []}

    items = []
    total_sv = 0.0
    for u in unlisted:
        sv = u.get("stake_value_억") or 0
        total_sv += sv
        items.append({
            "name": u.get("name", ""),
            "ownership_pct": u.get("ownership_pct", 0),
            "stake_value_억": sv,
            "book_value_억": u.get("book_value_억", 0),
            "fair_value_억": u.get("fair_value_억", 0),
            "revenue_억": u.get("revenue_억", 0),
            "profit_억": u.get("profit_억", 0),
        })

    items.sort(key=lambda x: x.get("stake_value_억", 0), reverse=True)

    return {
        "has_data": True,
        "total_count": len(items),
        "total_stake_value_억": round(total_sv, 1),
        "items": items[:10],
    }
