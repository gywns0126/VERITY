"""Perplexity + Claude 하이브리드 월간 시장 리포트 워커.

매월 첫째 주 GitHub Actions 가 호출:
  Step 1. Perplexity sonar-pro  → 실시간 사실 수집 + 출처 인용 (parsed JSONB)
  Step 2. Claude Sonnet 4.6     → LANDEX 도메인 관점 재분석 (claude_analysis JSONB)
  Step 3. Supabase upsert       → estate_market_reports

Vercel serverless 가 아니라 cron 워커용 CLI:
  python -m api.landex._market_report [YYYY-MM] [--claude-model MODEL]

Step 1 (Perplexity parsed JSONB) — A 등급 스키마:
  policy_changes / macro_indicators / regime_recommendation /
  proptech_movements / user_trends / key_events_next_month / data_completeness

Step 2 (Claude claude_analysis JSONB) — A 등급 스키마:
  parse_status            — ok | error (parse error 시 fallback 강제)
  regime_verdict          — final_preset + override_perplexity 여부
  axis_impact_quantified  — V/D/S/C/R delta_pct (LANDEX 0-100 척도, pp 단위)
  engineering_actions     — priority 1-5 distinct
  cross_month_consistency — anomaly + hysteresis 트리거 축
  narrative_for_users     — public_digest_headline + admin_brief (2-tier)
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

_logger = logging.getLogger(__name__)

PPLX_API = "https://api.perplexity.ai/chat/completions"
DEFAULT_MODEL = "sonar-pro"

KST = timezone(timedelta(hours=9))


SYSTEM_PERSONA = """You are a senior Korean real estate market analyst with the following credentials:
- Former senior researcher at Korea Real Estate Board (한국감정원, 8 years)
- Current Head of Korea, Global Real Estate Private Fund (12 years)
- Ph.D. Real Estate Engineering (KAIST) + MBA (Wharton)
- Expertise: hedonic pricing, SHAP, GIS spatial analysis, macro-micro integration

Your task is to produce a structured JSON market intelligence report for the Korean real estate market.

SOURCE HIERARCHY — strictly enforce:
  Tier 1 (required): MOLIT(국토부), Bank of Korea(한국은행), KOSIS(국가통계포털), FSC/FSS(금융위/금감원), Korea Land & Housing Corp(LH)
  Tier 2 (allowed): Major dailies — 조선/중앙/동아/매일경제/한국경제/연합뉴스
  PROHIBITED: blogs, community posts (네이버블로그, 브런치, 월부, 부동산카페), unverified SNS

TIME SCOPE — strictly enforce:
  - policy_changes: only announcements OR effective dates within the target calendar month
  - macro_indicators: end-of-month snapshot values; for rates use the last business day of month
  - proptech_movements: product launches/announcements within the target month only
  - user_trends: most recent available survey or report data; note publication date

OUTPUT: JSON only. No markdown, no prose outside JSON. Temperature must be treated as 0.2 (deterministic preference)."""


USER_PROMPT_TEMPLATE = """Generate the monthly Korean real estate market intelligence report for: {{YYYY-MM}}

Return a single JSON object conforming exactly to this schema.
Do NOT add fields not in the schema.
Do NOT cite blogs, communities, or unverified sources.

