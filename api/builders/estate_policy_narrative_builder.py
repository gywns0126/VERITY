"""
estate_policy_narrative_builder.py — ESTATE 주 1회 정책+시장 종합 narrative 빌더

PolicyPulse SECTION 4 ("WEEKLY BRIEF · 7D") 의 데이터 source.
Perplexity Sonar Pro + 한국 부동산 권위 도메인 whitelist 활용해서 지난 7일
한국 부동산 정책+시장 종합 narrative 를 weekly 로 생성.

equity_research_brief 패턴 그대로 이식 (api.intelligence.equity_research_brief),
다만 ticker 종목 단위 X → 시장 종합 단위.

Plumbing:
  - Output: data/estate_policy_narrative.json
  - Cron: .github/workflows/estate_policy_narrative.yml (주 1회, 월요일 KST 06:30)
  - Vercel endpoint: vercel-api/api/estate_policy_narrative.py read-through
  - PolicyPulse.tsx SECTION 4 가 consume

거짓말 트랩:
  T1·T9 silent fabricate X — 실패 시 _error 명시, 이전 JSON 유지 (return None)
  T2    mock fallback X — Perplexity 실패 시 silent skip, mock narrative 박지 않음
  T4    임의 상수 X — domain whitelist / verdict enum 모두 명시 명시 박음

Cost guard:
  - 1회 ~$0.04 (sonar-pro, US15 brief 와 동급)
  - 주 1회 × 4주 = ~$0.16/월
  - project_claude_budget_guard 외 budget (Perplexity track)

Memory: project_perplexity_equity_brief / feedback_perplexity_collaboration / feedback_estate_density_first
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from api.clients.perplexity_client import call_perplexity, get_session_stats  # noqa: E402

KST = timezone(timedelta(hours=9))
OUTPUT_PATH = REPO_ROOT / "data" / "estate_policy_narrative.json"

# 한국 부동산 권위 도메인 whitelist — 잡음(블로그/카페/유튜브) 차단.
# 정부·공기관·연구소·주요 경제지 + 부동산 정보 플랫폼 한정.
_KOREA_RE_DOMAINS = [
    # 정부 (정책 1차 source)
    "molit.go.kr",       # 국토교통부
    "moef.go.kr",        # 기획재정부
    "fsc.go.kr",         # 금융위원회
    "fss.or.kr",         # 금융감독원
    "nts.go.kr",         # 국세청
    # 공기관·중앙은행
    "bok.or.kr",         # 한국은행
    "reb.or.kr",         # 한국부동산원 (R-ONE)
    "krihs.re.kr",       # 국토연구원
    "kosis.kr",          # 통계청 KOSIS
    "kdi.re.kr",         # 한국개발연구원
    # 부동산 정보 플랫폼
    "kbland.kr",         # KB부동산
    "r114.com",          # 부동산114
    # 주요 경제지 (부동산 칼럼/리서치)
    "mk.co.kr",          # 매일경제
    "hankyung.com",      # 한국경제
    "sedaily.com",       # 서울경제
    "edaily.co.kr",      # 이데일리
    "chosun.com",        # 조선일보
    "joongang.co.kr",    # 중앙일보
]

_VERDICT_ENUM = ("BULLISH", "NEUTRAL", "BEARISH", "MIXED")

_SYSTEM_PROMPT = """You are a Korean real estate market analyst. Generate a concise, fact-based weekly brief for Korea's residential + commercial + office market. Use ONLY information from Korean government sources (MOLIT, MOEF, FSC, BOK), public research institutes (KRIHS, KDI), official real estate platforms (REB, KB Land, R114), and major Korean economic press (Maeil Business, Hankyung, Seoul Economic). Cite every fact. Output STRICT JSON matching the requested schema — no markdown, no prose outside the JSON object. Respond in Korean."""


