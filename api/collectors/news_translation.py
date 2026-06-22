"""뉴스 영어 헤드라인 → 한글 build-time 사전번역.

골든구스 뉴스탭 '미국' 탭의 영어 헤드라인에 title_ko 를 미리 적재(컴포넌트 ko/en 토글용).
- 번역기 = Gemini flash-lite (GEMINI_MODEL_CHAT) — Claude budget guard 회피, 최저비용.
- 캐시 = data/news_translation_cache.json (영문 title → ko). cache miss 만 호출 → 비용 선형 억제.
- 실패/키부재 시 graceful: cache hit 만 반환, 신규는 빈값(컴포넌트가 영문 fallback) — 파이프라인 무중단.
- 번역 = 사실 전달 유틸(narrative/점수/의견 생성 아님). RULE 6 경계 통과.
"""
import json
import os
import re
from typing import Dict, List

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_PATH = os.path.join(_ROOT, "data", "news_translation_cache.json")
MAX_NEW_PER_RUN = 100  # 신규 번역 cron 당 상한 (비용 가드). 종목 헤드라인 75개 + 미국 15개를 한 run에 전량 처리(stragglers 방지). Gemini flash-lite 1 batch call 비용 미미.
CACHE_CAP = 3000  # 캐시 size 상한 (최근 우선 유지)


def _has_hangul(s: str) -> bool:
    return bool(re.search(r"[가-힣]", s or ""))


def _load_cache() -> Dict[str, str]:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_cache(cache: Dict[str, str]) -> None:
    try:
        if len(cache) > CACHE_CAP:
            cache = dict(list(cache.items())[-CACHE_CAP:])
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


def _gemini_translate(titles: List[str]) -> Dict[str, str]:
    """영어 title list → {title: ko}. 1회 batch 호출. 실패 시 {}."""
    if not titles:
        return {}
    try:
        from google import genai
        from api.config import GEMINI_API_KEY, GEMINI_MODEL_CHAT

        if not GEMINI_API_KEY:
            return {}
        client = genai.Client(api_key=GEMINI_API_KEY)
        numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))
        prompt = (
            "다음 영어 금융 뉴스 헤드라인들을 자연스러운 한국어로 번역하라. "
            "고유명사(기업명·인명·티커)는 통용 표기 유지, 의역보다 정확성 우선. "
            '반드시 JSON 객체로만 응답: {"0":"번역문","1":"번역문",...} (키=번호 문자열).\n\n'
            + numbered
        )
        resp = client.models.generate_content(
            model=GEMINI_MODEL_CHAT,
            contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0},
        )
        text = (getattr(resp, "text", "") or "").strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
        data = json.loads(text)
        out: Dict[str, str] = {}
        for i, t in enumerate(titles):
            ko = data.get(str(i))
            if isinstance(ko, str) and ko.strip() and _has_hangul(ko):
                out[t] = ko.strip()
        return out
    except Exception:  # noqa: BLE001
        return {}


def translate_headlines_ko(titles: List[str]) -> Dict[str, str]:
    """영어 헤드라인 list → {원문 title: 한글}. 캐시 우선, miss 만 LLM batch 호출.

    이미 한글이 섞인 제목(미국 키워드 매칭된 국내 기사 등)은 번역 불필요 → 원문 그대로 매핑.
    """
    uniq: List[str] = []
    seen = set()
    for t in titles:
        if isinstance(t, str) and t.strip() and t not in seen:
            seen.add(t)
            uniq.append(t.strip())
    if not uniq:
        return {}

    cache = _load_cache()
    result: Dict[str, str] = {}
    misses: List[str] = []
    for t in uniq:
        if t in cache:
            result[t] = cache[t]
        elif _has_hangul(t):
            result[t] = t  # 이미 한국어 — 토글 시 그대로 노출
        else:
            misses.append(t)

    if misses:
        new = _gemini_translate(misses[:MAX_NEW_PER_RUN])
        if new:
            cache.update(new)
            result.update(new)
            _save_cache(cache)
    return result
