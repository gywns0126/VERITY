"""us_financials_builder — US15 SEC EDGAR XBRL 표준화 snapshot 빌드.

PM 직관 (사용자, 5/20): 미장 재무제표 분석 — bottom-up fundamentals layer.
[[project_us_financials_sec_edgar]] 정합.

데이터 흐름:
  data/portfolio.json recommendations → US ticker 추출
  → api.intelligence.us_financials.build_ticker_snapshot 호출
  → data/us_financials/<TICKER>.json per ticker
  → data/us_financials/_summary.json universe-level 요약

비용: 무료 (SEC EDGAR). User-Agent 헤더만.
호출 빈도: 월 1회 (분기 보고서 발표 후 갱신).

RULE 정합:
  - RULE 6 (LLM call 0건).
  - [[feedback_data_collection_verification_mandatory]] (logged=True 명시).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))  # noqa: E402

from api.intelligence import us_financials as usf  # noqa: E402

KST = timezone(timedelta(hours=9))
PORTFOLIO_PATH = REPO_ROOT / "data" / "portfolio.json"
OUTPUT_DIR = REPO_ROOT / "data" / "us_financials"
SUMMARY_PATH = OUTPUT_DIR / "_summary.json"

_logger = logging.getLogger(__name__)

# Default US15 fallback (portfolio 부재 시).
DEFAULT_US15 = [
    "MSFT", "JNJ", "BAC", "ADBE", "CRM",
    "JPM", "DIS", "SOFI", "QCOM", "META",
    "BRK-B", "TMO", "PG", "XOM", "CSCO",
]


def load_us_tickers() -> List[str]:
    """portfolio.json recommendations 의 US ticker 추출.

    KR ticker (6자리 숫자) 제외. portfolio 부재 시 DEFAULT_US15 fallback.
    """
    if not PORTFOLIO_PATH.exists():
        _logger.warning("portfolio.json 부재 — DEFAULT_US15 fallback")
        return list(DEFAULT_US15)
    try:
        data = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        _logger.error("portfolio.json parse failed: %s", e)
        return list(DEFAULT_US15)
    recs = data.get("recommendations") or []
    us = []
    for r in recs:
        t = (r.get("ticker") or "").strip().upper()
        if not t:
            continue
        # KR ticker = 6자리 숫자
        if t.isdigit() and len(t) == 6:
            continue
            us.append(t)
    return us or list(DEFAULT_US15)


def load_us_externals() -> Dict[str, Dict[str, Any]]:
    """portfolio.json 에서 US ticker → {market_cap, div_yield} (Lynch/원본 Altman 입력).

    SEC EDGAR 스냅샷에 없는 시가총액/배당 = portfolio (yfinance/KIS 수집분) wire.
    """
    if not PORTFOLIO_PATH.exists():
        return {}
    try:
        data = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for r in (data.get("recommendations") or []):
        t = (r.get("ticker") or "").strip().upper()
        if not t:
            continue
        out[t] = {
            "market_cap": r.get("market_cap"),
            "div_yield": r.get("div_yield"),
        }
    return out


def _save_ticker_snapshot(snap: Dict[str, Any]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ticker = snap.get("ticker", "UNKNOWN")
    path = OUTPUT_DIR / f"{ticker}.json"
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _build_summary(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """universe-level 요약 — derived metrics 만 추출.

    individual snapshot 은 별도 파일 — 본 summary 는 가벼운 dashboard 용.
    """
    rows = []
    for s in snapshots:
        if "_error" in s:
            rows.append({
                "ticker": s.get("ticker"),
                "error": s.get("_error"),
            })
            continue
        derived = s.get("derived") or {}
        meta = s.get("meta") or {}
        rows.append({
            "ticker": s.get("ticker"),
            "entity_name": meta.get("entity_name"),
            "cik": meta.get("cik"),
            "sic": meta.get("sic"),
            "is_financial": meta.get("is_financial"),
            "revenue_yoy_pct_annual": derived.get("revenue_yoy_pct_annual"),
            "revenue_yoy_pct_quarterly": derived.get("revenue_yoy_pct_quarterly"),
            "gross_margin_pct": derived.get("gross_margin_pct"),
            "operating_margin_pct": derived.get("operating_margin_pct"),
            "pretax_margin_pct": derived.get("pretax_margin_pct"),
            "net_margin_pct": derived.get("net_margin_pct"),
            "fcf_usd": derived.get("fcf_usd"),
            "fcf_na_reason": derived.get("fcf_na_reason"),
            "debt_to_equity": derived.get("debt_to_equity"),
            "roe_pct": derived.get("roe_pct"),
            "altman_z": (derived.get("altman_z") or {}).get("z_score"),
            "altman_zone": (derived.get("altman_z") or {}).get("zone"),
            "fscore": (derived.get("fscore") or {}).get("f_score"),
            "fscore_grade": (derived.get("fscore") or {}).get("grade"),
            "lynch_class": (derived.get("lynch") or {}).get("lynch_class"),
        })
    return {
        "schema_version": "v0.1",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "universe_size": len(snapshots),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ticker",
        help="단일 ticker (manual test 용). 비우면 portfolio.json recommendations US 전체.",
    )
    parser.add_argument("--limit", type=int, default=0,
                        help="최대 종목 수 (cost cap, 0=무제한).")
    args = parser.parse_args()

    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = load_us_tickers()
    if args.limit > 0:
        tickers = tickers[:args.limit]

    print(f"[us_financials] universe size={len(tickers)}", file=sys.stderr)

    print("[us_financials] ticker→CIK 매핑 fetch…", file=sys.stderr)
    cache = usf.build_ticker_cik_cache()
    if not cache:
        _logger.error("ticker_cik cache 비어있음 — SEC fetch 실패")
        return 1

    externals = load_us_externals()  # ticker → {market_cap, div_yield} (Lynch/원본 Altman)

    snapshots: List[Dict[str, Any]] = []
    for i, ticker in enumerate(tickers, 1):
        cik = cache.get(ticker.upper())
        if cik is None:
            print(f"  [{i}/{len(tickers)}] {ticker}: CIK 매핑 부재 skip", file=sys.stderr)
            snapshots.append({"ticker": ticker, "_error": "CIK not found"})
            continue
        print(f"  [{i}/{len(tickers)}] {ticker} (CIK {cik})…", file=sys.stderr, flush=True)
        _ext = externals.get(ticker.upper(), {})
        snap = usf.build_ticker_snapshot(ticker, cik,
                                         market_cap=_ext.get("market_cap"),
                                         div_yield=_ext.get("div_yield"))
        snapshots.append(snap)
        if "_error" in snap:
            print(f"     ERROR: {snap['_error']}", file=sys.stderr)
        else:
            saved = _save_ticker_snapshot(snap)
            d = snap.get("derived") or {}
            print(
                f"     saved {saved.name} | rev YoY {d.get('revenue_yoy_pct_annual')}% "
                f"op margin {d.get('operating_margin_pct')}% ROE {d.get('roe_pct')}%",
                file=sys.stderr,
            )
        # SEC rate limit 안전 (~0.15s/call already in fetch_companyfacts)
        time.sleep(0.3)

    summary = _build_summary(snapshots)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    ok_count = sum(1 for s in snapshots if "_error" not in s)
    print(
        f"[us_financials] DONE — {ok_count}/{len(tickers)} OK, summary saved (logged=True)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
