"""Order API 감사 로그 검증 — server/audit.py + main.py 핸들러.

검증 포커스:
  - emit() 가 `order.audit` 로거로 한 줄 JSON 을 남긴다
  - _detect_auth_path 가 4개 상태(none/primary/legacy/denied)를 정확히 구분한다
  - /api/order GET/POST 핸들러가 모든 종결 경로에서 audit 을 emit 한다
    (성공 / 검증실패 / 인증거부 / 브로커예외 / 브로커실패응답 / legacy 인증)
  - 토큰·비밀·Authorization 값이 audit payload 에 나타나지 않는다 (보안)
"""
import asyncio
import json
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


def _reset_secrets(monkeypatch):
    for k in ("RAILWAY_SHARED_SECRET", "ORDER_SECRET"):
        monkeypatch.delenv(k, raising=False)


def _capture_audit(caplog):
    """order.audit 로거의 레코드만 추려 payload list 반환."""
    payloads = []
    for r in caplog.records:
        if r.name != "order.audit":
            continue
        msg = r.getMessage()
        _, _, raw = msg.partition(" ")
        try:
            payloads.append(json.loads(raw))
        except Exception:
            pass
    return payloads


# ──────────────────────────────────────────────
# 1. emit() 단위 — 한 줄 JSON, 예외 안 터뜨림
# ──────────────────────────────────────────────

def test_emit_writes_one_json_line(caplog):
    from server import audit
    with caplog.at_level(logging.INFO, logger="order.audit"):
        audit.emit({"endpoint": "/api/order", "outcome": "success", "qty": 10})
    payloads = _capture_audit(caplog)
    assert len(payloads) == 1
    assert payloads[0]["outcome"] == "success"
    assert payloads[0]["qty"] == 10


def test_emit_non_serializable_falls_back_to_str(caplog):
    """default=str 로 fallback — 예외 삼키지 않고 emit 성공."""
    from server import audit

    class Weird:
        pass

    with caplog.at_level(logging.INFO, logger="order.audit"):
        audit.emit({"weird": Weird(), "ok": True})
    payloads = _capture_audit(caplog)
    assert len(payloads) == 1
    assert payloads[0]["ok"] is True


# ──────────────────────────────────────────────
# 2. _detect_auth_path — 4개 상태 정확 분기
# ──────────────────────────────────────────────

def test_detect_none_when_no_secrets(monkeypatch):
    _reset_secrets(monkeypatch)
    from server.main import _detect_auth_path
    assert _detect_auth_path(_mock_request()) == "none"


def test_detect_primary_when_header_match(monkeypatch):
    _reset_secrets(monkeypatch)
    monkeypatch.setenv("RAILWAY_SHARED_SECRET", "pk")
    from server.main import _detect_auth_path
    assert _detect_auth_path(_mock_request({"X-Service-Auth": "pk"})) == "primary"


def test_detect_legacy_when_bearer_match(monkeypatch):
    _reset_secrets(monkeypatch)
    monkeypatch.setenv("ORDER_SECRET", "lk")
    from server.main import _detect_auth_path
    assert _detect_auth_path(_mock_request({"Authorization": "Bearer lk"})) == "legacy"


def test_detect_denied_when_mismatch(monkeypatch):
    _reset_secrets(monkeypatch)
    monkeypatch.setenv("RAILWAY_SHARED_SECRET", "pk")
    from server.main import _detect_auth_path
    assert _detect_auth_path(_mock_request({"X-Service-Auth": "wrong"})) == "denied"


# ──────────────────────────────────────────────
# 3. POST /api/order — 감사 로그 경로들
# ──────────────────────────────────────────────

def test_post_success_emits_audit(monkeypatch, caplog):
    _reset_secrets(monkeypatch)
    monkeypatch.setenv("RAILWAY_SHARED_SECRET", "pk")
    from server import main
    monkeypatch.setattr(
        main,
        "place_kr_order",
        lambda *a, **kw: {
            "success": True,
            "rt_cd": "0",
            "msg_cd": "APBK0013",
            "order_no": "12345",
        },
    )
    req = _mock_request(
        {"X-Service-Auth": "pk"},
        body={
            "market": "kr",
            "ticker": "005930",
            "side": "buy",
            "qty": 10,
            "price": 70000,
        },
    )
    with caplog.at_level(logging.INFO, logger="order.audit"):
        asyncio.run(main.order_place(req))
    payloads = _capture_audit(caplog)
    assert len(payloads) == 1
    p = payloads[0]
    assert p["method"] == "POST"
    assert p["auth_path"] == "primary"
    assert p["outcome"] == "success"
    assert p["ticker"] == "005930"
    assert p["side"] == "buy"
    assert p["qty"] == 10
    assert p["broker_rt_cd"] == "0"
    assert p["broker_order_no"] == "12345"
    assert p["http_status"] == 200
    assert "latency_ms" in p


