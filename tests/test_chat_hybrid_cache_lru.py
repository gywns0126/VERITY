"""api/chat_hybrid/cache.py — LRU + TTL + maxsize 검증 (preflight #6).

이전 구현은 dict + opportunistic expired sweep 만 있어 warm 인스턴스가 오래
살 경우 무한 증가 가능했음. _MAX_ENTRIES + LRU 퇴출 도입 회귀 방지.
"""
import importlib
import os
import time

import pytest


@pytest.fixture
def cache_mod(monkeypatch):
    """계층당 최대 3개로 제한한 상태의 cache 모듈을 reload 하여 반환."""
    monkeypatch.setenv("CHAT_HYBRID_CACHE_MAX", "3")
    from api.chat_hybrid import cache as mod
    importlib.reload(mod)
    mod.clear()
    yield mod
    # 다음 테스트에 영향 없도록 기본값으로 복구
    monkeypatch.delenv("CHAT_HYBRID_CACHE_MAX", raising=False)
    importlib.reload(mod)


def test_basic_set_get(cache_mod):
    cache_mod.set_value("news", "k1", "v1")
    assert cache_mod.get("news", "k1") == "v1"


def test_miss_on_unknown_key(cache_mod):
    assert cache_mod.get("news", "nope") is None


def test_ttl_expiry_returns_miss(cache_mod):
    cache_mod.set_value("news", "k", "v", ttl_override=0.05)
    time.sleep(0.1)
    assert cache_mod.get("news", "k") is None
    # 만료 시 stats miss 로 집계
    s = cache_mod.stats()["news"]
    assert s["miss"] >= 1


def test_max_entries_evicts_oldest(cache_mod):
    """_MAX_ENTRIES 초과 시 LRU 퇴출 발생."""
    for i in range(5):
        cache_mod.set_value("news", f"k{i}", f"v{i}")
    s = cache_mod.stats()["news"]
    assert s["size"] == 3
    assert s["evict"] == 2
    # 가장 오래된 키 2개는 없어져 있어야
    assert cache_mod.get("news", "k0") is None
    assert cache_mod.get("news", "k1") is None
    assert cache_mod.get("news", "k2") == "v2"
    assert cache_mod.get("news", "k3") == "v3"
    assert cache_mod.get("news", "k4") == "v4"


def test_get_promotes_to_most_recent(cache_mod):
    """HIT 시 LRU 순서에서 맨 뒤로 이동 — 다음 퇴출 대상에서 제외."""
    for i in range(3):
        cache_mod.set_value("news", f"k{i}", f"v{i}")
    # k0 를 방금 사용 — 가장 오래된 것은 이제 k1
    cache_mod.get("news", "k0")
    cache_mod.set_value("news", "k3", "v3")  # 하나 초과 → k1 퇴출 기대
    assert cache_mod.get("news", "k0") == "v0"  # 살아 있어야
    assert cache_mod.get("news", "k1") is None  # LRU 퇴출 대상
    assert cache_mod.get("news", "k2") == "v2"
    assert cache_mod.get("news", "k3") == "v3"


def test_set_on_existing_key_refreshes_order(cache_mod):
    """기존 키 재입력 시 최신으로 이동."""
    for i in range(3):
        cache_mod.set_value("news", f"k{i}", f"v{i}")
    cache_mod.set_value("news", "k0", "v0_new")  # k0 재입력 — 최신 → k1 이 가장 오래됨
    cache_mod.set_value("news", "k3", "v3")
    assert cache_mod.get("news", "k0") == "v0_new"
    assert cache_mod.get("news", "k1") is None


def test_expired_entries_cleared_before_lru_eviction(cache_mod):
    """초과 시 먼저 만료 sweep, 그래도 초과면 LRU 퇴출."""
    # 2개는 짧은 TTL, 1개는 긴 TTL — 만료 sweep 만으로 해소되는 경우
    cache_mod.set_value("news", "short1", "x", ttl_override=0.05)
    cache_mod.set_value("news", "short2", "x", ttl_override=0.05)
    cache_mod.set_value("news", "long", "x", ttl_override=100)
    time.sleep(0.1)
    # 이제 추가 — 총 4 입력, max=3, 만료된 short1/short2 가 먼저 제거됨
    cache_mod.set_value("news", "fresh", "v")
    s = cache_mod.stats()["news"]
    assert s["size"] <= 3
    # LRU 퇴출 없이 만료 정리만으로 해소됐어야 함
    assert s["evict"] == 0
    assert cache_mod.get("news", "long") == "x"
    assert cache_mod.get("news", "fresh") == "v"


def test_stats_reports_size_and_max(cache_mod):
    cache_mod.set_value("news", "k", "v")
    s = cache_mod.stats()["news"]
    assert s["max_entries"] == 3
    assert s["size"] == 1
    assert "hit" in s and "miss" in s and "set" in s and "evict" in s


def test_clear_specific_tier(cache_mod):
    cache_mod.set_value("news", "k", "v")
    cache_mod.set_value("perplexity", "k", "v")
    cache_mod.clear("news")
    assert cache_mod.get("news", "k") is None
    assert cache_mod.get("perplexity", "k") == "v"


def test_unknown_tier_is_noop(cache_mod):
    """유효하지 않은 tier 는 get/set 모두 안전하게 no-op."""
    cache_mod.set_value("nope", "k", "v")  # 예외 없이 반환
    assert cache_mod.get("nope", "k") is None


def test_empty_key_is_noop(cache_mod):
    cache_mod.set_value("news", "", "v")
    assert cache_mod.get("news", "") is None
