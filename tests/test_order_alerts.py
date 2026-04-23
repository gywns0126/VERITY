"""Order 알림 파이프라인 검증 — server/alerts.py + handler 통합.

검증 포커스:
  - outcome 분기: success 는 무알림, exception/broker_error/auth_denied 는 알림
  - env opt-out (ORDER_ALERT_ENABLED=false, 토큰/챗ID 미설정) → 무알림
  - 5분 dedupe — 동일 (outcome, ticker, auth_path) 는 1회만
  - 토큰 값은 메시지에 섞이지 않음 (보안)
  - POST /api/order 브로커 예외 시 핸들러 finally 에서 dispatch 호출됨
"""
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock


def _mock_request(headers=None, body=None) -> MagicMock:
    req = MagicMock()
    lower_map = {k.lower(): v for k, v in (headers or {}).items()}
    req.headers.get.side_effect = lambda name, default=None: lower_map.get(
        name.lower(), default
    )
    req.json = AsyncMock(return_value=body or {})
    return req


def _reset(monkeypatch):
    for k in (
        "RAILWAY_SHARED_SECRET",
        "ORDER_SECRET",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "ORDER_ALERT_ENABLED",
    ):
        monkeypatch.delenv(k, raising=False)
    from server import alerts
    alerts.reset_dedupe_cache()


def _capture_dispatch(monkeypatch):
    """_dispatch 를 inline 캡처로 교체. (token, chat_id, text) 튜플 list 반환."""
    from server import alerts
    calls = []
    monkeypatch.setattr(
        alerts, "_dispatch", lambda t, c, text: calls.append((t, c, text))
    )
    return calls


# ──────────────────────────────────────────────
# 1. _should_alert — 트리거 분기
# ──────────────────────────────────────────────

def test_should_alert_on_exception():
    from server.alerts import _should_alert
    assert _should_alert({"outcome": "exception:RuntimeError"}) is True


def test_should_alert_on_broker_error():
    from server.alerts import _should_alert
    assert _should_alert({"outcome": "broker_error"}) is True


def test_should_alert_on_auth_denied():
    from server.alerts import _should_alert
    assert _should_alert({"outcome": "auth_denied"}) is True


def test_should_not_alert_on_success():
    from server.alerts import _should_alert
    assert _should_alert({"outcome": "success"}) is False


def test_should_not_alert_on_validation():
    from server.alerts import _should_alert
    assert _should_alert({"outcome": "validation:missing_ticker"}) is False


def test_should_not_alert_on_unknown():
    from server.alerts import _should_alert
    assert _should_alert({}) is False


# ──────────────────────────────────────────────
# 2. _enabled / 자격증명
# ──────────────────────────────────────────────

def test_enabled_default_true(monkeypatch):
    _reset(monkeypatch)
    from server.alerts import _enabled
    assert _enabled() is True