def test_post_validation_missing_ticker_emits_audit(monkeypatch, caplog):
    _reset_secrets(monkeypatch)
    monkeypatch.setenv("RAILWAY_SHARED_SECRET", "pk")
    from server import main
    req = _mock_request(
        {"X-Service-Auth": "pk"},
        body={"market": "kr", "ticker": "", "side": "buy", "qty": 10},
    )
    with caplog.at_level(logging.INFO, logger="order.audit"):
        asyncio.run(main.order_place(req))
    p = _capture_audit(caplog)[0]
    assert p["outcome"] == "validation:missing_ticker"
    assert p["http_status"] == 400


def test_post_validation_bad_side_emits_audit(monkeypatch, caplog):
    _reset_secrets(monkeypatch)
    monkeypatch.setenv("RAILWAY_SHARED_SECRET", "pk")
    from server import main
    req = _mock_request(
        {"X-Service-Auth": "pk"},
        body={"market": "kr", "ticker": "005930", "side": "hold", "qty": 1},
    )
    with caplog.at_level(logging.INFO, logger="order.audit"):
        asyncio.run(main.order_place(req))
    p = _capture_audit(caplog)[0]
    assert p["outcome"] == "validation:bad_side"
    assert p["http_status"] == 400


def test_post_auth_denied_emits_audit_without_body_fields(monkeypatch, caplog):
    """인증 거부는 body 파싱 전에 거부되므로 ticker 등 body 필드가 audit 에 없어야."""
    _reset_secrets(monkeypatch)
    monkeypatch.setenv("RAILWAY_SHARED_SECRET", "pk")
    from server import main
    req = _mock_request(
        {"X-Service-Auth": "wrong"},
        body={"ticker": "005930", "side": "buy", "qty": 10},
    )
    with caplog.at_level(logging.INFO, logger="order.audit"):
        asyncio.run(main.order_place(req))
    p = _capture_audit(caplog)[0]
    assert p["outcome"] == "auth_denied"
    assert p["auth_path"] == "denied"
    assert p["http_status"] == 401
    assert "ticker" not in p


def test_post_broker_exception_emits_audit(monkeypatch, caplog):
    _reset_secrets(monkeypatch)
    monkeypatch.setenv("RAILWAY_SHARED_SECRET", "pk")
    from server import main

    def boom(*a, **kw):
        raise RuntimeError("broker down")

    monkeypatch.setattr(main, "place_kr_order", boom)
    req = _mock_request(
        {"X-Service-Auth": "pk"},
        body={
            "market": "kr",
            "ticker": "005930",
            "side": "buy",
            "qty": 10,
            "price": 70000,
        },
    )
    with caplog.at_level(logging.INFO, logger="order.audit"):
        asyncio.run(main.order_place(req))
    p = _capture_audit(caplog)[0]
    assert p["outcome"] == "exception:RuntimeError"
    assert p["error_msg"] == "broker down"
    assert p["http_status"] == 502


def test_post_broker_error_response_emits_audit(monkeypatch, caplog):
    """브로커가 예외 없이 실패 응답을 주면 broker_error 로 기록."""
    _reset_secrets(monkeypatch)
    monkeypatch.setenv("RAILWAY_SHARED_SECRET", "pk")
    from server import main
    monkeypatch.setattr(
        main,
        "place_kr_order",
        lambda *a, **kw: {"success": False, "rt_cd": "1", "msg_cd": "APBK0999"},
    )
    req = _mock_request(
        {"X-Service-Auth": "pk"},
        body={
            "market": "kr",
            "ticker": "005930",
            "side": "buy",
            "qty": 10,
            "price": 70000,
        },
    )
    with caplog.at_level(logging.INFO, logger="order.audit"):
        asyncio.run(main.order_place(req))
    p = _capture_audit(caplog)[0]
    assert p["outcome"] == "broker_error"
    assert p["broker_rt_cd"] == "1"


