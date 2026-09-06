"""investor_profiles — 거장 인물 사진 라이선스 메타 수집.

2026-07-30 신설 (PM 요청 — "인물 설명도. 뭘 창업했고 엑싯했고 등등").

전기적 사실은 공식 기관 원문만 쓰며 공개 컴포넌트의 PROFILE_PROOFS가 담당한다.
이 모듈은 자유 라이선스가 확인된 사진과 저작자 표시 정보만 제공한다.

🚨🚨 동명이인 가드 — 제목 매칭만으로는 틀린 사람이 붙는다.
   실측(2026-07-30): 한국어 위키 "캐서린 우드" 는 **1914년생 소설가 캐서린 마셜**을 반환한다.
   그대로 실었으면 ARK 캐시 우드 카드에 소설가 약력이 붙었다.
   → extract 에 투자/사업 관련 직업 키워드가 없으면 폐기하고 다음 후보로 넘어간다.
   식별용 extract 는 저장하거나 공개하지 않는다.
"""
from __future__ import annotations

import html
import json
import logging
import re
import os
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote

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

# 기관 → 사진 식별 후보 (한국어 우선, 영문 fallback). 공개 사실 출처로 사용하지 않는다.
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
    """인물 식별 후 자유 라이선스 사진 메타만 반환한다."""
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
    out = {
        "name": j.get("title"),
        "lang": lang,
    }
    img = _fetch_image(j)
    if img:
        out["image"] = img
    return out


# ── 인물 사진 (2026-07-30 신설) ──────────────────────────────────────────────
# 프로필 텍스트와 같은 위키 경로에서 사진만 추가. 새 소스 0.
#
# 🚨 fail-closed — 자유 라이선스로 **확인된** 사진만 싣는다.
#   영문 위키백과는 생존 인물의 비자유 이미지를 금지(자유 대체본 생성 가능)하므로 실측상
#   대부분 CC/PD 지만, 정책에 기대지 않고 파일별 extmetadata 를 매번 확인한다.
#   라이선스 판정 실패 = 사진 생략. 조용히 권리 미확인본을 공개하지 않는다.
#   실측(2026-07-30, 추적 16인): 자유 라이선스 11 / 위키에 사진 자체 없음 5 / 판정불가 0.
#
# CC BY·BY-SA 는 저작자 표시가 의무 → artist/license/license_url 을 함께 저장해
# 컴포넌트가 사진 옆에 표기할 수 있게 한다. 표기 없이 쓰면 라이선스 위반이다.
# BY-SA 는 동일조건 변경허락이 걸리므로 원본을 자르기/리사이즈만 할 것(합성·색보정 금지).
_FREE_LICENSE_HINTS = ("cc0", "cc by", "cc-by", "public domain", "pd-", "attribution")


def _image_filename(url: str) -> Optional[str]:
    """업로드 URL → File: 이름. thumb 경로는 .../thumb/a/bc/<파일명>/<크기>-... 구조."""
    if not url:
        return None
    if "/thumb/" in url:
        parts = url.split("/thumb/", 1)[1].split("/")
        return unquote(parts[2]) if len(parts) > 2 else None
    return unquote(url.rsplit("/", 1)[-1])


