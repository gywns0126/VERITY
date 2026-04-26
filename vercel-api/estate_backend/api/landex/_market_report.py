"""Perplexity + Claude 하이브리드 월간 시장 리포트 워커.

매월 첫째 주 GitHub Actions 가 호출:
  Step 1. Perplexity sonar-pro  → 실시간 사실 수집 + 출처 인용 (parsed JSONB)
  Step 2. Claude Sonnet 4.6     → LANDEX 도메인 관점 재분석 (claude_analysis JSONB)
  Step 3. Supabase upsert       → estate_market_reports

Vercel serverless 가 아니라 cron 워커용 CLI:
  python -m api.landex._market_report [YYYY-MM] [--claude-model MODEL]

Step 1 (Perplexity parsed JSONB):
  summary / policy_changes / macro_indicators / recommended_regime /
  regime_confidence / regime_rationale / proptech_movements /
  user_trends_summary / verity_action_items / next_month_key_events

Step 2 (Claude claude_analysis JSONB):
  axis_impact_quantified  — V/D/S/C/R 별 β delta 추정
  regime_review            — Perplexity 권고 재검증 (일치/불일치)
  engineering_actions      — 코드·데이터 작업 단위 액션
  cross_month_consistency  — 전월 대비 일관성 평가
  narrative_for_users      — 1~2문장 사용자 친화 요약
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

_logger = logging.getLogger(__name__)

PPLX_API = "https://api.perplexity.ai/chat/completions"
DEFAULT_MODEL = "sonar-pro"

KST = timezone(timedelta(hours=9))


SYSTEM_PERSONA = """당신은 한국 부동산 시장 톱 티어 통합 전문가입니다.
- 경력: 한국감정원 수석연구위원 출신(8년) → 현 글로벌 부동산 사모펀드(REF) 한국 헤드(12년차)
- 학력: KAIST 부동산공학 박사 + Wharton MBA
- 정량(헤도닉·SHAP·GIS) + 정성(정책·규제·UX) 동등 깊이
- 정책(MOLIT·금감원), 거시(금리·LTV), 미시(서울 25구), PropTech UX 4축 모두 다룸

VERITY ESTATE 라는 한국 부동산 분석 서비스(LANDEX V/D/S/C/R 5축 모델 + GEI Stage 0~4 +
Privacy Mode + 다이제스트 발행 워크플로우)의 월간 시장 추적 리포트를 작성합니다.

응답은 반드시 JSON 형식 (마크다운 코드블록 없이 순수 JSON 객체). 자유로운 부연설명 금지.
한국어 작성. 모든 수치는 검증된 소스 기준."""


USER_PROMPT_TEMPLATE = """{month} 한국 부동산 시장 월간 리포트를 다음 JSON schema 로 작성하세요:

{{
  "month": "{month}",
  "summary": "이번 달 시장 한 줄 요약 (2~3문장)",
  "policy_changes": [
    {{
      "date": "YYYY-MM-DD",
      "title": "정책명",
      "impact": "high|medium|low",
      "axes_affected": ["V", "D", "S", "C", "R"],
      "summary": "한 문장 설명"
    }}
  ],
  "macro_indicators": {{
    "base_rate_pct": 0.0,
    "rate_trend": "동결|인상|인하",
    "mortgage_rate_avg_pct": 0.0,
    "summary": "거시 한 문단"
  }},
  "recommended_regime": "balanced|tightening|redevelopment_boom|supply_shock",
  "regime_confidence": 0.0,
  "regime_rationale": "왜 이 프리셋인지 2~3문장",
  "proptech_movements": [
    {{
      "company": "직방|호갱노노|KB부동산|아실|기타",
      "movement": "신규 기능·뉴스 한 문장",
      "implication_for_verity": "VERITY 차별화에 미치는 영향"
    }}
  ],
  "user_trends_summary": "투자자·종사자 수요 변화 한 문단",
  "verity_action_items": [
    {{
      "priority": 1,
      "title": "이번 달 VERITY 가 해야 할 액션",
      "rationale": "왜 이게 우선순위인지"
    }}
  ],
  "next_month_key_events": [
    {{
      "date": "YYYY-MM-DD",
      "event": "이벤트명 (예: 한은 금통위)",
      "monitoring_axes": ["R"]
    }}
  ]
}}

