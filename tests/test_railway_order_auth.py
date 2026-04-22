"""Railway 주문 API 인증 게이트 — fail-closed 전환 검증.

배경:
  2026-04-23 이전에는 ORDER_SECRET 미설정 시 fail-open(검증 생략)이었다.
  Vercel 쪽은 이미 X-Service-Auth + RAILWAY_SHARED_SECRET 을 쓰는데 Railway
  쪽은 Authorization Bearer + ORDER_SECRET 으로 스펙이 mismatch + fail-open
  인 상태였음. 실자금 주문 경로 보호를 위해 다음 정책으로 전환:

    1) 두 secret 모두 미설정 → 503 (fail-closed)
    2) X-Service-Auth == RAILWAY_SHARED_SECRET → 통과
    3) Authorization: Bearer ORDER_SECRET → 통과 (legacy, deprecation 예정)
    4) 둘 다 불일치 → 401
"""
import json
from unittest.mock import MagicMock

import pytest

# conftest 가 tests/ 안에 있고 repo root 를 sys.path 에 추가하므로 직접 import 가능.
# KIS WS client 가 import 시 무언가 하지 않도록, 함수 단위 import 로 부작용 최소화.


def _mock_request(headers: dict) -> MagicMock:
    """Request.headers.get(name) 만 사용하므로 그 메서드만 있으면 충분."""
    req = MagicMock()
    # 대소문자 구분 안 하는 방식으로 헤더 lookup 구현
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
# 1. 두 secret 모두 미설정 → 503 (fail-closed)
# ──────────────────────────────────────────────

def test_no_secrets_returns_503_fail_closed(monkeypatch):
    resp = _call(monkeypatch, env={}, headers={})
    assert _status(resp) == 503
    body = _body(resp)
    assert "RAILWAY_SHARED_SECRET" in body.get("detail", "")


def test_no_secrets_ignores_any_header(monkeypatch):
    """secret 미설정이면 어떤 헤더를 보내도 503 (우회 불가 확인)."""
    resp = _call(
        monkeypatch, env={},
        headers={"X-Service-Auth": "whatever", "Authorization": "Bearer guess"},
    )
    assert _status(resp) == 503


# ──────────────────────────────────────────────
# 2. X-Service-Auth 일치 → 통과 (primary)
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
    """primary 만 설정됐는데 헤더 자체 없음 → 401 (단, 503 아님 — secret 은 있음)."""
    resp = _call(
        monkeypatch,
        env={"RAILWAY_SHARED_SECRET": "primary-s3cret"},
        headers={},
    )
    assert _status(resp) == 401


# ──────────────────────────────────────────────
# 3. Legacy Authorization Bearer 경로
# ──────────────────────────────────────────────

def test_legacy_bearer_match_passes(monkeypatch):
    resp = _call(
        monkeypatch,
        env={"ORDER_SECRET": "legacy-s3cret"},
        headers={"Authorization": "Bearer legacy-s3cret"},
    )
    assert resp is None


def test_legacy_bearer_mismatch_returns_401(monkeypatch):
    resp = _call(
        monkeypatch,
        env={"ORDER_SECRET": "legacy-s3cret"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert _status(resp) == 401


def test_legacy_bearer_wrong_prefix_returns_401(monkeypatch):
    """'Bearer ' prefix 누락 시 fail (보안)."""
    resp = _call(
        monkeypatch,
        env={"ORDER_SECRET": "legacy-s3cret"},
        headers={"Authorization": "legacy-s3cret"},  # Bearer prefix 없음
    )
    assert _status(resp) == 401


# ──────────────────────────────────────────────
# 4. 두 secret 모두 설정 — 어느 한쪽 일치로 통과
# ──────────────────────────────────────────────

def test_both_secrets_set_primary_header_passes(monkeypatch):
    resp = _call(
        monkeypatch,
        env={"RAILWAY_SHARED_SECRET": "new", "ORDER_SECRET": "old"},
        headers={"X-Service-Auth": "new"},
    )
    assert resp is None


def test_both_secrets_set_legacy_bearer_passes(monkeypatch):
    """마이그레이션 과도기 — 오래된 클라이언트가 Bearer 로 오면 통과."""
    resp = _call(
        monkeypatch,
        env={"RAILWAY_SHARED_SECRET": "new", "ORDER_SECRET": "old"},
        headers={"Authorization": "Bearer old"},
    )
    assert resp is None


def test_both_secrets_set_both_wrong_returns_401(monkeypatch):
    resp = _call(
        monkeypatch,
        env={"RAILWAY_SHARED_SECRET": "new", "ORDER_SECRET": "old"},
        headers={"X-Service-Auth": "wrong", "Authorization": "Bearer wrong"},
    )
    assert _status(resp) == 401


# ──────────────────────────────────────────────
# 5. Cross-header leak 방지 — primary secret 을 Bearer 로 보내도 거부
# ──────────────────────────────────────────────

def test_primary_secret_not_accepted_via_bearer(monkeypatch):
    """primary 만 설정된 상태에서 클라이언트가 실수로 Bearer 로 보낸 경우.
    legacy secret 이 없으니 401 이어야 함 (헤더 혼용 방지)."""
    resp = _call(
        monkeypatch,
        env={"RAILWAY_SHARED_SECRET": "primary-s3cret"},
        headers={"Authorization": "Bearer primary-s3cret"},
    )
    assert _status(resp) == 401


# ──────────────────────────────────────────────
# 6. 타이밍 공격 — hmac.compare_digest 사용 확인 (빈 헤더 케이스)
# ──────────────────────────────────────────────

def test_empty_header_value_returns_401(monkeypatch):
    """X-Service-Auth 가 빈 문자열로 온 경우 통과하면 안 됨."""
    resp = _call(
        monkeypatch,
        env={"RAILWAY_SHARED_SECRET": "primary-s3cret"},
        headers={"X-Service-Auth": ""},
    )
    assert _status(resp) == 401
