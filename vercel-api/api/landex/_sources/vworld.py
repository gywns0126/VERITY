"""VWORLD (국토부 공간정보 오픈플랫폼) 지오코더 어댑터.

용도: estate_corp_facilities.location_gu 정확도 향상.
기존 정규식 방식(scripts/estate_corp_snapshot.extract_location_si_gu)이 실패하는
케이스를 VWORLD API 로 보강.

API 사양 (실측 검증 2026-04-29):
  - 엔드포인트: https://api.vworld.kr/req/address
  - 파라미터: service=address, request=getCoord, version=2.0, key=..., address=...,
              refine=true, simple=false, type=ROAD|PARCEL, crs=epsg:4326, format=json
  - 응답 파싱 위치: response.refined.structure (NOT response.result.structure)
    * level1 = 시도 (예: "서울특별시", "경기도")
    * level2 = 시군구 (서울 → "강남구", 성남 → "성남시 분당구" — 합쳐 나옴)
    * level3 = 읍면동 (예: "역삼동")
    * level4A / level4AC = 행정동명 / 행정동코드
  - 좌표: response.result.point.{x, y}
  - status: "OK" | "NOT_FOUND" | "ERROR"

전략:
  1) ROAD 먼저 시도 (도로명주소가 정확하면 1차 성공)
  2) NOT_FOUND 면 PARCEL 시도 (지번주소)
  3) 둘 다 실패 → None (호출자가 정규식 fallback)
  4) 메모리 LRU 캐시 — 동일 주소 재호출 방지 (운영 비용 ↓)

일일 한도: VWORLD 무료 키는 통상 30,000회/일. 초과 시 status=ERROR.
사용자 액션: vworld.kr 가입 후 V_WORLD_API_KEY env 등록.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

import requests

_logger = logging.getLogger(__name__)

VWORLD_BASE = "https://api.vworld.kr/req/address"

# 서울 25구 정규화용 (level2 가 "강남구" 같이 단독으로 나오는 경우)
SEOUL_GU_NAMES = frozenset([
    "강남구", "강동구", "강북구", "강서구", "관악구", "광진구",
    "구로구", "금천구", "노원구", "도봉구", "동대문구", "동작구",
    "마포구", "서대문구", "서초구", "성동구", "성북구", "송파구",
    "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구",
])


def _api_key() -> str:
    return os.environ.get("V_WORLD_API_KEY", "").strip()


def _kst_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=9)))


def _call_vworld(address: str, type_: str, timeout: float = 8.0) -> Optional[dict]:
    """VWORLD 단일 호출. status=OK 면 response 객체, 아니면 None."""
    key = _api_key()
    if not key:
        return None
    params = {
        "service": "address", "request": "getCoord", "version": "2.0",
        "crs": "epsg:4326", "key": key, "address": address,
        "refine": "true", "simple": "false",
        "type": type_, "format": "json",
    }
    try:
        r = requests.get(VWORLD_BASE, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        _logger.warning("VWORLD fetch 실패 (%s, %s): %s", address[:50], type_, e)
        return None

    resp = data.get("response") or {}
    status = resp.get("status")
    if status == "OK":
        return resp
    if status == "ERROR":
        # 일일 한도 초과·키 오류 등 — 로그 남기고 None
        err_text = (resp.get("error") or {}).get("text") or ""
        _logger.warning("VWORLD ERROR (%s): %s", address[:50], err_text)
    return None


@lru_cache(maxsize=4096)
def _geocode_cached(address: str, timeout: float = 8.0) -> Optional[dict]:
    """캐시된 지오코딩. 동일 주소 재호출 시 API 안 부름.

    Returns dict | None. None 이면 (키 없음 | NOT_FOUND | ERROR | 네트워크 실패).
    """
    if not address or not address.strip():
        return None
    addr = address.strip()

    # ROAD 먼저, NOT_FOUND 면 PARCEL
    for type_ in ("ROAD", "PARCEL"):
        resp = _call_vworld(addr, type_, timeout=timeout)
        if resp is None:
            continue
        struct = (resp.get("refined") or {}).get("structure") or {}
        point = (resp.get("result") or {}).get("point") or {}
        if not struct.get("level1"):
            continue
        return {
            "level1": struct.get("level1"),     # 시도
            "level2": struct.get("level2"),     # 시군구 (서울:"강남구" / 성남:"성남시 분당구")
            "level3": struct.get("level3"),     # 읍면동
            "level4A": struct.get("level4A"),   # 행정동
            "level4AC": struct.get("level4AC"), # 행정동코드
            "x": point.get("x"),                # 경도
            "y": point.get("y"),                # 위도
            "matched_type": type_,
            "refined_text": (resp.get("refined") or {}).get("text"),
        }
    return None


def geocode(address: str, timeout: float = 8.0) -> Optional[dict]:
    """주소 → 행정구역 + 좌표. None 이면 호출자가 정규식 fallback.

    Returns:
      {
        "level1": "서울특별시",
        "level2": "강남구",
        "level3": "역삼동",
        "level4A": "역삼1동", "level4AC": "1168064000",
        "x": "127.036514469", "y": "37.500028534",
        "matched_type": "ROAD" | "PARCEL",
        "refined_text": "서울특별시 강남구 테헤란로 152 (역삼동)",
        "as_of": "2026-04-29T...",  # 호출 시각
        "source": "vworld",
      }
    """
    out = _geocode_cached(address, timeout=timeout)
    if out is None:
        return None
    return {
        **out,
        "as_of": _kst_now().isoformat(timespec="seconds"),
        "source": "vworld",
    }


def extract_location_gu(address: str, timeout: float = 8.0) -> Optional[str]:
    """주소 → 시군구 단일 문자열. ESTATE 의 location_gu 채움 용도.

    서울 자치구는 "강남구" 같은 단순 형태.
    경기/광역시 일반구(분당/수성/마포 등)는 VWORLD 가 "성남시 분당구" 처럼 합쳐 반환 — 그대로 보존.

    None 이면 VWORLD 실패 또는 키 없음. 호출자가 fallback.
    """
    g = geocode(address, timeout=timeout)
    if g is None:
        return None
    level2 = g.get("level2")
    if not level2:
        return None
    return level2.strip() or None


def is_seoul_gu(level2: Optional[str]) -> bool:
    """level2 값이 서울 25구 중 하나인지."""
    return bool(level2 and level2.strip() in SEOUL_GU_NAMES)


def clear_cache() -> None:
    """테스트·운영 reset 용."""
    _geocode_cached.cache_clear()