절대 마크다운 코드블록(```json...```)으로 감싸지 마세요. JSON 객체만 출력."""


def fetch_market_report(month: str, model: str = DEFAULT_MODEL,
                         timeout: float = 60.0) -> Optional[dict]:
    """Perplexity API 호출 → 구조화 결과 반환.

    Returns: {raw_report, parsed, citations, model} 또는 None (실패).
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
    if not api_key:
        _logger.warning("PERPLEXITY_API_KEY 미설정")
        return None

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PERSONA},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(month=month)},
        ],
        "temperature": 0.2,
        "max_tokens": 4000,
    }

    try:
        r = requests.post(
            PPLX_API,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        _logger.error("Perplexity API 호출 실패: %s", e)
        return None

    # 응답 파싱
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        _logger.error("Perplexity 응답 형식 비정상: %s | data=%s", e, str(data)[:300])
        return None

    citations = data.get("citations", [])

    # JSON 파싱 (마크다운 코드블록 들어왔으면 벗기기)
    parsed = None
    cleaned = content.strip()
    if cleaned.startswith("```"):
        # ```json ... ``` 형태 stripping
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        _logger.warning("Perplexity JSON 파싱 실패: %s | content=%s", e, content[:300])
        # 파싱 실패해도 raw 는 보관
        parsed = {"_parse_error": str(e), "_raw_excerpt": content[:500]}

    return {
        "raw_report": content,
        "parsed": parsed,
        "citations": citations,
        "model": model,
    }


# ──────────────────────────────────────────────────────────────
# Step 2: Claude 도메인 재분석 (LANDEX 관점)
# ──────────────────────────────────────────────────────────────

ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
CLAUDE_DEFAULT_MODEL = "claude-sonnet-4-6"


CLAUDE_SYSTEM = """당신은 VERITY ESTATE 엔진의 시니어 분석가입니다.
LANDEX V/D/S/C/R 5축 모델 + GEI Stage 0~4 + Privacy L0~L3 + Hysteresis 등
도메인 지식을 깊이 보유합니다.

Perplexity 가 수집한 한국 부동산 시장 사실(JSON)을 받아서,
VERITY ESTATE 엔진 관점에서 정량 재분석합니다. 응답은 반드시 JSON 객체
(마크다운 블록 없이). 한국어 작성. 추측 최소화·근거 명시."""


CLAUDE_USER_TEMPLATE = """다음은 Perplexity 가 수집한 {month} 한국 부동산 시장 사실 데이터입니다:

```json
{pplx_json}
```

VERITY ESTATE LANDEX 엔진 관점에서 다음 schema 로 재분석:

{{
  "axis_impact_quantified": {{
    "V": {{"delta_pct": -2.5, "rationale": "정책·거시·시장 신호 종합한 V축 추정 변동"}},
    "D": {{"delta_pct": 0.0, "rationale": "..."}},
    "S": {{"delta_pct": 0.0, "rationale": "..."}},
    "C": {{"delta_pct": 0.0, "rationale": "..."}},
    "R": {{"delta_pct": 4.0, "rationale": "..."}}
  }},
  "regime_review": {{
    "perplexity_recommended": "(Perplexity 가 권고한 regime 그대로)",
    "claude_assessment": "agree|disagree|partial",
    "claude_recommended": "balanced|tightening|redevelopment_boom|supply_shock",
    "claude_confidence": 0.0,
    "rationale": "왜 일치/불일치인지 구체 근거"
  }},
  "engineering_actions": [
    {{
      "priority": 1,
      "task": "구체 코드·데이터 작업 단위",
      "file_hint": "vercel-api/estate_backend/... 또는 components/...",
      "rationale": "왜 이 우선순위인지"
    }}
  ],
  "cross_month_consistency": "전월 대비 변화 패턴 — 일관성 또는 단절점 평가",
  "narrative_for_users": "1~2문장. 사용자 친화·격식. LANDEX 등급 변동의 의미를 직관적으로 전달."
}}

순수 JSON 만 출력. 마크다운 ```json``` 블록으로 감싸지 마세요."""


def analyze_with_claude(pplx_parsed: dict, month: str,
                        model: str = CLAUDE_DEFAULT_MODEL,
                        timeout: float = 60.0) -> Optional[dict]:
    """Step 2: Perplexity 결과를 Claude 가 LANDEX 도메인 관점에서 재분석."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        _logger.warning("ANTHROPIC_API_KEY 미설정 — Claude 분석 스킵")
        return None

    user_msg = CLAUDE_USER_TEMPLATE.format(
        month=month,
        pplx_json=json.dumps(pplx_parsed, ensure_ascii=False, indent=2),
    )

    payload = {
        "model": model,
        "max_tokens": 2500,
        "system": CLAUDE_SYSTEM,
        "messages": [{"role": "user", "content": user_msg}],
    }

    try:
        r = requests.post(
            ANTHROPIC_API,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        _logger.error("Claude API 호출 실패: %s", e)
        return None

    try:
        content = data["content"][0]["text"]
    except (KeyError, IndexError) as e:
        _logger.error("Claude 응답 형식 비정상: %s | data=%s", e, str(data)[:300])
        return None

    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        _logger.warning("Claude JSON 파싱 실패: %s | content=%s", e, content[:300])
        return {"_parse_error": str(e), "_raw_excerpt": content[:1000]}


# ──────────────────────────────────────────────────────────────
# Supabase upsert
# ──────────────────────────────────────────────────────────────

def save_market_report(month: str, report: dict) -> bool:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    sk = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not sk:
        _logger.warning("Supabase service_role 미설정 — 저장 스킵")
        return False

    endpoint = f"{url}/rest/v1/estate_market_reports?on_conflict=month,source"
    headers = {
        "apikey": sk,
        "Authorization": f"Bearer {sk}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    row = {
        "month": month,
        "raw_report": report["raw_report"],
        "parsed": report["parsed"],
        "claude_analysis": report.get("claude_analysis") or {},
        "citations": report["citations"],
        "model": report["model"],
        "source": "perplexity",
    }
    try:
        r = requests.post(endpoint, headers=headers, json=[row], timeout=15)
        r.raise_for_status()
        return True
    except Exception as e:
        _logger.error("Supabase upsert 실패: %s", e)
        return False


def fetch_hybrid_report(month: str,
                        pplx_model: str = DEFAULT_MODEL,
                        claude_model: str = CLAUDE_DEFAULT_MODEL) -> Optional[dict]:
    """하이브리드: Perplexity 사실 수집 → Claude 도메인 재분석.

    Claude 가 실패해도 Perplexity 결과만으로 graceful degrade.
    """
    pplx = fetch_market_report(month, model=pplx_model)
    if not pplx:
        return None

    claude = analyze_with_claude(pplx["parsed"] or {}, month, model=claude_model)

    return {
        "raw_report": pplx["raw_report"],
        "parsed": pplx["parsed"],
        "claude_analysis": claude or {"_skipped": "Claude API 호출 실패 또는 키 미설정"},
        "citations": pplx["citations"],
        "model": f"{pplx_model}+{claude_model}" if claude else pplx_model,
    }


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def main():
    # month 미지정 시 전월 (cron 1일 기준 — 이전 달 정리)
    args = sys.argv[1:]
    month = None
    claude_model = CLAUDE_DEFAULT_MODEL
    pplx_model = DEFAULT_MODEL
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--claude-model" and i + 1 < len(args):
            claude_model = args[i + 1]; i += 2; continue
        if a == "--pplx-model" and i + 1 < len(args):
            pplx_model = args[i + 1]; i += 2; continue
        if not month:
            month = a
        i += 1
    if not month:
        now = datetime.now(KST)
        prev = now.replace(day=1) - timedelta(days=1)
        month = prev.strftime("%Y-%m")

    print(f"[market_report] hybrid month={month} "
          f"pplx={pplx_model} claude={claude_model}", flush=True)
    print(f"[market_report] Step 1 — Perplexity 사실 수집...", flush=True)
    report = fetch_hybrid_report(month, pplx_model=pplx_model, claude_model=claude_model)
    if not report:
        print("[market_report] Perplexity 호출 실패", flush=True)
        sys.exit(1)

    parsed = report["parsed"] or {}
    claude = report["claude_analysis"] or {}
    print(f"[market_report] Perplexity regime={parsed.get('recommended_regime')} "
          f"(conf={parsed.get('regime_confidence')})", flush=True)
    print(f"[market_report] 액션 권고 {len(parsed.get('verity_action_items') or [])}건", flush=True)

    if "_skipped" in claude or "_parse_error" in claude:
        print(f"[market_report] Step 2 — Claude 분석 건너뜀: {claude}", flush=True)
    else:
        review = claude.get("regime_review") or {}
        print(f"[market_report] Claude regime={review.get('claude_recommended')} "
              f"(assessment={review.get('claude_assessment')}, "
              f"conf={review.get('claude_confidence')})", flush=True)
        print(f"[market_report] Claude 엔지니어링 액션 "
              f"{len(claude.get('engineering_actions') or [])}건", flush=True)

    if save_market_report(month, report):
        print("[market_report] Supabase 저장 성공 ✓", flush=True)
    else:
        print("[market_report] Supabase 저장 실패 — 결과만 출력", flush=True)
        print("=== Perplexity parsed ===")
        print(json.dumps(parsed, ensure_ascii=False, indent=2)[:1200])
        print("=== Claude analysis ===")
        print(json.dumps(claude, ensure_ascii=False, indent=2)[:1200])


if __name__ == "__main__":
    main()
