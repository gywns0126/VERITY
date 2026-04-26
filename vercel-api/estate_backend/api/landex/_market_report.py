"""Perplexity 월간 시장 리포트 자동 수집 워커.

매월 첫째 주 GitHub Actions 가 호출 → Perplexity API → JSON 파싱 → Supabase upsert.
Vercel serverless 가 아니라 cron 워커용 CLI (python -m api.landex._market_report).

수집 항목 (parsed JSONB):
  - summary               이번 달 한 줄 요약
  - policy_changes[]      정책·규제 변경 (date / title / impact / axes_affected / summary)
  - macro_indicators      거시 (기준금리·주담대금리·추세)
  - recommended_regime    balanced | tightening | redevelopment_boom | supply_shock
  - regime_confidence     0~1
  - regime_rationale      왜 이 프리셋인지
  - proptech_movements[]  경쟁사 동향
  - user_trends_summary   투자자 수요 변화
  - verity_action_items[] VERITY ESTATE 액션 권고 (priority + title + rationale)
  - next_month_key_events[] (date / event / monitoring_axes)
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


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def main():
    # month 미지정 시 전월 (cron 1일 기준 — 이전 달 정리)
    if len(sys.argv) > 1:
        month = sys.argv[1]
    else:
        now = datetime.now(KST)
        prev = now.replace(day=1) - timedelta(days=1)
        month = prev.strftime("%Y-%m")

    print(f"[market_report] Perplexity 호출 month={month}", flush=True)
    report = fetch_market_report(month)
    if not report:
        print("[market_report] 호출 실패", flush=True)
        sys.exit(1)

    parsed = report["parsed"] or {}
    print(f"[market_report] regime={parsed.get('recommended_regime')} "
          f"(conf={parsed.get('regime_confidence')})", flush=True)
    print(f"[market_report] 액션 권고 {len(parsed.get('verity_action_items') or [])}건", flush=True)

    if save_market_report(month, report):
        print("[market_report] Supabase 저장 성공 ✓", flush=True)
    else:
        print("[market_report] Supabase 저장 실패 — 결과만 출력", flush=True)
        print(json.dumps(parsed, ensure_ascii=False, indent=2)[:1500])


if __name__ == "__main__":
    main()
