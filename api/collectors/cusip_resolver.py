"""cusip_resolver — CUSIP → ticker 매핑 (OpenFIGI, 디스크 캐시).

2026-06-22 신설. 13F 완전판([[project_us_financials_sec_edgar]] (b))의 CUSIP→ticker 인프라.
13F infotable / 13D-G 는 CUSIP 키 — sp1500(ticker) 연결에 결정적 매핑 필요.

소스: OpenFIGI v3 /mapping (무료, no-key 25 req/min, 배치 10 jobs/req). exchCode US + Common Stock.
캐시: data/cusip_ticker_map.json (CUSIP→ticker, 안정값 = 영구 캐시, 미스만 신규 resolve).
실호출 검증(2026-06-22): 037833100→AAPL / 594918104→MSFT (RULE 10).
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, Iterable, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_PATH = os.path.join(_ROOT, "data", "cusip_ticker_map.json")
OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
BATCH = 10                 # no-key 최대 10 jobs/request
RATE_SLEEP = 2.6           # 25 req/min → 안전 마진(no-key). API key 있으면 단축 가능.


def _norm(cusip: str) -> str:
    return str(cusip or "").strip().upper()


def load_cache() -> Dict[str, Optional[str]]:
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cache(cache: Dict[str, Optional[str]]) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=0, sort_keys=True)


def resolve_cusips(cusips: Iterable[str], session=None) -> Dict[str, Optional[str]]:
    """CUSIP 집합 → {cusip: ticker|None}. 캐시 우선, 미스만 OpenFIGI 배치 resolve.

    None = 매핑 실패(비상장/펀드/ETF 등) — 캐시에 고정해 재조회 방지(영구 미스도 기록).
    """
    import requests
    sess = session or requests.Session()
    cache = load_cache()
    want = {_norm(c) for c in cusips if _norm(c)}
    miss = sorted(c for c in want if c not in cache)
    if not miss:
        return {c: cache.get(c) for c in want}

    resolved = 0
    for i in range(0, len(miss), BATCH):
        chunk = miss[i:i + BATCH]
        body = [{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in chunk]
        try:
            r = sess.post(OPENFIGI_URL, json=body, headers={"Content-Type": "application/json"}, timeout=20)
            if r.status_code == 429:
                time.sleep(15)  # rate limit backoff 1회
                r = sess.post(OPENFIGI_URL, json=body, headers={"Content-Type": "application/json"}, timeout=20)
            if r.status_code != 200:
                print(f"[cusip] OpenFIGI {r.status_code} (chunk {i//BATCH}) — 미스 보류", file=sys.stderr)
                time.sleep(RATE_SLEEP)
                continue
            data = r.json()
        except Exception as e:  # noqa: BLE001
            print(f"[cusip] OpenFIGI 실패: {e!r}", file=sys.stderr)
            time.sleep(RATE_SLEEP)
            continue
        for cusip, item in zip(chunk, data):
            rows = item.get("data") or []
            # 보통주 우선, 없으면 첫 결과.
            tk = None
            for row in rows:
                if row.get("securityType") == "Common Stock" and row.get("ticker"):
                    tk = str(row["ticker"]).upper()
                    break
            if tk is None and rows:
                tk = (str(rows[0].get("ticker")).upper() if rows[0].get("ticker") else None)
            cache[cusip] = tk        # None 도 기록(영구 미스 = 재조회 방지)
            if tk:
                resolved += 1
        time.sleep(RATE_SLEEP)

    _save_cache(cache)
    print(f"[cusip] resolved {resolved}/{len(miss)} 신규 · 캐시 {len(cache)}건", file=sys.stderr)
    return {c: cache.get(c) for c in want}


if __name__ == "__main__":
    # manual: python -m api.collectors.cusip_resolver 037833100 594918104
    args = sys.argv[1:] or ["037833100", "594918104"]
    print(resolve_cusips(args))
