"""
VERITY Chat Hybrid — Rate Limit

두 단계:
  1. 사용자당 분당 10회 — 폭주 방지 (실수로 연타)
  2. 글로벌 일일 500회 — 비용 cap 강제 (월 $30 유지)

초과 시 HTTP 429 메시지 반환. 기존 vercel-api/api/chat.py 의 IP 기반
rate_limit 과 별개 (hybrid 전용). orchestrator 가 진입 시점에 호출.

환경변수:
  CHAT_HYBRID_PER_MIN_CAP   — 기본 10
  CHAT_HYBRID_DAILY_CAP     — 기본 500

Vercel serverless 분산이라 per-instance 이지만 글로벌 cap 은 근사치 여전히 유효.
진짜 분산 cap 이 필요하면 Vercel KV / Upstash Redis 연동 (별도 확장).
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict
from typing import Dict, Optional, Tuple


_PER_MIN_CAP = int(os.environ.get("CHAT_HYBRID_PER_MIN_CAP", "10"))
_DAILY_CAP = int(os.environ.get("CHAT_HYBRID_DAILY_CAP", "500"))

_MIN_WINDOW = 60            # 1분
_DAY_WINDOW = 24 * 3600     # 24시간


_lock = threading.Lock()
_per_user_log: Dict[str, list] = defaultdict(list)  # {session_id: [ts, ts, ...]}
_global_log: list = []                              # [ts, ts, ...]


def _prune(log: list, window: float, now: float) -> list:
    """window 밖 ts 제거. in-place 수정 후 반환."""
    log[:] = [t for t in log if now - t < window]
    return log


def check_and_consume(session_id: str = "anonymous") -> Tuple[bool, Optional[Dict]]:
    """rate limit 체크 + 통과 시 카운트 증가.

    Returns:
        (True, None) — 통과
        (False, {"reason", "retry_after_sec", "limit_type"}) — 차단
    """
    now = time.time()
    sid = str(session_id or "anonymous")[:120]

    with _lock:
        # 1. 사용자 분당
        user_log = _per_user_log[sid]
        _prune(user_log, _MIN_WINDOW, now)
        if len(user_log) >= _PER_MIN_CAP:
            oldest = user_log[0] if user_log else now
            retry = max(1, int(_MIN_WINDOW - (now - oldest) + 1))
            return False, {
                "reason": f"분당 {_PER_MIN_CAP}회 초과",
                "retry_after_sec": retry,
                "limit_type": "per_user_minute",
            }

        # 2. 글로벌 일일
        _prune(_global_log, _DAY_WINDOW, now)
        if len(_global_log) >= _DAILY_CAP:
            oldest = _global_log[0] if _global_log else now
            retry = max(60, int(_DAY_WINDOW - (now - oldest) + 1))
            return False, {
                "reason": f"일일 호출 {_DAILY_CAP}회 초과 (비용 cap)",
                "retry_after_sec": retry,
                "limit_type": "global_daily",
            }

        # 통과 — 카운트 증가
        user_log.append(now)
        _global_log.append(now)

        # 사이즈 관리 — 오래 안 쓰는 session_id 잔존 방지
        if len(_per_user_log) > 500:
            to_remove = [
                s for s, log in _per_user_log.items()
                if not log or now - log[-1] > _MIN_WINDOW * 10
            ]
            for s in to_remove[:100]:
                _per_user_log.pop(s, None)

        return True, None


def get_status(session_id: str = "anonymous") -> Dict:
    """현재 사용량 조회 (디버깅/UI 용)."""
    now = time.time()
    sid = str(session_id or "anonymous")[:120]

    with _lock:
        user_log = list(_per_user_log.get(sid, []))
        user_log = [t for t in user_log if now - t < _MIN_WINDOW]
        global_log = [t for t in _global_log if now - t < _DAY_WINDOW]

        return {
            "per_user_minute": {
                "used": len(user_log),
                "cap": _PER_MIN_CAP,
                "remaining": max(0, _PER_MIN_CAP - len(user_log)),
            },
            "global_daily": {
                "used": len(global_log),
                "cap": _DAILY_CAP,
                "remaining": max(0, _DAILY_CAP - len(global_log)),
            },
        }


def reset() -> None:
    """테스트용 초기화."""
    with _lock:
        _per_user_log.clear()
        _global_log.clear()
