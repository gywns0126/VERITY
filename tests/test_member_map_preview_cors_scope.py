"""Local-only regression tests for the editor-canvas CORS exception."""
import importlib.util
import io
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "vercel-api" / "api"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Handler:
    def __init__(self, command, origin, requested_method=None):
        self.command = command
        self.headers = {"Origin": origin}
        if requested_method is not None:
            self.headers["Access-Control-Request-Method"] = requested_method
        self.sent = []
        self.wfile = io.BytesIO()

    def send_response(self, _status):
        pass

    def send_header(self, key, value):
        self.sent.append((key, value))

    def end_headers(self):
        pass


@pytest.fixture
def apis(monkeypatch):
    package = types.ModuleType("api")
    package.__path__ = [str(API_DIR)]
    sb = types.ModuleType("api.supabase_client")
    sb.is_configured = lambda: True
    sb.verify_jwt = lambda _token: None
    monkeypatch.setitem(sys.modules, "api", package)
    monkeypatch.setitem(sys.modules, "api.supabase_client", sb)
    helper = _load("api.cors_helper", API_DIR / "cors_helper.py")
    monkeypatch.setitem(sys.modules, "api.cors_helper", helper)
    nest_validation = types.ModuleType("api.nest_validation")
    nest_validation.read_body = lambda _handler: {}
    nest_validation.number = lambda value, default=None: value if isinstance(value, (int, float)) else default
    nest_validation.asset = lambda _body: None
    nest_validation.select_all = lambda *_args: []
    monkeypatch.setitem(sys.modules, "api.nest_validation", nest_validation)
    validation = _load("api.member_map_state_validation", API_DIR / "member_map_state_validation.py")
    monkeypatch.setitem(sys.modules, "api.member_map_state_validation", validation)
    holdings = _load("preview_scope_holdings", API_DIR / "holdings.py")
    member_map = _load("preview_scope_member_map", API_DIR / "member_map_state.py")
    return helper, holdings, member_map


def _header(handler, key):
    return dict(handler.sent).get(key)


def test_preview_origin_is_exact_and_not_global(apis):
    helper, _, _ = apis
    preview = helper.MEMBER_PORTFOLIO_PREVIEW_ORIGIN
    assert helper.resolve_origin(preview) == ""
    assert helper.resolve_member_portfolio_origin(preview) == preview
    assert helper.resolve_member_portfolio_origin(preview + ".evil") == ""
    assert helper.resolve_member_portfolio_origin("null") == ""
    for production in ("https://www.alphanest.kr", "https://alphanest.kr"):
        assert helper.resolve_origin(production) == production


def test_holdings_preview_allows_only_get_and_get_preflight(apis):
    helper, holdings, _ = apis
    preview = helper.MEMBER_PORTFOLIO_PREVIEW_ORIGIN
    allowed = _Handler("GET", preview)
    holdings._cors_headers(allowed)
    assert _header(allowed, "Access-Control-Allow-Origin") == preview
    assert _header(allowed, "Access-Control-Allow-Methods") == "GET, OPTIONS"
    preflight = _Handler("OPTIONS", preview, "GET")
    holdings._cors_headers(preflight)
    assert _header(preflight, "Access-Control-Allow-Origin") == preview
    for method in ("POST", "PATCH", "DELETE"):
        denied = _Handler(method, preview)
        holdings._cors_headers(denied)
        assert _header(denied, "Access-Control-Allow-Origin") is None
    assert _header(_cors(holdings, "OPTIONS", preview, "POST"), "Access-Control-Allow-Origin") is None


def _cors(api, command, origin, requested_method=None):
    handler = _Handler(command, origin, requested_method)
    api._cors_headers(handler)
    return handler


def test_map_preview_allows_get_post_and_only_matching_preflight(apis):
    helper, _, member_map = apis
    preview = helper.MEMBER_PORTFOLIO_PREVIEW_ORIGIN
    for method in ("GET", "POST"):
        handler = _Handler(method, preview)
        member_map._json(handler, 200, {})
        assert _header(handler, "Access-Control-Allow-Origin") == preview
        assert _header(handler, "Access-Control-Allow-Methods") == "GET, POST, OPTIONS"
    for requested in ("GET", "POST"):
        handler = _Handler("OPTIONS", preview, requested)
        member_map.handler.do_OPTIONS(handler)
        assert _header(handler, "Access-Control-Allow-Origin") == preview
    denied = _Handler("OPTIONS", preview, "DELETE")
    member_map.handler.do_OPTIONS(denied)
    assert _header(denied, "Access-Control-Allow-Origin") is None


def test_evil_and_null_origins_have_no_endpoint_allowance(apis):
    helper, holdings, member_map = apis
    for origin in (helper.MEMBER_PORTFOLIO_PREVIEW_ORIGIN + ".evil", "null"):
        holding = _cors(holdings, "GET", origin)
        mapped = _Handler("POST", origin)
        member_map._json(mapped, 200, {})
        assert _header(holding, "Access-Control-Allow-Origin") is None
        assert _header(mapped, "Access-Control-Allow-Origin") is None


def test_production_origins_keep_existing_cors_behavior(apis):
    _, holdings, member_map = apis
    production = "https://www.alphanest.kr"
    holding = _cors(holdings, "POST", production)
    mapped = _Handler("POST", production)
    member_map._json(mapped, 200, {})
    assert _header(holding, "Access-Control-Allow-Origin") == production
    assert _header(holding, "Access-Control-Allow-Methods") == "GET, POST, PATCH, DELETE, OPTIONS"
    assert _header(mapped, "Access-Control-Allow-Origin") == production


def test_global_allowlist_cannot_expand_preview_methods(apis, monkeypatch):
    helper, holdings, member_map = apis
    preview = helper.MEMBER_PORTFOLIO_PREVIEW_ORIGIN
    monkeypatch.setattr(helper, "ALLOWED_ORIGINS", helper.ALLOWED_ORIGINS | {preview})
    assert helper.resolve_origin(preview) == preview
    for method in ("POST", "PATCH", "DELETE"):
        assert _header(_cors(holdings, method, preview), "Access-Control-Allow-Origin") is None
        assert _header(_cors(holdings, "OPTIONS", preview, method), "Access-Control-Allow-Origin") is None
    denied = _Handler("OPTIONS", preview, "DELETE")
    member_map.handler.do_OPTIONS(denied)
    assert _header(denied, "Access-Control-Allow-Origin") is None