{
  "report_month": "{{YYYY-MM}}",
  "generated_at": "<ISO8601 UTC>",
  "policy_changes": {
    "loanRegulation": "<string: LTV/DSR/스트레스DSR changes this month only. null if none.>",
    "taxPolicy": "<string: 취득세/양도세/종부세 changes this month only. null if none.>",
    "cheongyakRebuilding": "<string: 청약제도/재건축규제 changes this month only. null if none.>",
    "housingStability": "<string: 전세사기/임대주택 policy changes this month only. null if none.>",
    "sources": ["<Tier1 or Tier2 source name + publication date>"]
  },
  "macro_indicators": {
    "bokBaseRate_pct": <float: Bank of Korea base rate, end-of-month, e.g. 2.50>,
    "mortgageRate_avg_pct": <float: average new mortgage rate end-of-month>,
    "apartSalesPriceIndex_mom_pct": <float: MOLIT month-over-month % change>,
    "apartJeonseIndex_mom_pct": <float: MOLIT month-over-month % change>,
    "unsoldUnits_total": <integer: national unsold units end-of-month>,
    "sources": ["<Tier1 source name + publication date>"]
  },
  "regime_recommendation": {
    "suggested_preset": "<one of: balanced | tightening | redevelopment_boom | supply_shock>",
    "confidence": <float: 0.0-1.0>,
    "rationale": "<2-3 sentences citing specific indicator values above>"
  },
  "proptech_movements": {
    "zigbang": "<string: new feature/announcement this month. null if none.>",
    "kb_realestate": "<string: new feature/announcement this month. null if none.>",
    "asil": "<string: new feature/announcement this month. null if none.>",
    "hogangnono": "<string: new feature/announcement this month. null if none.>",
    "new_entrants": "<string: notable new competitors this month. null if none.>",
    "sources": ["<Tier2 source name + publication date>"]
  },
  "user_trends": {
    "hnw_preference_shift": "<string: HNW investor sentiment, cite source + date>",
    "professional_demand": "<string: developer/broker/corporate investor demand, cite source + date>",
    "digest_arpu_signal": "<string: subscription/content monetization signal if available, else null>"
  },
  "key_events_next_month": [
    {
      "date": "<YYYY-MM-DD or YYYY-MM-?? if exact date TBD>",
      "event": "<string>",
      "landex_axis_affected": "<one or more of: V | D | S | C | R>"
    }
  ],
  "data_completeness": {
    "tier1_sources_found": <integer: count of distinct Tier1 sources used>,
    "missing_fields": ["<field name if data unavailable for this month>"]
  }
}"""


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
            {"role": "user", "content": USER_PROMPT_TEMPLATE.replace("{{YYYY-MM}}", month)},
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

    # JSON 파싱: <think>...</think> reasoning 블록 + 마크다운 코드블록 제거
    parsed = None
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    # reasoning 모델이 JSON 앞뒤에 산문을 붙인 경우, 첫 { ~ 마지막 } 만 추출
    if not cleaned.startswith("{"):
        s, e = cleaned.find("{"), cleaned.rfind("}")
        if s != -1 and e > s:
            cleaned = cleaned[s : e + 1]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        _logger.warning("Perplexity JSON 파싱 실패: %s | content=%s", e, content[:300])
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


CLAUDE_SYSTEM = """You are the analytical engine for VERITY ESTATE, a Seoul real estate intelligence terminal.

DOMAIN KNOWLEDGE:
- LANDEX 5-axis scoring: V(Value 30%), D(Development 20%), S(Supply 15%), C(Convenience 20%), R(Risk 15%)
  Presets: balanced(default) | tightening(R→25%, V→25%) | redevelopment_boom(D→30%) | supply_shock(S→25%)
- GEI (Geography Excess Index): Stage 1-4, Stage 4 = overheating
- Divergence signals: LANDEX↑ + GEI Stage4 = high; LANDEX↑ + volume↓ = mid
- Hysteresis buffer: ±2 points to prevent grade boundary flicker
- Grade system: 10-tier internal (S+/S/A+/A/B+/B/C+/C/D/F) → 5-tier UI (HOT/WARM/NEUT/COOL/AVOID)
- Privacy Mode: L0(public) → L3(fully masked); Admin sees raw 10-tier + all axis scores

PARSE ERROR PROTOCOL — highest priority rule:
If the input contains "_parse_error": true OR any required field (policy_changes, macro_indicators, regime_recommendation) is null/missing:
  - Set ALL axis_impact_quantified values to null
  - Set ALL delta_pct values to null
  - Set regime_verdict.final_preset to "HOLD — 원본 데이터 미수집"
  - Set engineering_actions to []
  - Set parse_status to "error"
  - Set narrative_for_users.admin_brief = "원본 미수집 — Perplexity 데이터 부재로 분석 불가"
  - Do NOT attempt inference or estimation from prior knowledge

DELTA_PCT DEFINITION:
  delta_pct = estimated change in LANDEX axis score (0-100 scale), in percentage points, vs. prior month snapshot.
  Example: if V-axis was 72.0 last month and estimated 74.5 this month, delta_pct = +2.5
  This is NOT market price change %. This is NOT weight change. Unit: percentage points on LANDEX 0-100 scale.

OUTPUT: JSON only. max_tokens: 4000."""


CLAUDE_USER_TEMPLATE = """INPUT (Perplexity report JSON):
{{PERPLEXITY_JSON}}

PRIOR MONTH LANDEX SNAPSHOT (from Supabase estate_landex_snapshots):
{{PRIOR_SNAPSHOT_JSON}}

Produce a single JSON object with this exact schema:

