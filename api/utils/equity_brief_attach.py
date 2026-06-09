"""
equity_brief_attach — US 종목 stock dict 에 equity_research_brief field 주입.

Brain v6 prep (2026-05-17). project_perplexity_equity_brief 정합:
- data/equity_research/<TICKER>.json (주 1회 cron, equity_research_brief.py)
- → stock dict 에 'equity_research_brief' field 부착
- → verity_brain._compute_fact_score 가 equity_brief_verdict component 산출
- → fact_score 에 가중치 0.03 (constitution.json) 반영

stale 처리:
- max_stale_days = 10 (주 1회 + 3일 마진)
- 그 이상이면 cache miss → component=50 neutral (component map 자동 처리)
- silent skip 절대 금지 (feedback_data_collection_verification_mandatory)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

KST = timezone(timedelta(hours=9))

REPO_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
EQUITY_RESEARCH_DIR = REPO_ROOT / "data" / "equity_research"


def load_equity_brief(
    ticker: str,
    *,
    max_stale_days: int = 10,
    base_dir: Optional[Path] = None,
) -> Optional[Dict[str, any]]:
    """단일 ticker brief json load. stale 시 None.

    brief json schema (api/intelligence/equity_research_brief.py):
        {ticker, company_summary, thesis, recent_catalysts, earnings_highlights,
         sec_filings_recent, analyst_consensus, risks, brief_verdict, generated_at,
         model, cost_usd, citations}
    """
    base = base_dir or EQUITY_RESEARCH_DIR
    path = base / f"{ticker.upper()}.json"
    if not path.exists():
        return None
    try:
        d = json.loads(path.read_text())
    except Exception as e:
        print(f"[equity_brief] {ticker} parse fail: {e}", file=sys.stderr)
        return None

    # stale check
    gen_at = d.get("generated_at", "")
    if gen_at:
        try:
            ts = datetime.fromisoformat(gen_at)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=KST)
            age = datetime.now(KST) - ts
            if age.days > max_stale_days:
                print(
                    f"[equity_brief] {ticker} stale {age.days}d (>{max_stale_days}d) — skip",
                    file=sys.stderr,
                )
                return None
        except Exception:
            pass

    # _error 설정되어 있으면 skip
    if d.get("_error"):
        return None

    return d


def attach_briefs_to_stocks(
    stocks: List[Dict[str, any]],
    *,
    max_stale_days: int = 10,
    base_dir: Optional[Path] = None,
) -> int:
    """stocks list 의 US 종목에 equity_research_brief field 주입.

    Returns: attached 개수 (silent skip 차단 — stderr 명시).
    """
    attached = 0
    us_total = 0
    for s in stocks:
        market = str(s.get("market", "")).upper()
        if market not in ("US", "NASDAQ", "NYSE", "NYS"):
            continue
        us_total += 1
        ticker = s.get("ticker", "")
        if not ticker:
            continue
        brief = load_equity_brief(ticker, max_stale_days=max_stale_days, base_dir=base_dir)
        if brief:
            s["equity_research_brief"] = brief
            attached += 1

    print(
        f"[equity_brief] attached={attached}/{us_total} (US only, max_stale={max_stale_days}d)",
        file=sys.stderr,
    )
    return attached


if __name__ == "__main__":
    # CLI: universe_candidates 의 US 종목 부착 dry-run
    import json as _json
    universe_path = REPO_ROOT / "data" / "universe_candidates.json"
    if not universe_path.exists():
        print("[equity_brief] universe_candidates.json 없음 — dry-run test 만")
        sample = [
            {"ticker": "CRM", "market": "NYSE"},
            {"ticker": "AAPL", "market": "NASDAQ"},
            {"ticker": "005930", "market": "KR"},
        ]
        attached = attach_briefs_to_stocks(sample)
        print(f"sample attached: {attached}")
        for s in sample:
            if "equity_research_brief" in s:
                b = s["equity_research_brief"]
                print(f"  {s['ticker']}: verdict={b.get('brief_verdict')}, score component")
    else:
        u = _json.loads(universe_path.read_text())
        candidates = u.get("candidates", [])
        attached = attach_briefs_to_stocks(candidates)
        print(f"universe US 부착: {attached}")
