"""investor_profiles — 거장 인물 프로필 (위키백과 출처, 검증 가드 포함).

2026-07-30 신설 (PM 요청 — "인물 설명도. 뭘 창업했고 엑싯했고 등등").

🚨 인물 서술을 내 기억으로 쓰지 않는다 ([[feedback_llm_facts_no_unverified_assert]] /
   [[feedback_knowledge_cutoff_verify_first]]). 전기적 사실은 출처가 붙는 것만 싣고,
   출처 링크를 함께 노출한다.

🚨🚨 동명이인 가드 — 제목 매칭만으로는 틀린 사람이 붙는다.
   실측(2026-07-30): 한국어 위키 "캐서린 우드" 는 **1914년생 소설가 캐서린 마셜**을 반환한다.
   그대로 실었으면 ARK 캐시 우드 카드에 소설가 약력이 붙었다.
   → extract 에 투자/사업 관련 직업 키워드가 없으면 폐기하고 다음 후보로 넘어간다.
   후보를 다 소진하면 프로필 없음(빈 값)으로 둔다 — 추측으로 채우지 않는다.
"""
from __future__ import annotations

import json
import logging
import re
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from api.config import DATA_DIR

logger = logging.getLogger(__name__)

CACHE_PATH = os.path.join(DATA_DIR, "investor_profiles.json")
_UA = {"User-Agent": os.getenv("SEC_EDGAR_USER_AGENT", "VERITY verity@example.com")}

# 채택 조건 — extract 안에 아래 중 하나가 있어야 '그 인물'로 인정.
_OCCUPATION_KEYWORDS = (
    "investor", "hedge fund", "investment", "financier", "businessman",
    "business magnate", "philanthropist", "fund manager", "entrepreneur",
    "투자", "헤지", "기업인", "자산운용", "펀드", "실업가", "사업가",
)

# 기관 → 위키 후보 (한국어 우선, 영문 fallback). 영문 제목은 동명이인 회피 위해 명시적으로 지정.
WIKI_CANDIDATES: Dict[str, List[tuple]] = {
    "Berkshire Hathaway":       [("ko", "워런 버핏"), ("en", "Warren Buffett")],
    "Bridgewater Associates":   [("ko", "레이 달리오"), ("en", "Ray Dalio")],
    "Renaissance Technologies": [("ko", "제임스 사이먼스"), ("en", "Jim Simons")],
    "Pershing Square":          [("ko", "빌 애크먼"), ("en", "Bill Ackman")],
    "Third Point LLC":          [("en", "Daniel S. Loeb"), ("en", "Dan Loeb")],
    "Tiger Global":             [("en", "Chase Coleman III")],
    "ARK Invest":               [("en", "Cathie Wood")],
    "Point72":                  [("en", "Steve Cohen (businessman)")],
    "Duquesne Family Office":   [("en", "Stanley Druckenmiller")],
    "Soros Fund Management":    [("ko", "조지 소로스"), ("en", "George Soros")],
    "TCI Fund Management":      [("en", "Chris Hohn")],
    # "Andreas Halvorsen" 은 동음이의 페이지(type=disambiguation) → 정식 제목 사용.
    "Viking Global":            [("en", "Ole Andreas Halvorsen")],
    "AQR Capital":              [("en", "Cliff Asness")],
    "Fisher Asset Management":  [("en", "Ken Fisher")],
    "Tudor Investment":         [("en", "Paul Tudor Jones")],
    "Gates Foundation Trust":   [("ko", "빌 게이츠"), ("en", "Bill Gates")],
}


