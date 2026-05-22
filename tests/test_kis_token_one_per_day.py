"""🚨 RULE 1 — KIS 1일 1토큰 ABSOLUTE 가드 (2026-05-22 사고 정정).

검증: force_refresh=True 가 23h 파일 lock 을 존중 (2번째 토큰 발급 차단).
배경: 5/22 21:09 preflight 발급 후 latent bug 발견 —
  옛 broker `interval_h = 6 if force_refresh` + `if not force_refresh and lock`
  → force_refresh=True + fresh runner(빈 cache) = 파일 lock bypass → 2번째 토큰 가능.
정정: interval 23h 통일 + 파일 lock 전 caller 강제.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from api.trading import kis_broker as kb

KST = timezone(timedelta(hours=9))


def _broker(tmp_path, lock_hours_ago):
    b = kb.KISBroker()
    b.app_key = "test_key"
    b.app_secret = "test_secret"
    lock = tmp_path / ".kis_issued_date.txt"
    lock.write_text((datetime.now(KST) - timedelta(hours=lock_hours_ago)).isoformat())
    b._daily_lock_path = lambda: str(lock)  # type: ignore
    return b


def test_force_refresh_blocks_2nd_token_cross_runner(tmp_path):
    """fresh runner(빈 cache) + 2h 전 lock + force_refresh=True → 발급 금지."""
    b = _broker(tmp_path, lock_hours_ago=2)
    b._token = None
    b._token_expires = None
    with mock.patch.object(b, "_load_cached_token"):  # cache 빈 채 유지
        with mock.patch.object(kb.requests, "post") as mpost:
            with pytest.raises(RuntimeError):  # lock 존중 → 발급 불가 (cache 없음)
                b.authenticate(force_refresh=True)
    mpost.assert_not_called()  # 🚨 2번째 토큰 HTTP 발급 안 함


def test_force_refresh_returns_cache_when_recent(tmp_path):
    """2h 전 lock + 유효 cache + force_refresh=True → cache 반환, 발급 X."""
    b = _broker(tmp_path, lock_hours_ago=2)
    b._token = "CACHED"
    b._token_expires = datetime.now(KST) + timedelta(hours=20)
    with mock.patch.object(b, "_load_cached_token"):
        with mock.patch.object(kb.requests, "post") as mpost:
            token = b.authenticate(force_refresh=True)
    mpost.assert_not_called()
    assert token == "CACHED"


def test_force_refresh_issues_after_23h(tmp_path):
    """25h 전 lock(>23h) + 빈 cache + force_refresh=True → 정상 발급 (backup 작동)."""
    b = _broker(tmp_path, lock_hours_ago=25)
    b._token = None
    b._token_expires = None
    fake = mock.Mock()
    fake.json.return_value = {
        "access_token": "NEW_TOKEN",
        "access_token_token_expired": "2099-01-01 00:00:00",
    }
    fake.raise_for_status = lambda: None
    with mock.patch.object(b, "_load_cached_token"), \
         mock.patch.object(b, "_save_cached_token"), \
         mock.patch.object(b, "_mark_issued_today"), \
         mock.patch.object(kb.requests, "post", return_value=fake) as mpost:
        token = b.authenticate(force_refresh=True)
    mpost.assert_called_once()  # 23h 경과 = backup 발급 정상
    assert token == "NEW_TOKEN"
