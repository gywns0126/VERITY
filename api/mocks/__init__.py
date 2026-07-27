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


# ── mock 호출 census (2026-07-27) ───────────────────────────────────────────
# WHY: daily_realtime / daily_analysis 워크플로에 VERITY_MODE 가 없어 기본값 dev 로 도는데,
#   prod 전환 시 늘어날 유료 실호출 건수를 알 방법이 없었음. mock 레이어의 기존 logger.info 는
#   루트 로거 WARNING 레벨이라 GH Actions 로그에서 통째로 억제됨(실측: INFO 라인 0건).
#   → 비-prod 런 종료 시 mock 된 키를 집계 출력. dev 는 여전히 mock 이므로 측정 비용 0.
#   이 census 가 "prod 로 켰을 때 실호출이 될 목록" 과 1:1.
_MOCK_CENSUS: "dict[str, int]" = {}


def mock_call_census() -> "dict[str, int]":
    """이번 프로세스에서 mock 으로 대체된 키별 호출 수 (prod 였다면 실호출 건수)."""
    return dict(_MOCK_CENSUS)


def _print_mock_census() -> None:
    if config.VERITY_MODE == "prod" or not _MOCK_CENSUS:
        return
    total = sum(_MOCK_CENSUS.values())
    print(f"\n[MOCK CENSUS] VERITY_MODE={config.VERITY_MODE} — mock 대체 {total}건 "
          f"({len(_MOCK_CENSUS)} 키). prod 전환 시 이만큼이 실호출:")
    for k, n in sorted(_MOCK_CENSUS.items(), key=lambda x: -x[1]):
        print(f"    {n:5d}  {k}")


try:
    import atexit
    atexit.register(_print_mock_census)
except Exception:      # pragma: no cover — 등록 실패해도 본 기능에 영향 없음
    pass


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
                _MOCK_CENSUS[key] = _MOCK_CENSUS.get(key, 0) + 1
                logger.info(
                    "[VERITY_MODE=%s] MOCK %s (skipping %s)",
                    config.VERITY_MODE, key, fn.__qualname__,
                )
                return _resolve_mock(key)
            return fn(*args, **kwargs)
        wrapper._mock_key = key  # type: ignore[attr-defined]
        return wrapper
    return decorator
