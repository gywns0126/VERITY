"""KIS REST fail-closed — env 누락 시 self-issue 차단 회귀 (2026-06-17 dual-issuer 사고).

사고: KIS_SHARED_TOKEN/SUPABASE env 가 하나라도 누락되면 _shared_enabled()=False 가 되어
옛 설계는 곧장 self-issue 했다(fail-OPEN). Railway env 1개 누락 = 2토큰 발급 = 계좌 제재.
이제 self-issue 는 KIS_ALLOW_SELF_ISSUE=1 명시 opt-in 일 때만. 기본 = 발급 금지(fail-CLOSED).
"""
import unittest.mock as m

import pytest


def _clear_env(monkeypatch):
    for k in ("KIS_SHARED_TOKEN", "KIS_ALLOW_SELF_ISSUE",
              "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.delenv(k, raising=False)


def test_env_missing_blocks_self_issue(monkeypatch):
    """env 전부 누락 + opt-in 없음 → RuntimeError(fail-closed), tokenP POST 절대 안 함."""
    _clear_env(monkeypatch)
    from server import kis_rest_client as k
    k._token = None
    k._token_expires = 0
    with m.patch.object(k, "_read_shared_token", return_value=None), \
         m.patch.object(k, "_load_cached_token", return_value=False), \
         m.patch("requests.post") as mp:
        with pytest.raises(RuntimeError, match="fail-closed"):
            k._get_token()
        assert not mp.called  # 🚨 self-issue HTTP 발급 안 함 (RULE 1)


def test_rule1_ok_false_on_self_issue_without_shared(monkeypatch):
    """self_issue 면 shared_flag 무관하게 rule1_ok=False — env 누락 시 거짓 True 보고 차단."""
    _clear_env(monkeypatch)
    from server import kis_rest_client as k
    k._token_source = "self_issue"
    assert k.token_status()["rule1_ok"] is False


def test_consumer_mode_blocks_without_opt_in(monkeypatch):
    """KIS_SHARED_TOKEN=1 (소비자 모드) + store/cache 없음 → 발급 금지 (기존 가드 유지)."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("KIS_SHARED_TOKEN", "1")
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    from server import kis_rest_client as k
    k._token = None
    k._token_expires = 0
    with m.patch.object(k, "_read_shared_token", return_value=None), \
         m.patch.object(k, "_load_cached_token", return_value=False), \
         m.patch("requests.post") as mp:
        with pytest.raises(RuntimeError):
            k._get_token()
        assert not mp.called