# ──────────────────────────────────────────────
# 4. GET /api/order — 잔고 조회도 audit
# ──────────────────────────────────────────────

def test_get_balance_success_emits_audit(monkeypatch, caplog):
    _reset_secrets(monkeypatch)
    monkeypatch.setenv("RAILWAY_SHARED_SECRET", "pk")
    from server import main
    monkeypatch.setattr(main, "get_balance", lambda m: {"cash": 1_000_000})
    req = _mock_request({"X-Service-Auth": "pk"})
    with caplog.at_level(logging.INFO, logger="order.audit"):
        asyncio.run(main.order_balance(req, market="kr"))
    p = _capture_audit(caplog)[0]
    assert p["method"] == "GET"
    assert p["outcome"] == "success"
    assert p["market"] == "kr"
    assert p["auth_path"] == "primary"
    assert p["http_status"] == 200


def test_get_balance_auth_denied_emits_audit(monkeypatch, caplog):
    _reset_secrets(monkeypatch)
    monkeypatch.setenv("RAILWAY_SHARED_SECRET", "pk")
    from server import main
    req = _mock_request({"X-Service-Auth": "wrong"})
    with caplog.at_level(logging.INFO, logger="order.audit"):
        asyncio.run(main.order_balance(req, market="kr"))
    p = _capture_audit(caplog)[0]
    assert p["outcome"] == "auth_denied"
    assert p["http_status"] == 401


def test_get_balance_fail_closed_emits_audit(monkeypatch, caplog):
    """secret 미설정 → 503 도 audit 되어야 (운영 가시성)."""
    _reset_secrets(monkeypatch)
    from server import main
    req = _mock_request({})
    with caplog.at_level(logging.INFO, logger="order.audit"):
        asyncio.run(main.order_balance(req, market="kr"))
    p = _capture_audit(caplog)[0]
    assert p["outcome"] == "auth_denied"
    assert p["auth_path"] == "none"
    assert p["http_status"] == 503


# ──────────────────────────────────────────────
# 5. 보안 — 토큰/비밀 값이 audit 에 leak 되지 않아야 함
# ──────────────────────────────────────────────

def test_audit_never_contains_secret_values(monkeypatch, caplog):
    secret = "SUPERSECRET_ABC123"
    _reset_secrets(monkeypatch)
    monkeypatch.setenv("RAILWAY_SHARED_SECRET", secret)
    from server import main
    monkeypatch.setattr(
        main,
        "place_kr_order",
        lambda *a, **kw: {"success": True, "rt_cd": "0"},
    )
    req = _mock_request(
        {"X-Service-Auth": secret, "Authorization": f"Bearer {secret}"},
        body={
            "market": "kr",
            "ticker": "005930",
            "side": "buy",
            "qty": 1,
            "price": 100,
        },
    )
    with caplog.at_level(logging.INFO, logger="order.audit"):
        asyncio.run(main.order_place(req))
    for r in [r for r in caplog.records if r.name == "order.audit"]:
        assert secret not in r.getMessage(), "secret leaked into audit log"


# ──────────────────────────────────────────────
# 6. Legacy 인증 경로 — audit 에 구분 기록
# ──────────────────────────────────────────────

def test_post_legacy_auth_recorded_in_audit(monkeypatch, caplog):
    _reset_secrets(monkeypatch)
    monkeypatch.setenv("ORDER_SECRET", "legacy-k")
    from server import main
    monkeypatch.setattr(
        main,
        "place_kr_order",
        lambda *a, **kw: {"success": True, "rt_cd": "0"},
    )
    req = _mock_request(
        {"Authorization": "Bearer legacy-k"},
        body={
            "market": "kr",
            "ticker": "005930",
            "side": "sell",
            "qty": 5,
            "price": 10000,
        },
    )
    with caplog.at_level(logging.INFO, logger="order.audit"):
        asyncio.run(main.order_place(req))
    p = _capture_audit(caplog)[0]
    assert p["auth_path"] == "legacy"
    assert p["outcome"] == "success"
