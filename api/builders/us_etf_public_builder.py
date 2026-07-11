"""미장(US) ETF 빌더 — 주요 US 상장 ETF(VOO/SPY/QQQ 등) 사실(카테고리·AUM·운용사·보유종목·보수).

배경(2026-07-11): KR ETF(ACE 미국S&P500 등 KRX 상장)는 검색되나 US 상장 ETF(VOO)는 유니버스 부재
→ 검색·리포트 0. KR ETF flow(설정/환매)의 US 대응 = US ETF는 KRX 미상장이라 yfinance 소스.

🚨 RULE 7 — 사실만: 카테고리·순자산(AUM)·운용사·보수율·보유종목 top(비중). 자체 점수·판단 0.
🚨 가격/NAV 재배포 회피 = 실시간 시세 미노출(증권사 link-out). 여긴 구성·비용 사실 렌즈.

소스 = yfinance (Ticker.info + funds_data.top_holdings). 큐레이션 ~70종(AUM 상위 광범/섹터/해외/채권/원자재).
출력 = data/us_etf.json {_meta, etfs:[{ticker, name, category, aum_usd, family, expense, top_holdings}]}.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_PATH = os.path.join(_ROOT, "data", "us_etf_cache.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_etf.json")
KST = timezone(timedelta(hours=9))
FRESH_DAYS = 5          # ETF 구성/AUM 저빈도 변동 → 5일 재수집
MAX_PER_RUN = 40        # yfinance 레이트리밋 안전 (큐레이션 ~70 → 2일 내 전 커버)
THROTTLE_SEC = 0.3
STALE_EMIT_DAYS = 30

# 큐레이션 = AUM/인지도 상위 US 상장 ETF (광범·섹터·해외·채권·원자재·테마)
CURATED: List[str] = [
    # 광범 시장
    "VOO", "SPY", "IVV", "VTI", "QQQ", "QQQM", "SPLG", "DIA", "IWM", "IJH", "IJR", "RSP", "MDY", "VO", "VB",
    # 스타일
    "VUG", "VTV", "IWF", "IWD", "SCHG", "SCHD", "VIG", "VYM", "DVY", "HDV", "QUAL", "MTUM", "USMV",
    # 섹터 (SPDR Select)
    "XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLC", "XLRE",
    "SMH", "SOXX", "IBB", "XBI", "KRE", "ITB", "JETS",
    # 해외
    "VEA", "VWO", "IEFA", "IEMG", "EFA", "EEM", "VXUS", "SCHF", "INDA", "MCHI", "FXI", "EWJ", "EWZ", "EWY",
    # 채권
    "BND", "AGG", "TLT", "IEF", "SHY", "LQD", "HYG", "TIP", "VCIT", "MUB", "BIL", "SGOV",
    # 원자재·기타
    "GLD", "IAU", "SLV", "USO", "DBC", "URA",
    # 테마·인컴·레버리지
    "ARKK", "JEPI", "JEPQ", "SCHY", "TQQQ", "SQQQ",
]


def _now_kst() -> datetime:
    return datetime.now(KST)


def _age_days(as_of: str, now: datetime) -> float:
    try:
        return (now - datetime.fromisoformat(as_of)).days
    except (ValueError, TypeError):
        return 1e9


def _expense(info: Dict[str, Any]) -> Optional[float]:
    # yfinance annualReportExpenseRatio = 이미 % 표기 값(VOO=0.03 → 0.03%). ×100 금지.
    for k in ("annualReportExpenseRatio", "netExpenseRatio", "expenseRatio"):
        v = info.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return round(v, 3)
    return None


def _fetch_one(ticker: str) -> Dict[str, Any]:
    """yfinance ETF 사실 (info + top_holdings). 실패 시 {}."""
    import yfinance as yf
    t = yf.Ticker(ticker)
    info = t.info or {}
    if not info or str(info.get("quoteType") or "").upper() not in ("ETF", "MUTUALFUND"):
        return {}
    out: Dict[str, Any] = {
        "name": info.get("shortName") or info.get("longName") or ticker,
        "category": info.get("category"),
        "aum_usd": info.get("totalAssets"),
        "family": info.get("fundFamily"),
        "expense": _expense(info),
    }
    try:
        th = t.funds_data.top_holdings  # DataFrame index=심볼, cols=[Name, Holding Percent]
        holdings = []
        for sym, row in th.head(10).iterrows():
            pct = row.get("Holding Percent")
            w = None
            try:
                fp = float(pct)
                if fp == fp:  # NaN 가드 (NaN != NaN) — json.dump 의 NaN 리터럴 = JS JSON.parse 깨짐
                    w = round(fp * 100, 2) if fp < 1 else round(fp, 2)  # funds_data=분수(0.075=7.5%)
            except (TypeError, ValueError):
                pass
            holdings.append({"t": str(sym), "n": str(row.get("Name") or ""), "w": w})
        if holdings:
            out["top_holdings"] = holdings
    except Exception:  # noqa: BLE001 — funds_data 없는 ETF (채권/원자재 등) graceful
        pass
    return out


def main() -> int:
    cache: Dict[str, Any] = {"updated_at": None, "by_ticker": {}}
    if os.path.exists(CACHE_PATH):
        try:
            cache = json.load(open(CACHE_PATH, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    by_ticker: Dict[str, Any] = cache.get("by_ticker") or {}

    now = _now_kst()
    todo = [t for t in CURATED if _age_days((by_ticker.get(t) or {}).get("as_of", ""), now) >= FRESH_DAYS]
    todo.sort(key=lambda t: (by_ticker.get(t) or {}).get("as_of", ""))
    todo = todo[:MAX_PER_RUN]

    fetched = 0
    for t in todo:
        try:
            rec = _fetch_one(t)
        except Exception as e:  # noqa: BLE001 — 개별 실패 격리
            print(f"[us_etf] {t} 실패: {type(e).__name__}", file=sys.stderr)
            rec = {}
        if rec:
            rec["as_of"] = now.isoformat()
            by_ticker[t] = rec
            fetched += 1
        time.sleep(THROTTLE_SEC)

    cache["by_ticker"] = by_ticker
    cache["updated_at"] = now.isoformat()
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)

    etfs = []
    for t in CURATED:
        rec = by_ticker.get(t)
        if not rec or not rec.get("name") or _age_days(rec.get("as_of", ""), now) > STALE_EMIT_DAYS:
            continue
        etfs.append({
            "ticker": t, "name": rec.get("name"), "category": rec.get("category"),
            "aum_usd": rec.get("aum_usd"), "family": rec.get("family"),
            "expense": rec.get("expense"), "top_holdings": rec.get("top_holdings"),
        })
    etfs.sort(key=lambda e: (e.get("aum_usd") or 0), reverse=True)

    out = {
        "_meta": {
            "generated_at": now.isoformat(),
            "source": "yfinance (US 상장 ETF info + top_holdings)",
            "curated_n": len(CURATED),
            "covered_n": len(etfs),
            "fetched_this_run": fetched,
            "disclaimer": "US ETF 사실(카테고리·AUM·운용사·보수·보유종목 top) — 점수/추천 아님(RULE 7). "
                          "실시간 시세·NAV 미노출(증권사 앱). yfinance 무료 소스.",
        },
        "etfs": etfs,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"[us_etf] curated {len(CURATED)} | fetched {fetched} | covered {len(etfs)} | out={OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
