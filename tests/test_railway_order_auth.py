"""Railway 주문 API 인증 게이트 — fail-closed 검증.

배경:
  - 2026-04-23 이전에는 ORDER_SECRET 미설정 시 fail-open(검증 생략)이었다.
  - 같은 날 fail-closed 로 전환 + X-Service-Auth / RAILWAY_SHARED_SECRET 도입,
    legacy Authorization Bearer / ORDER_SECRET 경로는 마이그레이션 호환으로 병행.
  - 2026-04-23 legacy 경로 완전 제거 — X-Service-Auth 단일 경로로 통일.

현 정책:
  1) RAILWAY_SHARED_SECRET 미설정 → 503 (fail-closed, 서비스 불가 명시)
  2) X-Service-Auth == RAILWAY_SHARED_SECRET → 통과
  3) 불일치 → 401
"""
import json
from unittest.mock import MagicMock

import pytest


def _mock_request(headers: dict) -> MagicMock:
    """Request.headers.get(name) 만 사용하므로 그 메서드만 있으면 충분."""
    req = MagicMock()
    lower_map = {k.lower(): v for k, v in headers.items()}
    req.headers.get.side_effect = lambda name, default=None: lower_map.get(
        name.lower(), default
    )
    return req


def _call(monkeypatch, env: dict, headers: dict):
    """_order_auth_fail_response 호출. env·headers 조합으로 결과 확인."""
    for k in ("RAILWAY_SHARED_SECRET", "ORDER_SECRET"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from server.main import _order_auth_fail_response  # 지연 import
    return _order_auth_fail_response(_mock_request(headers))


def _status(resp):
    return getattr(resp, "status_code", None)


def _body(resp) -> dict:
    # fastapi.responses.JSONResponse.body 는 bytes
    raw = getattr(resp, "body", b"")
    if isinstance(raw, (bytes, bytearray)):
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}
    return {}


# ──────────────────────────────────────────────
# 1. secret 미설정 → 503 (fail-closed)
# ──────────────────────────────────────────────

def test_no_secret_returns_503_fail_closed(monkeypatch):
    resp = _call(monkeypatch, env={}, headers={})
    assert _status(resp) == 503
    body = _body(resp)
    assert "RAILWAY_SHARED_SECRET" in body.get("detail", "")


def test_no_secret_ignores_any_header(monkeypatch):
    """secret 미설정이면 어떤 헤더를 보내도 503 (우회 불가 확인)."""
    resp = _call(
        monkeypatch, env={},
        headers={"X-Service-Auth": "whatever", "Authorization": "Bearer guess"},
    )
    assert _status(resp) == 503


def test_legacy_order_secret_env_alone_does_not_enable(monkeypatch):
    """ORDER_SECRET 만 설정돼도 legacy 경로가 제거됐으므로 503 유지 (회귀 방지)."""
    resp = _call(
        monkeypatch,
        env={"ORDER_SECRET": "legacy-s3cret"},
        headers={"Authorization": "Bearer legacy-s3cret"},
    )
    assert _status(resp) == 503


# ──────────────────────────────────────────────
# 2. X-Service-Auth 일치 → 통과
# ──────────────────────────────────────────────

def test_primary_header_match_passes(monkeypatch):
    resp = _call(
        monkeypatch,
        env={"RAILWAY_SHARED_SECRET": "primary-s3cret"},
        headers={"X-Service-Auth": "primary-s3cret"},
    )
    assert resp is None  # None 은 auth 통과


def test_primary_header_mismatch_returns_401(monkeypatch):
    resp = _call(
        monkeypatch,
        env={"RAILWAY_SHARED_SECRET": "primary-s3cret"},
        headers={"X-Service-Auth": "wrong"},
    )
    assert _status(resp) == 401


def test_primary_secret_set_but_header_missing_returns_401(monkeypatch):
    """secret 설정됐는데 헤더 없음 → 401 (503 아님 — secret 은 있음)."""
    resp = _call(
        monkeypatch,
        env={"RAILWAY_SHARED_SECRET": "primary-s3cret"},
        headers={},
    )
    assert _status(resp) == 401


# ──────────────────────────────────────────────
# 3. Cross-header 방지 — Bearer 로 primary secret 을 보내도 거부
# ──────────────────────────────────────────────

def test_primary_secret_not_accepted_via_bearer(monkeypatch):
    """클라이언트가 실수로 X-Service-Auth 대신 Bearer 로 primary 값을 보낸 경우.
    legacy 경로가 제거됐으므로 401 (헤더 이름 혼용 방지)."""
    resp = _call(
        monkeypatch,
        env={"RAILWAY_SHARED_SECRET": "primary-s3cret"},
        headers={"Authorization": "Bearer primary-s3cret"},
    )
    assert _status(resp) == 401


# ──────────────────────────────────────────────
# 4. 타이밍 공격 — hmac.compare_digest 사용 확인 (빈 헤더 케이스)
# ──────────────────────────────────────────────

def test_empty_header_value_returns_401(monkeypatch):
    """X-Service-Auth 가 빈 문자열로 온 경우 통과하면 안 됨."""
    resp = _call(
        monkeypatch,
        env={"RAILWAY_SHARED_SECRET": "primary-s3cret"},
        headers={"X-Service-Auth": ""},
    )
    assert _status(resp) == 401
