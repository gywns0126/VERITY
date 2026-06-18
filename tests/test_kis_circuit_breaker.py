"""KIS 연결 circuit breaker 검증 (2026-06-18).

사고: KIS 외부 불통 시 realtime 시세/호가/체결 콜이 각 connect timeout(10s)로 직렬 실패 →
10분 watchdog 예산 소진 → 첫 save_portfolio 전 SIGTERM → portfolio 미저장 (6/4·6/10·6/18 재발).
breaker: 연속 연결 실패 N회 → open → 이후 _get/_post 즉시 raise(네트워크 시도 0) → 예산 보호.
"""
import time

import pytest
import requests

import api.trading.kis_broker as kb
from api.trading.kis_broker import KISBroker, KISCircuitOpen


@pytest.fixture(autouse=True)
def _reset_breaker():
    KISBroker._cb_consecutive_failures = 0
    KISBroker._cb_open_until = 0.0
    yield
    KISBroker._cb_consecutive_failures = 0
    KISBroker._cb_open_until = 0.0


def _broker():
    # __init__ 우회 — 네트워크/토큰 무관하게 _get 만 검사
    b = KISBroker.__new__(KISBroker)
    b.base_url = kb._PROD_URL
    return b


def _patch_conn_fail(monkeypatch):
    def _boom(*a, **k):
        raise requests.ConnectionError("connect timeout simulated")
    monkeypatch.setattr(kb.requests, "get", _boom)
    monkeypatch.setattr(KISBroker, "_auth_headers", lambda self: {}, raising=False)
    monkeypatch.setattr(KISBroker, "_tr_id", lambda self, t: t, raising=False)


def test_breaker_trips_after_threshold_then_fast_fails(monkeypatch):
    _patch_conn_fail(monkeypatch)
    b = _broker()
    # threshold 직전까지 = 실제 ConnectionError (네트워크 시도)
    for _ in range(kb._KIS_CB_FAIL_THRESHOLD):
        with pytest.raises(requests.ConnectionError):
            b._get("/p", "TR", {})
    assert KISBroker._cb_open_until > 0  # trip
    # open 상태 = 네트워크 시도 없이 KISCircuitOpen 즉시 (requests.get 호출 안 됨)
    calls = {"n": 0}
    monkeypatch.setattr(kb.requests, "get", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1))
    with pytest.raises(KISCircuitOpen):
        b._get("/p", "TR", {})
    assert calls["n"] == 0  # 네트워크 0회 = 예산 보호


def test_success_resets_breaker(monkeypatch):
    b = _broker()
    monkeypatch.setattr(KISBroker, "_auth_headers", lambda self: {}, raising=False)
    monkeypatch.setattr(KISBroker, "_tr_id", lambda self, t: t, raising=False)
    KISBroker._cb_consecutive_failures = 2  # threshold 직전

    class _OK:
        def raise_for_status(self): pass
        def json(self): return {"rt_cd": "0"}
    monkeypatch.setattr(kb.requests, "get", lambda *a, **k: _OK())
    b._get("/p", "TR", {})
    assert KISBroker._cb_consecutive_failures == 0
    assert KISBroker._cb_open_until == 0.0


def test_half_open_after_cooldown_allows_retry(monkeypatch):
    _patch_conn_fail(monkeypatch)
    b = _broker()
    for _ in range(kb._KIS_CB_FAIL_THRESHOLD):
        with pytest.raises(requests.ConnectionError):
            b._get("/p", "TR", {})
    # cooldown 만료 상황 시뮬 — open_until 을 과거로
    KISBroker._cb_open_until = time.monotonic() - 1.0
    # half-open: check_open 통과(reset) 후 실제 시도 → 다시 ConnectionError (KISCircuitOpen 아님)
    with pytest.raises(requests.ConnectionError):
        b._get("/p", "TR", {})


def test_http_error_does_not_trip_breaker(monkeypatch):
    # KIS 도달 가능(HTTP 500)= 불통 아님 → breaker 미작동
    b = _broker()
    monkeypatch.setattr(KISBroker, "_auth_headers", lambda self: {}, raising=False)
    monkeypatch.setattr(KISBroker, "_tr_id", lambda self, t: t, raising=False)

    class _Err:
        def raise_for_status(self): raise requests.HTTPError("500")
        def json(self): return {}
    monkeypatch.setattr(kb.requests, "get", lambda *a, **k: _Err())
    for _ in range(kb._KIS_CB_FAIL_THRESHOLD + 2):
        with pytest.raises(requests.HTTPError):
            b._get("/p", "TR", {})
    assert KISBroker._cb_open_until == 0.0  # 연결 실패 아님 = trip 안 함
