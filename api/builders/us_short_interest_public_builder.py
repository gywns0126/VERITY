"""미장(US) 공매도 잔고 빌더 — short interest 사실(short %·days-to-cover·추세).

토스가 미장 종목 화면에 표시하는 공매도 잔고 = 이탈 트리거. yfinance(NYSE/NASDAQ 공시 기반,
월 2회 갱신) 무료 수집. us_forensics 엔드포인트 소스로 합류 → PublicStockReport usForen 카드.

🚨 사실만 (RULE 7): short_pct · days_to_cover · shares_short · 추세(전기 대비 증감). 자체 점수·
   판단 0. "공매도 많다 = 하락 신호" 아님(참고 사실).

⚠️ yfinance 레이트리밋 → capped 회전(MAX_PER_RUN) + 캐시 slow-fill. short 는 ~2주 주기
   갱신이라 FRESH_DAYS=14 재수집. 전 유니버스 ~N일 만에 커버 후 신선도 유지.

입력: data/us_universe_combined.json (tickers/names)
출력: data/us_short_interest.json {_meta, stocks:[{ticker, name, short_pct, days_to_cover, ...}]}
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UNIVERSE_PATH = os.path.join(_ROOT, "data", "us_universe_combined.json")
CACHE_PATH = os.path.join(_ROOT, "data", "us_short_interest_cache.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_short_interest.json")

KST = timezone(timedelta(hours=9))
FRESH_DAYS = 14        # short = 월 2회 공시 → 2주 주기 재수집
MAX_PER_RUN = 150      # yfinance 레이트리밋 안전 (일 회전 → ~10일 만에 전 유니버스)
THROTTLE_SEC = 0.2
STALE_EMIT_DAYS = 45   # 이보다 오래된 캐시 = 발행 제외(신선도 가드)


def _now_kst() -> datetime:
    return datetime.now(KST)


def _yahoo_ticker(t: str) -> str:
    """US 티커 → yahoo 표기 (클래스주 BRK.B → BRK-B)."""
    return str(t or "").strip().upper().replace(".", "-")


def _age_days(as_of: str, now: datetime) -> float:
    try:
        return (now - datetime.fromisoformat(as_of)).days
    except (ValueError, TypeError):
        return 1e9


def main() -> int:
    if not os.path.exists(UNIVERSE_PATH):
        print(f"[us_short] 유니버스 부재: {UNIVERSE_PATH} — skip", file=sys.stderr)
        return 0
    uni = json.load(open(UNIVERSE_PATH, encoding="utf-8"))
    tickers = uni.get("tickers") or []
    names = uni.get("names") or {}

    cache = {"updated_at": None, "by_ticker": {}}
    if os.path.exists(CACHE_PATH):
        try:
            cache = json.load(open(CACHE_PATH, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    by_ticker = cache.get("by_ticker") or {}

    now = _now_kst()
    # 회전 대상 = 캐시 없음 or FRESH_DAYS 초과 (오래된 것 우선)
    todo = [t for t in tickers
            if _age_days((by_ticker.get(t) or {}).get("as_of", ""), now) >= FRESH_DAYS]
    todo.sort(key=lambda t: (by_ticker.get(t) or {}).get("as_of", ""))  # 가장 오래된 먼저
    todo = todo[:MAX_PER_RUN]

    fetched = 0
    if todo:
        try:
            from api.collectors.stock_data import get_short_interest_yf
        except Exception as e:  # noqa: BLE001
            print(f"[us_short] get_short_interest_yf import 실패: {e}", file=sys.stderr)
            return 0
        for t in todo:
            try:
                r = get_short_interest_yf(_yahoo_ticker(t)) or {}
            except Exception as e:  # noqa: BLE001 — 개별 실패 격리(회전)
                print(f"[us_short] {t} 실패: {type(e).__name__}", file=sys.stderr)
                r = {}
            by_ticker[t] = {
                "short_pct": r.get("short_pct"),
                "short_pct_prior": r.get("short_pct_prior"),
                "days_to_cover": r.get("days_to_cover"),
                "shares_short": r.get("shares_short"),
                "report_date": r.get("report_date"),
                "trend": r.get("trend"),
                "as_of": now.isoformat(),
            }
            fetched += 1
            time.sleep(THROTTLE_SEC)

    cache["by_ticker"] = by_ticker
    cache["updated_at"] = now.isoformat()
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)

    # 발행 = short_pct 유효 + 캐시 신선(STALE_EMIT_DAYS 내) 종목만
    stocks = []
    for t, rec in by_ticker.items():
        if rec.get("short_pct") is None:
            continue
        if _age_days(rec.get("as_of", ""), now) > STALE_EMIT_DAYS:
            continue
        stocks.append({
            "ticker": t,
            "name": names.get(t) or "",
            "short_pct": rec.get("short_pct"),
            "short_pct_prior": rec.get("short_pct_prior"),
            "days_to_cover": rec.get("days_to_cover"),
            "shares_short": rec.get("shares_short"),
            "report_date": rec.get("report_date"),
            "trend": rec.get("trend"),
        })
    stocks.sort(key=lambda s: s.get("short_pct") or 0, reverse=True)

    out = {
        "_meta": {
            "generated_at": now.isoformat(),
            "source": "yfinance (NYSE/NASDAQ short interest, 월 2회 공시)",
            "universe_n": len(tickers),
            "covered_n": len(stocks),
            "fetched_this_run": fetched,
            "disclaimer": "공매도 잔고 사실(short %·days-to-cover·전기 대비 추세) — 점수/추천 아님(RULE 7). "
                          "공매도 많음 = 하락 신호 아님(참고). yfinance 무료 소스, 월 2회 갱신.",
        },
        "stocks": stocks,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"[us_short] universe {len(tickers)} | fetched {fetched} | covered {len(stocks)} | out={OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
