"""Offline contract tests: synthetic credentials, fake HTTP, no server import.

Direct execution (standard library only):
    env -i /absolute/path/to/python3 -I /absolute/path/to/test_service_auth_verify.py
Only direct execution installs the socket-denial audit hook before loading the
isolated modules. Importing for test collection never registers that global hook.
"""
import sys

sys.dont_write_bytecode = True


def _deny_network(event, args):
    if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo",
                 "socket.gethostbyname", "socket.gethostbyaddr", "socket.sendto",
                 "socket.sendmsg", "socket.bind"}:
        raise AssertionError("Network is forbidden in this offline suite")


if __name__ == "__main__":
    sys.addaudithook(_deny_network)

import ast
import asyncio
import contextlib
import importlib.util
import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = ROOT / "server/service_auth.py"
MAIN_PATH = ROOT / "server/main.py"
SCRIPT_PATH = ROOT / "vercel-api/service_auth_verify.py"
RAILWAY = "https://verity-production-1e44.up.railway.app/internal/service-auth/verify"
SUPABASE = "https://lykqebdcurreppowulsl.supabase.co/rest/v1/blocked_ips?select=ip&limit=0"
PRIMARY = "synthetic-current-service-secret"
LEGACY = "synthetic-retired-service-secret"
SB_KEY = "sb_secret_synthetic_only"
VERIFY_ID = "0123456789abcdef0123456789abcdef"
ENV = {"RAILWAY_SHARED_SECRET": PRIMARY,
       "SUPABASE_SERVICE_ROLE_KEY": SB_KEY,
       "VERCEL_GIT_COMMIT_SHA": "synthetic-source-revision"}


