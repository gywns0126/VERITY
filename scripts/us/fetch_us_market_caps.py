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

호출 빈도: 월 1회 (us_financials.yml 와 동반).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))  # noqa: E402

from api.collectors.yfinance_safe import yf_ticker, safe_yf_call, get_state_snapshot  # noqa: E402

KST = timezone(timedelta(hours=9))
SP1500_PATH = REPO_ROOT / "data" / "us_universe_sp1500.json"
OUTPUT_PATH = REPO_ROOT / "data" / "us_market_caps.json"

# Lynch DEFAULT_US15 fallback 과 동일 (유니버스 부재 시).
DEFAULT_US15 = [
    "MSFT", "JNJ", "BAC", "ADBE", "CRM", "JPM", "DIS", "SOFI",
    "QCOM", "META", "BRK-B", "TMO", "PG", "XOM", "CSCO",
]


def load_sp1500_tickers() -> List[str]:
    if not SP1500_PATH.exists():
        print("[us_market_caps] us_universe_sp1500.json 부재 — US15 fallback", file=sys.stderr)
        return list(DEFAULT_US15)
    try:
        d = json.loads(SP1500_PATH.read_text(encoding="utf-8"))
        tickers = [str(t).strip().upper() for t in (d.get("tickers") or []) if str(t).strip()]
        return tickers or list(DEFAULT_US15)
    except Exception as e:  # noqa: BLE001
        print(f"[us_market_caps] sp1500 parse 실패: {e!r} — US15 fallback", file=sys.stderr)
        return list(DEFAULT_US15)


def load_existing() -> Dict[str, float]:
    """기존 산출 → 멱등 merge base (이번 run fail ticker 보존)."""
    if not OUTPUT_PATH.exists():
        return {}
    try:
        d = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        mc = d.get("market_caps") or {}
        return {str(k).upper(): float(v) for k, v in mc.items()
                if isinstance(v, (int, float)) and v == v and v > 0}
    except Exception as e:  # noqa: BLE001
        print(f"[us_market_caps] 기존 파일 parse 실패(무시): {e!r}", file=sys.stderr)
        return {}


def fetch_market_cap(ticker: str) -> Optional[float]:
    """yfinance fast_info.market_cap (raw USD). rate-limit safe. fail=None."""
    def _call() -> Optional[float]:
        # FastInfo: .market_cap 속성(snake) 정상. .get("market_cap")=None(내부키 marketCap)이라
        # 속성 접근 우선, 실패 시 marketCap 키 fallback.
        fi = yf_ticker(ticker).fast_info
        mc = getattr(fi, "market_cap", None)
        if mc is None:
            try:
                mc = fi["marketCap"]
            except (KeyError, TypeError):
                mc = None
        if mc is None:
            return None
        v = float(mc)
        return v if (v == v and v > 0) else None

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
    args = parser.parse_args()

    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = load_sp1500_tickers()
        if args.offset > 0:
            tickers = tickers[args.offset:]
        if args.limit > 0:
            tickers = tickers[:args.limit]

    print(f"[us_market_caps] universe size={len(tickers)}", file=sys.stderr)

    merged: Dict[str, float] = load_existing()
    ok = 0
    fail = 0
    for i, tk in enumerate(tickers, 1):
        mc = fetch_market_cap(tk)
        if mc is not None:
            merged[tk] = mc
            ok += 1
            if i % 100 == 0 or i == len(tickers):
                print(f"  [{i}/{len(tickers)}] {tk} ${mc/1e9:.2f}B (ok={ok} fail={fail})",
                      file=sys.stderr, flush=True)
        else:
            fail += 1
            print(f"  [{i}/{len(tickers)}] {tk}: market_cap 부재/실패 "
                  f"({'기존값 보존' if tk in merged else '결손'})", file=sys.stderr)

    payload = {
        "schema_version": "v0",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "count": len(merged),
        "source": "yfinance.fast_info.market_cap",
        "market_caps": dict(sorted(merged.items())),
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    rl = get_state_snapshot().get("rate_limit_count", 0)
    # logged=True — [[feedback_data_collection_verification_mandatory]]
    print(f"[us_market_caps] logged=True · this_run ok={ok} fail={fail} · "
          f"total stored={len(merged)} · rate_limited={rl} -> {OUTPUT_PATH.name}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
