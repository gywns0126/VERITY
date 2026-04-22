"""
VERITY Chat Hybrid — 3단 TTL 캐시

캐시 계층 (TTL 다름):
  news       — 5분. 종목 뉴스 반복 조회 (예: "NVDA 오늘 뉴스?" 5분 내 동일 질문)
  perplexity — 3분. 동일 쿼리 연타 방지
  brain      — 1분. Brain 점수·컨텍스트 재연산 회피

in-memory dict + threading.Lock (Vercel Python serverless 환경에서 프로세스
수명 동안 유효. cold start 시 초기화되지만 warm 동안 캐시 hit).

향후 확장: Vercel KV / Redis backend 선택 (CHAT_HYBRID_CACHE_BACKEND env).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional


_TTL = {
    "news": 5 * 60,          # 5분
    "perplexity": 3 * 60,    # 3분
    "brain": 1 * 60,         # 1분
    "grounding": 3 * 60,     # Perplexity 와 동일 정책
    "intent": 10 * 60,       # 10분 (동일 쿼리 의도 재분류 방지)
}


class _TieredCache:
    """계층별 TTL + thread-safe in-memory 캐시."""

    def __init__(self):
        self._lock = threading.Lock()
        # {tier: {key: (value, expire_ts)}}
        self._store: Dict[str, Dict[str, tuple]] = {t: {} for t in _TTL}
        self._stats: Dict[str, Dict[str, int]] = {
            t: {"hit": 0, "miss": 0, "set": 0} for t in _TTL
        }

    def _now(self) -> float:
        return time.time()

    def get(self, tier: str, key: str) -> Optional[Any]:
        if tier not in self._store or not key:
            return None
        with self._lock:
            entry = self._store[tier].get(key)
            if entry is None:
                self._stats[tier]["miss"] += 1
                return None
            value, expire_ts = entry
            if self._now() >= expire_ts:
                # 만료 제거
                self._store[tier].pop(key, None)
                self._stats[tier]["miss"] += 1
                return None
            self._stats[tier]["hit"] += 1
            return value

    def set(self, tier: str, key: str, value: Any, ttl_override: Optional[float] = None) -> None:
        if tier not in self._store or not key:
            return
        ttl = ttl_override if ttl_override is not None else _TTL[tier]
        with self._lock:
            self._store[tier][key] = (value, self._now() + ttl)
            self._stats[tier]["set"] += 1
            # 간단 cleanup: 100개 초과 시 만료된 항목 제거
            if len(self._store[tier]) > 100:
                now = self._now()
                self._store[tier] = {
                    k: v for k, v in self._store[tier].items() if v[1] > now
                }

    def clear(self, tier: Optional[str] = None) -> None:
        with self._lock:
            if tier is None:
                for t in self._store:
                    self._store[t].clear()
            elif tier in self._store:
                self._store[tier].clear()

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            result = {}
            for tier, s in self._stats.items():
                total = s["hit"] + s["miss"]
                hit_rate = round(s["hit"] / total * 100, 1) if total > 0 else 0.0
                result[tier] = {
                    **s,
                    "total_reads": total,
                    "hit_rate_pct": hit_rate,
                    "size": len(self._store[tier]),
                }
            return result


# 모듈 싱글턴
_cache = _TieredCache()


def get(tier: str, key: str) -> Optional[Any]:
    return _cache.get(tier, key)


def set_value(tier: str, key: str, value: Any, ttl_override: Optional[float] = None) -> None:
    _cache.set(tier, key, value, ttl_override)


def clear(tier: Optional[str] = None) -> None:
    _cache.clear(tier)


def stats() -> Dict[str, Any]:
    return _cache.stats()
