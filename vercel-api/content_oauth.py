"""Invite-only OAuth code + S256 PKCE for public content, not website login.

No refresh tokens, dynamic clients, private user scopes or outbound redirects
except the pre-registered ChatGPT callback. DB checks are never cached.
"""
import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import time
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlencode, urlsplit

from content_mcp import ServiceError, _json_request

SCOPE = "content:read"
CLIENT_ID = "alphanest-content-chatgpt"
REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"
COOKIE = "__Host-ancontent-consent"


def config():
    origin = os.environ.get("CONTENT_MCP_ORIGIN", "")
    if (os.environ.get("CONTENT_MCP_ENABLED") != "1"
            or not re.fullmatch(r"https://[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", origin)):
        raise ServiceError(503, "connection_not_configured")
    return {"origin": origin, "issuer": origin + "/api/content_oauth",
            "resource": origin + "/api/content_mcp",
            "metadata": origin + "/.well-known/oauth-protected-resource/api/content_mcp"}


def rpc(name, params):
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not re.fullmatch(r"https://[a-z0-9-]+\.supabase\.co", base) or not key:
        raise ServiceError(503, "connection_not_configured")
    result = _json_request(base + "/rest/v1/rpc/" + name,
                           headers={"Content-Type": "application/json", "apikey": key,
                                    "Authorization": "Bearer " + key},
                           data=json.dumps(params).encode(), limit=4096)
    if not isinstance(result, dict):
        raise ServiceError(503, "access_check_unavailable")
    return result


