"""build_us_universe_cache — sp1500 yfinance 1패스 → US 유니버스 캐시 + 시총맵.

2026-06-23 — 국장 parity. universe_scan 의 US 소스가 ~150 static fallback 이던 것을
  sp1500 1500 으로 확대([[project_us_financials_sec_edgar]] / [[feedback_us_expansion_settled_no_relitigate]]).
  universe_builder._load_us_static_cache 가 읽는 data/cache/universe_us.json = "weekly refresh 캐시"
  (코드가 의도했으나 생성기 부재로 deferred 였던 것) 를 본 스크립트가 생성.

fast_info 1패스로 per-ticker 수집 → 두 산출(중복 fetch 회피):
  - data/us_market_caps.json        : {ticker: market_cap}  (Lynch/원본 Altman, us_financials_builder 소비)
  - data/cache/universe_us.json     : [universe entries]     (hard_floor 통과용 market_cap + avg_trading_value_30d)

avg_trading_value_30d = threeMonthAverageVolume × lastPrice (USD/일). hard_floor US $10M floor 판정용.
yfinance_safe(429 backoff+cooler) + 멱등 merge(실패 종목 기존값 보존). 월 1회(us_financials.yml).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))  # noqa: E402

from api.collectors.yfinance_safe import yf_ticker, safe_yf_call, get_state_snapshot  # noqa: E402

KST = timezone(timedelta(hours=9))
SP1500_PATH = REPO_ROOT / "data" / "us_universe_sp1500.json"
MCAP_PATH = REPO_ROOT / "data" / "us_market_caps.json"
CACHE_PATH = REPO_ROOT / "data" / "cache" / "universe_us.json"

DEFAULT_US15 = [
    "MSFT", "JNJ", "BAC", "ADBE", "CRM", "JPM", "DIS", "SOFI",
    "QCOM", "META", "BRK-B", "TMO", "PG", "XOM", "CSCO",
]


def _now_kst() -> datetime:
    return datetime.now(KST)


def _f(v) -> Optional[float]:
    try:
        x = float(v)
        return x if (x == x and x > 0) else None
    except (TypeError, ValueError):
        return None


def load_sp1500_tickers() -> List[str]:
    if not SP1500_PATH.exists():
        print("[us_universe] us_universe_sp1500.json 부재 — US15 fallback", file=sys.stderr)
        return list(DEFAULT_US15)
    try:
        d = json.loads(SP1500_PATH.read_text(encoding="utf-8"))
        out = [str(t).strip().upper() for t in (d.get("tickers") or []) if str(t).strip()]
        return out or list(DEFAULT_US15)
    except Exception as e:  # noqa: BLE001
        print(f"[us_universe] sp1500 parse 실패: {e!r} — US15 fallback", file=sys.stderr)
        return list(DEFAULT_US15)


def _load_existing_records() -> Dict[str, Dict[str, Any]]:
    """직전 universe_us.json → {ticker: {market_cap, avg_trading_value_30d}} (멱등 merge 베이스)."""
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        out = {}
        for e in (data if isinstance(data, list) else []):
            tk = str(e.get("ticker") or "").upper()
            if tk:
                out[tk] = {"market_cap": e.get("market_cap") or 0,
                           "avg_trading_value_30d": e.get("avg_trading_value_30d") or 0}
        return out
    except Exception:  # noqa: BLE001
        return {}


def fetch_record(ticker: str) -> Optional[Dict[str, float]]:
    """fast_info → {market_cap, adv}. 실패=None."""
    def _call():
        fi = yf_ticker(ticker).fast_info
        mc = getattr(fi, "market_cap", None)
        if mc is None:
            try:
                mc = fi["marketCap"]
            except (KeyError, TypeError):
                mc = None
        # 거래대금 = 3개월 평균 거래량 × 현재가 (USD/일)
        vol = getattr(fi, "three_month_average_volume", None)
        if vol is None:
            try:
                vol = fi["threeMonthAverageVolume"]
            except (KeyError, TypeError):
                vol = None
        px = getattr(fi, "last_price", None)
        if px is None:
            try:
                px = fi["lastPrice"]
            except (KeyError, TypeError):
                px = None
        mc_v = _f(mc)
        if mc_v is None:
            return None
        adv = 0.0
        vv, pv = _f(vol), _f(px)
        if vv and pv:
            adv = vv * pv
        return {"market_cap": mc_v, "adv": adv}

    try:
        return safe_yf_call(_call, label=ticker, per_call_sleep_s=0.05)
    except Exception as e:  # noqa: BLE001
        print(f"[us_universe] {ticker} fetch 실패: {e!r}", file=sys.stderr)
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--ticker")
    args = parser.parse_args()

    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = load_sp1500_tickers()
        if args.offset > 0:
            tickers = tickers[args.offset:]
        if args.limit > 0:
            tickers = tickers[:args.limit]

    print(f"[us_universe] universe size={len(tickers)}", file=sys.stderr)

    # 멱등 merge 베이스 (실패 종목 기존값 보존)
    prev = _load_existing_records()
    records: Dict[str, Dict[str, float]] = {
        tk: {"market_cap": float(r.get("market_cap") or 0), "adv": float(r.get("avg_trading_value_30d") or 0)}
        for tk, r in prev.items()
    }

    ok = fail = 0
    for i, tk in enumerate(tickers, 1):
        rec = fetch_record(tk)
        if rec is not None:
            records[tk] = rec
            ok += 1
            if i % 100 == 0 or i == len(tickers):
                print(f"  [{i}/{len(tickers)}] {tk} ${rec['market_cap']/1e9:.1f}B ADV${rec['adv']/1e6:.0f}M (ok={ok} fail={fail})",
                      file=sys.stderr, flush=True)
        else:
            fail += 1

    # us_core (코어 화이트리스트 — 항상 포함)
    try:
        from api.collectors.universe_builder import _load_core_pools
        _, us_core = _load_core_pools()
    except Exception:  # noqa: BLE001
        us_core = set()

    # 산출 1 — us_market_caps.json (Lynch)
    mcaps = {tk: r["market_cap"] for tk, r in records.items() if r.get("market_cap")}
    MCAP_PATH.write_text(json.dumps({
        "schema_version": "v0", "generated_at": _now_kst().isoformat(timespec="seconds"),
        "count": len(mcaps), "source": "yfinance.fast_info.market_cap",
        "market_caps": dict(sorted(mcaps.items())),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # 산출 2 — data/cache/universe_us.json (universe entries, hard_floor 통과용)
    entries: List[Dict[str, Any]] = []
    for tk in sorted(records.keys()):
        r = records[tk]
        entries.append({
            "ticker": tk, "name": tk, "market": "US", "currency": "USD",
            "market_cap": int(r.get("market_cap") or 0),
            "avg_trading_value_30d": int(r.get("adv") or 0),
            "is_core": tk in us_core, "is_managed": False, "is_suspended": False,
            "tier": "core" if tk in us_core else "extended",
            "source": "sp1500_yf",
        })
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")

    rl = get_state_snapshot().get("rate_limit_count", 0)
    print(f"[us_universe] logged=True · this_run ok={ok} fail={fail} · entries={len(entries)} "
          f"mcaps={len(mcaps)} rate_limited={rl} -> us_market_caps.json + cache/universe_us.json",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
