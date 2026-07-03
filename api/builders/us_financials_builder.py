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
SMALLCAP_SUMMARY_PATH = OUTPUT_DIR / "_summary_smallcap.json"  # smallcap 트랙 별 summary (sp1500 _summary 미덮음)

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
        # KR ticker = 6자리 숫자 → skip
        if t.isdigit() and len(t) == 6:
            continue
        us.append(t)  # 2026-06-21 fix: continue 뒤 dead-code 였음(us 항상 빈값→US15 fallback 고착)
    return us or list(DEFAULT_US15)


# S&P Composite 1500 정적 유니버스 (scripts/us/fetch_sp1500_universe.py 산출).
SP1500_PATH = REPO_ROOT / "data" / "us_universe_sp1500.json"
# 소형주 트랙 universe = Polygon CS active ∪ sp1500 (scripts/us/fetch_us_smallcap_universe.py).
COMBINED_PATH = REPO_ROOT / "data" / "us_universe_combined.json"
# 1500 시가총액 (scripts/us/fetch_us_market_caps.py, yfinance fast_info). Lynch size + 원본 Altman X4.
MARKET_CAPS_PATH = REPO_ROOT / "data" / "us_market_caps.json"
# 소형주 컷 — 시총 분포 확인 후 조정(잠정). 시총 부재 종목은 제외(RULE 7: 사실 없으면 비노출).
SMALLCAP_CAP_MAX = 5_000_000_000  # $5B 이하 = 소형주 트랙 backfill 대상


def load_sp1500_tickers() -> List[str]:
    """미장 확대 유니버스 = S&P 500+400+600 (fetch_sp1500_universe.py). 부재/결손 시 DEFAULT_US15 fallback."""
    if not SP1500_PATH.exists():
        _logger.warning("us_universe_sp1500.json 부재 — scripts/us/fetch_sp1500_universe.py 먼저 실행. US15 fallback")
        return list(DEFAULT_US15)
    try:
        d = json.loads(SP1500_PATH.read_text(encoding="utf-8"))
        tickers = [str(t).strip().upper() for t in (d.get("tickers") or []) if str(t).strip()]
        return tickers or list(DEFAULT_US15)
    except Exception as e:  # noqa: BLE001
        _logger.error("us_universe_sp1500.json parse failed: %s — US15 fallback", e)
        return list(DEFAULT_US15)


def load_smallcap_tickers() -> List[str]:
    """소형주 트랙 universe = combined(Polygon CS ∪ sp1500) 중 시총 ≤ SMALLCAP_CAP_MAX.

    시총 부재 종목은 제외(RULE 7 — 사실 없으면 비노출, delisted 자동 탈락).
    us_market_caps.json(combined) 선행 필요. 부재/결손 시 sp1500 fallback.
    """
    if not COMBINED_PATH.exists():
        _logger.warning("us_universe_combined.json 부재 — fetch_us_smallcap_universe.py 먼저. sp1500 fallback")
        return load_sp1500_tickers()
    try:
        d = json.loads(COMBINED_PATH.read_text(encoding="utf-8"))
        universe = [str(t).strip().upper() for t in (d.get("tickers") or []) if str(t).strip()]
    except Exception as e:  # noqa: BLE001
        _logger.error("us_universe_combined.json parse failed: %s — sp1500 fallback", e)
        return load_sp1500_tickers()
    caps = load_market_caps()
    small = [t for t in universe if 0 < caps.get(t, 0) <= SMALLCAP_CAP_MAX]
    if not small:
        _logger.warning("시총 컷 결과 0 — us_market_caps(combined) 미충전 의심. sp1500 fallback")
        return load_sp1500_tickers()
    _logger.info("smallcap universe = %d (combined %d 중 시총 ≤ $%.1fB)",
                 len(small), len(universe), SMALLCAP_CAP_MAX / 1e9)
    return small