def _fetch_summary(lang: str, title: str) -> Optional[Dict[str, Any]]:
    """위키백과 REST summary. 채택 조건 미달이면 None (조용히 틀린 사람 싣지 않음)."""
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
    try:
        r = requests.get(url, headers=_UA, timeout=15)
    except Exception as e:                                     # noqa: BLE001
        logger.warning("[profile] %s:%s 조회 실패 %s", lang, title, e)
        return None
    if r.status_code != 200:
        return None
    try:
        j = r.json()
    except ValueError:
        return None
    if j.get("type") != "standard":                            # 동음이의 페이지 등
        return None
    extract = (j.get("extract") or "").strip()
    if not extract:
        return None
    low = extract.lower()
    if not any(k.lower() in low for k in _OCCUPATION_KEYWORDS):
        logger.warning("[profile] %s:%s 폐기 — 직업 키워드 없음(동명이인 의심): %.50s",
                       lang, title, extract)
        return None
    return {
        "name": j.get("title"),
        "summary": extract,
        "source": "위키백과",
        "source_url": (j.get("content_urls") or {}).get("desktop", {}).get("page"),
        "lang": lang,
    }


def fetch_profile(institution: str) -> Optional[Dict[str, Any]]:
    for lang, title in WIKI_CANDIDATES.get(institution, []):
        got = _fetch_summary(lang, title)
        time.sleep(0.25)                                       # 위키 예의상 스로틀
        if got:
            return got
    logger.warning("[profile] %s — 후보 소진, 프로필 없음", institution)
    return None


def _translate_ko(texts: List[str]) -> Dict[str, str]:
    """영문 프로필 → 한국어. 기존 뉴스 번역과 동일 경로(Gemini flash-lite, 1 batch).

    🚨 번역 = 사실 전달 유틸이지 narrative 생성이 아니다(RULE 6 경계 — news_translation 과 동일 판단).
       원문(summary)은 지우지 않고 summary_ko 를 덧붙인다. 번역 실패 시 원문 그대로 노출되므로
       화면이 비지 않는다. 프로필은 16건 고정 + 캐시라 호출은 사실상 최초 1회.
    """
    if not texts:
        return {}
    try:
        from google import genai
        from api.config import GEMINI_API_KEY, GEMINI_MODEL_CHAT

        if not GEMINI_API_KEY:
            return {}
        client = genai.Client(api_key=GEMINI_API_KEY)
        numbered = "\n\n".join(f"{i}. {t}" for i, t in enumerate(texts))
        prompt = (
            "다음 영어 인물 소개문들을 자연스러운 한국어로 번역하라. "
            "고유명사(인명·기업명·펀드명)는 통용 표기 유지, 숫자·연도·금액은 원문 그대로. "
            "의역·요약·추가 서술 금지 — 원문에 없는 사실을 만들지 말 것. "
            '반드시 JSON 객체로만 응답: {"0":"번역문","1":"번역문",...} (키=번호 문자열).\n\n'
            + numbered
        )
        resp = client.models.generate_content(
            model=GEMINI_MODEL_CHAT,
            contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0},
        )
        raw = (getattr(resp, "text", "") or "").strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return {}
        obj = json.loads(m.group(0))
        out: Dict[str, str] = {}
        for k, v in obj.items():
            try:
                idx = int(k)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(texts) and isinstance(v, str) and v.strip():
                out[texts[idx]] = v.strip()
        return out
    except Exception as e:                                     # noqa: BLE001
        logger.warning("[profile] 번역 실패(원문 유지): %s", e)
        return {}


def load_cache() -> Dict[str, Any]:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def collect_profiles(institutions: List[str], refresh: bool = False) -> Dict[str, Any]:
    """기관 목록 → 프로필 dict. 기존 캐시는 보존(전기 사실은 거의 안 변함 + 위키 호출 절약)."""
    cache = load_cache()
    for inst in institutions:
        if not refresh and cache.get(inst):
            continue
        p = fetch_profile(inst)
        if p:
            cache[inst] = p

    # 영문 프로필만 한국어 병기 (한국어 위키에서 온 건 그대로).
    need = [
        v["summary"] for v in cache.values()
        if isinstance(v, dict) and v.get("lang") != "ko"
        and v.get("summary") and not v.get("summary_ko")
    ]
    if need:
        ko = _translate_ko(need)
        for v in cache.values():
            if isinstance(v, dict) and ko.get(v.get("summary") or ""):
                v["summary_ko"] = ko[v["summary"]]

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CACHE_PATH)
    return cache