def _query_template() -> str:
    today = datetime.now(KST).strftime("%Y-%m-%d")
    return f"""한국 부동산 시장 지난 7일 (오늘={today} 기준) 종합 weekly brief 를 작성하라. 다루는 내용:

1. **market_overview** (2-3 문장): 지난 7일 한국 부동산 시장 종합 요약 (가격·거래량·심리 종합).
2. **policy_changes** (0-5 items with date): 지난 7일 국토부/기재부/금융위/국세청 등에서 발표된 주요 정책·세제·대출규제 변화. 각 항목 = {{date, title, impact}}. 없으면 빈 배열.
3. **sector_dynamics**: 세 섹터 각 1-2 문장 — residential (주거), commercial (오피스/리테일), office_specific (오피스 별도 동향, 공실률 등).
4. **regional_highlights** (0-5 items): 지역별 주목 동향 (강남 / 송파 / 분당 / 마포 / 지방 광역시 등). 각 항목 = {{region, trend}}.
5. **outlook** (1-2 문장): 향후 1주~1개월 전망. 단정 X, 시나리오·조건 명시.
6. **risks** (3-5 bullets): 주의해야 할 downside 시나리오 (금리·DSR·미분양·정책 변동·역전세 등).
7. **verdict**: BULLISH / NEUTRAL / BEARISH / MIXED — 단일 라벨, 위 내용 종합 판단.

Output STRICT JSON (no markdown wrappers, real Korean content):
{{
  "market_overview": "<2-3 문장>",
  "policy_changes": [{{"date": "YYYY-MM-DD", "title": "<text>", "impact": "<text>"}}],
  "sector_dynamics": {{
    "residential": "<1-2 문장>",
    "commercial": "<1-2 문장>",
    "office_specific": "<1-2 문장>"
  }},
  "regional_highlights": [{{"region": "<지역명>", "trend": "<text>"}}],
  "outlook": "<1-2 문장>",
  "risks": ["<bullet>", "..."],
  "verdict": "<BULLISH|NEUTRAL|BEARISH|MIXED>"
}}"""


def _parse_brief_json(content: str) -> Optional[Dict[str, Any]]:
    """LLM response 에서 JSON 객체 추출. markdown wrapper / 잡음 제거."""
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
        print(f"[policy_narrative] JSON parse error: {e}", file=sys.stderr)
        return None


def build() -> Optional[Dict[str, Any]]:
    """주 1회 narrative brief 생성. 실패 시 None (이전 JSON 유지, T21)."""
    print("[policy_narrative] Perplexity Sonar Pro 호출…", file=sys.stderr)
    res = call_perplexity(
        query=_query_template(),
        system_prompt=_SYSTEM_PROMPT,
        max_tokens=4000,
        temperature=0.2,
        model="sonar-pro",
        search_domain_filter=_KOREA_RE_DOMAINS,
        search_recency_filter="week",
    )

    if "error" in res:
        print(f"[policy_narrative] Perplexity error: {res['error']}", file=sys.stderr)
        return None

    content = res.get("content", "")
    brief = _parse_brief_json(content)
    if not brief:
        print(f"[policy_narrative] JSON parse failed. raw preview: {content[:300]}", file=sys.stderr)
        return None

    verdict = brief.get("verdict", "")
    if verdict not in _VERDICT_ENUM:
        print(f"[policy_narrative] verdict 비정상 ({verdict}) → NEUTRAL", file=sys.stderr)
        brief["verdict"] = "NEUTRAL"

    now_kst = datetime.now(KST)
    usage = res.get("usage", {})
    cost_obj = usage.get("cost", {})
    if isinstance(cost_obj, dict):
        cost_usd = round(cost_obj.get("total_cost", 0), 4)
    else:
        cost_usd = float(cost_obj) if isinstance(cost_obj, (int, float)) else 0.0

    return {
        "schema_version": "1.0",
        "generated_at": now_kst.isoformat(timespec="seconds"),
        "lookback_days": 7,
        "market_overview": brief.get("market_overview", ""),
        "policy_changes": brief.get("policy_changes", []) or [],
        "sector_dynamics": brief.get("sector_dynamics", {}) or {},
        "regional_highlights": brief.get("regional_highlights", []) or [],
        "outlook": brief.get("outlook", ""),
        "risks": brief.get("risks", []) or [],
        "verdict": brief["verdict"],
        "model": res.get("model", "sonar-pro"),
        "cost_usd": cost_usd,
        "citations": (res.get("citations") or [])[:20],
    }


def _write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    brief = build()
    if brief is None:
        print("[policy_narrative] build 실패 — 이전 JSON 유지 (T21)", file=sys.stderr)
        return 1
    _write_json_atomic(OUTPUT_PATH, brief)
    stats = get_session_stats()
    print(
        f"[policy_narrative] 완료 verdict={brief['verdict']} "
        f"policy_changes={len(brief['policy_changes'])} "
        f"cost=${brief['cost_usd']} session=${stats['cost_usd']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
