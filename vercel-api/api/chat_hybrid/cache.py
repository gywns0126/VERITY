"""
VERITY Chat Hybrid — 3단 TTL + LRU 캐시

캐시 계층 (TTL 다름):
  news       — 5분. 종목 뉴스 반복 조회 (예: "NVDA 오늘 뉴스?" 5분 내 동일 질문)
  perplexity — 3분. 동일 쿼리 연타 방지
  brain      — 1분. Brain 점수·컨텍스트 재연산 회피
  grounding  — 3분. Perplexity 와 동일 정책
  intent     — 10분. 동일 쿼리 의도 재분류 방지

저장소: OrderedDict + threading.Lock (Vercel Python serverless 환경에서 프로세스
수명 동안 유효. cold start 시 초기화되지만 warm 동안 캐시 hit).

경계 장치 (2026-04-22 preflight #6 대응):
  - 계층별 _MAX_ENTRIES (기본 500, env `CHAT_HYBRID_CACHE_MAX` 로 조절).
  - set 시 초과하면: 먼저 만료 엔트리 sweep → 그래도 초과면 LRU 퇴출.
  - get 은 HIT 시 move_to_end 하여 LRU ordering 갱신.

향후 확장: Vercel KV / Redis backend 선택 (CHAT_HYBRID_CACHE_BACKEND env).
"""
from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional


_TTL = {
    "news": 5 * 60,          # 5분
    "perplexity": 3 * 60,    # 3분
    "brain": 1 * 60,         # 1분
    "grounding": 3 * 60,     # Perplexity 와 동일 정책
    "intent": 10 * 60,       # 10분 (동일 쿼리 의도 재분류 방지)
}

# 계층당 최대 엔트리 수 — 메모리 OOM 방지. 초과시 LRU 퇴출.
_MAX_ENTRIES = max(1, int(os.environ.get("CHAT_HYBRID_CACHE_MAX", "500") or 500))


class _TieredCache:
    """계층별 TTL + LRU + thread-safe in-memory 캐시."""

    def __init__(self):
        self._lock = threading.Lock()
        # {tier: OrderedDict[key, (value, expire_ts)]} — LRU: 최근 사용일수록 뒤쪽
        self._store: Dict[str, "OrderedDict[str, tuple]"] = {
            t: OrderedDict() for t in _TTL
        }
        self._stats: Dict[str, Dict[str, int]] = {
            t: {"hit": 0, "miss": 0, "set": 0, "evict": 0} for t in _TTL
        }

    def _now(self) -> float:
        return time.time()

    def get(self, tier: str, key: str) -> Optional[Any]:
        if tier not in self._store or not key:
            return None
        with self._lock:
            tier_store = self._store[tier]
            entry = tier_store.get(key)
            if entry is None:
                self._stats[tier]["miss"] += 1
                return None
            value, expire_ts = entry
            if self._now() >= expire_ts:
                tier_store.pop(key, None)
                self._stats[tier]["miss"] += 1
                return None
            # LRU — 최근 사용 표기
            tier_store.move_to_end(key)
            self._stats[tier]["hit"] += 1
            return value

    def set(self, tier: str, key: str, value: Any, ttl_override: Optional[float] = None) -> None:
        if tier not in self._store or not key:
            return
        ttl = ttl_override if ttl_override is not None else _TTL[tier]
        with self._lock:
            tier_store = self._store[tier]
            tier_store[key] = (value, self._now() + ttl)
            tier_store.move_to_end(key)
            self._stats[tier]["set"] += 1

            # 크기 제한 초과 — 만료 sweep 후에도 초과면 LRU 퇴출
            if len(tier_store) > _MAX_ENTRIES:
                now = self._now()
                expired_keys = [k for k, v in tier_store.items() if v[1] <= now]
                for k in expired_keys:
                    tier_store.pop(k, None)
                while len(tier_store) > _MAX_ENTRIES:
                    tier_store.popitem(last=False)
                    self._stats[tier]["evict"] += 1

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
                    "max_entries": _MAX_ENTRIES,
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