def test_disabled_via_env_false(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("ORDER_ALERT_ENABLED", "false")
    from server.alerts import _enabled
    assert _enabled() is False


def test_disabled_via_env_zero(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("ORDER_ALERT_ENABLED", "0")
    from server.alerts import _enabled
    assert _enabled() is False


# ──────────────────────────────────────────────
# 3. 메시지 포맷 — 토큰/비밀 미포함 확인
# ──────────────────────────────────────────────

def test_format_exception_message_contains_fields():
    from server.alerts import _format_message
    text = _format_message({
        "outcome": "exception:RuntimeError",
        "auth_path": "primary",
        "method": "POST",
        "ticker": "005930",
        "side": "buy",
        "qty": 10,
        "price": 70000,
        "market": "kr",
        "error_msg": "broker down",
        "http_status": 502,
        "latency_ms": 120,
        "ts": 1713826000,
    })
    assert "🚨" in text
    assert "005930" in text
    assert "exception:RuntimeError" in text
    assert "broker down" in text
    assert "502" in text


def test_format_auth_denied_omits_order_line():
    from server.alerts import _format_message
    text = _format_message({
        "outcome": "auth_denied",
        "auth_path": "denied",
        "method": "POST",
        "http_status": 401,
        "latency_ms": 2,
        "ts": 1713826000,
    })
    assert "🔒" in text
    assert "auth_denied" in text
    assert "order:" not in text  # ticker 없으면 order 줄 생략


def test_format_escapes_html():
    from server.alerts import _format_message
    text = _format_message({
        "outcome": "broker_error",
        "auth_path": "primary",
        "method": "POST",
        "ticker": "<script>",
        "side": "buy",
        "qty": 1,
        "price": 100,
        "market": "kr",
        "http_status": 502,
        "latency_ms": 10,
        "ts": 1713826000,
    })
    assert "<script>" not in text
    assert "&lt;script&gt;" in text


# ──────────────────────────────────────────────
# 4. Dedupe — 5분 윈도
# ──────────────────────────────────────────────

def test_dedupe_suppresses_second_identical(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    from server import alerts
    calls = _capture_dispatch(monkeypatch)
    audit = {
        "outcome": "broker_error",
        "ticker": "005930",
        "auth_path": "primary",
        "method": "POST",
        "http_status": 502,
        "latency_ms": 10,
        "ts": 1713826000,
    }
    assert alerts.maybe_alert_from_audit(audit) is True
    assert alerts.maybe_alert_from_audit(audit) is False  # dedupe
    assert len(calls) == 1


def test_dedupe_allows_different_outcome(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    from server import alerts
    calls = _capture_dispatch(monkeypatch)
    base = {
        "ticker": "005930",
        "auth_path": "primary",
        "method": "POST",
        "http_status": 502,
        "latency_ms": 10,
        "ts": 1713826000,
    }
    assert alerts.maybe_alert_from_audit({**base, "outcome": "broker_error"}) is True
    assert alerts.maybe_alert_from_audit({**base, "outcome": "exception:X"}) is True
    assert len(calls) == 2


def test_dedupe_allows_different_ticker(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    from server import alerts
    calls = _capture_dispatch(monkeypatch)
    base = {
        "outcome": "broker_error",
        "auth_path": "primary",
        "method": "POST",
        "http_status": 502,
        "latency_ms": 10,
        "ts": 1713826000,
    }
    assert alerts.maybe_alert_from_audit({**base, "ticker": "005930"}) is True
    assert alerts.maybe_alert_from_audit({**base, "ticker": "000660"}) is True
    assert len(calls) == 2


def test_dedupe_reset_allows_repeat(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    from server import alerts
    calls = _capture_dispatch(monkeypatch)
    audit = {
        "outcome": "broker_error",
        "ticker": "005930",
        "auth_path": "primary",
        "method": "POST",
        "http_status": 502,
        "latency_ms": 10,
        "ts": 1713826000,
    }
    assert alerts.maybe_alert_from_audit(audit) is True
    alerts.reset_dedupe_cache()
    assert alerts.maybe_alert_from_audit(audit) is True
    assert len(calls) == 2


# ──────────────────────────────────────────────
# 5. No-op 경로
# ──────────────────────────────────────────────

def test_no_alert_when_token_missing(monkeypatch):
    _reset(monkeypatch)
    # chat_id 있지만 token 없음
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    from server import alerts
    calls = _capture_dispatch(monkeypatch)
    assert alerts.maybe_alert_from_audit({
        "outcome": "broker_error", "ticker": "X", "auth_path": "primary",
    }) is False
    assert calls == []


def test_no_alert_when_chat_id_missing(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    from server import alerts
    calls = _capture_dispatch(monkeypatch)
    assert alerts.maybe_alert_from_audit({
        "outcome": "broker_error", "ticker": "X", "auth_path": "primary",
    }) is False
    assert calls == []


def test_no_alert_when_disabled(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setenv("ORDER_ALERT_ENABLED", "false")
    from server import alerts
    calls = _capture_dispatch(monkeypatch)
    assert alerts.maybe_alert_from_audit({
        "outcome": "broker_error", "ticker": "X", "auth_path": "primary",
    }) is False
    assert calls == []


def test_no_alert_on_success_outcome(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    from server import alerts
    calls = _capture_dispatch(monkeypatch)
    assert alerts.maybe_alert_from_audit({
        "outcome": "success", "ticker": "005930", "auth_path": "primary",
    }) is False
    assert calls == []


# ──────────────────────────────────────────────
# 6. 보안 — 토큰 값이 dispatch payload 밖으로 새지 않음
# ──────────────────────────────────────────────

def test_token_never_in_message_body(monkeypatch):
    _reset(monkeypatch)
    TOKEN = "SUPER_TELEGRAM_TOKEN_XYZ"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    from server import alerts
    calls = _capture_dispatch(monkeypatch)
    audit = {
        "outcome": "broker_error",
        "ticker": "005930",
        "auth_path": "primary",
        "method": "POST",
        "http_status": 502,
        "latency_ms": 10,
        "ts": 1713826000,
    }
    alerts.maybe_alert_from_audit(audit)
    # token 은 dispatch 인자로만 전달되고 메시지 text 에 나타나면 안 됨
    assert len(calls) == 1
    _, _, text = calls[0]
    assert TOKEN not in text


# ──────────────────────────────────────────────
# 7. 통합 — POST /api/order 브로커 예외 시 핸들러 finally 가 alert dispatch
# ──────────────────────────────────────────────

def test_handler_dispatches_alert_on_broker_exception(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("RAILWAY_SHARED_SECRET", "pk")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    from server import main, alerts
    calls = _capture_dispatch(monkeypatch)

    def boom(*a, **kw):
        raise RuntimeError("broker down")

    monkeypatch.setattr(main, "place_kr_order", boom)
    req = _mock_request(
        {"X-Service-Auth": "pk"},
        body={
            "market": "kr", "ticker": "005930", "side": "buy",
            "qty": 10, "price": 70000,
        },
    )
    asyncio.run(main.order_place(req))
    assert len(calls) == 1
    _, _, text = calls[0]
    assert "005930" in text
    assert "exception:RuntimeError" in text


def test_handler_no_dispatch_on_success(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("RAILWAY_SHARED_SECRET", "pk")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    from server import main
    calls = _capture_dispatch(monkeypatch)
    monkeypatch.setattr(
        main, "place_kr_order",
        lambda *a, **kw: {"success": True, "rt_cd": "0"},
    )
    req = _mock_request(
        {"X-Service-Auth": "pk"},
        body={
            "market": "kr", "ticker": "005930", "side": "buy",
            "qty": 10, "price": 70000,
        },
    )
    asyncio.run(main.order_place(req))
    assert calls == []


def test_handler_dispatches_alert_on_auth_denied(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("RAILWAY_SHARED_SECRET", "pk")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    from server import main
    calls = _capture_dispatch(monkeypatch)
    req = _mock_request({"X-Service-Auth": "wrong"}, body={})
    asyncio.run(main.order_place(req))
    assert len(calls) == 1
    _, _, text = calls[0]
    assert "auth_denied" in text
