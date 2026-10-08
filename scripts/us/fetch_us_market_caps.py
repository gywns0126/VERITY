"""fetch_us_market_caps — S&P Composite 1500 시가총액 수집 (yfinance fast_info).

배경 ([[feedback_us_expansion_settled_no_relitigate]] / [[project_us_financials_sec_edgar]]):
  미장 유니버스 15→1500 확대 후, 재무/Altman/F-Score 는 SEC EDGAR 로 1500 완전.
  그러나 Lynch 분류의 size 차원(Stalwart ≥$10B) + 원본 Altman X4(시가/총부채) = market_cap 필요.
  market_cap 은 SEC XBRL 부재 → portfolio.json(추천 15)에만 있어 1500 중 1490 size 미상.

소스 결정 (PM 2026-06-21): **yfinance marketCap 직접** (shares×price 계산 불요).
  - fast_info.market_cap = 라이브러리 산출 raw USD (compute_lynch_us 의 10e9 임계 단위 정합).
  - 무료. 1500 batch = yfinance_safe (curl_cffi anti-bot + 429 backoff + cooler) 로 rate-limit 안전.
  - Lynch size buckets 는 coarse($10B)라 월간 cron freshness 충분.

산출: data/us_market_caps.json = {schema_version, generated_at, count, market_caps:{TICKER: usd}}.
  멱등 — 이번 run 에서 fail 한 ticker 는 기존 값 보존 (silent data loss 금지,
  [[feedback_data_collection_verification_mandatory]]).
  market_cap_as_of = 종목별 성공 수집시각(거래소 시세시각 아님); legacy 미상은 null.
  failed_tickers = 미복구 실패 목록. --retry-only / --stale-days 필터 후 --offset/--limit 적용.

호출 빈도: 월 1회 (us_financials.yml 와 동반).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))  # noqa: E402

from api.collectors.yfinance_safe import (  # noqa: E402
    yf_ticker, safe_yf_call, get_state_snapshot, _is_rate_limit_error,
)

KST = timezone(timedelta(hours=9))
SP1500_PATH = REPO_ROOT / "data" / "us_universe_sp1500.json"
COMBINED_PATH = REPO_ROOT / "data" / "us_universe_combined.json"
OUTPUT_PATH = REPO_ROOT / "data" / "us_market_caps.json"

# Lynch DEFAULT_US15 fallback 과 동일 (유니버스 부재 시).
DEFAULT_US15 = [
    "MSFT", "JNJ", "BAC", "ADBE", "CRM", "JPM", "DIS", "SOFI",
    "QCOM", "META", "BRK-B", "TMO", "PG", "XOM", "CSCO",
]


def load_universe_tickers(path: Path) -> List[str]:
    if not path.exists():
        print(f"[us_market_caps] {path.name} 부재 — US15 fallback", file=sys.stderr)
        return list(DEFAULT_US15)
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        tickers = [str(t).strip().upper() for t in (d.get("tickers") or []) if str(t).strip()]
        return tickers or list(DEFAULT_US15)
    except Exception as e:  # noqa: BLE001
        print(f"[us_market_caps] {path.name} parse 실패: {e!r} — US15 fallback", file=sys.stderr)
        return list(DEFAULT_US15)


def _positive_finite(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def _load_existing_document() -> dict:
    """Unreadable prior data must not be overwritten by a partial recovery."""
    if not OUTPUT_PATH.exists():
        return {}
    doc = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("market_caps"), dict):
        raise ValueError("existing market_caps must be an object")
    return doc


def load_existing(document: Optional[dict] = None) -> Dict[str, float]:
    """기존 유효 시총만 merge base 로 사용; 실패 종목의 last-good 보존."""
    doc = _load_existing_document() if document is None else document
    return {str(k).upper(): v for k, raw in doc.get("market_caps", {}).items()
            if isinstance(raw, (int, float)) and (v := _positive_finite(raw)) is not None}


def _is_stale(as_of: Any, now: datetime, days: int) -> bool:
    try:
        stamp = datetime.fromisoformat(as_of)
        if stamp.tzinfo is None or stamp > now:
            return True
        return now - stamp >= timedelta(days=days)
    except (TypeError, ValueError):
        return True  # Legacy generated_at does not date each retained value.


def fetch_market_cap(ticker: str) -> Optional[float]:
    """FastInfo then info.marketCap; no shares×price estimate or extra retry loop.

    Each safe_yf_call attempt tries each source at most once. Rate limits propagate
    to the existing bounded retry/backoff wrapper instead of triggering a fallback.
    """
    def _call() -> Optional[float]:
        stock = yf_ticker(ticker)
        try:
            fi = stock.fast_info
            mc = fi.get("marketCap") if isinstance(fi, dict) else fi.market_cap
            value = _positive_finite(mc)
            if value is not None:
                return value
        except Exception as e:  # noqa: BLE001 — malformed FastInfo, e.g. currentTradingPeriod
            if _is_rate_limit_error(e):
                raise
        # Reading the camelCase FastInfo alias again would repeat the same failing
        # history/metadata access. Use the independent quote field instead.
        info = stock.info
        return _positive_finite(info.get("marketCap")) if isinstance(info, dict) else None

    # rate limit 외 예외(개별 ticker delisted 등)는 fail 처리 (전체 중단 방지).
    try:
        return safe_yf_call(_call, label=ticker, per_call_sleep_s=0.05)
    except Exception as e:  # noqa: BLE001
        print(f"[us_market_caps] {ticker} fetch 실패: {e!r}", file=sys.stderr)
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="최대 종목 수 (0=무제한).")
    parser.add_argument("--offset", type=int, default=0, help="유니버스 시작 오프셋 (배치 분할).")
    parser.add_argument("--ticker", help="단일 ticker (manual test).")
    parser.add_argument("--universe", choices=["sp1500", "combined"], default="sp1500",
                        help="sp1500=S&P 1500 / combined=Polygon CS active ∪ sp1500(소형주 트랙).")
    recovery = parser.add_mutually_exclusive_group()
    recovery.add_argument("--retry-only", action="store_true",
                          help="현재 유니버스 중 결손 또는 기록된 실패 종목만 조회.")
    recovery.add_argument("--stale-days", type=int,
                          help="결손·기록된 실패·수집시각 미상 또는 N일 이상 지난 종목만 조회.")
    args = parser.parse_args()
    if args.limit < 0 or args.offset < 0 or (args.stale_days is not None and args.stale_days < 0):
        parser.error("limit, offset and stale-days must be non-negative")

    try:
        existing = _load_existing_document()
        merged = load_existing(existing)
    except (OSError, ValueError) as e:
        print(f"[us_market_caps] 기존 파일 읽기 실패 — 보존 후 중단: {e!r}", file=sys.stderr)
        return 1
    # Per-ticker successful collection time, NOT exchange/quote time. Unknown
    # legacy dates stay null: generated_at could include failed carry-forwards.
    prior_dates = existing.get("market_cap_as_of") or {}
    if not isinstance(prior_dates, dict):
        prior_dates = {}
    as_of = {tk: prior_dates.get(tk) if isinstance(prior_dates.get(tk), str) else None
             for tk in merged}
    failed = existing.get("failed_tickers") or []
    failed = {tk for tk in failed if isinstance(tk, str)} if isinstance(failed, list) else set()
    now = datetime.now(KST)

    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        path = COMBINED_PATH if args.universe == "combined" else SP1500_PATH
        tickers = load_universe_tickers(path)
    tickers = list(dict.fromkeys(tickers))
    if args.retry_only or args.stale_days is not None:
        tickers = [tk for tk in tickers if tk not in merged or tk in failed
                   or (args.stale_days is not None and _is_stale(as_of.get(tk), now, args.stale_days))]
    # Recovery filtering precedes batching so healthy prefixes do not starve gaps.
    tickers = tickers[args.offset:]
    if args.limit > 0:
        tickers = tickers[:args.limit]

    print(f"[us_market_caps] universe size={len(tickers)}", file=sys.stderr)

    if not tickers:
        return 0  # No fetch and no misleading generated_at refresh on a no-op.
    ok = 0
    fail = 0
    for i, tk in enumerate(tickers, 1):
        mc = _positive_finite(fetch_market_cap(tk))
        if mc is not None:
            merged[tk] = mc
            as_of[tk] = datetime.now(KST).isoformat(timespec="seconds")
            failed.discard(tk)
            ok += 1
            if i % 100 == 0 or i == len(tickers):
                print(f"  [{i}/{len(tickers)}] {tk} ${mc/1e9:.2f}B (ok={ok} fail={fail})",
                      file=sys.stderr, flush=True)
        else:
            fail += 1
            failed.add(tk)
            print(f"  [{i}/{len(tickers)}] {tk}: market_cap 부재/실패 "
                  f"({'기존값 보존' if tk in merged else '결손'})", file=sys.stderr)

    payload = {
        "schema_version": "v0",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "count": len(merged),
        "source": "yfinance.fast_info.market_cap; fallback=yfinance.info.marketCap",
        "market_caps": dict(sorted(merged.items())),
        "market_cap_as_of": dict(sorted(as_of.items())),
        "failed_tickers": sorted(failed),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

    rl = get_state_snapshot().get("rate_limit_count", 0)
    # logged=True — [[feedback_data_collection_verification_mandatory]]
    print(f"[us_market_caps] logged=True · this_run ok={ok} fail={fail} · "
          f"total stored={len(merged)} · rate_limited={rl} -> {OUTPUT_PATH.name}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
