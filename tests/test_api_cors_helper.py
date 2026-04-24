"""vercel-api/api/cors_helper.py — API_ALLOWED_ORIGINS 화이트리스트 동작 검증.

BLK-3 (/api/chat), BLK-5 (/api/watchgroups) 이 공유하는 공용 helper.
order 의 기존 테스트(tests/test_vercel_order_guards.py) 와 동일 패턴.
"""
import importlib.util
import os
from pathlib import Path

import pytest


_CORS_PATH = (
    Path(__file__).resolve().parent.parent
    / "vercel-api" / "api" / "cors_helper.py"
)


def _reload_helper(value: str):
    """env 설정 후 파일 직접 로드해서 모듈 레벨 상수 재평가.
    vercel-api/api/ 에 __init__.py 없어 정상 import 불가 → spec_from_file_location 사용."""
    os.environ["API_ALLOWED_ORIGINS"] = value
    spec = importlib.util.spec_from_file_location("vercel_api_cors_helper", str(_CORS_PATH))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _cleanup_env(monkeypatch):
    monkeypatch.delenv("API_ALLOWED_ORIGINS", raising=False)
    yield
    monkeypatch.delenv("API_ALLOWED_ORIGINS", raising=False)


def test_no_env_returns_empty_string(monkeypatch):
    """env 미설정 → 빈 whitelist → 어떤 origin 도 빈 문자열 반환 (fail-closed)."""
    monkeypatch.delenv("API_ALLOWED_ORIGINS", raising=False)
    mod = _reload_helper("")
    assert mod.resolve_origin("https://example.com") == ""
    assert mod.resolve_origin("") == ""


def test_wildcard_in_env_is_stripped():
    """'*' 는 명시적으로 제거. wildcard 우회 불가."""
    mod = _reload_helper("https://ok.example.com, *")
    assert "*" not in mod.ALLOWED_ORIGINS
    assert mod.resolve_origin("*") == ""


def test_exact_match_returns_origin():
    mod = _reload_helper("https://a.com,https://b.com")
    assert mod.resolve_origin("https://a.com") == "https://a.com"
    assert mod.resolve_origin("https://b.com") == "https://b.com"


def test_mismatch_returns_empty():
    mod = _reload_helper("https://a.com")
    assert mod.resolve_origin("https://evil.com") == ""


def test_whitespace_trimmed():
    mod = _reload_helper("  https://a.com  ,  https://b.com  ")
    assert mod.resolve_origin("https://a.com") == "https://a.com"


def test_empty_origin_returns_empty():
    mod = _reload_helper("https://a.com")
    assert mod.resolve_origin("") == ""
    assert mod.resolve_origin(None) == ""  # type: ignore[arg-type]


def test_subdomain_does_not_match_parent():
    """정확 일치 정책 — 서브도메인 자동 허용 없음."""
    mod = _reload_helper("https://example.com")
    assert mod.resolve_origin("https://api.example.com") == ""
