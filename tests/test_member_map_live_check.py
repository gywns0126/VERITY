"""Offline safety checks for the controlled two-account deployment probe."""
import copy
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("member_map_live_check", Path(__file__).resolve().parents[1] / "scripts/member_map_live_check.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def exercise(*, bad_header=False, wrong_owner=False, bad_preflight=False):
    users = [{"id": "test-A"}, {"id": "test-B"}]
    states = [{"user_id": user["id"], "revision": 4,
               "document": {"layouts": [{"test": user["id"]}]}, "public_event_cursor_at": None} for user in users]
    database = copy.deepcopy(states)
    checks, calls = [], []

    def check(kind, ok, statuses=(), count=1):
        checks.append(kind)
        assert ok, kind

    def request(method, token, body, query, origin):
        calls.append((method, token, body, query))
        headers = {"Cache-Control": "private, no-store", "Vary": "Authorization, Origin"}
        if origin == probe.SITE_ORIGIN:
            headers["Access-Control-Allow-Origin"] = origin
        if bad_header:
            headers["Access-Control-Allow-Origin"] = "*"
        if method == "OPTIONS":
            headers.update({"Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                            "Access-Control-Allow-Headers": "Authorization, Content-Type"})
            if bad_preflight:
                headers["Access-Control-Allow-Headers"] = "Content-Type"
            return 200, {}, headers
        if token is None:
            return 401, {"error": "authentication_required"}, headers
        index = 0 if token.endswith("A") else 1
        state = database[index]
        if method == "POST":
            if "user_id" in body:
                return 400, {"error": "invalid_request"}, headers
            if body["expected_revision"] != state["revision"]:
                return 409, {"error": "revision_conflict"}, headers
            state["revision"] += 1
            state["document"] = copy.deepcopy(body["document"])
        if wrong_owner and method == "GET":
            state = database[1-index]
        return 200, {key: copy.deepcopy(state[key]) for key in ("revision", "document", "public_event_cursor_at")}, headers

    def own(token, user, kind, expected):
        assert database[users.index(user)] == expected
        check(kind, True)

    probe.check_api_surface(request, check, users, ["jwt-A", "jwt-B"], states,
                            lambda user: "fresh-" + user["id"][-1], own)
    return checks, calls, database


def test_deployed_api_probe_uses_two_known_records_and_fresh_logins():
    checks, calls, database = exercise()
    assert checks.count("api_fresh_signin_restore") == 2
    assert checks.count("api_database_readback") == 2
    assert checks.count("api_stale_rejected") == 2
    assert checks.count("api_owner_payload_rejected") == 2
    assert {state["revision"] for state in database} == {5}
    assert not any("service" in (token or "") for _, token, _, _ in calls)
    assert probe.API_ENDPOINT == "https://project-yw131.vercel.app/api/member_map_state"


def test_preflight_reproduces_browser_authorization_and_json_headers():
    assert probe.api_headers("OPTIONS", None, probe.SITE_ORIGIN) == {
        "Origin": probe.SITE_ORIGIN, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type"}
    assert probe.api_headers("GET", "fixture-token", probe.SITE_ORIGIN) == {
        "Origin": probe.SITE_ORIGIN, "Authorization": "Bearer fixture-token"}


@pytest.mark.parametrize("fault, expected", [("bad_header", "api_private_headers"), ("wrong_owner", "api_restore_own"), ("bad_preflight", "api_preflight_permissions")])
def test_deployment_probe_stops_on_first_boundary_failure(fault, expected):
    with pytest.raises(AssertionError, match=expected):
        exercise(**{fault: True})
