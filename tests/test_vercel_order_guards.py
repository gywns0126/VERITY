"""Vercel /api/order 방어 로직 — fail-closed CORS + secret 검증.

2026-04-23 변경 사항 검증:
  1. ORDER_ALLOWED_ORIGINS 미설정 시 _resolve_origin() 이 "" 반환 (wildcard 폴백 제거)
  2. ORDER_ALLOWED_ORIGINS 값에 '*' 가 섞여 들어와도 무시
  3. RAILWAY_SHARED_SECRET 미설정 시 모듈 로드 로그 (CRITICAL)

주의:
  _authorized_user() 전체 경로는 Supabase HTTP 호출까지 가므로 단위 테스트 범위 밖.
  여기서는 설정 게이트·origin 해석 로직만 테스트.
"""
import importlib
import sys
import types
from unittest.mock import MagicMock

import pytest


def _reload(monkeypatch, env: dict):
    """환경변수 재설정 후 vercel-api/api/order.py 재로드.
    모듈 상단에서 env 를 frozenset 으로 굳히므로 reload 필요.

    Vercel 전용 모듈(api.supabase_client) 은 테스트 환경에 없으므로 stub 주입.
    order.py 는 sb.verify_jwt / sb.select 만 쓰는데 이 단위 테스트는 CORS·secret
    게이트만 검증하고 그 메서드를 호출하는 경로는 안 탐.
    """
    for k in ("RAILWAY_SHARED_SECRET", "ORDER_ALLOWED_ORIGINS"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    # Stub: api.supabase_client (vercel-only 의존성)
    stub = types.ModuleType("api.supabase_client")
    stub.verify_jwt = MagicMock(return_value=None)
    stub.select = MagicMock(return_value=[])
    monkeypatch.setitem(sys.modules, "api.supabase_client", stub)

    import importlib.util
    import os
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "vercel-api", "api", "order.py",
    )
    spec = importlib.util.spec_from_file_location("vercel_order_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ──────────────────────────────────────────────
# _resolve_origin — CORS fail-closed
# ──────────────────────────────────────────────

def test_no_origins_env_returns_empty_string(monkeypatch):
    """ORDER_ALLOWED_ORIGINS 미설정 → "" (wildcard 폴백 제거 확인)."""
    mod = _reload(monkeypatch, env={"RAILWAY_SHARED_SECRET": "x"})
    assert mod._resolve_origin("https://verity.ai") == ""
    assert mod._resolve_origin("") == ""
    assert mod._resolve_origin("https://evil.example.com") == ""


def test_wildcard_in_env_is_stripped(monkeypatch):
    """값에 '*' 포함돼도 제거. 명시 origin 만 살아남음."""
    mod = _reload(monkeypatch, env={
        "RAILWAY_SHARED_SECRET": "x",
        "ORDER_ALLOWED_ORIGINS": "https://verity.ai, *, https://kim-hyojun.github.io",
    })
    assert "https://verity.ai" in mod._ALLOWED_ORIGINS
    assert "https://kim-hyojun.github.io" in mod._ALLOWED_ORIGINS
    assert "*" not in mod._ALLOWED_ORIGINS
    assert mod._WILDCARD_IN_ENV is True
    # 요청이 '*' 로 와도 거부
    assert mod._resolve_origin("*") == ""


def test_origin_exact_match_returns_origin(monkeypatch):
    mod = _reload(monkeypatch, env={
        "RAILWAY_SHARED_SECRET": "x",
        "ORDER_ALLOWED_ORIGINS": "https://verity.ai,https://kim-hyojun.github.io",
    })
    assert mod._resolve_origin("https://verity.ai") == "https://verity.ai"
    assert mod._resolve_origin("https://kim-hyojun.github.io") == "https://kim-hyojun.github.io"


def test_origin_mismatch_returns_empty(monkeypatch):
    mod = _reload(monkeypatch, env={
        "RAILWAY_SHARED_SECRET": "x",
        "ORDER_ALLOWED_ORIGINS": "https://verity.ai",
    })
    assert mod._resolve_origin("https://evil.example.com") == ""
    assert mod._resolve_origin("https://verity.ai.evil.com") == ""  # substring attack 차단
    assert mod._resolve_origin("http://verity.ai") == ""  # scheme mismatch


def test_whitespace_trimmed_from_env(monkeypatch):
    mod = _reload(monkeypatch, env={
        "RAILWAY_SHARED_SECRET": "x",
        "ORDER_ALLOWED_ORIGINS": "  https://verity.ai  ,  https://kim-hyojun.github.io  ",
    })
    assert mod._resolve_origin("https://verity.ai") == "https://verity.ai"
    # request_origin 도 strip 후 비교되므로 공백 포함 입력은 매치됨 (브라우저가 공백 안 보내므로 실용상 무해)
    assert mod._resolve_origin("  https://verity.ai  ") == "https://verity.ai"


def test_empty_strings_in_env_ignored(monkeypatch):
    """쉼표 연속으로 빈 항목 생겨도 무시."""
    mod = _reload(monkeypatch, env={
        "RAILWAY_SHARED_SECRET": "x",
        "ORDER_ALLOWED_ORIGINS": "https://verity.ai,,,",
    })
    assert mod._ALLOWED_ORIGINS == frozenset({"https://verity.ai"})


# ──────────────────────────────────────────────
# RAILWAY_SHARED_SECRET 모듈 로드 상태
# ──────────────────────────────────────────────

def test_secret_strip_quotes(monkeypatch):
    """환경변수에 따옴표 섞여 있으면 제거."""
    mod = _reload(monkeypatch, env={
        "RAILWAY_SHARED_SECRET": '"quoted-secret"',
    })
    assert mod._RAILWAY_SHARED_SECRET == "quoted-secret"


def test_secret_missing_is_empty_string(monkeypatch):
    """secret 미설정 → 빈 문자열 (None 아님)."""
    mod = _reload(monkeypatch, env={})
    assert mod._RAILWAY_SHARED_SECRET == ""
