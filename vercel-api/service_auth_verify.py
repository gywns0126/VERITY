"""Manual deployment-build verification only. Never imported by an API or cron.

Uses already-provisioned server environment values without returning or logging
credentials. Fixed destinations, no redirects, no retries, no financial APIs.
"""
import json
import os
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


RAILWAY_CHECK = "https://verity-production-1e44.up.railway.app/internal/service-auth/verify"
SUPABASE_CHECK = "https://lykqebdcurreppowulsl.supabase.co/rest/v1/blocked_ips?select=ip&limit=0"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(opener, url, *, method="GET", headers=None):
    request = Request(url, method=method, headers=headers or {})
    try:
        with opener.open(request, timeout=10) as response:
            raw = response.read(4097)
            if len(raw) > 4096:
                return response.status, None
            try:
                return response.status, json.loads(raw)
            except (ValueError, UnicodeError):
                return response.status, None
    except HTTPError as error:
        # Neither upstream response bodies nor exception strings are printed.
        return error.code, None
    except (URLError, TimeoutError, OSError, ValueError):
        return 0, None


def verify(environ, opener):
    primary = (environ.get("RAILWAY_SHARED_SECRET") or "").strip().strip('"')
    supabase = (environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip().strip('"')
    verification_id = uuid.uuid4().hex
    report = {
        "verification_id": verification_id,
        "scope": "service-auth-only",
        "execution": "vercel-build-once",
        "source_commit": environ.get("VERCEL_GIT_COMMIT_SHA", ""),
        "configuration_present": bool(primary and supabase),
    }
    if not report["configuration_present"]:
        report["ok"] = False
        return report
    base_headers = {"X-Verification-Id": verification_id}
    checks = {}
    for label, extra_headers, expected in (
        ("missing_rejected", {}, 401),
        ("synthetic_wrong_rejected", {"X-Service-Auth": "rotation-probe-invalid"}, 401),
        ("bearer_only_rejected", {"Authorization": "Bearer rotation-probe-invalid"}, 401),
        ("current_secret_accepted", {"X-Service-Auth": primary}, 200),
    ):
        status, payload = request_json(
            opener, RAILWAY_CHECK, method="POST", headers={**base_headers, **extra_headers}
        )
        accepted = status == expected
        if expected == 200:
            accepted = accepted and isinstance(payload, dict) and payload.get("ok") is True and payload == {
                "ok": True,
                "scope": "service-auth-only",
                "verification_id": verification_id,
            }
        checks[label] = {"status": status, "passed": accepted}
    status, payload = request_json(opener, SUPABASE_CHECK, headers={"apikey": supabase})
    checks["supabase_zero_row_read"] = {"status": status, "passed": status == 200 and payload == []}
    report["checks"] = checks
    report["ok"] = all(check["passed"] for check in checks.values())
    return report


if __name__ == "__main__":
    result = verify(os.environ, build_opener(ProxyHandler({}), NoRedirect()))
    print("SERVICE_AUTH_VERIFICATION " + json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["ok"] else 1)
