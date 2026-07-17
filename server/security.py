"""
IP 침입 시도 추적 · 자동 차단 미들웨어 (Railway FastAPI).

방어층 — 민감 데이터는 이미 인증(RAILWAY_SHARED_SECRET)+Supabase RLS로 잠김.
이 미들웨어는 그 위에서 (1) 스캐너 소음 감소 (2) 가시성 (3) 명백 악성 IP 속도 저하.

동작:
- 차단 IP(blocked_ips, TTL) = 전 경로 즉시 403.
- .env/.git/wp-/경로순회/시크릿 파일 스캔 = 로깅 + 임계 N회 초과 시 자동 차단(TTL).
- Supabase(security_probe_log/blocked_ips)는 Vercel 과 공유 = 단일 블록리스트.

비차단 설계:
- Supabase 쓰기 = 데몬 스레드 fire-and-forget (이벤트 루프 미차단).
- 블록리스트 = 60초 캐시(데몬 스레드 갱신), 미들웨어는 메모리 set 만 읽음.

env (Railway 이미 배선): SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
조정: SEC_BLOCK_THRESHOLD(기본 3), SEC_BLOCK_TTL_SEC(기본 86400), SEC_DISABLED(=1 이면 관측만·차단 안 함).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Set

import requests
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("security")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SURFACE = "railway"

# SEC_DISABLED=1 → 관측(로깅)만, 실제 403 차단은 하지 않음 (오탐 관측 기간용 킬스위치).
BLOCK_ENABLED = os.environ.get("SEC_DISABLED", "").strip() not in ("1", "true", "True")
AUTO_BLOCK_THRESHOLD = int(os.environ.get("SEC_BLOCK_THRESHOLD", "3") or "3")
BLOCK_TTL_SEC = int(os.environ.get("SEC_BLOCK_TTL_SEC", str(24 * 3600)) or str(24 * 3600))
WINDOW_SEC = 600          # 스캔 카운트 슬라이딩 윈도(10분)
CACHE_TTL = 60            # 블록리스트 캐시 주기(초)
_HTTP_TIMEOUT = 4

# 명백 악성 스캔 패턴 — 정상 트래픽엔 나오지 않음 (오탐 최소화).
_PROBE = [
    (re.compile(r"\.env(\.|$|/|\?)", re.I), "env_probe"),
    (re.compile(r"/\.git(/|$)", re.I), "git_probe"),
    (re.compile(r"(wp-admin|wp-login|xmlrpc\.php|wp-content|wp-includes)", re.I), "wp_probe"),
    (re.compile(r"(\.\./|\.\.%2f|%2e%2e/|/etc/passwd)", re.I), "path_traversal"),
    (re.compile(r"/(phpmyadmin|adminer|\.aws|\.ssh|id_rsa|credentials|\.htpasswd|\.DS_Store|dump\.sql)", re.I), "secret_probe"),
    (re.compile(r"\.(php|asp|aspx|jsp|cgi|bak|old|sql|zip|tar\.gz)(/|$|\?)", re.I), "cgi_probe"),
]
# 정상 서비스 경로 접두어 — 여기서 시작하면 스캔 검사 스킵(오탐 방지).
_ALLOW_PREFIX = (
    "/health", "/tickers", "/snapshot", "/candles", "/chart",
    "/program", "/subscribe", "/api/order", "/stream",
    "/docs", "/openapi.json", "/redoc", "/favicon",
)

_blocked: Set[str] = set()
_counts: Dict[str, Deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(ts))


def _client_ip(request: Request) -> str:
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    if xff:
        return xff.split(",")[0].strip()
    xr = (request.headers.get("x-real-ip") or "").strip()
    if xr:
        return xr
    return (request.client.host if request.client else "") or ""


def _post(table: str, payload: dict) -> None:
    if not (SUPABASE_URL and SUPABASE_KEY):
        return
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            json=payload,
            headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates"},
            timeout=_HTTP_TIMEOUT,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("security supabase write fail (%s): %s", table, e)


def _log_probe(ip: str, path: str, method: str, ua: str, country: str, reason: str) -> None:
    _post("security_probe_log", {
        "ip": ip, "path": path[:400], "method": method,
        "user_agent": (ua or "")[:400], "country": country or None,
        "reason": reason, "surface": SURFACE,
    })


def _auto_block(ip: str, reason: str, hits: int) -> None:
    _post("blocked_ips", {
        "ip": ip, "reason": reason, "hits": hits, "auto": True,
        "surface": SURFACE, "created_by": "auto",
        "expires_at": _iso(time.time() + BLOCK_TTL_SEC),
    })
    with _lock:
        _blocked.add(ip)
    logger.warning("security auto-block ip=%s reason=%s hits=%s", ip, reason, hits)


def _refresh_blocklist() -> None:
    global _blocked
    if not (SUPABASE_URL and SUPABASE_KEY):
        return
    try:
        now_iso = _iso(time.time())
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/blocked_ips",
            params={"select": "ip,expires_at", "or": f"(expires_at.is.null,expires_at.gt.{now_iso})"},
            headers=_sb_headers(),
            timeout=5,
        )
        if r.status_code == 200:
            ips = {row["ip"] for row in r.json() if row.get("ip")}
            _blocked = ips  # 원자적 참조 스왑
    except Exception as e:  # noqa: BLE001
        logger.warning("security blocklist refresh fail: %s", e)


def _bg_refresher() -> None:
    while True:
        _refresh_blocklist()
        time.sleep(CACHE_TTL)


def _bump(ip: str) -> int:
    now = time.time()
    with _lock:
        dq = _counts[ip]
        dq.append(now)
        while dq and now - dq[0] > WINDOW_SEC:
            dq.popleft()
        return len(dq)


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        ip = _client_ip(request)

        # 1) 차단 IP → 즉시 403 (전 경로)
        if BLOCK_ENABLED and ip and ip in _blocked:
            return JSONResponse({"error": "forbidden"}, status_code=403)

        # 2) 정상 경로는 스캔 검사 스킵
        if not path.startswith(_ALLOW_PREFIX):
            for pat, reason in _PROBE:
                if pat.search(path):
                    ua = request.headers.get("user-agent", "")
                    country = request.headers.get("x-vercel-ip-country", "")
                    threading.Thread(
                        target=_log_probe, args=(ip, path, request.method, ua, country, reason), daemon=True
                    ).start()
                    n = _bump(ip) if ip else 0
                    if ip and n >= AUTO_BLOCK_THRESHOLD:
                        threading.Thread(target=_auto_block, args=(ip, reason, n), daemon=True).start()
                    if BLOCK_ENABLED:
                        return JSONResponse({"error": "forbidden"}, status_code=403)
                    break

        return await call_next(request)


def start_security(app) -> None:
    """미들웨어 등록 + 블록리스트 백그라운드 갱신 시작. main.py 에서 CORS 등록 뒤 호출."""
    if not (SUPABASE_URL and SUPABASE_KEY):
        logger.warning("security: SUPABASE_URL/SERVICE_ROLE_KEY 미설정 — 미들웨어 관측만(차단 로직 no-op).")
    _refresh_blocklist()
    threading.Thread(target=_bg_refresher, daemon=True).start()
    app.add_middleware(SecurityMiddleware)
    logger.info(
        "security middleware on (block=%s threshold=%s ttl=%ss)",
        BLOCK_ENABLED, AUTO_BLOCK_THRESHOLD, BLOCK_TTL_SEC,
    )