def _fetch_image(summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """REST summary 응답 → 자유 라이선스 사진 메타. 미확인이면 None."""
    thumb = (summary.get("thumbnail") or {}).get("source")
    if not thumb:
        return None
    fname = _image_filename(thumb)
    if not fname:
        return None
    for host in ("commons.wikimedia.org", "en.wikipedia.org"):
        try:
            r = requests.get(
                f"https://{host}/w/api.php",
                params={"action": "query", "titles": f"File:{fname}",
                        "prop": "imageinfo", "iiprop": "extmetadata", "format": "json"},
                headers=_UA, timeout=15,
            )
            if r.status_code != 200:
                continue
            page = list(r.json()["query"]["pages"].values())[0]
            meta = page["imageinfo"][0]["extmetadata"]
        except Exception:                                          # noqa: BLE001
            continue
        lic = (meta.get("LicenseShortName", {}).get("value") or "").strip()
        if not any(h in lic.lower() for h in _FREE_LICENSE_HINTS):
            logger.warning("[profile] %s 사진 생략 — 자유 라이선스 아님/미확인(%s)", fname, lic or "?")
            return None
        # Artist 는 HTML 조각으로 온다 — 태그 제거 후 엔티티까지 풀어야 화면에 '&amp;' 가 안 남는다.
        artist = html.unescape(
            re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value") or "")
        ).strip()
        artist = re.sub(r"\s+", " ", artist)
        return {
            "url": thumb,
            "width": (summary.get("thumbnail") or {}).get("width"),
            "height": (summary.get("thumbnail") or {}).get("height"),
            "artist": artist[:120] or None,
            "license": lic,
            "license_url": (meta.get("LicenseUrl", {}).get("value") or "").strip() or None,
            "file_page": f"https://{host}/wiki/File:{quote(fname)}",
        }
    logger.warning("[profile] %s 사진 생략 — 라이선스 조회 실패", fname)
    return None


def backfill_images(cache: Dict[str, Any]) -> int:
    """기존 캐시 항목에 사진만 덧붙인다 (텍스트 재조회 없음).

    캐시가 이미 차 있으면 collect_profiles 가 fetch_profile 을 건너뛰므로, 이 경로가 없으면
    사진이 영원히 안 붙는다. image 키가 이미 있으면(성공이든 실패 후 None 이든) 재시도하지 않는다.
    """
    added = 0
    for inst, v in cache.items():
        if not isinstance(v, dict) or "image" in v or not v.get("name"):
            continue
        lang = v.get("lang") or "en"
        try:
            r = requests.get(
                f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(v['name'])}",
                headers=_UA, timeout=15)
            j = r.json() if r.status_code == 200 else {}
        except Exception:                                          # noqa: BLE001
            j = {}
        img = _fetch_image(j) if j else None
        v["image"] = img          # None 도 기록 — 매 run 재조회 방지
        if img:
            added += 1
        time.sleep(0.25)
    return added


def fetch_profile(institution: str) -> Optional[Dict[str, Any]]:
    for lang, title in WIKI_CANDIDATES.get(institution, []):
        got = _fetch_summary(lang, title)
        time.sleep(0.25)                                       # 위키 예의상 스로틀
        if got:
            return got
    logger.warning("[profile] %s — 후보 소진, 프로필 없음", institution)
    return None


def _image_only_profile(value: Any) -> Optional[Dict[str, Any]]:
    """옛 전기 캐시에서 사진 관련 필드만 남긴다."""
    if not isinstance(value, dict):
        return None
    out: Dict[str, Any] = {}
    if value.get("name"):
        out["name"] = value["name"]
    if value.get("lang"):
        out["lang"] = value["lang"]
    if "image" in value:
        out["image"] = value.get("image")
    return out or None


def load_cache() -> Dict[str, Any]:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def collect_profiles(institutions: List[str], refresh: bool = False) -> Dict[str, Any]:
    """기관 목록 → 자유 라이선스 사진 메타. 전기 문장은 저장하지 않는다."""
    cache = {
        inst: cleaned
        for inst, value in load_cache().items()
        if (cleaned := _image_only_profile(value)) is not None
    }
    for inst in institutions:
        if not refresh and cache.get(inst):
            continue
        p = fetch_profile(inst)
        if p:
            cache[inst] = p

    # 기존 캐시 항목에 사진 백필 (2026-07-30). 캐시가 이미 차 있으면 위 루프가 skip 되므로
    # 이 경로가 없으면 사진이 영원히 안 붙는다. image 키가 있으면 재조회하지 않는다.
    n_img = backfill_images(cache)
    if n_img:
        logger.info("[profile] 사진 %d건 신규 확보", n_img)

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CACHE_PATH)
    return cache
