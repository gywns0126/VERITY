"""
VERITY Chat Hybrid — 결정적 종목명→코드 resolver (L2, 2026-06-03)

한계 돌파: B(KIS 시세)는 6자리 코드에 의존하는데, 코드 출처가 classifier(LLM)라
"삼성전자→005930" 변환을 LLM 이 놓치거나(누락) 틀리게(환각) 할 수 있었다.
DART 전체 상장사 마스터({종목코드:종목명}, ~3,965)에서 역맵을 만들어 query 내 종목명을
**결정적으로** 코드 변환한다 — LLM 무관 → 코드 환각 0.

source: data/kr_stock_names.json (dart_corp_code.build_mapping 생성, publish 됨).
  - 로컬 우선(서버/GH), 없으면 blob URL 폴백(Vercel). 부재 시 [] 반환 = web grounding 폴백.
※ dart_fss 등 백엔드 의존 없음 — 순수 JSON read (Vercel 번들 호환).
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_URL_CACHE_TTL = 3600.0  # 이름맵은 월1회 갱신이라 1시간 캐시 충분
_cache: Dict[str, Any] = {"pairs": None, "ts": 0.0}


def _name_map_url() -> str:
    return os.environ.get(
        "KR_STOCK_NAMES_URL",
        "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/kr_stock_names.json",
    )


def _local_path() -> str:
    try:
        from api.config import DATA_DIR
        return os.path.join(DATA_DIR, "kr_stock_names.json")
    except Exception:
        return ""


def _load_raw() -> Dict[str, str]:
    """{종목코드: 종목명} 로드 (로컬 우선, URL 폴백). 실패 시 {}."""
    p = _local_path()
    if p and os.path.isfile(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                return d
        except (json.JSONDecodeError, OSError):
            pass
    try:
        import urllib.request
        req = urllib.request.Request(_name_map_url(), headers={"User-Agent": "VERITY-Chat-Hybrid/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception as e:
        logger.warning("kr_stock_names 로드 실패: %s", e)
        return {}


def _sorted_pairs() -> List[Tuple[str, str]]:
    """[(name, code)] — 이름 길이 내림차순 (최장 우선 매칭). 1시간 캐시."""
    now = time.time()
    if _cache["pairs"] is not None and now - _cache["ts"] < _URL_CACHE_TTL:
        return _cache["pairs"]
    raw = _load_raw()
    pairs = [
        (str(name).strip(), str(code).strip())
        for code, name in raw.items()
        if name and code and len(str(name).strip()) >= 2  # 1글자 이름 = 오매칭 위험 제외
    ]
    pairs.sort(key=lambda nc: len(nc[0]), reverse=True)
    _cache["pairs"] = pairs
    _cache["ts"] = now
    return pairs


def resolve(query: str, exclude: Optional[Any] = None, limit: int = 3) -> List[str]:
    """query 텍스트에서 종목명을 찾아 코드 리스트 반환 (결정적, LLM 무관).

    - 최장 이름 우선 + 매칭 span 을 공백처리 → 짧은 이름이 긴 이름 내부에서 재매칭되는 것 방지
      (예: '삼성전자' 매칭 후 '삼성'이 그 자리에서 또 매칭되지 않음).
    - exclude(이미 유니버스 매칭된 코드)는 제외. 최대 limit 개.
    """
    if not query:
        return []
    pairs = _sorted_pairs()
    if not pairs:
        return []
    excl = {str(e).strip().upper() for e in (exclude or [])}
    q = str(query)
    found: List[str] = []
    seen = set()
    for name, code in pairs:
        cu = code.upper()
        if cu in excl or cu in seen:
            continue
        idx = q.find(name)
        if idx >= 0:
            found.append(code)
            seen.add(cu)
            # 매칭 구간 blank 처리 — 부분 문자열 이름 재매칭 차단
            q = q[:idx] + (" " * len(name)) + q[idx + len(name):]
            if len(found) >= limit:
                break
    return found
