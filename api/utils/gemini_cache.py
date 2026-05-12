"""Gemini explicit context caching — 75% input token discount on cached prefix.

호출 패턴이 반복되는 system_instruction 을 서버측 캐시로 등록하고
generate_content 에 cached_content 로 참조시켜 입력 토큰 단가를 25%로 낮춘다.

- 모델별 최소 토큰: gemini-2.5-flash ≥ 1024, gemini-2.5-pro ≥ 4096 (대략).
  미달 시 caches.create() 가 거부됨 → 본 모듈은 None 을 반환하고 호출자는 무캐시 경로로 폴백.
- 동일 (model, sys_instr_hash) 조합은 프로세스 내에서 재사용 (TTL 갱신 만료 직전엔 재생성).
"""
from __future__ import annotations

import hashlib
import logging
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_CACHE_REGISTRY: Dict[Tuple[str, str], Tuple[str, float]] = {}

_DEFAULT_TTL_SECONDS = 3600


def get_or_create_cache(
    client,
    model: str,
    system_instruction: str,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
) -> Optional[str]:
    """캐시 이름을 반환 (cached_content 인자로 전달용). 실패 시 None.

    호출자는 None 일 때 평소처럼 system_instruction 직접 전달 경로로 폴백해야 한다.
    """
    if not system_instruction or not system_instruction.strip():
        return None

    sys_hash = hashlib.sha1(system_instruction.encode("utf-8")).hexdigest()[:16]
    key = (model, sys_hash)
    now = time.time()

    entry = _CACHE_REGISTRY.get(key)
    if entry and entry[1] > now + 60:
        return entry[0]

    try:
        from google.genai import types as genai_types
    except Exception as e:
        logger.debug(f"[gemini-cache] genai types import 실패: {e}")
        return None

    try:
        cache = client.caches.create(
            model=model,
            config=genai_types.CreateCachedContentConfig(
                system_instruction=system_instruction,
                ttl=f"{ttl_seconds}s",
            ),
        )
    except Exception as e:
        msg = str(e)
        if "minimum" in msg.lower() or "token" in msg.lower():
            logger.info(
                f"[gemini-cache] {model} 최소 토큰 미달로 캐시 생략 "
                f"(sys_instr {len(system_instruction)} chars)"
            )
        else:
            logger.warning(f"[gemini-cache] create 실패 model={model}: {e}")
        return None

    cache_name = getattr(cache, "name", None)
    if not cache_name:
        return None

    _CACHE_REGISTRY[key] = (cache_name, now + ttl_seconds)
    logger.info(
        f"[gemini-cache] 생성 {cache_name} model={model} ttl={ttl_seconds}s "
        f"sys_instr={len(system_instruction)}chars"
    )
    return cache_name


def generate_with_cache(client, *, model: str, contents, system_instruction: str, **extra_config):
    """generate_content 래퍼 — 캐시 등록 시도 후 cached_content 로 호출, 실패 시 직접 전달.

    호출자는 평소처럼 결과 객체를 받는다. 캐시 적용 여부는 로그로만 확인.
    """
    cache_name = get_or_create_cache(client, model, system_instruction)
    config = dict(extra_config)
    if cache_name:
        config["cached_content"] = cache_name
    else:
        config["system_instruction"] = system_instruction
    return client.models.generate_content(model=model, contents=contents, config=config)


def invalidate_all() -> None:
    """프로세스 내 등록만 비움. 원격 캐시는 TTL 만료로 자연 소멸."""
    _CACHE_REGISTRY.clear()


def cache_stats() -> dict:
    return {
        "entries": len(_CACHE_REGISTRY),
        "keys": [{"model": m, "hash": h} for (m, h) in _CACHE_REGISTRY.keys()],
    }
