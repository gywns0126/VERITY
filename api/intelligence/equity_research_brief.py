"""
Perplexity Sonar 기반 US 종목 equity research brief 자동 생성.

Sonar Pro + search_mode='sec' + finance domain filter 활용. Institutional-grade
brief 를 ticker 별 JSON 으로 저장.

Plumbing:
  - Input: data/universe_candidates.json 의 US15
  - Output: data/equity_research/<TICKER>.json
  - Cron: .github/workflows/equity_research_brief.yml (주 1회, 월요일 KST 06:00)
  - Brain v6 input source 후보 (현재는 산출물 생성 단계)

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
PORTFOLIO_PATH = DATA_DIR / "portfolio.json"  # 2026-05-17 verity_trail source
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

_SYSTEM_PROMPT = """You are an institutional equity research analyst writing for a Korean professional investor. Generate a concise, fact-based research brief for the given US public company. Use ONLY information from SEC filings, IR pages, and reputable financial media (Bloomberg, WSJ, Reuters, FT, CNBC, Barron's, SeekingAlpha). Cite every fact. Output STRICT JSON matching the requested schema — no markdown, no prose outside the JSON object.

LANGUAGE RULE — IMPORTANT:
- All JSON KEYS must remain in English exactly as specified in the schema (e.g. company_summary, thesis, recent_catalysts, risks, brief_verdict, industry_themes, theme, direction, conviction, evidence, event, topic, form, period, fy_guidance_update).
- All free-text VALUES must be written in natural KOREAN (한국어) — company_summary, thesis bullets, recent_catalysts.event, sec_filings_recent.topic, risks bullets, earnings_highlights.fy_guidance_update, industry_themes.theme & evidence.
- ENUM values stay English/numeric exactly as listed: brief_verdict (STRONG_BUY|BUY|HOLD|AVOID|STRONG_AVOID), direction (positive|negative|neutral), conviction (high|mid|low), form (8-K|10-Q|10-K|proxy), date (YYYY-MM-DD), and all numbers.
- Ticker symbols, company names, product names, and metric units may stay in their original form within Korean sentences (e.g. "Salesforce 의 Data Cloud 매출이 전년比 22% 성장").
- Tone: 한국 기관 리서치 보고서 (간결, 사실 중심, 존댓말 X — '~함/~임/~했다' 체)."""


def _query_template(ticker: str) -> str:
    return f"""Generate an institutional equity research brief for ticker **{ticker}** (US listed). All free-text values must be in Korean (한국어). Cover:

1. **company_summary** (2-3 한국어 문장): business model + segment mix
2. **thesis** (3-5 한국어 bullet 문장): current bull/bear consensus
3. **recent_catalysts** (3-5 items with date): material events past 60 days — event 값은 한국어 서술
4. **earnings_highlights**: most recent quarter EPS actual vs estimate, revenue actual vs estimate, FY guidance update (fy_guidance_update 값은 한국어)
5. **sec_filings_recent** (3-5 items): 8-K / 10-Q / 10-K / proxy filings past 60 days — topic 값은 한국어 요약
6. **risks** (3-5 bullets, 한국어): downside catalysts, regulatory, competitive, macro
7. **brief_verdict**: STRONG_BUY / BUY / HOLD / AVOID / STRONG_AVOID — single English label based on above
8. **industry_themes** (3-5 items): industry/macro themes mentioned in latest earnings call or guidance — NOT company-specific.
   theme = 한국어 짧은 라벨 (1-6자), direction/conviction = 영어 enum, evidence = 한국어 1문장 (가능하면 컨콜/가이던스 인용).
   예: "AI 투자" / "재고 조정" / "환율 역풍" / "인건비 인플레" / "관세 영향" / "소비 둔화".

(analyst_consensus 는 별도 호출에서 채워짐 — 본 query 에서는 omit)

Output STRICT JSON schema (no markdown wrappers, no example values copied — fill from real sources). KEYS in English, free-text VALUES in Korean:
{{
  "ticker": "{ticker}",
  "company_summary": "<2-3 한국어 문장>",
  "thesis": ["<한국어 bullet>", "..."],
  "recent_catalysts": [{{"date": "YYYY-MM-DD", "event": "<한국어 서술>"}}],
  "earnings_highlights": {{
    "last_quarter": {{"period": "<FYxQy>", "eps_actual": <num>, "eps_estimate": <num>, "revenue_actual_m": <num>, "revenue_estimate_m": <num>}},
    "fy_guidance_update": "<한국어 요약>"
  }},
  "sec_filings_recent": [{{"date": "YYYY-MM-DD", "form": "<8-K|10-Q|10-K|proxy>", "topic": "<한국어 요약>"}}],
  "risks": ["<한국어 bullet>", "..."],
  "brief_verdict": "<STRONG_BUY|BUY|HOLD|AVOID|STRONG_AVOID>",
  "industry_themes": [
    {{"theme": "<한국어 라벨>", "direction": "<positive|negative|neutral>", "conviction": "<high|mid|low>", "evidence": "<한국어 1문장>"}}
  ]
}}"""


def fetch_verity_trail(ticker: str) -> Dict[str, Any]:
    """portfolio.json 의 recommendations 에서 ticker 매치 → VERITY 자체 trail 추출.

    2026-05-17 빅브라더 정합 발견으로 추가 ([[feedback_no_new_llm_narrative_features]]).
    Perplexity narrative = LLM 우위 (사용자가 Pro 가입 후 직접 묻는 게 더 좋음).
    VERITY 의 진짜 차별점 = 1년 운영 trail + 자체 산식 (Brain v5 가중치 / Lynch 룰 /
    VCI / red_flags / position_guide) — LLM 가입자 못 가짐.

    EquityBriefCard 사용자에게 "VERITY 관점" 노출 → unique view 가치.

    Returns dict (success) 또는 {"_error": str} (fail).
    """
    if not PORTFOLIO_PATH.exists():
        return {"_error": "portfolio.json 부재 (run main.py first)"}
    try:
        pdata = json.loads(PORTFOLIO_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return {"_error": f"portfolio.json parse: {e}"}

    recs = pdata.get("recommendations") or []
    rec = next((r for r in recs if (r.get("ticker") or "").upper() == ticker.upper()), None)
    if not rec:
        return {"_error": f"{ticker} not in current US15 universe"}

    vb = rec.get("verity_brain") or {}
    lynch = rec.get("lynch_kr") or {}
    vams = pdata.get("vams") or {}
    holdings = vams.get("holdings") or []
    holding = next((h for h in holdings if (h.get("ticker") or "").upper() == ticker.upper()), None)

    # 자체 trail dict — LLM 가입자 가질 수 없는 unique data
    trail = {
        "_source": "VERITY own metrics (Brain v5 + Lynch + VAMS) — NOT from external LLM",
        "_doc": "1년 운영 trail + 자체 산식. LLM 무료/유료 가입자도 못 가짐 (자기 자본 진화 + 자기 universe + 자기 cron 자동화).",
        # Brain v5 자체 결정 (가중치 7:3 / 등급 75-60-45-30 / VCI 임계 / GS bonus)
        "brain_score": vb.get("brain_score"),
        "brain_score_raw": rec.get("raw_brain_score"),
        "grade": vb.get("grade"),
        "grade_label": vb.get("grade_label"),
        "grade_confidence": vb.get("grade_confidence"),
        "fact_score": (vb.get("fact_score") or {}).get("score"),
        "sentiment_score": (vb.get("sentiment_score") or {}).get("score"),
        # VCI (팩트-심리 정렬 신호)
        "vci_value": (vb.get("vci") or {}).get("vci"),
        "vci_signal": (vb.get("vci") or {}).get("signal"),
        "vci_label": (vb.get("vci") or {}).get("label"),
        # Red flags (Lynch 절대 매도 / Graham 기준 위반 등)
        "red_flags_auto_avoid": (vb.get("red_flags") or {}).get("auto_avoid") or [],
        "red_flags_downgrade": (vb.get("red_flags") or {}).get("downgrade") or [],
        "has_critical": (vb.get("red_flags") or {}).get("has_critical", False),
        # Lynch 6 카테고리 (자체 룰 매핑)
        "lynch_class": lynch.get("class"),
        "lynch_label": lynch.get("label"),
        "lynch_summary": lynch.get("summary"),
        # Position guide (Kelly + max_pct 자체 산식)
        "recommended_position_pct": (vb.get("position_guide") or {}).get("recommended_pct"),
        "position_rationale": (vb.get("position_guide") or {}).get("rationale"),
        # 자체 reasoning (1줄 narrative — LLM call 없음, 룰 기반 합성)
        "reasoning": vb.get("reasoning"),
        # VAMS 보유 상태 (현재 + 과거)
        "vams_holding_status": "holding" if holding else "not_held",
        "vams_holding_qty": (holding or {}).get("qty"),
        "vams_holding_entry_price": (holding or {}).get("entry_price"),
        "vams_holding_pnl_pct": (holding or {}).get("pnl_pct"),
        "vams_holding_days": (holding or {}).get("holding_days"),
        # 자체 universe stage (funnel 1-4 미구현 — 현재 5000→25 직접 압축)
        "universe_stage": "final_25",  # Phase 2-D 후 정합
        "trail_collected_at": datetime.now(KST).isoformat(timespec="seconds"),
    }
    return trail


def fetch_analyst_consensus(ticker: str) -> Dict[str, Any]:
    """yfinance.Ticker.info 에서 analyst consensus 추출.

    Perplexity Sonar 가 SeekingAlpha/Bloomberg 구독 wall 못 뚫어서 null 만 반환하던
    문제 (2026-05-16 실측). yfinance 가 free + Yahoo Finance 자체 analyst 데이터
    제공 (targetMeanPrice / numberOfAnalystOpinions / recommendationKey).

    Returns dict (success) 또는 {"_error": str} (fail).
    """
    try:
        import yfinance as yf
    except ImportError:
        return {"_error": "yfinance 미설치"}
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as e:
        return {"_error": f"yfinance fetch: {e}"}

    if not info:
        return {"_error": "yfinance info 비어있음"}

    # Yahoo recommendationKey: strong_buy / buy / hold / underperform / sell / none
    rec_key = info.get("recommendationKey", "none")
    rec_mean = info.get("recommendationMean")  # 1.0=strong_buy ~ 5.0=sell

    return {
        "price_target_avg": info.get("targetMeanPrice"),
        "price_target_high": info.get("targetHighPrice"),
        "price_target_low": info.get("targetLowPrice"),
        "price_target_median": info.get("targetMedianPrice"),
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "n_analysts": info.get("numberOfAnalystOpinions"),
        "recommendation_key": rec_key,
        "recommendation_mean": rec_mean,
        "eps_fy1_estimate": info.get("forwardEps"),
        "pe_forward": info.get("forwardPE"),
        "_source": "yfinance (Yahoo Finance)",
    }


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
    """단일 ticker brief 생성. 실패 시 _error 필드 포함 dict 반환.

    2026-05-16 B 옵션 fix: search_mode='sec' 제거 → default 'web'.
    SEC 만 우선 시 analyst_consensus null 빔. domain filter (Bloomberg/Reuters/seekingalpha)
    가중으로 SEC + analyst 동시 fetch.
    """
    print(f"  ▶ {ticker} brief 생성 중…", file=sys.stderr)
    res = call_perplexity(
        query=_query_template(ticker),
        system_prompt=_SYSTEM_PROMPT,
        max_tokens=4000,
        temperature=0.1,
        model="sonar-pro",
        # search_mode 제거 (default 'web') — analyst_consensus 채움 위해
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
        brief_cost = round(cost_obj.get("total_cost", 0), 4)
    else:
        brief_cost = float(cost_obj) if isinstance(cost_obj, (int, float)) else 0.0
    brief["citations"] = res.get("citations", [])[:20]

    # yfinance 로 analyst_consensus (free, no hallucination, Sonar 구독 wall 우회)
    print(f"  ▶ {ticker} analyst consensus (yfinance)…", file=sys.stderr)
    brief["analyst_consensus"] = fetch_analyst_consensus(ticker)

    # 2026-05-17 빅브라더 정합 — VERITY 자체 trail (Brain v5 + Lynch + VAMS) 첨부.
    # LLM 가입자가 못 가지는 unique view. EquityBriefCard 가 "VERITY 관점" 섹션으로 노출.
    # 메모리 [[feedback_no_new_llm_narrative_features]] + [[feedback_pm_decision_trail_in_commit]] 정합.
    print(f"  ▶ {ticker} VERITY trail attach…", file=sys.stderr)
    brief["verity_trail"] = fetch_verity_trail(ticker)
    brief["cost_usd"] = brief_cost  # yfinance + portfolio.json fetch = free (자체 데이터)
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
