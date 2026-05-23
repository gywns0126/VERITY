"""dart_metrics — DART OpenAPI 호출 실패율 측정 (W3 4/4 완성, 2026-05-23).

설계 (yfinance_safe 패턴 정합):
  - process-level counter (attempted / failed / rate_limited)
  - DART OpenAPI 가 cross-cutting — DartScout._call 18+ endpoint + dart_fundamentals
    _fetch_fnltt_all_cached 두 경로가 공유.
  - 호출 종료 시 `record_dart_call(status, success)` 1줄. 잠금 thread-safe.
  - 측정 drain = stock_filter._log_w1_runtime 의 finally hook (W1 runtime hook 정합).

DART status 분류:
  - "000" → 성공
  - "013" → 데이터 없음 (실패 X. 미커버 종목/기간 정상 path)
  - "010"/"012" → 키/IP 차단 (실패)
  - "011"/"020" → 요청 제한 (실패 + rate_limited)
  - "100"/"800"/"900" → 입력/서버/기타 (실패)
  - "timeout"/"error" → 내부 sentinel (실패)
  - 그 외 → 실패

운영:
  - CI cron = 1 process / run → 자연 reset (carry-over 없음).
  - dev/test = reset_dart_state() 명시 호출.
  - dart_failure_rate trigger 임계 5% (ramp_up_monitor.FAIL_TRIGGER_DART_FAIL_RATE).
"""
from __future__ import annotations

import threading
from typing import Dict


# 성공 status (실패 카운터 미증가)
_SUCCESS_STATUSES = frozenset({"000", "013"})

# rate limit status (실패 + rate_limited 카운터 둘 다)
_RATE_LIMIT_STATUSES = frozenset({"011", "020"})


_lock = threading.Lock()
_state: Dict[str, int] = {
    "dart_attempted": 0,
    "dart_failed": 0,
    "dart_rate_limited": 0,
}


def record_dart_call(status: str) -> None:
    """DART OpenAPI 호출 1건 기록.

    Args:
        status: DART 응답 status 문자열. "000"/"013" 성공, 그 외 실패.
                "timeout"/"error" sentinel 도 실패로 집계.
    """
    s = (status or "").strip()
    is_success = s in _SUCCESS_STATUSES
    is_rate_limited = s in _RATE_LIMIT_STATUSES
    with _lock:
        _state["dart_attempted"] += 1
        if not is_success:
            _state["dart_failed"] += 1
        if is_rate_limited:
            _state["dart_rate_limited"] += 1


def get_dart_snapshot() -> Dict[str, int]:
    """현재 누적 카운터 snapshot (drain 용).

    Returns:
        {"dart_attempted": int, "dart_failed": int, "dart_rate_limited": int}
    """
    with _lock:
        return dict(_state)


def compute_dart_failure_rate() -> float:
    """dart_failed / dart_attempted. attempted=0 → 0.0 (호출 없음 = 실패 0)."""
    snap = get_dart_snapshot()
    attempted = snap["dart_attempted"]
    if attempted <= 0:
        return 0.0
    return snap["dart_failed"] / attempted


def reset_dart_state() -> None:
    """테스트/dev 명시 reset. CI cron 은 process 자연 reset."""
    with _lock:
        _state["dart_attempted"] = 0
        _state["dart_failed"] = 0
        _state["dart_rate_limited"] = 0