def digest(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def challenge(verifier):
    return b64(hashlib.sha256(verifier.encode("ascii")).digest())


def authenticate(headers):
    cfg = config()
    auth = headers.get("authorization", "")
    if not re.fullmatch(r"Bearer ancontent_[A-Za-z0-9_-]{43}", auth):
        raise ServiceError(401, "unauthorized")
    result = rpc("content_mcp_consume_token", {
        "p_token_hash": digest(auth[7:]), "p_resource": cfg["resource"], "p_scope": SCOPE})
    if result.get("status") == "limited":
        raise ServiceError(429, "request_limit_reached")
    if result.get("status") != "allowed":
        raise ServiceError(401, "unauthorized")


def fields(raw):
    try:
        pairs = parse_qs(raw, keep_blank_values=True, max_num_fields=16,
                         encoding="utf-8", errors="strict")
    except (ValueError, UnicodeError):
        raise ServiceError(400, "invalid_request") from None
    if any(len(v) != 1 or len(v[0]) > 4096 for v in pairs.values()):
        raise ServiceError(400, "invalid_request")
    return {k: v[0] for k, v in pairs.items()}


def validated_authorization(params, cfg):
    required = {"client_id", "response_type", "redirect_uri", "resource", "scope",
                "state", "code_challenge", "code_challenge_method"}
    if (set(params) - {"ui_locales"} != required or params["client_id"] != CLIENT_ID
            or params["redirect_uri"] != REDIRECT or params["response_type"] != "code"
            or params["resource"] != cfg["resource"] or params["scope"] != SCOPE
            or params["code_challenge_method"] != "S256"
            or not re.fullmatch(r"[A-Za-z0-9_-]{43}", params["code_challenge"])
            or not 1 <= len(params["state"]) <= 1024
            or any(ord(c) < 32 or ord(c) == 127 for c in params["state"])):
        # Invalid/untrusted requests never receive a redirect.
        raise ServiceError(400, "invalid_authorization_request")
    # ChatGPT sends this optional display hint. fields() already bounds its
    # length and rejects duplicates; never render, seal or forward the hint.
    return {key: value for key, value in params.items() if key in required}


def signing_key():
    key = os.environ.get("CONTENT_MCP_CONSENT_SECRET", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", key):
        raise ServiceError(503, "connection_not_configured")
    return key.encode("ascii")


def seal(params, nonce):
    value = b64(json.dumps({"params": params, "nonce": nonce,
                            "exp": int(time.time()) + 300}, separators=(",", ":")).encode())
    return value + "." + b64(hmac.digest(signing_key(), value.encode(), "sha256"))


def unseal(value, cookie):
    try:
        encoded, signature = value.split(".")
        expected = b64(hmac.digest(signing_key(), encoded.encode(), "sha256"))
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        doc = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        jar = SimpleCookie()
        jar.load(cookie)
        nonce = jar[COOKIE].value
        if (not re.fullmatch(r"[A-Za-z0-9_-]{43}", nonce)
                or not hmac.compare_digest(doc["nonce"], nonce)
                or not time.time() < doc["exp"] <= time.time() + 301):
            raise ValueError()
        return doc["params"]
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise ServiceError(400, "invalid_or_expired_consent") from None


def metadata(kind, cfg):
    if kind == "resource":
        return {"resource": cfg["resource"], "authorization_servers": [cfg["issuer"]],
                "scopes_supported": [SCOPE], "bearer_methods_supported": ["header"],
                "resource_name": "AlphaNest public content"}
    return {"issuer": cfg["issuer"], "authorization_endpoint": cfg["issuer"] + "?op=authorize",
            "token_endpoint": cfg["issuer"] + "?op=token", "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"], "scopes_supported": [SCOPE],
            "token_endpoint_auth_methods_supported": ["none"],
            "code_challenge_methods_supported": ["S256"],
            "authorization_response_iss_parameter_supported": True}


def process(method, path, headers, body):
    """Return status, body (dict or HTML), extra headers. No secret-bearing logs."""
    cfg = config()
    headers = {k.lower(): v for k, v in headers.items()}
    if len(path) > 8192 or len(body) > 16384:
        raise ServiceError(413, "request_too_large")
    url = urlsplit(path)
    query = fields(url.query)
    op = query.pop("op", "")
    if url.path == "/.well-known/oauth-authorization-server/api/content_oauth":
        op = "server"
    elif url.path == "/.well-known/oauth-protected-resource/api/content_mcp":
        op = "resource"
    if op in ("server", "resource"):
        if method != "GET" or query:
            raise ServiceError(400, "invalid_request")
        return 200, metadata(op, cfg), {}
    if op == "authorize" and method == "GET":
        params = validated_authorization(query, cfg)
        nonce = secrets.token_urlsafe(32)
        signed = seal(params, nonce)
        page = '''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>알파네스트 콘텐츠 연결</title>
<style>body{font:17px/1.7 system-ui;margin:40px auto;padding:24px;max-width:520px;color:#202530;background:#f7f8fa}main{background:white;padding:28px;border-radius:20px}input,button{box-sizing:border-box;font:inherit;padding:12px;margin-top:12px;width:100%%}button{cursor:pointer}small{color:#596474}</style>
<main><h1>알파네스트 콘텐츠 연결</h1><p>ChatGPT에 공개 공시·교육용 자료 조회를 허용합니다.</p>
<p>개인 보유종목·계정 정보·관리자 권한은 포함하지 않습니다. 매매와 자동 게시도 할 수 없습니다.</p>
<p><small>허용 권한: content:read · 연결 유효기간 최대 1시간 · 만료 시 다시 연결합니다.</small></p>
<form method="post" action="/api/content_oauth?op=authorize">
<input type="hidden" name="consent" value="%s">
<label>전달받은 콘텐츠 전용 초대코드<input type="password" name="invite" maxlength="53" autocomplete="off" spellcheck="false"></label>
<button name="decision" value="allow">공개 자료 조회 허용</button>
<button name="decision" value="deny">취소</button></form>
<p><small>사이트 비밀번호나 증권사·관리자 키를 입력하지 마세요.</small></p></main></html>''' % html.escape(signed, quote=True)
        return 200, page, {"Set-Cookie": COOKIE + "=" + nonce + "; Path=/; Max-Age=300; Secure; HttpOnly; SameSite=Lax"}
    if method != "POST" or op not in ("authorize", "token") or query:
        raise ServiceError(405, "method_not_allowed")
    if headers.get("content-type", "").split(";", 1)[0].strip() != "application/x-www-form-urlencoded":
        raise ServiceError(415, "form_required")
    try:
        data = fields(body.decode("utf-8"))
    except UnicodeError:
        raise ServiceError(400, "invalid_request") from None
    if op == "authorize":
        if headers.get("origin") != cfg["origin"] or set(data) != {"consent", "invite", "decision"}:
            raise ServiceError(403, "invalid_consent")
        params = validated_authorization(unseal(data["consent"], headers.get("cookie", "")), cfg)
        response = {"state": params["state"], "iss": cfg["issuer"]}
        if data["decision"] == "deny":
            response["error"] = "access_denied"
        elif data["decision"] == "allow":
            if not re.fullmatch(r"aninvite_[A-Za-z0-9_-]{43}", data["invite"]):
                raise ServiceError(403, "invalid_invitation")
            code = "ancode_" + secrets.token_urlsafe(32)
            result = rpc("content_mcp_issue_code", {
                "p_invite_hash": digest(data["invite"]), "p_code_hash": digest(code),
                **{"p_" + k: params[k] for k in ("client_id", "redirect_uri", "resource", "scope", "code_challenge")}})
            if result.get("status") == "limited":
                raise ServiceError(429, "request_limit_reached")
            if result.get("status") != "allowed":
                raise ServiceError(403, "invalid_invitation")
            response["code"] = code
        else:
            raise ServiceError(400, "invalid_consent")
        return 303, {}, {"Location": REDIRECT + "?" + urlencode(response),
                         "Set-Cookie": COOKIE + "=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax"}
    # Token exchange: no website login tokens and no client secret accepted.
    required = {"grant_type", "code", "client_id", "redirect_uri", "resource", "code_verifier"}
    if (set(data) - {"scope"} != required or data["grant_type"] != "authorization_code"
            or data["client_id"] != CLIENT_ID or data["redirect_uri"] != REDIRECT
            or data["resource"] != cfg["resource"] or data.get("scope", SCOPE) != SCOPE
            or not re.fullmatch(r"ancode_[A-Za-z0-9_-]{43}", data["code"])
            or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", data["code_verifier"])
            or headers.get("authorization")
            or headers.get("origin", "https://chatgpt.com") not in ("https://chatgpt.com", "https://chat.openai.com")):
        raise ServiceError(400, "invalid_grant")
    token = "ancontent_" + secrets.token_urlsafe(32)
    result = rpc("content_mcp_exchange_code", {
        "p_code_hash": digest(data["code"]), "p_token_hash": digest(token), "p_scope": SCOPE,
        "p_code_challenge": challenge(data["code_verifier"]),
        **{"p_" + k: data[k] for k in ("client_id", "redirect_uri", "resource")}})
    expires = result.get("expires_in")
    if result.get("status") != "allowed" or type(expires) is not int or not 0 < expires <= 3600:
        raise ServiceError(400, "invalid_grant")
    return 200, {"access_token": token, "token_type": "Bearer", "expires_in": expires, "scope": SCOPE}, {}
