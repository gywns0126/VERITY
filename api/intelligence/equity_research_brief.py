"""
Perplexity Sonar 기반 US 종목 equity research brief 자동 생성.

Sonar Pro + search_mode='sec' + finance domain filter 활용. Institutional-grade
brief 를 ticker 별 JSON 으로 저장.

Plumbing:
  - Input: data/universe_candidates.json 의 US15
  - Output: data/equity_research/<TICKER>.json
  - Cron: .github/workflows/equity_research_brief.yml (주 1회, 월요일 KST 06:00)
  - Brain v6 input source 후보 (현재는 산출물 박는 단계)

Cost guard:
  - 종목당 ~$0.05-0.20 추정 (sonar-pro)
  - US15 = 주당 ~$0.75-3 = 월 ~$3-12
  - 호출 실패 시 silent skip (cached 그대로 유지). budget overrun 방지

Memory: project_sentiment_13source_design / feedback_perplexity_collaboration
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from api.clients.perplexity_client import call_perplexity, get_session_stats  # noqa: E402

KST = timezone(timedelta(hours=9))
DATA_DIR = REPO_ROOT / "data"
UNIVERSE_PATH = DATA_DIR / "universe_candidates.json"
OUTPUT_DIR = DATA_DIR / "equity_research"

# Finance brief domain whitelist — SEC + IR + 주요 미장 금융 미디어.
# 사용자 의도된 모범 source 만 — 잡음 (블로그/포럼) 차단.
_FINANCE_DOMAINS = [
    "sec.gov",
    "investor.relations",
    "seekingalpha.com",
    "wsj.com",
    "bloomberg.com",
    "reuters.com",
    "ft.com",
    "cnbc.com",
    "marketwatch.com",
    "barrons.com",
]

_SYSTEM_PROMPT = """You are an institutional equity research analyst. Generate a concise, fact-based research brief for the given US public company. Use ONLY information from SEC filings, IR pages, and reputable financial media (Bloomberg, WSJ, Reuters, FT, CNBC, Barron's, SeekingAlpha). Cite every fact. Output STRICT JSON matching the requested schema — no markdown, no prose outside the JSON object."""


def _query_template(ticker: str) -> str:
    return f"""Generate an institutional equity research brief for ticker **{ticker}** (US listed). Cover:

1. **company_summary** (2-3 sentences): business model + segment mix
2. **thesis** (3-5 bullet sentences): current bull/bear consensus
3. **recent_catalysts** (3-5 items with date): material events past 60 days
4. **earnings_highlights**: most recent quarter EPS actual vs estimate, revenue actual vs estimate, FY guidance update if any
5. **sec_filings_recent** (3-5 items): 8-K / 10-Q / 10-K / proxy filings past 60 days with topic
6. **analyst_consensus**: avg price target (12-month), rating distribution (buy/hold/sell), consensus EPS FY+1
7. **risks** (3-5 bullets): downside catalysts, regulatory, competitive, macro
8. **brief_verdict**: STRONG_BUY / BUY / HOLD / AVOID / STRONG_AVOID — single label based on above

Output STRICT JSON (no markdown wrappers):
{{
  "ticker": "{ticker}",
  "company_summary": "...",
  "thesis": ["...", "..."],
  "recent_catalysts": [{{"date": "YYYY-MM-DD", "event": "..."}}],
  "earnings_highlights": {{
    "last_quarter": {{"period": "FYxQy", "eps_actual": 0.0, "eps_estimate": 0.0, "revenue_actual_m": 0, "revenue_estimate_m": 0}},
    "fy_guidance_update": "..."
  }},
  "sec_filings_recent": [{{"date": "YYYY-MM-DD", "form": "8-K", "topic": "..."}}],
  "analyst_consensus": {{"price_target_avg": 0.0, "rating": {{"buy": 0, "hold": 0, "sell": 0}}, "eps_fy1_estimate": 0.0}},
  "risks": ["...", "..."],
  "brief_verdict": "BUY"
}}"""


def _parse_brief_json(content: str, ticker: str) -> Optional[Dict[str, Any]]:
    """LLM response 에서 JSON 객체 추출. markdown wrapper / 잡음 제거."""
    content = content.strip()
    # ```json ... ``` wrapper 제거
    if content.startswith("```"):
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines)
    # 첫 { 부터 마지막 } 까지
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end < 0 or end < start:
        return None
    try:
        obj = json.loads(content[start:end + 1])
        if obj.get("ticker", "").upper() != ticker.upper():
            obj["ticker"] = ticker
        return obj
    except json.JSONDecodeError as e:
        print(f"[brief] {ticker} JSON parse error: {e}", file=sys.stderr)
        return None


