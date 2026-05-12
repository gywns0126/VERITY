"""
api.notifications.quiet_hours + send_message 의 야간 묵음 게이트 검증.
"""
from __future__ import annotations

import importlib
import os
from datetime import datetime
from typing import List, Tuple

import pytest


@pytest.fixture(autouse=True)
def _set_telegram_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    # 영속 dedupe 파일 경로 격리 — 운영 data/ 충돌 방지 (2026-05-12).
    monkeypatch.setenv("TELEGRAM_DEDUPE_STORE_PATH", str(tmp_path / "tg_dedupe.json"))
    yield


def _reload_modules():
    import api.config
    importlib.reload(api.config)
    import api.notifications.quiet_hours as qh
    importlib.reload(qh)
    import api.notifications.telegram as tg
    importlib.reload(tg)
    return api.config, qh, tg


def test_is_quiet_hours_default_window_wraps_midnight(monkeypatch):
    monkeypatch.setenv("TELEGRAM_QUIET_HOURS_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_QUIET_START_KST", "23")
    monkeypatch.setenv("TELEGRAM_QUIET_END_KST", "7")
    cfg, qh, _ = _reload_modules()
    KST = cfg.KST

    assert qh.is_quiet_hours(datetime(2026, 5, 8, 22, 59, tzinfo=KST)) is False
    assert qh.is_quiet_hours(datetime(2026, 5, 8, 23, 0, tzinfo=KST)) is True
    assert qh.is_quiet_hours(datetime(2026, 5, 9, 0, 30, tzinfo=KST)) is True
    assert qh.is_quiet_hours(datetime(2026, 5, 9, 6, 59, tzinfo=KST)) is True
    assert qh.is_quiet_hours(datetime(2026, 5, 9, 7, 0, tzinfo=KST)) is False
    assert qh.is_quiet_hours(datetime(2026, 5, 9, 12, 0, tzinfo=KST)) is False


def test_is_quiet_hours_disabled_via_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_QUIET_HOURS_ENABLED", "0")
    cfg, qh, _ = _reload_modules()
    KST = cfg.KST
    assert qh.is_quiet_hours(datetime(2026, 5, 9, 3, 0, tzinfo=KST)) is False


def test_is_quiet_hours_same_day_window(monkeypatch):
    monkeypatch.setenv("TELEGRAM_QUIET_HOURS_ENABLED", "1")
    monkeypatch.setenv("TELEGRAM_QUIET_START_KST", "1")
    monkeypatch.setenv("TELEGRAM_QUIET_END_KST", "5")
    cfg, qh, _ = _reload_modules()
    KST = cfg.KST
    assert qh.is_quiet_hours(datetime(2026, 5, 8, 0, 30, tzinfo=KST)) is False
    assert qh.is_quiet_hours(datetime(2026, 5, 8, 1, 0, tzinfo=KST)) is True
    assert qh.is_quiet_hours(datetime(2026, 5, 8, 4, 59, tzinfo=KST)) is True
    assert qh.is_quiet_hours(datetime(2026, 5, 8, 5, 0, tzinfo=KST)) is False


def _patch_requests(monkeypatch, tg_module) -> List[Tuple]:
    """requests.post 호출을 캡처."""
    import requests

    class _R:
        status_code = 200
        text = "ok"

    captured: List[Tuple] = []

    def _fake_post(*a, **kw):
        captured.append((a, kw))
        return _R()

    monkeypatch.setattr(requests, "post", _fake_post)
    tg_module.reset_message_dedupe_cache()
    return captured


def test_send_message_skipped_during_quiet_hours(monkeypatch):
    monkeypatch.setenv("TELEGRAM_QUIET_HOURS_ENABLED", "1")
    cfg, qh, tg = _reload_modules()
    monkeypatch.setattr(qh, "is_quiet_hours", lambda now=None: True)
    sent = _patch_requests(monkeypatch, tg)

    ok = tg.send_message("야간 routine 알림", dedupe=False)
    assert ok is False
    assert len(sent) == 0


def test_send_message_bypass_quiet_sends_anyway(monkeypatch):
    monkeypatch.setenv("TELEGRAM_QUIET_HOURS_ENABLED", "1")
    cfg, qh, tg = _reload_modules()
    monkeypatch.setattr(qh, "is_quiet_hours", lambda now=None: True)
    sent = _patch_requests(monkeypatch, tg)

    ok = tg.send_message("긴급 critical", dedupe=False, bypass_quiet=True)
    assert ok is True
    assert len(sent) == 1


def test_send_message_quiet_skip_does_not_register_dedupe(monkeypatch):
    """야간에 skip된 메시지의 fingerprint 가 dedupe set 에 남으면, 주간이 되어도 같은 메시지가 영구 차단됨 — 그 회귀를 막음."""
    monkeypatch.setenv("TELEGRAM_QUIET_HOURS_ENABLED", "1")
    cfg, qh, tg = _reload_modules()
    sent = _patch_requests(monkeypatch, tg)

    # 1차: quiet hours → skip
    monkeypatch.setattr(qh, "is_quiet_hours", lambda now=None: True)
    ok1 = tg.send_message("동일 본문", dedupe=True)
    assert ok1 is False
    assert len(sent) == 0

    # 2차: quiet hours 끝남 → 동일 본문이 정상 발송돼야 함
    monkeypatch.setattr(qh, "is_quiet_hours", lambda now=None: False)
    ok2 = tg.send_message("동일 본문", dedupe=True)
    assert ok2 is True
    assert len(sent) == 1


def test_send_alerts_bypasses_when_critical_present(monkeypatch):
    """2026-05-12: 묶음 bypass 폐기 — CRITICAL 묶음만 bypass 발송, INFO 묶음은 quiet hours skip.
    야간 + INFO+CRITICAL 입력 → CRITICAL 묶음 1통만 발송됨.
    """
    monkeypatch.setenv("TELEGRAM_QUIET_HOURS_ENABLED", "1")
    cfg, qh, tg = _reload_modules()
    monkeypatch.setattr(qh, "is_quiet_hours", lambda now=None: True)
    sent = _patch_requests(monkeypatch, tg)

    ok = tg.send_alerts([
        {"level": "INFO", "message": "참고 1"},
        {"level": "CRITICAL", "message": "긴급 1"},
    ])
    assert ok is True
    # CRITICAL 묶음만 발송 (INFO 묶음은 quiet hours 차단)
    assert len(sent) == 1
    payload = sent[0][1].get("json") or {}
    text = payload.get("text", "")
    assert "긴급" in text
    assert "참고 1" not in text


def test_send_alerts_skipped_when_only_info_at_night(monkeypatch):
    monkeypatch.setenv("TELEGRAM_QUIET_HOURS_ENABLED", "1")
    cfg, qh, tg = _reload_modules()
    monkeypatch.setattr(qh, "is_quiet_hours", lambda now=None: True)
    sent = _patch_requests(monkeypatch, tg)

    ok = tg.send_alerts([
        {"level": "INFO", "message": "참고 1"},
        {"level": "WARNING", "message": "주의 1"},
    ])
    assert ok is False
    assert len(sent) == 0
