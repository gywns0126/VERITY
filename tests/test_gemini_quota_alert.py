"""Gemini 429/RESOURCE_EXHAUSTED 알림 + PDF fallback 텍스트 필터 검증.

핵심 (2026-06-05 정공법 개편 반영):
  - _is_quota_error: 에러 문자열 패턴 매칭
  - _classify_quota_error: 선불 크레딧 / 월 지출 한도 / rate-limit 분기
  - _alert_gemini_quota_exceeded: 연속 ≥2 사이클일 때만 발송 (단발 transient 무시)
    + 한 run 1회 + 1h dedupe backstop
  - _reset_quota_streak: 정상 응답 시 streak 0
  - _is_fallback_text: PDF 출력 전 fallback 메시지 필터
"""
import time

import pytest


# ──────────────────────────────────────────────
# 공통 fixture — streak store 를 in-memory 로 stub + 모듈 run-flag 초기화
# ──────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_quota(monkeypatch):
    from api.analyzers import gemini_analyst as ga
    ga._quota_alert_last_ts = 0.0
    ga._quota_run_bumped = False
    ga._quota_run_reset = False
    store = {"streak": 0}
    monkeypatch.setattr(ga, "_read_quota_streak", lambda: store["streak"])
    monkeypatch.setattr(ga, "_write_quota_state", lambda n, **kw: store.__setitem__("streak", int(n)))
    yield store


# ──────────────────────────────────────────────
# 1. _is_quota_error / _classify_quota_error
# ──────────────────────────────────────────────

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


def test_classify_quota_error_branches():
    from api.analyzers.gemini_analyst import _classify_quota_error
    # 선불 크레딧 (이번 사고의 실제 에러)
    assert _classify_quota_error(
        "429 RESOURCE_EXHAUSTED. {'message': 'Your prepayment credits are depleted.'}"
    ) == "credits"
    assert _classify_quota_error("credits are depleted") == "credits"
    # 월 지출 한도
    assert _classify_quota_error("exceeded its monthly spending cap") == "spend_cap"
    # 그 외 429 = 비율/일시
    assert _classify_quota_error("429 RESOURCE_EXHAUSTED") == "rate_limit"


# ──────────────────────────────────────────────
# 2. _alert_gemini_quota_exceeded — persistence gate + 분기
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


def test_single_transient_failure_suppressed(monkeypatch):
    """단발(1 사이클) 실패 = 일시 글리치 가능 → 알림 보류."""
    calls = _patch_send_message(monkeypatch)
    from api.analyzers.gemini_analyst import _alert_gemini_quota_exceeded
    _alert_gemini_quota_exceeded(
        "daily_report", "429 RESOURCE_EXHAUSTED prepayment credits are depleted"
    )
    assert calls == []


def test_alert_fires_on_second_consecutive_cycle(monkeypatch):
    """연속 2 사이클 실패 시에만 발송."""
    calls = _patch_send_message(monkeypatch)
    from api.analyzers import gemini_analyst as ga
    ga._alert_gemini_quota_exceeded("daily_report", "429 RESOURCE_EXHAUSTED")
    assert calls == []                # 1 사이클 = 보류
    ga._quota_run_bumped = False      # 다음 run 시뮬
    ga._alert_gemini_quota_exceeded("daily_report", "429 RESOURCE_EXHAUSTED")
    assert len(calls) == 1            # 2 사이클 연속 → 발송
    assert "daily_report" in calls[0]


def test_alert_skipped_for_non_quota_error(monkeypatch):
    calls = _patch_send_message(monkeypatch)
    from api.analyzers.gemini_analyst import _alert_gemini_quota_exceeded
    _alert_gemini_quota_exceeded("daily_report", "ConnectionError: timeout")
    assert calls == []


def test_alert_once_per_run(monkeypatch, _reset_quota):
    """한 run 에서 여러 호출이 실패해도 streak 1회 증가 + 알림 1회."""
    _reset_quota["streak"] = 1        # 직전 사이클 이미 실패
    calls = _patch_send_message(monkeypatch)
    from api.analyzers.gemini_analyst import _alert_gemini_quota_exceeded
    for _ in range(5):
        _alert_gemini_quota_exceeded("periodic_report", "429 RESOURCE_EXHAUSTED")
    assert len(calls) == 1
    assert _reset_quota["streak"] == 2   # 1회만 증가


def test_alert_resends_next_run_after_window(monkeypatch, _reset_quota):
    """다음 run + 1h dedupe 경과 시 재발송 (장애 지속 알림)."""
    _reset_quota["streak"] = 1
    calls = _patch_send_message(monkeypatch)
    from api.analyzers import gemini_analyst as ga
    ga._alert_gemini_quota_exceeded("periodic_report", "429 RESOURCE_EXHAUSTED")
    assert len(calls) == 1
    ga._quota_run_bumped = False
    ga._quota_alert_last_ts = time.time() - (3600 + 1)
    ga._alert_gemini_quota_exceeded("periodic_report", "429 RESOURCE_EXHAUSTED")
    assert len(calls) == 2


