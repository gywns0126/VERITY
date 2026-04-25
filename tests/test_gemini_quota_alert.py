"""Gemini 429/RESOURCE_EXHAUSTED 알림 + PDF fallback 텍스트 필터 검증.

핵심:
  - _is_quota_error: 에러 문자열 패턴 매칭
  - _alert_gemini_quota_exceeded: 1h dedupe — Telegram 호출 mock 으로 검증
  - _is_fallback_text: PDF 출력 전 fallback 메시지 필터
"""
import time

import pytest


# ──────────────────────────────────────────────
# 1. _is_quota_error
# ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_dedupe():
    """각 테스트 전에 quota alert dedupe 타임스탬프 초기화."""
    from api.analyzers import gemini_analyst as ga
    ga._quota_alert_last_ts = 0.0
    yield
    ga._quota_alert_last_ts = 0.0


def test_is_quota_error_recognizes_429_and_resource_exhausted():
    from api.analyzers.gemini_analyst import _is_quota_error
    assert _is_quota_error("429 RESOURCE_EXHAUSTED. {'error': ...}")
    assert _is_quota_error("Your project has exceeded its monthly spending cap")
    assert _is_quota_error("HTTP 429")
    assert _is_quota_error("RESOURCE_EXHAUSTED")


def test_is_quota_error_rejects_other_errors():
    from api.analyzers.gemini_analyst import _is_quota_error
    assert not _is_quota_error("ConnectionError: timeout")
    assert not _is_quota_error("ValueError: bad JSON")
    assert not _is_quota_error("")
    assert not _is_quota_error(None)


# ──────────────────────────────────────────────
# 2. _alert_gemini_quota_exceeded — 1h dedupe + Telegram 호출
# ──────────────────────────────────────────────

def _patch_send_message(monkeypatch):
    """api.notifications.telegram.send_message 를 캡처용 list 로 교체."""
    calls: list = []
    import importlib
    try:
        tg = importlib.import_module("api.notifications.telegram")
    except Exception:
        pytest.skip("telegram 모듈 없음")
    monkeypatch.setattr(tg, "send_message", lambda text, dedupe=True: calls.append(text) or True)
    return calls


def test_alert_fires_on_quota_error(monkeypatch):
    calls = _patch_send_message(monkeypatch)
    from api.analyzers.gemini_analyst import _alert_gemini_quota_exceeded
    _alert_gemini_quota_exceeded("daily_report", "429 RESOURCE_EXHAUSTED")
    assert len(calls) == 1
    assert "Gemini" in calls[0]
    assert "daily_report" in calls[0]


def test_alert_skipped_for_non_quota_error(monkeypatch):
    calls = _patch_send_message(monkeypatch)
    from api.analyzers.gemini_analyst import _alert_gemini_quota_exceeded
    _alert_gemini_quota_exceeded("daily_report", "ConnectionError: timeout")
    assert calls == []


def test_alert_dedupe_within_1h(monkeypatch):
    """같은 cap 초과 상황에서 5번 호출돼도 알림은 1번만."""
    calls = _patch_send_message(monkeypatch)
    from api.analyzers.gemini_analyst import _alert_gemini_quota_exceeded
    for _ in range(5):
        _alert_gemini_quota_exceeded("periodic_report", "429 RESOURCE_EXHAUSTED")
    assert len(calls) == 1


def test_alert_resends_after_dedupe_window(monkeypatch):
    """1시간 지나면 다시 알림 (사용자가 cap 풀고 다음번에 또 실패하는 경우 등)."""
    calls = _patch_send_message(monkeypatch)
    from api.analyzers import gemini_analyst as ga
    ga._alert_gemini_quota_exceeded("periodic_report", "429 RESOURCE_EXHAUSTED")
    assert len(calls) == 1
    # 시뮬레이트 — 1h+1 초 경과
    ga._quota_alert_last_ts = time.time() - (3600 + 1)
    ga._alert_gemini_quota_exceeded("periodic_report", "429 RESOURCE_EXHAUSTED")
    assert len(calls) == 2


def test_alert_silent_on_telegram_module_failure(monkeypatch):
    """telegram 모듈 자체가 import 실패해도 분석 흐름이 깨지면 안 됨."""
    from api.analyzers import gemini_analyst as ga
    # telegram import 자체를 실패시키긴 어려우니 send_message 가 raise 하도록 패치
    import api.notifications.telegram as tg
    def _boom(*a, **kw):
        raise RuntimeError("telegram down")
    monkeypatch.setattr(tg, "send_message", _boom)
    # 예외 없이 종료해야
    ga._alert_gemini_quota_exceeded("daily_report", "429 RESOURCE_EXHAUSTED")


# ──────────────────────────────────────────────
# 3. PDF fallback 필터 — _is_fallback_text
# ──────────────────────────────────────────────

def test_is_fallback_text_detects_known_markers():
    from api.reports.pdf_generator import _is_fallback_text
    assert _is_fallback_text("AI 리포트 생성 실패 (429 ...)")
    assert _is_fallback_text("AI 분석 실패 — 섹터 데이터 참조")
    assert _is_fallback_text("Gemini API 연결 시 상세 분석 제공")
    assert _is_fallback_text("RESOURCE_EXHAUSTED")
    assert _is_fallback_text("데이터 기반 판단 필요")


def test_is_fallback_text_passes_normal_content():
    from api.reports.pdf_generator import _is_fallback_text
    # 실제 분석 텍스트는 통과해야
    assert not _is_fallback_text("이번 주 KOSPI 는 외국인 매도세에 의해 1.2% 하락했다.")
    assert not _is_fallback_text("미국 금리 인하 기대로 성장주 우위.")


def test_is_fallback_text_treats_empty_as_fallback():
    """빈 문자열·None 도 fallback 으로 간주 (PDF 에 빈 섹션 안 띄우려고)."""
    from api.reports.pdf_generator import _is_fallback_text
    assert _is_fallback_text("")
    assert _is_fallback_text(None)


def test_safe_report_text_returns_placeholder_for_fallback():
    from api.reports.pdf_generator import _safe_report_text
    assert _safe_report_text("AI 리포트 생성 실패 ...") == ""
    assert _safe_report_text("AI 리포트 생성 실패 ...", placeholder="—") == "—"
    assert _safe_report_text("정상 분석 텍스트") == "정상 분석 텍스트"
