"""macro_themes_brief — IB strategist 매크로 themes weekly 추출 (Perplexity Sonar Pro).

PM 직관 (사용자, 5/20): 테크 애널리스트가 매크로 데이터 + 매크로 애널리스트 자료를 통해 매크로/산업 측면 봄.
→ Top-down 정공법: Macro → Industry → Stock filter.
→ A 옵션 (Macro layer) 즉시 진입 ([[project_macro_themes_tracker]]).

Industry Themes Tracker (5/20 추가됨) 와 차별:
  - Industry Themes: 15 brief × earnings call themes = cross-ticker frequency
  - Macro Themes (본 모듈): 1 weekly Perplexity call × IB strategist views = snapshot
    + 시계열 누적 (향후 v0.1 aggregator 에서 weekly recurrence 산출)

비용: ~$0.10-0.20/주 × 52주 = ~$5-10/년 (negligible).

RULE 6 정합 ([[feedback_no_new_llm_narrative_features]]): metric/category/direction
산출 only — narrative 결과 X. 1년 누적 trail = LLM 가입자 못 가지는 unique data.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))  # noqa: E402

from api.clients.perplexity_client import call_perplexity  # noqa: E402

KST = timezone(timedelta(hours=9))
DATA_DIR = REPO_ROOT / "data"
OUTPUT_PATH = DATA_DIR / "macro_themes_pulse.json"
HISTORY_PATH = DATA_DIR / "macro_themes_history.jsonl"

_logger = logging.getLogger(__name__)

_FINANCE_DOMAINS = [
    "bloomberg.com",
    "wsj.com",
    "reuters.com",
    "ft.com",
    "cnbc.com",
    "barrons.com",
    "marketwatch.com",
    "federalreserve.gov",
    "bok.or.kr",
]

VALID_CATEGORIES = (
    "policy", "growth", "inflation", "labor",
    "fx", "credit", "geopolitical", "sector_rotation",
)

DIRECTION_SCORE = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
CONVICTION_WEIGHT = {"high": 1.0, "mid": 0.6, "low": 0.3}

# Verdict 임계 (v0 가설, RULE 7 — PM 1회 사전 승인).
# 가중 평균 sign 으로 분류. N≥30 (~7개월) 후 walk-forward 조정.
VERDICT_BULLISH_THRESHOLD = 0.30
VERDICT_BEARISH_THRESHOLD = -0.30

_SYSTEM_PROMPT = """You are an institutional macro strategist. Summarize the dominant macro themes of the current week from major IB strategists (Goldman Sachs, Morgan Stanley, JPMorgan, BofA, Citi, UBS, Barclays, Deutsche Bank) and central bank watchers (Fed, BOK, ECB, BOJ). Use ONLY information from Bloomberg, WSJ, Reuters, FT, CNBC, Barron's, MarketWatch, federalreserve.gov, bok.or.kr. Cite analyst/bank names. Output STRICT JSON matching the requested schema — no markdown, no prose outside the JSON object."""


def _query_template() -> str:
    return f"""Identify the **top 5-10 macro themes** dominating IB strategist / Fed-watcher commentary THIS WEEK. Each theme must be:
  - industry/sector-agnostic (NOT company-specific)
  - sourced from major IB strategist views or central bank speak
  - actionable (asset allocation / sector rotation / risk-on/off implication)

Categories (pick exactly one per theme):
  - policy        (Fed/BOK/ECB/BOJ rate path, QT/QE)
  - growth        (GDP, PMI, recession risk)
  - inflation     (CPI/PCE/wage, supply vs demand inflation)
  - labor         (employment, JOLTS, wages)
  - fx            (DXY, USDKRW, JPY carry)
  - credit        (HY/IG spreads, default risk)
  - geopolitical  (China/Taiwan/Russia/Middle East/tariff)
  - sector_rotation (cyclicals vs defensives, growth vs value)

For each theme provide:
  - direction: positive (risk-on) | negative (risk-off) | neutral
  - conviction: high | mid | low
  - evidence: ONE short sentence quoting analyst/bank (mention name)
  - sources: list of analyst/bank names (1-3)

Output STRICT JSON schema:
{{
  "themes": [
    {{
      "theme": "<short label, 2-6 words>",
      "category": "<one of: policy|growth|inflation|labor|fx|credit|geopolitical|sector_rotation>",
      "direction": "<positive|negative|neutral>",
      "conviction": "<high|mid|low>",
      "evidence": "<one short sentence with analyst/bank name>",
      "sources": ["<analyst or IB name>", "..."]
    }}
  ]
}}"""


def _parse_brief_json(content: str) -> Optional[Dict[str, Any]]:
    """LLM response → JSON 객체. markdown wrapper 제거 + 첫{~마지막} 추출."""
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines)
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end < 0 or end < start:
        return None
    try:
        return json.loads(content[start:end + 1])
    except json.JSONDecodeError as e:
        print(f"[macro_themes] JSON parse error: {e}", file=sys.stderr)
        return None


