"""
VERITY Mock Layer — VERITY_MODE=dev/staging 시 AI·유료 API 호출을 mock으로 대체.

사용법:
    from api.mocks import mockable

    @mockable("gemini.daily_report")
    def generate_daily_report(...): ...

동작:
    prod  → 원래 함수 실행
    dev   → 무조건 mock 반환
    staging → VERITY_STAGING_REAL_KEYS에 포함된 키만 실호출, 나머지 mock
"""
from __future__ import annotations

import copy
import functools
import logging
from typing import Any, Callable, Optional

from api import config

logger = logging.getLogger(__name__)


def _should_mock(key: str) -> bool:
    if config.VERITY_MODE == "prod":
        return False
    if config.VERITY_MODE == "dev":
        return True
    # staging: allowlist만 실호출
    return key not in config.VERITY_STAGING_REAL_KEYS


def _resolve_mock(key: str) -> Any:
    """traces 재생 → fixtures fallback → empty dict 순으로 mock 데이터 탐색."""
    # 1) traces 재생
    try:
        from api.mocks.trace_replay import load_latest_trace
        traced = load_latest_trace(key)
        if traced is not None:
            logger.info("[MOCK:%s] trace replay", key)
            return copy.deepcopy(traced)
    except Exception:
        pass

    # 2) 하드코딩 fixture
    try:
        from api.mocks.fixtures import FIXTURES
        if key in FIXTURES:
            logger.info("[MOCK:%s] fixture fallback", key)
            return copy.deepcopy(FIXTURES[key])
    except Exception:
        pass

    # 3) 최후 — 빈 dict
    logger.info("[MOCK:%s] empty fallback", key)
    return {}


def mockable(key: str):
    """데코레이터: VERITY_MODE에 따라 함수를 mock으로 대체."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if _should_mock(key):
                logger.info(
                    "[VERITY_MODE=%s] MOCK %s (skipping %s)",
                    config.VERITY_MODE, key, fn.__qualname__,
                )
                return _resolve_mock(key)
            return fn(*args, **kwargs)
        wrapper._mock_key = key  # type: ignore[attr-defined]
        return wrapper
    return decorator
