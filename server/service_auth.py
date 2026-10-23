"""Non-financial service authentication check; no broker imports or calls."""
import hmac
import re


def verify_service_auth(primary: str, provided: str, verification_id: str):
    primary = (primary or "").strip().strip('"')
    provided = (provided or "").strip()
    if not primary:
        return 503, {"ok": False, "error": "service_auth_unconfigured"}
    if not provided or not hmac.compare_digest(
        primary.encode("utf-8"), provided.encode("utf-8")
    ):
        return 401, {"ok": False, "error": "unauthorized"}
    if not re.fullmatch(r"[0-9a-f]{32}", verification_id or ""):
        return 400, {"ok": False, "error": "invalid_verification_id"}
    return 200, {
        "ok": True,
        "scope": "service-auth-only",
        "verification_id": verification_id,
    }
