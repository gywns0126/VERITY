#!/usr/bin/env python3
"""미국 티커 → 네이버 해외증시 코드(reutersCode) 해석 — 딥링크 정확도용.

배경 (2026-07-29 PM 지시 "최대한의 정보 노출은 하자"):
  미국 시세 시계열은 재배포 권리가 없어 자체 차트를 못 그린다. 대신 증권사(네이버)가 서빙하는
  실시간 화면으로 딥링크한다 — 증권사가 보여주는 것이라 재배포가 아니다(KR 차트에서 쓰던 방식).

  그런데 네이버 해외 코드는 거래소 접미어가 붙는다. 실측(2026-07-29 api.stock.naver.com):
    · AAPL.O → 200 "애플"          · TSLA(맨) → 빈 응답, TSLA.O 필요
    · VOO(맨) → 200 "Vanguard 500" · VOO.P → 409 Not Exist Master
  즉 **접미어 유무가 종목마다 다르고** 우리 universe_search 에는 거래소 정보가 없다(market="US"/"ETF" 뿐).
  런타임에 컴포넌트가 탐색할 수도 없다(교차출처 + 티커마다 추가 호출).
  → 빌드 타임에 한 번 해석해 캐시하고, universe_search 에 nv 필드로 실어 보낸다.

동작:
  · 후보 = 맨 티커 → .O(나스닥) → .N(뉴욕) → .K 순으로 첫 성공 채택. 실패는 miss 로 기록해 재시도 제한.
  · drip = 1 run 당 US_NV_PER_RUN(기본 300). 5,562 종 = 약 19 run 에 전량 커버.
  · 이미 해석된 종목은 US_NV_REFRESH_DAYS(기본 90) 지나야 재해석 — 상장폐지/이관 대응.

🚨 RULE 7 무관 — 링크 주소 해석이며 점수·판단이 아니다.
🚨 시세 값을 저장하지 않는다. 저장 대상 = 코드 문자열 + 표시명뿐.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_PATH = os.path.join(_ROOT, "data", "us_naver_code.json")
UNIVERSE_PATH = os.path.join(_ROOT, "data", "universe_search.json")
KST = timezone(timedelta(hours=9))

PER_RUN = int(os.environ.get("US_NV_PER_RUN") or 600)
REFRESH_DAYS = int(os.environ.get("US_NV_REFRESH_DAYS") or 90)
MISS_RETRY_DAYS = int(os.environ.get("US_NV_MISS_RETRY_DAYS") or 30)
THROTTLE = float(os.environ.get("US_NV_THROTTLE") or 0.12)
API = "https://api.stock.naver.com/stock/{}/basic"
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
# 실측 우선순위 — 맨 티커가 통하는 종목이 가장 많고(ETF 다수), 나머지는 대부분 나스닥(.O)
SUFFIXES = ["", ".O", ".N", ".K"]


def _now() -> datetime:
    return datetime.now(KST)


def _age_days(iso: str, now: datetime) -> float:
    try:
        return (now - datetime.fromisoformat(iso)).days
    except (ValueError, TypeError):
        return 1e9


def _probe(code: str) -> Optional[Dict[str, Any]]:
    """네이버 basic 조회. 유효하면 {code, name, kind}, 아니면 None."""
    try:
        req = urllib.request.Request(API.format(code), headers=_UA)
        with urllib.request.urlopen(req, timeout=8) as r:
            doc = json.loads(r.read())
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, TimeoutError):
        return None
    rc = str(doc.get("reutersCode") or "")
    if not rc:
        return None
    return {
        "code": rc,
        "name": str(doc.get("stockName") or ""),
        "kind": str(doc.get("stockEndType") or ""),  # stock | etf
    }


def _bases(ticker: str) -> List[str]:
    """티커 표기 변형 — 클래스주 표기가 소스마다 다르다.

    실측(2026-07-29): BRK.B / BRK-B / BRKB 전부 실패하고 **BRKb** 만 200("버크셔 해서웨이 Class B").
    즉 네이버는 클래스 문자를 소문자로 붙여 쓴다. 원문 → 소문자클래스 순으로 시도한다.
    """
    out = [ticker]
    if "." in ticker or "-" in ticker:
        head, _, tail = ticker.replace("-", ".").partition(".")
        if head and len(tail) == 1:
            out.append(head + tail.lower())
    return out


def resolve(ticker: str) -> Optional[Dict[str, Any]]:
    """표기 변형 × 거래소 접미어를 순서대로 시도해 첫 성공 반환."""
    for base in _bases(ticker):
        for suf in SUFFIXES:
            hit = _probe(base + suf)
            if hit:
                return hit
            time.sleep(THROTTLE)
    return None


def _us_tickers() -> List[str]:
    """universe_search 의 미국 티커 — 6자리 숫자(국내) 제외."""
    try:
        doc = json.load(open(UNIVERSE_PATH, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    arr = doc if isinstance(doc, list) else (doc.get("stocks") or [])
    out = []
    for e in arr:
        t = str((e or {}).get("ticker") or "").strip()
        if t and not t.isdigit():
            out.append(t)
    return out


def load_map() -> Dict[str, str]:
    """빌더용 — {ticker: reutersCode}. 캐시 없으면 빈 dict(호출부는 graceful)."""
    try:
        doc = json.load(open(CACHE_PATH, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out = {}
    for t, rec in (doc.get("by_ticker") or {}).items():
        code = str((rec or {}).get("code") or "")
        if code:
            out[t] = code
    return out


def main() -> int:
    now = _now()
    cache: Dict[str, Any] = {"updated_at": None, "by_ticker": {}}
    if os.path.exists(CACHE_PATH):
        try:
            cache = json.load(open(CACHE_PATH, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    by_ticker: Dict[str, Any] = cache.get("by_ticker") or {}

    tickers = _us_tickers()
    if not tickers:
        print("[us_naver_code] universe_search 미로드 — skip", file=sys.stderr)
        return 0

    todo = []
    for t in tickers:
        rec = by_ticker.get(t)
        if not rec:
            todo.append(t)
            continue
        age = _age_days(str(rec.get("as_of") or ""), now)
        limit = MISS_RETRY_DAYS if not rec.get("code") else REFRESH_DAYS
        if age >= limit:
            todo.append(t)
    # 우선순위 = ① 사이트에서 실제로 열리는 ETF(us_etf.json 큐레이션) ② 미해석 ③ 오래된 순.
    # 유니버스 순서가 임의라 그대로 두면 VOO/TSLA 같은 대표 종목이 뒤로 밀려 수 주간 링크가 빈다.
    prio = set()
    try:
        _e = json.load(open(os.path.join(_ROOT, "data", "us_etf.json"), encoding="utf-8"))
        prio = {str(x.get("ticker") or "") for x in (_e.get("etfs") or [])}
    except (OSError, json.JSONDecodeError):
        pass
    todo.sort(key=lambda t: (t not in prio,
                             bool((by_ticker.get(t) or {}).get("code")),
                             str((by_ticker.get(t) or {}).get("as_of") or "")))
    todo = todo[:PER_RUN]

    hit = 0
    for t in todo:
        r = resolve(t)
        rec: Dict[str, Any] = {"as_of": now.isoformat()}
        if r:
            rec.update(r)
            hit += 1
        by_ticker[t] = rec

    cache["by_ticker"] = by_ticker
    cache["updated_at"] = now.isoformat()
    resolved = sum(1 for v in by_ticker.values() if (v or {}).get("code"))
    cache["_meta"] = {
        "source": "api.stock.naver.com/stock/{code}/basic — 딥링크 코드 해석(시세 값 미저장)",
        "universe_n": len(tickers),
        "resolved_n": resolved,
        "pending_n": len(tickers) - len(by_ticker),
        "generated_at": now.isoformat(),
    }
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)
    print(f"[us_naver_code] 이번 run {len(todo)}종 시도 · 해석 {hit} · 누적 {resolved}/{len(tickers)} "
          f"-> {os.path.relpath(CACHE_PATH, _ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
