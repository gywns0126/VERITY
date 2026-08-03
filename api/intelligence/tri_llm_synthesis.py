"""tri_llm_synthesis — 각기 재능이 다른 3종 LLM 종합 분석 (PM 2026-08-01 결정).

재능 배치:
  Perplexity  = 실시간 웹·뉴스·최근 이벤트 (매우 신선한 외부 사실)  [[feedback_perplexity_collaboration]]
  Gemini      = 빠르고 저렴한 구조적 정리 (우리 팩트 + 재무 구조화)
  Claude(opus-5) = 종합·판단 — 세 입력 + 우리 trail 을 하나의 정합 판단으로 (PM: Opus 5)

🚨 RULE 6 — "AI 에게 묻기" 아니라 "내 시스템에게 묻기". 3-LLM 전부 우리 사실 + 자기 trail
   (Brain 등급·VAMS·깔때기 사유, equity_research_brief.fetch_verity_trail 재사용) 위에서 종합.
   ungrounded LLM 잡담 금지 — LLM 무료 tier 가 못 가지는 view 가 해자.
🚨 RULE 7 — LLM 의견 = provenance 태그(어느 LLM 이 뭘). Brain 점수 = 가설/N.
   **이 종합을 fact_score/brain_score 에 재주입 절대 금지** (2026-07-23 사고 = LLM 정성점수 무검증
   주입으로 fact_score 오염). 이건 오퍼레이터 읽기 보조 산출물이지 채점 입력이 아니다.
🚨 법적 — Perplexity 가 물어온 컨센서스 목표가 = us_analyst_consensus 재배포 금지선. 사실 서술 +
   citations(출처 링크)만. 목표가 숫자를 우리 산출물로 재발행하지 않는다.

하이브리드 (PM 결정): 추천/보유 종목 = cron 사전계산(항상 준비). 임의 검색 종목 = 온디맨드 1회
   + 24h fact-fingerprint 캐시. 비용 = claude budget guard 존중.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Dict, Optional

from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

CACHE_PATH = os.path.join(DATA_DIR, "tri_synthesis_cache.json")
CACHE_TTL_HOURS = 24
CLAUDE_SYNTH_MODEL = "claude-opus-5"   # PM 2026-08-01. 종합자 = 최고 판단력.


# ─── 캐시 (fact-fingerprint) ─────────────────────────────────────────────


def _fingerprint(ticker: str, trail: Dict[str, Any]) -> str:
    """가격 jitter 로 캐시 무효화되지 않게 핵심 사실만 반올림해 지문 생성."""
    vb = trail.get("verity_brain") or {}
    parts = [
        ticker.upper(),
        str(round(float(trail.get("per") or 0), 1)),
        str(round(float(trail.get("pbr") or 0), 1)),
        str(round(float(trail.get("roe") or 0), 0)),
        str(vb.get("grade") or ""),
        str(round(float(vb.get("brain_score") or 0), 0)),
        str(trail.get("recommendation") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _load_cache() -> Dict[str, Any]:
    if not os.path.isfile(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(cache: Dict[str, Any]) -> None:
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, separators=(",", ":"))
    except OSError as e:
        logger.warning("[tri_llm] 캐시 저장 실패: %s", e)


def _cache_fresh(entry: Dict[str, Any]) -> bool:
    ts = entry.get("generated_at")
    if not ts:
        return False
    try:
        from datetime import datetime
        gen = datetime.fromisoformat(ts)
        age_h = (now_kst() - gen).total_seconds() / 3600.0
        return age_h < CACHE_TTL_HOURS
    except (ValueError, TypeError):
        return False


# ─── 자기 trail (RULE 6 grounding) ───────────────────────────────────────


def _trail(ticker: str) -> Dict[str, Any]:
    try:
        from api.intelligence.equity_research_brief import fetch_verity_trail
        t = fetch_verity_trail(ticker)
        return t if isinstance(t, dict) and "_error" not in t else {}
    except Exception as e:
        logger.warning("[tri_llm] trail fetch 실패: %s", e)
        return {}


def _trail_summary(ticker: str, trail: Dict[str, Any]) -> str:
    """LLM 입력용 자기 trail 요약 (RULE 7 라벨 포함)."""
    if not trail:
        return f"{ticker}: VERITY 자체 trail 없음 (추천 유니버스 밖)."
    vb = trail.get("verity_brain") or {}
    lines = [f"[VERITY 자체 trail — 검증 전 가설(N<252, 2027 게이트)]"]
    if vb.get("brain_score") is not None:
        lines.append(f"- Brain 등급: {vb.get('grade_label') or vb.get('grade')} (점수 {vb.get('brain_score')}, 가설)")
    for k, label in (("per", "PER"), ("pbr", "PBR"), ("roe", "ROE(%)")):
        if trail.get(k) is not None:
            lines.append(f"- {label}: {trail.get(k)}")
    if trail.get("recommendation"):
        lines.append(f"- 분류: {trail.get('recommendation')} (가설, 매수 지시 아님)")
    if trail.get("lynch_kr"):
        lines.append(f"- Lynch 분류: {trail.get('lynch_kr')}")
    return "\n".join(lines)


# ─── ① Perplexity: 신선 외부 사실 ─────────────────────────────────────────


def _perplexity_fresh(ticker: str, name: str) -> Dict[str, Any]:
    try:
        from api.clients.perplexity_client import call_perplexity
    except Exception as e:
        return {"error": f"perplexity 모듈 부재: {e}"}
    q = (
        f"{name}({ticker}) 관련 최근 1주일 내 주가에 영향 줄 사실만 간결히: "
        f"실적·공시·계약·규제·경영진·수급 이벤트. 목표가/투자의견 숫자는 제외하고 "
        f"사실과 출처만. 없으면 '특이사항 없음'."
    )
    sysp = "너는 사실 수집기다. 의견·추천·전망 금지. 확인된 사실과 출처만 3~5줄."
    r = call_perplexity(q, system_prompt=sysp, max_tokens=700, search_recency_filter="week")
    if r.get("error"):
        return {"error": r["error"]}
    return {"content": r.get("content", ""), "citations": r.get("citations", []), "model": r.get("model")}


# ─── ② Gemini: 구조적 정리 ───────────────────────────────────────────────


def _gemini_structure(ticker: str, name: str, trail_summary: str, fresh: str) -> Dict[str, Any]:
    try:
        from google import genai
        from api.config import GEMINI_API_KEY, GEMINI_MODEL_CHAT
    except Exception as e:
        return {"error": f"gemini 모듈/키 부재: {e}"}
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY 미설정"}
    prompt = (
        f"종목 {name}({ticker}). 아래 자체 trail 과 신선 사실을 3개 축으로 구조화하라 "
        f"(강점/약점/지켜볼 것). 사실 기반, 새 숫자·전망 창작 금지, 각 축 1~2줄.\n\n"
        f"[자체 trail]\n{trail_summary}\n\n[신선 사실]\n{fresh}"
    )
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(model=GEMINI_MODEL_CHAT, contents=prompt)
        text = getattr(resp, "text", "") or ""
        return {"content": text.strip(), "model": GEMINI_MODEL_CHAT}
    except Exception as e:
        return {"error": f"gemini 호출 실패: {e}"}


# ─── ③ Claude opus-5: 종합 ───────────────────────────────────────────────


def _claude_synthesize(ticker: str, name: str, trail_summary: str,
                       fresh: str, structured: str) -> Dict[str, Any]:
    try:
        import anthropic
        from api.config import ANTHROPIC_API_KEY
    except Exception as e:
        return {"error": f"anthropic 모듈 부재: {e}"}
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY 미설정"}
    system = (
        "너는 VERITY 오퍼레이터의 종합 분석가다. 세 입력(자체 trail=우리 산식, 신선 사실=Perplexity, "
        "구조화=Gemini)을 하나의 정합 판단으로 종합한다. 규칙: (1) 우리 자체 trail 을 판단의 축으로 삼되 "
        "'검증 전 가설(N<252)'로 정직히 다룬다. (2) 매수/매도 지시·목표가 숫자 재발행 금지. "
        "(3) 상충하는 신호는 상충으로 드러낸다. (4) 6~8줄, 마지막 줄에 '지켜볼 트리거' 1개."
    )
    user = (
        f"종목: {name}({ticker})\n\n[① 자체 trail]\n{trail_summary}\n\n"
        f"[② 신선 사실]\n{fresh}\n\n[③ 구조화]\n{structured}\n\n"
        f"위 셋을 종합해 이 종목의 현재 그림을 오퍼레이터에게 정리하라."
    )
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        # opus-5 = thinking 기본 on, max_tokens 가 thinking+텍스트 공통 캡 → 여유(3000).
        # effort low = 비용 절감(하이브리드), opus-5 는 low 도 강함(claude-api skill).
        # output_config 은 extra_body 로 전달 = SDK 0.89 버전 안전(kwarg 미지원 회피).
        # temperature/top_p/budget_tokens 는 opus-5 에서 400 → 미전달.
        msg = client.messages.create(
            model=CLAUDE_SYNTH_MODEL,
            max_tokens=3000,
            system=system,
            messages=[{"role": "user", "content": user}],
            extra_body={"output_config": {"effort": "low"}},
        )
        text = ""
        for block in msg.content:
            if getattr(block, "type", None) == "text":
                text += block.text
        usage = getattr(msg, "usage", None)
        return {
            "content": text.strip(),
            "model": CLAUDE_SYNTH_MODEL,
            "input_tokens": getattr(usage, "input_tokens", None) if usage else None,
            "output_tokens": getattr(usage, "output_tokens", None) if usage else None,
        }
    except Exception as e:
        return {"error": f"claude 호출 실패: {e}"}


# ─── 통합 ────────────────────────────────────────────────────────────────


def synthesize(ticker: str, name: str = "", use_cache: bool = True,
               force: bool = False) -> Dict[str, Any]:
    """3종 LLM 종합. 하이브리드 = 캐시 우선(24h fact-fingerprint), 미스 시 온디맨드 계산."""
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return {"error": "ticker 필요"}

    trail = _trail(ticker)
    if not name:
        name = trail.get("name") or ticker
    fp = _fingerprint(ticker, trail)

    cache = _load_cache() if use_cache else {}
    if use_cache and not force:
        entry = cache.get(ticker)
        if entry and entry.get("fingerprint") == fp and _cache_fresh(entry):
            entry["_cache"] = "hit"
            return entry

    ts = _trail_summary(ticker, trail)
    px = _perplexity_fresh(ticker, name)
    fresh_txt = px.get("content") or ("(신선 사실 수집 실패: " + str(px.get("error")) + ")")
    gm = _gemini_structure(ticker, name, ts, fresh_txt)
    struct_txt = gm.get("content") or ("(구조화 실패: " + str(gm.get("error")) + ")")
    cl = _claude_synthesize(ticker, name, ts, fresh_txt, struct_txt)

    result = {
        "ticker": ticker,
        "name": name,
        "generated_at": now_kst().isoformat(),
        "fingerprint": fp,
        # provenance 분리 (RULE 7 — 어느 LLM 이 무엇을)
        "sources": {
            "perplexity": {"content": px.get("content"), "citations": px.get("citations"),
                           "model": px.get("model"), "error": px.get("error")},
            "gemini": {"content": gm.get("content"), "model": gm.get("model"), "error": gm.get("error")},
            "claude": {"content": cl.get("content"), "model": cl.get("model"), "error": cl.get("error"),
                       "input_tokens": cl.get("input_tokens"), "output_tokens": cl.get("output_tokens")},
        },
        "verity_trail": {"summary": ts, "has_trail": bool(trail)},
        "disclosure": {
            "note": "3종 LLM 종합. Perplexity=신선사실·Gemini=구조화·Claude=종합. Brain 점수=가설(N<252, 2027). "
                    "LLM 의견은 의견이며 채점 입력 아님. 목표가 숫자 재발행 없음.",
            "rule6": "grounded (자기 trail 위 종합)",
            "rule7_hypothesis": True,
        },
        "_cache": "miss",
    }

    if use_cache and cl.get("content"):   # 종합 성공분만 캐시 (실패 재시도 허용)
        cache[ticker] = {k: v for k, v in result.items() if k != "_cache"}
        _save_cache(cache)
    return result
