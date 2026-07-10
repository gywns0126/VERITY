"""us_analyst_consensus_public_builder — 공개 터미널 美 애널리스트 컨센서스 빌더.

2026-06-22 신설. US 후속 (b) us_flow 컨센서스 1500 확대.
PM 결정(짜장면 비유): 컨센서스는 커모디티(모든 앱에 있음)나, 완전한 터미널의 기본 메뉴 —
  차별점(Form4/13D-G/13F forensics)은 그 위에 얹음. [[feedback_us_expansion_settled_no_relitigate]].

소스: yfinance(무료, Finnhub rate 회피). Ticker.info = recommendationKey/Mean·numAnalysts·
  targetMean/High/Low + Ticker.recommendations = strongBuy/buy/hold/sell 분포(현 기간).
🚨 RULE 7 = 외부 사실(애널리스트 집계) + 출처 명시. 우리 자체 점수·매매신호 아님 (관측·표시용).
  rec_mean = yfinance 1(strongBuy)~5(strongSell) 척도 그대로 — 우리 산식 아님.

설계 = insider 빌더 rotation(portfolio 우선+day-of-year) + market_cap 멱등 merge(실패 보존) + budget.


🚫 발행 금지 (PM 확정 2026-07-10): 본 산출물은 내부 관측 전용 — publish-data allowlist
  등재 금지 (yfinance 목표가·의견 = Benzinga/S&P 실권리, 재배포 blocker). 공개 = 출처
  링크아웃(StockReport), 숫자 부활 = 유료 Polygon×Benzinga 정식 라이선스 후에만.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)  # noqa: E402

from api.collectors.yfinance_safe import yf_ticker, safe_yf_call, get_state_snapshot  # noqa: E402
from api.builders.us_insider_trades_public_builder import _ordered_universe  # noqa: E402

KST = timezone(timedelta(hours=9))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "us_analyst_consensus.json")
MAX_SECONDS = int(os.environ.get("US_CONSENSUS_MAX_SECONDS", "2400"))
MAX_CALLS = int(os.environ.get("US_CONSENSUS_MAX_CALLS", "12000"))


def _now_kst() -> datetime:
    return datetime.now(KST)


def _f(v) -> Optional[float]:
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


def _load_prev() -> Dict[str, Dict[str, Any]]:
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            doc = json.load(f)
        return {str(s.get("ticker") or ""): s for s in (doc.get("stocks") or []) if s.get("ticker")}
    except (OSError, ValueError):
        return {}


def _build_consensus(ticker: str, info: Dict[str, Any], counts: Dict[str, int]) -> Optional[Dict[str, Any]]:
    """순수 파싱 — info dict + rating counts → 컨센서스 dict. 커버리지 0 = None."""
    num = info.get("numberOfAnalystOpinions")
    target_mean = _f(info.get("targetMeanPrice"))
    rec_key = info.get("recommendationKey")
    if not num and target_mean is None and not rec_key:
        return None  # 애널리스트 커버리지 없음
    current = _f(info.get("currentPrice")) or _f(info.get("regularMarketPrice"))
    upside = round((target_mean - current) / current * 100, 1) if (target_mean and current) else None
    return {
        "ticker": ticker, "name": ticker,
        "rec_key": rec_key,                                  # buy/hold/sell/strong_buy...
        "rec_mean": _f(info.get("recommendationMean")),      # yfinance 1(strongBuy)~5(strongSell)
        "num_analysts": int(num) if num else None,
        "target_mean": target_mean,
        "target_high": _f(info.get("targetHighPrice")),
        "target_low": _f(info.get("targetLowPrice")),
        "current_price": current,
        "upside_pct": upside,
        "counts": counts,                                    # strongBuy/buy/hold/sell/strongSell
        "collected_at": _now_kst().date().strftime("%Y-%m-%d"),
    }


def _extract_counts(rec) -> Dict[str, int]:
    """recommendations DataFrame 현 기간(0m) 행 → 등급 분포."""
    try:
        if rec is not None and len(rec) > 0:
            row = rec.iloc[0]
            return {k: int(row[k]) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")
                    if k in row and row[k] == row[k]}
    except Exception:  # noqa: BLE001
        pass
    return {}


def fetch_consensus(ticker: str) -> Optional[Dict[str, Any]]:
    """yfinance info + recommendations → 컨센서스 dict. 애널리스트 0 또는 실패 = None."""
    info = safe_yf_call(lambda: yf_ticker(ticker).info, label=f"{ticker}.info", per_call_sleep_s=0.05)
    if not info:
        return None
    rec = safe_yf_call(lambda: yf_ticker(ticker).recommendations, label=f"{ticker}.recs", per_call_sleep_s=0.02)
    return _build_consensus(ticker, info, _extract_counts(rec))


def main() -> int:
    ok = False
    try:
        merged = _load_prev()
        order = _ordered_universe()
        t0 = time.monotonic()
        calls = collected = 0
        for tk in order:
            if time.monotonic() - t0 > MAX_SECONDS or calls >= MAX_CALLS:
                print(f"[us_consensus] budget 도달 (calls={calls}, {int(time.monotonic()-t0)}s) — 나머지 carry-forward", file=sys.stderr)
                break
            calls += 1
            try:
                c = fetch_consensus(tk)
            except Exception as e:  # noqa: BLE001
                print(f"[us_consensus] {tk} 실패: {e!r}", file=sys.stderr)
                c = None
            if c is not None:
                merged[tk] = c
                collected += 1
            # 실패 = 이전 보존(merged 유지). 커버리지 없는 신규는 미수록.

        stocks = sorted(merged.values(),
                        key=lambda s: (s.get("num_analysts") or 0), reverse=True)
        if not stocks and os.path.isfile(OUTPUT_PATH):
            print("[us_consensus] 0 종목 — 기존 보존", file=sys.stderr)
            ok = True
            return 0

        rl = get_state_snapshot().get("rate_limit_count", 0)
        out = {
            "_meta": {
                "generated_at": _now_kst().isoformat(),
                "source": "yfinance (Yahoo Finance 애널리스트 컨센서스 집계)",
                "count": len(stocks),
                "universe": len(order),
                "collected_today": collected,
                "rate_limited": rl,
                "note": "외부 애널리스트 집계 사실 — 등급·목표가·업사이드. rec_mean=yfinance 1(strongBuy)~5(strongSell) 척도. 우리 자체 점수·매매신호 아님 (RULE 7, 표시·관측용). 전 종목(sp1500) 회전 수집.",
            },
            "stocks": stocks,
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[us_consensus] logged=True · {len(stocks)} 종목(누적) · 오늘수집 {collected}/{len(order)} · rate_limited={rl} -> {os.path.relpath(OUTPUT_PATH, REPO_ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[us_consensus] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[us_consensus] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