def _validate_theme(t: Any) -> Optional[Dict[str, Any]]:
    """단일 theme dict 검증. invalid 면 None (silent drop)."""
    if not isinstance(t, dict):
        return None
    theme = (t.get("theme") or "").strip()
    if not theme or len(theme) > 80:
        return None
    category = (t.get("category") or "").strip().lower()
    if category not in VALID_CATEGORIES:
        category = "policy"  # fallback (loose validation — LLM 가끔 카테고리 오답)
    direction = (t.get("direction") or "").strip().lower()
    if direction not in DIRECTION_SCORE:
        direction = "neutral"
    conviction = (t.get("conviction") or "").strip().lower()
    if conviction not in CONVICTION_WEIGHT:
        conviction = "mid"
    evidence = (t.get("evidence") or "").strip()[:240]
    sources_raw = t.get("sources") or []
    sources = [str(s).strip()[:40] for s in sources_raw if str(s).strip()][:5]
    return {
        "theme": theme[:80],
        "category": category,
        "direction": direction,
        "conviction": conviction,
        "evidence": evidence,
        "sources": sources,
    }


def compute_macro_verdict(themes: List[Dict[str, Any]]) -> str:
    """direction × conviction weight → 가중 평균 sign → verdict.

    risk-on / risk-off framework. mixed = 양/음 themes 모두 강함.
    """
    if not themes:
        return "UNAVAILABLE"
    score_sum = 0.0
    weight_sum = 0.0
    pos_strong = neg_strong = 0
    for t in themes:
        d = DIRECTION_SCORE.get(t["direction"], 0.0)
        w = CONVICTION_WEIGHT.get(t["conviction"], CONVICTION_WEIGHT["mid"])
        score_sum += d * w
        weight_sum += w
        if t["direction"] == "positive" and t["conviction"] == "high":
            pos_strong += 1
        if t["direction"] == "negative" and t["conviction"] == "high":
            neg_strong += 1
    if weight_sum == 0:
        return "UNAVAILABLE"
    if pos_strong >= 2 and neg_strong >= 2:
        return "MIXED"
    avg = score_sum / weight_sum
    if avg >= VERDICT_BULLISH_THRESHOLD:
        return "BULLISH"
    if avg <= VERDICT_BEARISH_THRESHOLD:
        return "BEARISH"
    return "NEUTRAL"


def _iso_week_label(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def generate_brief() -> Dict[str, Any]:
    """단일 weekly Perplexity 호출 + parse + verdict.

    실패 시 _error 필드 포함 dict 반환 (cron 정상 종료, 다음 주 재시도).
    """
    now = datetime.now(KST)
    print("[macro_themes] Perplexity 호출 시작…", file=sys.stderr)
    res = call_perplexity(
        query=_query_template(),
        system_prompt=_SYSTEM_PROMPT,
        max_tokens=3000,
        temperature=0.1,
        model="sonar-pro",
        search_domain_filter=_FINANCE_DOMAINS,
        search_recency_filter="week",
    )

    base = {
        "schema_version": "v0.1",
        "generated_at": now.isoformat(timespec="seconds"),
        "week": _iso_week_label(now),
    }

    if "error" in res:
        return {**base, "_error": res["error"], "themes": [], "macro_verdict": "UNAVAILABLE"}

    content = res.get("content", "")
    parsed = _parse_brief_json(content)
    if not parsed or not isinstance(parsed.get("themes"), list):
        return {
            **base,
            "_error": "brief JSON parse failed",
            "_raw_preview": content[:500],
            "themes": [],
            "macro_verdict": "UNAVAILABLE",
        }

    themes_validated: List[Dict[str, Any]] = []
    for t in parsed["themes"]:
        v = _validate_theme(t)
        if v is not None:
            themes_validated.append(v)

    verdict = compute_macro_verdict(themes_validated)

    usage = res.get("usage", {})
    cost_obj = usage.get("cost", {})
    cost = (
        round(cost_obj.get("total_cost", 0), 4)
        if isinstance(cost_obj, dict)
        else float(cost_obj) if isinstance(cost_obj, (int, float)) else 0.0
    )

    return {
        **base,
        "macro_verdict": verdict,
        "themes": themes_validated,
        "model": res.get("model", "sonar-pro"),
        "citations": res.get("citations", [])[:20],
        "cost_usd": cost,
    }


def _append_history(brief: Dict[str, Any], path: Path = HISTORY_PATH) -> None:
    """매 weekly snapshot 을 jsonl 에 append. v0.1 aggregator 의 입력.

    silent — 실패해도 운영 영향 X (cron 정상 종료).
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(brief, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[macro_themes] history append failed: {e}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="실제 Perplexity 호출 없이 schema/parser 만 smoke test")
    args = parser.parse_args()

    if args.dry_run:
        print("[macro_themes] dry-run mode — Perplexity 호출 없이 schema 만 검증", file=sys.stderr)
        return 0

    brief = generate_brief()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _append_history(brief)

    if "_error" in brief:
        print(f"[macro_themes] FAILED: {brief['_error']}", file=sys.stderr)
        return 0  # cron 정상 종료 (다음 주 재시도)

    print(
        f"[macro_themes] verdict={brief['macro_verdict']} themes={len(brief['themes'])} "
        f"cost=${brief.get('cost_usd', 0):.3f}",
        file=sys.stderr,
    )
    for t in brief["themes"]:
        print(
            f"  · [{t['category']:18s}] {t['theme']:35s} {t['direction']:8s} ({t['conviction']})",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
