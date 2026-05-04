"""
EPS Estimate Snapshot Collector — Sprint 1 prep (2026-05-04~)

Purpose: revision_score 용 일일 EPS estimate snapshot 누적.
PIT historical 무료 source 부재 (Polygon/AV PIT snapshot 없음) → 자체 누적이 유일.
B&T 1989 RW 기대모형은 PEAD/Surprise 만 cover, revision 은 별도 누적 필요.

Output: data/metadata/eps_estimates.jsonl (line append, invalidate flag 지원)

NOTE:
  - 본 모듈은 fact_score 호출 0. Phase 0 단일 변수 통제 영향 없음.
  - revision_score 산출 로직은 본 모듈에 없음 — Sprint 1 본 진입(5/16 후)에서 계산.
  - cron 등록은 별도 작업. 본 모듈은 manual 또는 GitHub Actions 에서 호출.

Manual run:
    python -m api.collectors.eps_estimate_snapshot
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import yfinance as yf

OUTPUT_PATH = Path("data/metadata/eps_estimates.jsonl")
SOURCE = "yfinance"


def _df_to_dict(df) -> dict:
    """yfinance DataFrame → JSON-safe dict. None / NaN 은 누락."""
    if df is None:
        return {}
    try:
        if hasattr(df, "empty") and df.empty:
            return {}
        records = df.to_dict(orient="index")
        out = {}
        for period, row in records.items():
            clean = {}
            for k, v in row.items():
                if v is None:
                    continue
                try:
                    if v != v:  # NaN
                        continue
                except Exception:
                    pass
                if isinstance(v, (int, float, str, bool)):
                    clean[str(k)] = v
                else:
                    clean[str(k)] = str(v)
            if clean:
                out[str(period)] = clean
        return out
    except Exception:
        return {}


def fetch_one(ticker: str) -> Optional[dict]:
    """단일 ticker 의 EPS estimate snapshot 1건 산출. 실패 시 None."""
    try:
        t = yf.Ticker(ticker)
        eps_trend = _df_to_dict(getattr(t, "eps_trend", None))
        earnings_estimate = _df_to_dict(getattr(t, "earnings_estimate", None))

        if not eps_trend and not earnings_estimate:
            return None

        return {
            "eps_trend": eps_trend,
            "earnings_estimate": earnings_estimate,
        }
    except Exception:
        return None


def _load_universe(explicit: Optional[Iterable[str]] = None) -> list[str]:
    if explicit:
        return list(explicit)
    from api.collectors.stock_data import US_MAJOR
    return list(US_MAJOR)


def run_snapshot(
    tickers: Optional[Iterable[str]] = None,
    output_path: Path = OUTPUT_PATH,
) -> dict:
    """
    Daily snapshot 1회 실행. 각 ticker 1 line append.
    Returns: {"date": ..., "n_total": ..., "n_ok": ..., "n_fail": ..., "failed": [...]}
    """
    universe = _load_universe(tickers)
    now = datetime.now(timezone.utc)
    snapshot_date = now.date().isoformat()
    snapshot_ts = now.isoformat(timespec="seconds")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    n_ok = 0
    n_fail = 0
    failed: list[str] = []

    with output_path.open("a", encoding="utf-8") as f:
        for ticker in universe:
            payload = fetch_one(ticker)
            if payload is None:
                n_fail += 1
                failed.append(ticker)
                continue
            line = {
                "snapshot_date": snapshot_date,
                "snapshot_ts": snapshot_ts,
                "ticker": ticker,
                "source": SOURCE,
                **payload,
                "invalidate": False,
            }
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
            n_ok += 1

    return {
        "date": snapshot_date,
        "n_total": len(universe),
        "n_ok": n_ok,
        "n_fail": n_fail,
        "failed": failed,
        "output": str(output_path),
    }


if __name__ == "__main__":
    result = run_snapshot()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["n_ok"] > 0 else 1)