def test_reset_clears_streak(_reset_quota):
    from api.analyzers import gemini_analyst as ga
    _reset_quota["streak"] = 3
    ga._reset_quota_streak()
    assert _reset_quota["streak"] == 0


def test_credits_error_points_to_billing_not_cap(monkeypatch, _reset_quota):
    """선불 크레딧 에러 → 결제(Billing) 탭 안내, cap 증액 오안내 안 함."""
    _reset_quota["streak"] = 1
    calls = _patch_send_message(monkeypatch)
    from api.analyzers import gemini_analyst as ga
    ga._alert_gemini_quota_exceeded(
        "daily_report", "429 RESOURCE_EXHAUSTED prepayment credits are depleted"
    )
    assert len(calls) == 1
    assert "결제" in calls[0]
    assert "지출 한도 수정" not in calls[0]


def test_spend_cap_error_points_to_cap(monkeypatch, _reset_quota):
    _reset_quota["streak"] = 1
    calls = _patch_send_message(monkeypatch)
    from api.analyzers import gemini_analyst as ga
    ga._alert_gemini_quota_exceeded("daily_report", "exceeded its monthly spending cap")
    assert len(calls) == 1
    assert "지출 한도" in calls[0]


def test_alert_silent_on_telegram_module_failure(monkeypatch, _reset_quota):
    """telegram send 가 raise 해도 분석 흐름이 깨지면 안 됨."""
    _reset_quota["streak"] = 1
    import api.notifications.telegram as tg
    def _boom(*a, **kw):
        raise RuntimeError("telegram down")
    monkeypatch.setattr(tg, "send_message", _boom)
    from api.analyzers import gemini_analyst as ga
    ga._alert_gemini_quota_exceeded("daily_report", "429 RESOURCE_EXHAUSTED")  # 예외 없이 종료


# ──────────────────────────────────────────────
# 2.5 _carry_forward_daily_report — Gemini 일시 장애 1 사이클 bridge
# ──────────────────────────────────────────────

def _write_portfolio(tmp_path, payload):
    import json as _json
    (tmp_path / "portfolio.json").write_text(
        _json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def test_carry_forward_reuses_real_prev_report(monkeypatch, tmp_path):
    from api.analyzers import gemini_analyst as ga
    _write_portfolio(tmp_path, {"daily_report": {
        "market_summary": "코스피 상승 우위", "risk_watch": "외국인 수급 점검",
        "_gemini_model": "gemini-2.5-pro",
    }})
    monkeypatch.setattr(ga, "DATA_DIR", str(tmp_path))
    out = ga._carry_forward_daily_report("kr")
    assert out is not None
    assert out["market_summary"] == "코스피 상승 우위"
    assert out["_stale"] is True
    assert out["_gemini_model"] == "carry_forward"


def test_carry_forward_skips_fallback_prev(monkeypatch, tmp_path):
    from api.analyzers import gemini_analyst as ga
    _write_portfolio(tmp_path, {"daily_report": {
        "market_summary": "x",
        "risk_watch": "구체적 리스크 분석은 Gemini API 연결 시 제공됩니다",
        "_gemini_model": "fallback",
    }})
    monkeypatch.setattr(ga, "DATA_DIR", str(tmp_path))
    assert ga._carry_forward_daily_report("kr") is None


def test_carry_forward_skips_already_carried(monkeypatch, tmp_path):
    """지속 장애 — 직전이 carry 면 무한 stale 방지 위해 재사용 안 함."""
    from api.analyzers import gemini_analyst as ga
    _write_portfolio(tmp_path, {"daily_report": {
        "market_summary": "x", "_stale": True, "_gemini_model": "carry_forward",
    }})
    monkeypatch.setattr(ga, "DATA_DIR", str(tmp_path))
    assert ga._carry_forward_daily_report("kr") is None


def test_carry_forward_none_when_no_file(monkeypatch, tmp_path):
    from api.analyzers import gemini_analyst as ga
    monkeypatch.setattr(ga, "DATA_DIR", str(tmp_path))  # 빈 디렉토리
    assert ga._carry_forward_daily_report("kr") is None


def test_carry_forward_uses_us_key(monkeypatch, tmp_path):
    from api.analyzers import gemini_analyst as ga
    _write_portfolio(tmp_path, {"daily_report_us": {
        "market_summary": "S&P 강세", "_gemini_model": "gemini-2.5-pro",
    }})
    monkeypatch.setattr(ga, "DATA_DIR", str(tmp_path))
    out = ga._carry_forward_daily_report("us")
    assert out is not None and out["market_summary"] == "S&P 강세"


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