def load_market_caps() -> Dict[str, float]:
    """data/us_market_caps.json (yfinance fast_info, 1500) → ticker → market_cap(raw USD).

    sp1500 Lynch size 차원 / 원본 Altman X4 입력. 부재 시 빈 dict (portfolio 15만 wire 됨).
    """
    if not MARKET_CAPS_PATH.exists():
        _logger.warning("us_market_caps.json 부재 — scripts/us/fetch_us_market_caps.py 먼저 실행. "
                        "sp1500 Lynch size 미상(portfolio 15만 wire)")
        return {}
    try:
        d = json.loads(MARKET_CAPS_PATH.read_text(encoding="utf-8"))
        mc = d.get("market_caps") or {}
        return {str(k).upper(): float(v) for k, v in mc.items()
                if isinstance(v, (int, float)) and v == v and v > 0}
    except Exception as e:  # noqa: BLE001
        _logger.error("us_market_caps.json parse failed: %s", e)
        return {}


def load_us_externals() -> Dict[str, Dict[str, Any]]:
    """US ticker → {market_cap, div_yield} (Lynch/원본 Altman 입력).

    SEC EDGAR 스냅샷에 없는 시가총액/배당 wire:
      - market_cap = us_market_caps.json(yfinance, 1500) 기반 + portfolio(추천 15)가 우선 overlay
        (portfolio 는 KIS/yfinance 라이브 수집분이라 더 신선).
      - div_yield = portfolio 만 (1500 배당 수집 = 후속 큐).
    """
    out: Dict[str, Dict[str, Any]] = {}

    # 1) 1500 base = us_market_caps.json
    for t, mc in load_market_caps().items():
        out[t] = {"market_cap": mc, "div_yield": None}

    # 2) portfolio overlay (추천 15 = 라이브 market_cap 우선 + div_yield)
    if PORTFOLIO_PATH.exists():
        try:
            data = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        for r in (data.get("recommendations") or []):
            t = (r.get("ticker") or "").strip().upper()
            if not t:
                continue
            prev = out.get(t, {})
            out[t] = {
                "market_cap": r.get("market_cap") if r.get("market_cap") is not None
                else prev.get("market_cap"),
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
    parser.add_argument("--universe", choices=["portfolio", "sp1500", "smallcap"], default="portfolio",
                        help="portfolio=추천 US(기본) / sp1500=S&P Composite 1500 / "
                             "smallcap=소형주 트랙(combined 중 시총 ≤ $%dB)" % (SMALLCAP_CAP_MAX // 10**9))
    parser.add_argument("--offset", type=int, default=0,
                        help="유니버스 시작 오프셋 (다일/배치 분할 적재용, 멱등 재개).")
    args = parser.parse_args()

    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.universe == "smallcap":
        tickers = load_smallcap_tickers()
    elif args.universe == "sp1500":
        tickers = load_sp1500_tickers()
    else:
        tickers = load_us_tickers()
    if args.offset > 0:
        tickers = tickers[args.offset:]
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
    summary_path = SMALLCAP_SUMMARY_PATH if args.universe == "smallcap" else SUMMARY_PATH
    # 🚨 부분 실행(--ticker/--limit/--offset) = 기존 _summary 에 병합 — 통째 덮어쓰면 1,505 rows 가
    # 소수 rows 로 파괴되고 후속 report 빌더가 그걸 그대로 발행 (2026-07-04 로컬 실사고, coverage WARN 이 탐지).
    partial = bool(args.ticker) or bool(args.limit) or bool(getattr(args, "offset", 0))
    if partial and summary_path.exists():
        try:
            prev = json.loads(summary_path.read_text(encoding="utf-8"))
            prev_rows = {str(r.get("ticker")): r for r in (prev.get("rows") or []) if isinstance(r, dict)}
            for r in summary.get("rows") or []:
                prev_rows[str(r.get("ticker"))] = r
            summary["rows"] = sorted(prev_rows.values(), key=lambda r: str(r.get("ticker")))
            summary["universe_size"] = len(summary["rows"])
            print(f"[us_financials] 부분 실행 — _summary 병합 (총 {len(summary['rows'])} rows 유지)", file=sys.stderr)
        except (OSError, json.JSONDecodeError, TypeError) as e:
            print(f"[us_financials] _summary 병합 실패({e}) — 안전을 위해 덮어쓰기 중단", file=sys.stderr)
            return 1
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    ok_count = sum(1 for s in snapshots if "_error" not in s)
    print(
        f"[us_financials] DONE — {ok_count}/{len(tickers)} OK, summary saved (logged=True)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