def load_isolated(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPER = load_isolated("isolated_service_auth", HELPER_PATH)
SCRIPT = load_isolated("isolated_service_auth_build_probe", SCRIPT_PATH)
MAIN_TREE = ast.parse(MAIN_PATH.read_text(encoding="utf-8"), filename=str(MAIN_PATH))
SCRIPT_TREE = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"), filename=str(SCRIPT_PATH))


class Headers(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


class Response:
    def __init__(self, status, body):
        self.status = status
        self.raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        self.read_sizes.append(size)
        return self.raw[:size]


class FakeOpener:
    def __init__(self, mutate=None):
        self.calls = []
        self.mutate = mutate

    def open(self, request, timeout):
        if request.full_url not in (RAILWAY, SUPABASE):
            raise AssertionError("Unexpected destination")
        self.calls.append((request, timeout))
        headers = Headers((key.lower(), value) for key, value in request.header_items())
        if request.full_url == SUPABASE:
            result = (200, [])
        else:
            result = HELPER.verify_service_auth(
                PRIMARY, headers.get("x-service-auth", ""),
                headers.get("x-verification-id", ""))
        if self.mutate is not None:
            result = self.mutate(request, *result)
        if isinstance(result, BaseException):
            raise result
        return Response(*result)


def run_verify(opener, environ=None):
    # A supplied mapping is the only environment source; real process values
    # and credential/configuration files are never queried by these tests.
    with patch.object(SCRIPT.uuid, "uuid4", return_value=SimpleNamespace(hex=VERIFY_ID)):
        return SCRIPT.verify(dict(ENV if environ is None else environ), opener)


def extracted_route(environ):
    node = next(n for n in MAIN_TREE.body
                if isinstance(n, ast.AsyncFunctionDef) and n.name == "service_auth_verify")
    # Compile only this route. No imports, other functions, module-level
    # initializers, FastAPI lifespan or broker objects from main are executed.
    tree = ast.parse(ast.unparse(node))
    tree.body[0].decorator_list = []
    logger = Mock()

    def response(payload, status_code, headers):
        return SimpleNamespace(payload=payload, status_code=status_code, headers=headers)

    namespace = {"Request": object, "verify_service_auth": HELPER.verify_service_auth,
                 "os": SimpleNamespace(environ=environ), "logger": logger,
                 "JSONResponse": response}
    exec(compile(tree, "<isolated-auth-only-route>", "exec"), namespace)
    return namespace["service_auth_verify"], logger


class ServiceAuthHelperTests(unittest.TestCase):
    def test_primary_only_and_missing_configuration(self):
        cases = [("", PRIMARY, 503), ("   ", PRIMARY, 503),
                 (PRIMARY, "", 401), (PRIMARY, LEGACY, 401),
                 (PRIMARY, "Bearer " + PRIMARY, 401), (PRIMARY, PRIMARY, 200)]
        for configured, supplied, expected in cases:
            with self.subTest(expected=expected, supplied_kind=bool(supplied)):
                status, payload = HELPER.verify_service_auth(configured, supplied, VERIFY_ID)
                self.assertEqual(status, expected)
                self.assertIs(payload["ok"], expected == 200)
                self.assertNotIn(PRIMARY, json.dumps(payload))

    def test_correlation_id_validation(self):
        for value in ("", "../unsafe", "a" * 31, "a" * 33, "G" * 32, "a" * 32 + "\n"):
            with self.subTest(value_length=len(value)):
                self.assertEqual(HELPER.verify_service_auth(PRIMARY, PRIMARY, value)[0], 400)


class IsolatedRouteTests(unittest.TestCase):
    def test_auth_only_post_registration_and_dependency_boundary(self):
        node = next(n for n in MAIN_TREE.body
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == "service_auth_verify")
        self.assertEqual(len(node.decorator_list), 1)
        decorator = node.decorator_list[0]
        self.assertEqual(decorator.func.attr, "post")
        self.assertEqual(decorator.args[0].value, "/internal/service-auth/verify")
        forbidden = {"get_balance", "place_kr_order", "place_us_order", "token_status",
                     "ws_client", "_get_token", "requests", "_order_auth_fail_response"}
        self.assertFalse({n.id for n in ast.walk(node) if isinstance(n, ast.Name)} & forbidden)

    def test_route_legacy_headers_fail_and_never_return_secret(self):
        env = {"RAILWAY_SHARED_SECRET": PRIMARY, "ORDER_SECRET": LEGACY}
        route, logger = extracted_route(env)
        for headers, expected in [({}, 401),
                ({"authorization": "Bearer " + LEGACY}, 401),
                ({"authorization": "Bearer " + PRIMARY}, 401),
                ({"x-service-auth": LEGACY}, 401),
                ({"x-service-auth": PRIMARY}, 200)]:
            with self.subTest(expected=expected, header_names=list(headers)):
                response = asyncio.run(route(SimpleNamespace(headers=Headers(
                    {**headers, "x-verification-id": VERIFY_ID}))))
                self.assertEqual(response.status_code, expected)
                self.assertEqual(response.headers.get("Cache-Control"), "no-store")
                for secret in (PRIMARY, LEGACY, SB_KEY):
                    self.assertNotIn(secret, json.dumps(response.payload))
                    self.assertNotIn(secret, repr(logger.mock_calls))

    def test_legacy_configuration_cannot_replace_primary(self):
        route, _ = extracted_route({"ORDER_SECRET": LEGACY})
        response = asyncio.run(route(SimpleNamespace(headers=Headers({
            "x-service-auth": LEGACY, "x-verification-id": VERIFY_ID}))))
        self.assertEqual(response.status_code, 503)


class BuildProbeTests(unittest.TestCase):
    def test_success_uses_only_fixed_destinations_and_five_bounded_requests(self):
        opener = FakeOpener()
        result = run_verify(opener, {**ENV, "RAILWAY_URL": "https://synthetic.invalid/",
            "SUPABASE_URL": "https://synthetic.invalid/", "ORDER_SECRET": LEGACY})
        self.assertIs(result["ok"], True)
        self.assertEqual(len(opener.calls), 5)  # four auth checks, one zero-row read
        self.assertEqual([r.full_url for r, _ in opener.calls], [RAILWAY] * 4 + [SUPABASE])
        self.assertEqual([r.get_method() for r, _ in opener.calls], ["POST"] * 4 + ["GET"])
        for request, timeout in opener.calls:
            self.assertEqual(timeout, 10)
            self.assertIsNone(request.data)
            headers = Headers((k.lower(), v) for k, v in request.header_items())
            self.assertNotIn("x-verity-broker", headers)
            self.assertNotIn("x-verity-user-id", headers)
        sb_headers = Headers((k.lower(), v) for k, v in opener.calls[-1][0].header_items())
        self.assertEqual(dict(sb_headers), {"apikey": SB_KEY})
        self.assertNotIn("server.main", sys.modules)

    def test_missing_either_key_makes_no_requests(self):
        for key in ("RAILWAY_SHARED_SECRET", "SUPABASE_SERVICE_ROLE_KEY"):
            for value in (None, "", "   "):
                env = dict(ENV)
                env[key] = value
                opener = FakeOpener()
                self.assertIs(run_verify(opener, env)["ok"], False)
                self.assertEqual(opener.calls, [])

    def test_auth_503_or_wrong_negative_status_cannot_pass(self):
        for status in (200, 400, 403, 503):
            opener = FakeOpener(lambda req, code, body:
                (status, body) if req.full_url == RAILWAY and code == 401 else (code, body))
            self.assertIs(run_verify(opener)["ok"], False)
            self.assertEqual(len(opener.calls), 5)

    def test_success_payload_requires_exact_values_and_fields(self):
        bad = [{}, [], None, {"ok": True},
               {"ok": True, "scope": "other", "verification_id": VERIFY_ID},
               {"ok": True, "scope": "service-auth-only", "verification_id": "b" * 32},
               {"ok": True, "scope": "service-auth-only", "verification_id": VERIFY_ID,
                "unexpected": True}]
        for payload in bad:
            opener = FakeOpener(lambda req, code, body:
                (code, payload) if req.full_url == RAILWAY and code == 200 else (code, body))
            self.assertIs(run_verify(opener)["ok"], False)

    def test_numeric_ok_is_not_a_boolean_success(self):
        opener = FakeOpener(lambda req, code, body:
            (code, {**body, "ok": 1}) if req.full_url == RAILWAY and code == 200 else (code, body))
        self.assertIs(run_verify(opener)["ok"], False,
                      "Numeric ok must not satisfy the boolean success contract")

    def test_supabase_requires_200_and_an_empty_array(self):
        for status, payload in [(401, []), (503, []), (200, {}), (200, None),
                                (200, [{"ip": "synthetic"}]), (204, [])]:
            opener = FakeOpener(lambda req, code, body:
                (status, payload) if req.full_url == SUPABASE else (code, body))
            self.assertIs(run_verify(opener)["ok"], False)

    def test_request_json_bounds_body_and_rejects_invalid_json(self):
        for body in (b"x" * 4097, b"not-json", b"\xff", b""):
            response = Response(200, body)
            opener = SimpleNamespace(open=Mock(return_value=response))
            self.assertEqual(SCRIPT.request_json(opener, RAILWAY), (200, None))
            self.assertEqual(response.read_sizes, [4097])
            self.assertEqual(opener.open.call_count, 1)

    def test_redirect_handler_refuses_all_redirects_without_followup(self):
        for status in (301, 302, 303, 307, 308):
            self.assertIsNone(SCRIPT.NoRedirect().redirect_request(
                Request(RAILWAY), None, status, "synthetic", {}, "https://synthetic.invalid/"))
            opener = FakeOpener(lambda req, code, body:
                HTTPError(req.full_url, status, "synthetic", {}, None))
            self.assertIs(run_verify(opener)["ok"], False)
            self.assertEqual(len(opener.calls), 5)

    def test_timeouts_errors_and_sensitive_exception_text_never_pass_or_leak(self):
        for error in (TimeoutError(PRIMARY), URLError(SB_KEY), OSError(LEGACY),
                      HTTPError(RAILWAY, 503, PRIMARY, {}, None)):
            output = io.StringIO()
            logs = io.StringIO()
            handler = logging.StreamHandler(logs)
            logging.getLogger().addHandler(handler)
            try:
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    opener = FakeOpener(lambda *args: error)
                    report = run_verify(opener)
            finally:
                logging.getLogger().removeHandler(handler)
            self.assertIs(report["ok"], False)
            self.assertEqual(len(opener.calls), 5)  # no retries of any check
            for secret in (PRIMARY, LEGACY, SB_KEY):
                self.assertNotIn(secret, output.getvalue() + logs.getvalue() + json.dumps(report))

    def _run_entrypoint(self, opener, build_factory=None):
        node = next(n for n in SCRIPT_TREE.body if isinstance(n, ast.If)
                    and "__name__" in ast.unparse(n.test))
        namespace = dict(vars(SCRIPT), __name__="__main__",
                         os=SimpleNamespace(environ=dict(ENV)),
                         build_opener=build_factory or (lambda *handlers: opener))
        output = io.StringIO()
        with patch.object(SCRIPT.uuid, "uuid4", return_value=SimpleNamespace(hex=VERIFY_ID)):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                with self.assertRaises(SystemExit) as stopped:
                    exec(compile(ast.Module(body=node.body, type_ignores=[]),
                                 "<isolated-probe-entrypoint>", "exec"), namespace)
        return stopped.exception.code, output.getvalue()

    def test_entrypoint_exit_code_and_stdout_are_sanitized(self):
        for failed in (False, True):
            opener = FakeOpener((lambda *args: TimeoutError(PRIMARY)) if failed else None)
            code, output = self._run_entrypoint(opener)
            self.assertEqual(code, int(failed))
            self.assertEqual(len(output.splitlines()), 1)
            report = json.loads(output.removeprefix("SERVICE_AUTH_VERIFICATION "))
            self.assertIs(report["ok"], not failed)
            for secret in (PRIMARY, LEGACY, SB_KEY):
                self.assertNotIn(secret, output)

    def test_entrypoint_explicitly_disables_environment_proxies(self):
        seen = []

        def factory(*handlers):
            # Only synthetic proxy discovery is used; no process env is read.
            with patch("urllib.request.getproxies", return_value={
                    "https": "http://synthetic-proxy.invalid:3128"}):
                actual = build_opener(*handlers)
            seen.extend(h for h in actual.handlers if isinstance(h, ProxyHandler))
            return FakeOpener()

        self._run_entrypoint(FakeOpener(), factory)
        self.assertFalse(any(handler.proxies for handler in seen),
                         "Build opener must explicitly disable environment proxies")


if __name__ == "__main__":
    unittest.main(verbosity=2)
