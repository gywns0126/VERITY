"""KIS Supabase 공유 store read-fallback 테스트 (cutover GH 소비자 완성, 2026-06-03).

핵심 검증:
1. _kis_load_shared_token: 유효 row → (token,expires,issued) / 만료·app_key불일치·없음 → None.
2. authenticate() 재발급 guard 에서 file cache 부재 시 Supabase read → 토큰 반환.
3. 🚨 RULE 1: read-fallback 가 신규 발급(oauth2/tokenP POST)을 절대 호출하지 않음.
"""
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

import api.trading.kis_broker as kb

KST = timezone(timedelta(hours=9))
_APP_KEY = "TESTAPPKEY1234567890"


@pytest.fixture
def shared_env(monkeypatch):
    monkeypatch.setenv("KIS_SHARED_TOKEN", "1")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc_role_key")
    monkeypatch.setenv("KIS_APP_KEY", _APP_KEY)
    monkeypatch.setenv("KIS_APP_SECRET", "TESTSECRET")


def _row(token="SHAREDTOKEN", hours_valid=10, app_key=_APP_KEY):
    now = datetime.now(KST)
    return {
        "access_token": token,
        "expires_at": (now + timedelta(hours=hours_valid)).isoformat(),
        "issued_at": now.isoformat(),
        "app_key_fp": kb._kis_app_key_fp(app_key),
    }


def _mock_get(rows):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=rows)
    return resp


def test_load_shared_token_valid(shared_env):
    with patch.object(kb.requests, "get", return_value=_mock_get([_row()])):
        out = kb._kis_load_shared_token(_APP_KEY)
    assert out is not None
    token, expires_dt, issued_dt = out
    assert token == "SHAREDTOKEN"
    assert expires_dt > datetime.now(KST)


def test_load_shared_token_expired(shared_env):
    with patch.object(kb.requests, "get", return_value=_mock_get([_row(hours_valid=-1)])):
        assert kb._kis_load_shared_token(_APP_KEY) is None


def test_load_shared_token_app_key_mismatch(shared_env):
    with patch.object(kb.requests, "get", return_value=_mock_get([_row(app_key="OTHERACCOUNT")])):
        assert kb._kis_load_shared_token(_APP_KEY) is None


def test_load_shared_token_empty(shared_env):
    with patch.object(kb.requests, "get", return_value=_mock_get([])):
        assert kb._kis_load_shared_token(_APP_KEY) is None


def test_disabled_when_flag_off(monkeypatch):
    monkeypatch.delenv("KIS_SHARED_TOKEN", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    assert kb._kis_load_shared_token(_APP_KEY) is None


def test_authenticate_uses_shared_token_no_issuance(shared_env):
    """🚨 RULE 1 핵심: 오늘 이미 발급(guard) + file cache 부재 → Supabase read 로 토큰 반환,
    신규 발급 POST(oauth2/tokenP) 절대 호출 안 함."""
    broker = kb.KISBroker()
    # 오늘 이미 발급됨 (lock) — file cache 는 비어있음(토큰 None 유지)
    broker._is_recently_issued = MagicMock(return_value=True)
    broker._load_cached_token = MagicMock()  # no-op → self._token 그대로 None
    broker._token = None

    with patch.object(kb.requests, "get", return_value=_mock_get([_row()])) as mget, \
         patch.object(kb.requests, "post") as mpost:
        token = broker.authenticate()

    assert token == "SHAREDTOKEN"
    mget.assert_called()           # Supabase read 발생
    mpost.assert_not_called()      # 🚨 신규 발급 절대 X (RULE 1)


def test_authenticate_raises_when_shared_also_absent(shared_env):
    """Supabase 도 없으면 종전대로 raise (발급 X)."""
    broker = kb.KISBroker()
    broker._is_recently_issued = MagicMock(return_value=True)
    broker._load_cached_token = MagicMock()
    broker._token = None

    with patch.object(kb.requests, "get", return_value=_mock_get([])), \
         patch.object(kb.requests, "post") as mpost:
        with pytest.raises(RuntimeError):
            broker.authenticate()
    mpost.assert_not_called()      # 🚨 발급 X
