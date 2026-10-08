"""AlphaConsole may access its groups without widening other API origins."""
import importlib.util
import io
import json
import sys
import types
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[1] / "vercel-api" / "api"
ORIGIN = "https://alphanest-psi.vercel.app"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def api(monkeypatch):
    monkeypatch.delenv("API_ALLOWED_ORIGINS", raising=False)
    package = types.ModuleType("api")
    package.__path__ = [str(API)]
    sb = types.ModuleType("api.supabase_client")
    sb.is_configured = lambda: True
    sb.verify_jwt = lambda _token: None
    sb.select = lambda *_args, **_kwargs: pytest.fail("Unauthenticated DB access")
    monkeypatch.setitem(sys.modules, "api", package)
    monkeypatch.setitem(sys.modules, "api.supabase_client", sb)
    helper = load("api.cors_helper", API / "cors_helper.py")
    monkeypatch.setitem(sys.modules, "api.cors_helper", helper)
    return load("operator_watchgroups", API / "watchgroups.py"), helper


class Handler:
    def __init__(self, method="GET", origin=ORIGIN, requested="GET", token=None):
        self.command = method
        self.headers = {"Origin": origin, "Access-Control-Request-Method": requested}
        if token:
            self.headers["Authorization"] = "Bearer " + token
        self.client_address = ("127.0.0.1", 1234)
        self.sent = {}
        self.wfile = io.BytesIO()
        self.status = None

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.sent[name] = value

    def end_headers(self):
        pass


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_exact_operator_preflight_and_response(api, method):
    endpoint, helper = api
    preflight = Handler("OPTIONS", requested=method)
    endpoint.handler.do_OPTIONS(preflight)
    response = Handler(method)
    endpoint._json_response(response, {"error": "example"}, 500)
    for handler in (preflight, response):
        assert handler.sent["Access-Control-Allow-Origin"] == ORIGIN
        assert handler.sent["Vary"] == "Origin"
        assert handler.sent["Access-Control-Allow-Methods"] == "GET, POST, DELETE, OPTIONS"
        assert "Access-Control-Allow-Credentials" not in handler.sent
    assert helper.resolve_origin(ORIGIN) == ""  # no global allowance


@pytest.mark.parametrize("origin", [ORIGIN + ".evil", "https://child.alphanest-psi.vercel.app", "http://alphanest-psi.vercel.app", "null", "", "*"])
def test_untrusted_origins_remain_denied(api, origin):
    endpoint, _ = api
    handler = Handler("OPTIONS", origin)
    endpoint.handler.do_OPTIONS(handler)
    assert "Access-Control-Allow-Origin" not in handler.sent


def test_operator_patch_not_added(api):
    endpoint, _ = api
    for handler in (Handler("PATCH"), Handler("OPTIONS", requested="PATCH")):
        endpoint._cors_headers(handler)
        assert "Access-Control-Allow-Origin" not in handler.sent


def test_public_origin_unchanged(api):
    endpoint, _ = api
    handler = Handler("PATCH", "https://www.alphanest.kr")
    endpoint._cors_headers(handler)
    assert handler.sent["Access-Control-Allow-Origin"] == "https://www.alphanest.kr"
    assert "PATCH" in handler.sent["Access-Control-Allow-Methods"]


@pytest.mark.parametrize("token", [None, "invalid-test-token"])
def test_operator_origin_does_not_bypass_auth(api, token):
    endpoint, _ = api
    handler = Handler(token=token)
    endpoint.handler.do_GET(handler)
    assert handler.status == 401
    assert handler.sent["Access-Control-Allow-Origin"] == ORIGIN
    assert "error" in json.loads(handler.wfile.getvalue())