def generate_brief(ticker: str) -> Dict[str, Any]:
    """단일 ticker brief 생성. 실패 시 _error 필드 포함 dict 반환."""
    print(f"  ▶ {ticker} brief 생성 중…", file=sys.stderr)
    res = call_perplexity(
        query=_query_template(ticker),
        system_prompt=_SYSTEM_PROMPT,
        max_tokens=4000,
        temperature=0.1,
        model="sonar-pro",
        search_mode="sec",  # SEC filings 우선
        search_domain_filter=_FINANCE_DOMAINS,
        search_recency_filter="month",
    )

    if "error" in res:
        return {
            "ticker": ticker,
            "_error": res["error"],
            "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        }

    content = res.get("content", "")
    brief = _parse_brief_json(content, ticker)
    if not brief:
        return {
            "ticker": ticker,
            "_error": "brief JSON parse failed",
            "_raw_preview": content[:500],
            "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        }

    brief["generated_at"] = datetime.now(KST).isoformat(timespec="seconds")
    brief["model"] = res.get("model", "")
    usage = res.get("usage", {})
    cost_obj = usage.get("cost", {})
    if isinstance(cost_obj, dict):
        brief["cost_usd"] = round(cost_obj.get("total_cost", 0), 4)
    else:
        brief["cost_usd"] = float(cost_obj) if isinstance(cost_obj, (int, float)) else 0.0
    brief["citations"] = res.get("citations", [])[:20]
    return brief


def load_us_tickers() -> List[str]:
    """universe_candidates.json 에서 US15 추출."""
    if not UNIVERSE_PATH.exists():
        print(f"[brief] {UNIVERSE_PATH} 없음. dry-run 모드로 SPY 만 처리.", file=sys.stderr)
        return ["SPY"]
    try:
        u = json.loads(UNIVERSE_PATH.read_text())
        candidates = u.get("candidates", [])
        us = [
            c.get("ticker", "").upper()
            for c in candidates
            if c.get("market", "").upper() in ("US", "NASDAQ", "NYSE", "NYS")
        ]
        return [t for t in us if t]
    except Exception as e:
        print(f"[brief] universe load 실패: {e}", file=sys.stderr)
        return []


def main() -> int:
    ap = argparse.ArgumentParser(description="Perplexity equity research brief generator")
    ap.add_argument("--ticker", help="단일 ticker 만 (dry-run / manual test)")
    ap.add_argument("--limit", type=int, default=20, help="최대 종목 수 (cost cap)")
    ap.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = ap.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        tickers = load_us_tickers()[: args.limit]

    print(f"[brief] 대상 {len(tickers)} 종목: {', '.join(tickers)}", file=sys.stderr)

    results = {"generated_at": datetime.now(KST).isoformat(timespec="seconds"), "briefs": []}
    for t in tickers:
        brief = generate_brief(t)
        out_path = output_dir / f"{t}.json"
        out_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2))
        results["briefs"].append({
            "ticker": t,
            "ok": "_error" not in brief,
            "cost_usd": brief.get("cost_usd", 0),
            "verdict": brief.get("brief_verdict", ""),
            "path": str(out_path.relative_to(REPO_ROOT)),
        })
        print(f"  ✓ {t} → {out_path.name} ({brief.get('brief_verdict', 'ERROR')}, ${brief.get('cost_usd', 0)})", file=sys.stderr)

    # Summary 박기
    summary_path = output_dir / "_summary.json"
    stats = get_session_stats()
    results["session_stats"] = stats
    summary_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))

    ok_count = sum(1 for b in results["briefs"] if b["ok"])
    print(f"[brief] 완료 — {ok_count}/{len(tickers)} 성공, ${stats['cost_usd']} 비용", file=sys.stderr)
    return 0 if ok_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