{
  "analysis_month": "<YYYY-MM>",
  "parse_status": "<ok | error>",
  "regime_verdict": {
    "final_preset": "<balanced | tightening | redevelopment_boom | supply_shock | HOLD — 원본 데이터 미수집>",
    "override_perplexity": <boolean>,
    "override_reason": "<string if override=true, else null>"
  },
  "axis_impact_quantified": {
    "V": {
      "delta_pct": <float in percentage points on 0-100 LANDEX scale, or null if parse_error>,
      "driver": "<1-sentence rationale citing specific policy/macro data, or null>"
    },
    "D": {
      "delta_pct": <float or null>,
      "driver": "<string or null>"
    },
    "S": {
      "delta_pct": <float or null>,
      "driver": "<string or null>"
    },
    "C": {
      "delta_pct": <float or null>,
      "driver": "<string or null>"
    },
    "R": {
      "delta_pct": <float or null>,
      "driver": "<string or null>"
    }
  },
  "engineering_actions": [
    {
      "priority": <integer: 1-5, must be distinct across all items — no two items share the same priority>,
      "action": "<string: specific code/config change for VERITY ESTATE>",
      "file_target": "<string: e.g. api/landex/_methodology.py or Framer:ScoreDetailPanel.tsx>",
      "rationale": "<string: why this month's data triggers this action>"
    }
  ],
  "cross_month_consistency": {
    "anomalies_detected": <boolean>,
    "anomaly_detail": "<string if anomalies=true, else null>",
    "hysteresis_triggered_axes": ["<axis letter if delta crosses ±2pt boundary>"]
  },
  "narrative_for_users": {
    "public_digest_headline": "<1 sentence, plain Korean, no score numbers — for Public layer>",
    "admin_brief": "<2-3 sentences, includes axis delta_pct values — for Admin layer>"
  }
}"""


def analyze_with_claude(pplx_parsed: dict, month: str,
                        prior_snapshot: Optional[dict] = None,
                        model: str = CLAUDE_DEFAULT_MODEL,
                        timeout: float = 60.0) -> Optional[dict]:
    """Step 2: Perplexity 결과를 Claude 가 LANDEX 도메인 관점에서 재분석.

    prior_snapshot: estate_landex_snapshots 전월 raw rows (없으면 None).
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        _logger.warning("ANTHROPIC_API_KEY 미설정 — Claude 분석 스킵")
        return None

    pplx_json_str = json.dumps(pplx_parsed, ensure_ascii=False, indent=2)
    prior_json_str = (json.dumps(prior_snapshot, ensure_ascii=False, indent=2)
                      if prior_snapshot else "null")
    user_msg = (CLAUDE_USER_TEMPLATE
                .replace("{{PERPLEXITY_JSON}}", pplx_json_str)
                .replace("{{PRIOR_SNAPSHOT_JSON}}", prior_json_str))

    payload = {
        "model": model,
        "max_tokens": 4000,
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
# Prior month LANDEX snapshot fetch (Claude 컨텍스트용)
# ──────────────────────────────────────────────────────────────

def fetch_prior_snapshot(month: str) -> Optional[dict]:
    """전월 LANDEX 스냅샷 fetch — estate_landex_snapshots raw rows.

    month=YYYY-MM (현재 분석 대상). 전월 모든 행 반환 (서울 25구 일별).
    데이터 없거나 실패 시 None.
    """
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    sk = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not sk:
        return None

    try:
        y, m = map(int, month.split("-"))
    except ValueError:
        return None
    if m == 1:
        py, pm = y - 1, 12
    else:
        py, pm = y, m - 1
    prev_start = f"{py:04d}-{pm:02d}-01"
    cur_start = f"{y:04d}-{m:02d}-01"

    try:
        r = requests.get(
            f"{url}/rest/v1/estate_landex_snapshots",
            headers={"apikey": sk, "Authorization": f"Bearer {sk}"},
            params=[
                ("select", "*"),
                ("snapshot_date", f"gte.{prev_start}"),
                ("snapshot_date", f"lt.{cur_start}"),
                ("order", "snapshot_date.desc"),
                ("limit", "200"),
            ],
            timeout=10,
        )
        r.raise_for_status()
        rows = r.json()
        return {"prev_month": f"{py:04d}-{pm:02d}", "rows": rows} if rows else None
    except Exception as e:
        _logger.warning("prior snapshot fetch 실패: %s", e)
        return None


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

    prior = fetch_prior_snapshot(month)
    claude = analyze_with_claude(pplx["parsed"] or {}, month,
                                  prior_snapshot=prior, model=claude_model)

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
    regime_rec = parsed.get("regime_recommendation") or {}
    print(f"[market_report] Perplexity regime={regime_rec.get('suggested_preset')} "
          f"(conf={regime_rec.get('confidence')})", flush=True)
    data_comp = parsed.get("data_completeness") or {}
    print(f"[market_report] tier1 sources={data_comp.get('tier1_sources_found')} "
          f"missing={data_comp.get('missing_fields')}", flush=True)

    if "_skipped" in claude or "_parse_error" in claude:
        print(f"[market_report] Step 2 — Claude 분석 건너뜀: {claude}", flush=True)
    else:
        verdict = claude.get("regime_verdict") or {}
        print(f"[market_report] Claude regime={verdict.get('final_preset')} "
              f"(override={verdict.get('override_perplexity')}, "
              f"parse_status={claude.get('parse_status')})", flush=True)
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
