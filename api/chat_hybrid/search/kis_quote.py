"""
VERITY Chat Hybrid — 유니버스 밖 KR 종목 on-demand 시세 (2026-06-03, 갈래 B)

유니버스(25종목) 밖 KR 종목 질의 시 실시간 시세를 grounding 에 주입한다.

🚨 RULE 1 (KIS 1일 1토큰 ABSOLUTE) 준수 설계:
  - KIS 를 직접 호출하거나 토큰을 발급하지 **않는다**.
  - Railway(`server/kis_rest_client.py`)의 `/chart/{ticker}?type=price` 를 HTTP 로 호출.
    Railway 는 KIS_SHARED_TOKEN 공유토큰 read 소비자 — 발급 경로가 RuntimeError 로 차단됨.
  - Vercel 엔 KIS creds 가 없으므로(2026-05-13 제거) 직접 호출이 구조적으로 불가능.
  - 따라서 새 KIS consumer 신설 0, 발급 경로 0. 단순 내부 HTTP read.
  - 실패(타임아웃/비200/가격0/비-KR) 시 None → caller 는 web grounding 으로 fallback.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_KR_TICKER_RE = re.compile(r"^\d{6}$")


def _railway_url() -> str:
    # order.py 와 동일 기본값 (Vercel→Railway 기존 패턴).
    return (
        os.environ.get("RAILWAY_URL")
        or "https://verity-production-1e44.up.railway.app"
    ).rstrip("/")


def fetch_kr_quote(ticker: str, timeout: float = 2.5) -> Optional[Dict[str, Any]]:
    """KR 6자리 종목 현재가 — Railway read-only 경유. 실패 시 None.

    Returns: {"ticker": "005930", "price": 365000, "change_pct": 1.2} 또는 None.
    """
    raw = str(ticker or "").strip()
    # 숫자만으로 구성된 KR 코드만 — 'NVDA' 등 US 티커/종목명은 네트워크 호출 없이 즉시 거부.
    if not raw.isdigit():
        return None
    tk = raw.zfill(6)
    if not _KR_TICKER_RE.match(tk):
        return None
    url = f"{_railway_url()}/chart/{tk}?type=price"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VERITY-Chat-Hybrid/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        price_obj = (data or {}).get("price") or {}
        price = price_obj.get("price")
        if not price or float(price) <= 0:
            return None
        chg = price_obj.get("change_pct")
        return {
            "ticker": tk,
            "price": int(float(price)),
            "change_pct": float(chg) if isinstance(chg, (int, float)) else None,
        }
    except Exception as e:
        logger.warning("KIS quote(Railway) 실패 %s: %s", tk, e)
        return None


def fetch_kr_quotes(tickers: List[str], timeout: float = 2.5) -> Dict[str, Dict[str, Any]]:
    """여러 KR 티커 시세 — 성공분만 {ticker: quote}. KR 6자리만 시도."""
    out: Dict[str, Dict[str, Any]] = {}
    for t in tickers:
        q = fetch_kr_quote(t, timeout=timeout)
        if q:
            out[q["ticker"]] = q
    return out
