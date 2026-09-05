"""macro_synthesis — 출처가 있는 국내외 거시 사실 번들.

2026-09-05 PM 결정으로 구형 3모델 시나리오 종합을 종료했다.
  Perplexity = 최근 72h 글로벌 거시 사실과 출처
  Gemini     = 최근 72h 국내 거시 사실과 검색 근거
  최종 해석 = 이 파일에서 만들지 않음. 필요할 때 Codex 세션이 원문을 확인하고 수행.

🚨 RULE 6 — grounding 전부 자기 자산: market_horizon(자기 산식)·briefing·global_events·
   sector_rotation·daily_report·보유/현금 컨텍스트 (portfolio.json). PM 명시 요청분.
🚨 RULE 7 — market_horizon = 자기 산식 → 본문 인용 시 '(가설)' 병기. 종합을 채점에 재주입 금지.
채점·추천·포트폴리오 함의 생성은 0건이다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Dict

from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

PORTFOLIO_PATH = os.path.join(DATA_DIR, "portfolio.json")
OUT_PATH = os.path.join(DATA_DIR, "macro_synthesis.json")
CACHE_PATH = os.path.join(DATA_DIR, "macro_synthesis_cache.json")
# 프롬프트 개정 시 +1 — fingerprint 포함 = 구 시나리오 캐시 자동 무효화.
PROMPT_VERSION = "3"


def _load_portfolio() -> Dict[str, Any]:
    try:
        with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("[macro_synth] portfolio.json 로드 실패: %s", e)
        return {}


def _grounding(p: Dict[str, Any]) -> str:
    """자기 자산 요약 — LLM 입력 (RULE 6)."""
    lines = []
    mh = p.get("market_horizon") or {}
    if mh.get("verdict"):
        lines.append(f"[자기 산식 market_horizon — 가설(미검정)] {mh.get('verdict')}")
    br = p.get("briefing") or {}
    if br.get("headline"):
        lines.append(f"[브리핑] tone={br.get('tone')} · {br.get('headline')}")
    rot = p.get("sector_rotation") or {}
    if rot.get("cycle_label"):
        lines.append(f"[섹터 사이클] {rot.get('cycle_label')} — {str(rot.get('cycle_desc') or '')[:120]}")
    dr = p.get("daily_report") or {}
    for k, label in (("market_analysis", "일일 분석"), ("risk_watch", "리스크"), ("tomorrow_outlook", "내일 관점")):
        if dr.get(k):
            lines.append(f"[{label}] {str(dr.get(k))[:180]}")
    events = [e for e in (p.get("global_events") or []) if isinstance(e, dict)]
    highs = [e for e in events if str(e.get("severity", "")).lower() == "high"][:4]
    for e in highs:
        lines.append(f"[이벤트/{e.get('country', '')}] {e.get('name')} — {str(e.get('impact') or '')[:140]}")
    macro = p.get("macro") or {}
    kv = []
    for k in ("usd_krw", "wti_oil", "gold", "vix"):
        node = macro.get(k) or {}
        v = node.get("value") if isinstance(node, dict) else node
        if v is not None:
            kv.append(f"{k}={v}")
    if kv:
        lines.append("[매크로] " + " · ".join(str(x) for x in kv))
    vams = p.get("vams") or {}
    ta, cash = vams.get("total_asset"), vams.get("cash")
    if isinstance(ta, (int, float)) and isinstance(cash, (int, float)) and ta > 0:
        lines.append(f"[우리 포지션] 주식 노출 {round((ta - cash) / ta * 100, 1)}% · 현금 {round(cash / ta * 100, 1)}% (중용 사이징 결과)")
    heads = [h.get("title") for h in (p.get("bloomberg_google_headlines") or [])[:4] if isinstance(h, dict) and h.get("title")]
    for t in heads:
        lines.append(f"[글로벌 헤드라인] {t}")
    return "\n".join(lines) if lines else "(자기 자산 요약 없음)"


def _fingerprint(p: Dict[str, Any]) -> str:
    mh = p.get("market_horizon") or {}
    br = p.get("briefing") or {}
    parts = [
        PROMPT_VERSION,
        now_kst().strftime("%Y-%m-%d"),   # 일 1회 자연 무효화
        str(mh.get("verdict") or ""),
        str(br.get("headline") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _perplexity_fresh() -> Dict[str, Any]:
    try:
        from api.clients.perplexity_client import call_perplexity
    except Exception as e:
        return {"error": f"perplexity 모듈 부재: {e}"}
    q = (
        "최근 72시간 글로벌 거시경제에서 시장에 영향 준 확인된 사실만: 중앙은행(Fed/BOJ/ECB/한은) "
        "결정·발언, 주요 지표(물가·고용·PMI), 지정학 이벤트, 원자재·환율 급변. "
        "전망·의견 제외, 사실과 출처만."
    )
    sysp = (
        "너는 사실 수집기다. 의견·추천·전망 금지. 확인된 사실과 출처만 4~6줄. "
        "평문으로만 — 마크다운 굵게(**)·헤딩(#)·이모지 금지."
    )
    r = call_perplexity(q, system_prompt=sysp, max_tokens=800, search_recency_filter="day", caller="macro_synthesis")
    if r.get("error"):
        return {"error": r["error"]}
    return {"content": r.get("content", ""), "citations": r.get("citations", []), "model": r.get("model")}


def _filter_citation_refs(urls: Any, limit: int = 6) -> tuple[List[str], List[Dict[str, Any]]]:
    """품질 필터 뒤에도 Perplexity 본문의 원래 인용 번호를 보존한다."""
    raw = [u for u in (urls or []) if isinstance(u, str) and u]
    from api.intelligence.source_tiers import filter_citations

    filtered = filter_citations(raw, limit=limit)
    used: set[int] = set()
    refs: List[Dict[str, Any]] = []
    for url in filtered:
        for index, original in enumerate(raw, start=1):
            if index not in used and original == url:
                refs.append({"n": index, "url": url})
                used.add(index)
                break
    return filtered, refs


# 그라운딩 검증 모델 — 2026-08-03 프로브에서 google_search 그라운딩 정합 실측
# (코스피·미10y 정확 일치, 환각 0, 국내 주류 출처). flash-lite 는 그라운딩 미검증이라 명시 고정.
_GEMINI_GROUNDED_MODEL = "gemini-2.5-flash"


def _gemini_facts(grounding: str, fresh: str) -> Dict[str, Any]:
    """국내 신선 사실 수집 — 구글 검색 그라운딩으로
    한국 거시·시장 사실(한국은행·금융위·주류 언론)을 보강. Perplexity(글로벌)와 상보.
    출처는 source_tiers 로 T1/T2 만 citations 저장 (프로브 실측: 저품질 27% 차단)."""
    try:
        from google import genai
        from google.genai import types as _gtypes
        from api.config import GEMINI_API_KEY
    except Exception as e:
        return {"error": f"gemini 모듈/키 부재: {e}"}
    if not GEMINI_API_KEY:
        return {"error": "GEMINI_API_KEY 미설정"}
    prompt = (
        "구글 검색을 사용해 최근 72시간 한국 거시·시장의 확인된 사실만 3~6줄로 수집하라. "
        "한국은행·금융위원회·정부·거래소·기업 공식 발표를 우선하고 날짜와 수치를 병기하라. "
        "각 줄 '- ' 시작. 레짐 판정·전망·리스크 추정·투자의견·포트폴리오 함의는 생성하지 마라. "
        "마크다운(**, ##)·이모지 금지, 평문만. 아래 내용과 중복되는 사실은 생략하라.\n\n"
        f"[자기 자산]\n{grounding}\n\n[신선 사실(글로벌)]\n{fresh}"
    )
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(
            model=_GEMINI_GROUNDED_MODEL,
            contents=prompt,
            config=_gtypes.GenerateContentConfig(
                tools=[_gtypes.Tool(google_search=_gtypes.GoogleSearch())],
            ),
        )
        cites: list = []
        try:
            from api.intelligence.source_tiers import tier_of
            gm_meta = resp.candidates[0].grounding_metadata
            for ch in (getattr(gm_meta, "grounding_chunks", None) or []):
                web = getattr(ch, "web", None)
                title = getattr(web, "title", "") if web else ""
                uri = getattr(web, "uri", "") if web else ""
                # 프로브 실측: title = 도메인 문자열 → tier 판정은 title 로 (uri 는 구글 redirect)
                if title and uri and tier_of(title) >= 1:
                    cites.append({"title": title, "uri": uri})
                if len(cites) >= 6:
                    break
        except Exception:
            pass
        return {
            "content": (getattr(resp, "text", "") or "").strip(),
            "model": _GEMINI_GROUNDED_MODEL + "+search",
            "citations": cites,
        }
    except Exception as e:
        return {"error": f"gemini 호출 실패: {e}"}


def synthesize_macro(force: bool = False) -> Dict[str, Any]:
    """국내외 거시 사실 번들 — 일 1회 fingerprint 캐시."""
    p = _load_portfolio()
    fp = _fingerprint(p)

    if not force and os.path.isfile(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f) or {}
            sources = cached.get("sources", {})
            if cached.get("fingerprint") == fp and (
                sources.get("perplexity", {}).get("content")
                or sources.get("gemini", {}).get("content")
            ):
                cached["_cache"] = "hit"
                return cached
        except (OSError, json.JSONDecodeError):
            pass

    grounding = _grounding(p)
    px = _perplexity_fresh()
    # Perplexity citations 도 차단 겹 통과 (source_tiers)
    try:
        px["citations"], px["citation_refs"] = _filter_citation_refs(px.get("citations") or [], limit=6)
    except Exception:
        pass
    fresh_txt = px.get("content") or ("(신선 사실 수집 실패: " + str(px.get("error")) + ")")
    gm = _gemini_facts(grounding, fresh_txt)

    result = {
        "generated_at": now_kst().isoformat(),
        "fingerprint": fp,
        "contract": "macro-facts-v1",
        "grounding": grounding,
        "sources": {
            "perplexity": {"content": px.get("content"), "citations": px.get("citations"),
                           "citation_refs": px.get("citation_refs"),
                           "model": px.get("model"), "error": px.get("error")},
            "gemini": {"content": gm.get("content"), "model": gm.get("model"), "error": gm.get("error"),
                       "gm_citations": gm.get("citations")},
        },
        "disclosure": {
            "note": "출처가 있는 국내외 거시 사실 번들. 시나리오·전망·추천·채점 재주입 없음. "
                    "최종 해석은 Codex 세션에서 원문 확인 후 수행.",
            "rule6": "grounded",
            "rule7_hypothesis": True,
            "legacy_chain_retired": True,
        },
        "_cache": "miss",
    }

    if px.get("content") or gm.get("content"):
        try:
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump({k: v for k, v in result.items() if k != "_cache"}, f, ensure_ascii=False, separators=(",", ":"))
        except OSError as e:
            logger.warning("[macro_synth] 캐시 저장 실패: %s", e)
    return result
