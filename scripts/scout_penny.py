#!/usr/bin/env python3
"""US 페니주 워치리스트 — Perplexity 다중쿼리 → 빈도 ≥3 → 상위 5.

수동 실행 (cron 미연동):
  python3 scripts/scout_penny.py            # 5쿼리 실행 → data/penny_watchlist.json
  python3 scripts/scout_penny.py --dry-run  # API 호출 없이 캐시·whitelist 만 점검

설계 원칙:
  - VAMS 검증 기간 중 — **워치리스트 전용**. Brain 파이프라인에 inject 하지 않음.
  - Perplexity sonar-pro × 5쿼리 = 약 $0.05~0.10 / 회.
  - NASDAQ trader 공식 dump 로 티커 화이트리스트 (7일 캐시).
  - common-word 블록리스트로 USA, AI, CEO, FED 같은 prose 약어 제거.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from api.clients.perplexity_client import call_perplexity, get_session_stats  # noqa: E402

DATA_DIR = REPO_ROOT / "data"
WHITELIST_PATH = DATA_DIR / "us_tickers.txt"
OUTPUT_PATH = DATA_DIR / "penny_watchlist.json"

NASDAQ_DUMP_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"
WHITELIST_TTL_SEC = 7 * 24 * 3600  # 7일

SCOUT_QUERIES = [
    "best US penny stocks under $5 to buy April 2026 — list ticker symbols",
    "top US penny stocks momentum breakout April 2026 watchlist tickers",
    "most mentioned US penny stocks Reddit wallstreetbets stocktwits 2026",
    "US penny stocks strong fundamentals analyst picks April 2026 ticker list",
    "hot US penny stocks under $3 April 2026 names",
]

# 실제 티커이지만 prose 에서 약어/단어로 더 자주 쓰이는 심볼 — 블록.
# 예: "USA" 는 Liberty All-Star Equity Fund 티커지만, 문장에선 미국 의미.
COMMON_WORD_BLOCKLIST = {
    "USA", "US", "UK", "EU", "UN", "AI", "IT", "TV", "PC", "PR",
    "CEO", "CFO", "CTO", "COO", "IPO", "ETF", "REIT", "LLC", "INC", "LTD",
    "FDA", "SEC", "FED", "IRS", "NYSE", "GDP", "CPI", "PMI", "USD", "EUR",
    "JPY", "CNY", "GBP", "IMF", "WHO", "EPS", "PE", "PEG", "ROE", "ROI",
    "ROA", "EBIT", "FCF", "MA", "RSI", "ADX", "ATR", "VWAP", "OTC", "AMA",
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
    "NOV", "DEC", "MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN",
    "Q1", "Q2", "Q3", "Q4", "H1", "H2", "FY", "YOY", "QOQ", "MOM",
    "AGM", "EGM", "CFO", "ESG", "API", "SDK", "URL", "FAQ", "PDF", "CSV",
    "USA", "U", "UK",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_whitelist(force_refresh: bool = False) -> set[str]:
    """NASDAQ trader dump 로 US 티커 화이트리스트. 7일 캐시.

    Returns:
        set of uppercase ticker strings (NASDAQ + NYSE 등 모든 traded).
    """
    needs_fetch = force_refresh
    if not WHITELIST_PATH.exists():
        needs_fetch = True
    elif (time.time() - WHITELIST_PATH.stat().st_mtime) > WHITELIST_TTL_SEC:
        needs_fetch = True

    if needs_fetch:
        try:
            print(f"  ↓ NASDAQ dump fetching → {WHITELIST_PATH.name}")
            resp = requests.get(NASDAQ_DUMP_URL, timeout=30)
            resp.raise_for_status()
            WHITELIST_PATH.write_text(resp.text, encoding="utf-8")
        except Exception as e:
            if not WHITELIST_PATH.exists():
                raise RuntimeError(f"NASDAQ dump fetch 실패 + 캐시 없음: {e}")
            print(f"  ⚠ fetch 실패, 기존 캐시 사용: {e}")

    text = WHITELIST_PATH.read_text(encoding="utf-8")
    tickers: set[str] = set()
    for line in text.splitlines():
        if not line or line.startswith(("Nasdaq Traded|", "File Creation Time")):
            continue
        parts = line.split("|")
        if len(parts) < 2:
            continue
        sym = parts[1].strip().upper()
        # 옵션·우선주 (.W .U .R) 등 잡음 제거 — 보통주만
        if not sym or "." in sym or "$" in sym or len(sym) > 5:
            continue
        if not sym.isalpha():
            continue
        tickers.add(sym)
    return tickers


_TICKER_RE = re.compile(r"\b([A-Z]{2,5})\b")


def _extract_tickers(text: str, whitelist: set[str]) -> list[str]:
    """본문에서 화이트리스트 ∩ regex 매치. 블록리스트 제거."""
    found = _TICKER_RE.findall(text or "")
    out = []
    for sym in found:
        if sym in COMMON_WORD_BLOCKLIST:
            continue
        if sym not in whitelist:
            continue
        out.append(sym)
    return out


def _run_query(query: str, whitelist: set[str], dry_run: bool) -> dict:
    if dry_run:
        return {"query": query, "tickers": [], "raw_chars": 0, "skipped": True}

    print(f"  ▶ {query[:60]}…")
    res = call_perplexity(query, max_tokens=2000, temperature=0.1)
    if "error" in res:
        print(f"    ✗ error: {res['error']}")
        return {"query": query, "tickers": [], "raw_chars": 0, "error": res["error"]}

    content = res.get("content", "")
    tickers = _extract_tickers(content, whitelist)
    # 같은 응답 내 중복 카운트는 1회만 (한 소스 = 1표)
    unique_tickers = sorted(set(tickers))
    print(f"    ✓ {len(unique_tickers)} tickers: {', '.join(unique_tickers[:8])}"
          + ("…" if len(unique_tickers) > 8 else ""))
    return {
        "query": query,
        "tickers": unique_tickers,
        "raw_chars": len(content),
        "citations": res.get("citations", []),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="US 페니주 워치리스트 스카우트")
    ap.add_argument("--dry-run", action="store_true",
                    help="Perplexity 호출 없이 whitelist·캐시만 점검")
    ap.add_argument("--top", type=int, default=5, help="상위 N (default 5)")
    ap.add_argument("--min-freq", type=int, default=3,
                    help="최소 언급 빈도 (default 3 — 5쿼리 중 3개 이상에서 등장)")
    ap.add_argument("--refresh-whitelist", action="store_true",
                    help="NASDAQ dump 강제 재다운로드")
    args = ap.parse_args()

    if not os.environ.get("PERPLEXITY_API_KEY") and not args.dry_run:
        print("✗ PERPLEXITY_API_KEY 미설정. --dry-run 또는 환경변수 설정 후 재시도.")
        return 2

    print("=" * 70)
    print(f"VERITY PennyScout — {_now_iso()}")
    print("=" * 70)

    whitelist = _load_whitelist(force_refresh=args.refresh_whitelist)
    print(f"  화이트리스트: {len(whitelist):,}개 심볼 ({WHITELIST_PATH.name})")
    print()

    counter: Counter[str] = Counter()
    per_query = []
    for q in SCOUT_QUERIES:
        result = _run_query(q, whitelist, args.dry_run)
        per_query.append(result)
        for t in result["tickers"]:
            counter[t] += 1

    print()
    print(f"📊 빈도 집계 (총 {len(counter)} 후보)")
    common = counter.most_common(20)
    for sym, n in common:
        bar = "█" * n
        marker = " ✓" if n >= args.min_freq else ""
        print(f"    {sym:<6} {n}회 {bar}{marker}")

    finalists = [(s, n) for s, n in common if n >= args.min_freq][: args.top]
    print()
    print(f"🎯 최종 워치리스트 — 빈도 ≥{args.min_freq}, 상위 {args.top}")
    if not finalists:
        print(f"    (조건 충족 종목 없음 — 다음 주 재실행 권장)")
    else:
        for sym, n in finalists:
            print(f"    {sym:<6} ({n}/{len(SCOUT_QUERIES)} 소스)")

    if args.dry_run:
        print()
        print("(dry-run — 결과 파일 쓰지 않음. 실제 실행은 PERPLEXITY_API_KEY 환경변수 + 인자 없이.)")
        return 0

    payload = {
        "generated_at": _now_iso(),
        "queries_run": len(SCOUT_QUERIES),
        "min_frequency": args.min_freq,
        "candidates_total": len(counter),
        "watchlist": [
            {"ticker": s, "frequency": n, "sources": f"{n}/{len(SCOUT_QUERIES)}"}
            for s, n in finalists
        ],
        "all_candidates_top20": [
            {"ticker": s, "frequency": n} for s, n in common
        ],
        "perplexity_session": get_session_stats(),
        "whitelist_size": len(whitelist),
        "note": "VAMS 검증 기간 — 워치리스트 전용. Brain 파이프라인 inject 안 함.",
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"💾 saved → {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print(f"   Perplexity: {payload['perplexity_session']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
