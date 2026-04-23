#!/usr/bin/env python3
"""
VERITY /api/order — Railway 라이브 스모크 테스트.

배포 직후 /api/order 가 fail-closed 인증 + 검증 + 잔고 조회를 제대로 수행하는지
빠르게 확인. **실제 주문은 절대 전송하지 않음** — 검증실패 또는 인증거부로
응답하는 경로만 때린다.

체크 항목:
  1. X-Service-Auth 없음       → 401 또는 503
  2. X-Service-Auth 틀림        → 401
  3. GET 잔고 (market=kr)       → 200 + 구조
  4. POST ticker 누락           → 400 (broker 미도달)
  5. POST side 이상             → 400 (broker 미도달)
  6. POST qty=0                → 400 (broker 미도달)

사용:
  export RAILWAY_SHARED_SECRET='...'
  python3 scripts/smoke_order.py                                       # 기본 URL
  python3 scripts/smoke_order.py --url https://my.up.railway.app
  python3 scripts/smoke_order.py --skip-balance                        # KIS 키 없을 때
  python3 scripts/smoke_order.py --secret env:MY_SECRET_VAR

실패 신호:
  - 1/2 에서 200 반환 → fail-closed 미작동 (CRIT)
  - 3 에서 502/500   → KIS 토큰/계좌 문제 (--skip-balance 로 우회)
  - 4/5/6 에서 200  → 검증 게이트 우회 (POST가 실주문까지 도달했을 가능성)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional, Tuple

try:
    import requests
except ImportError:
    print("ERROR: requests 모듈 필요 — pip install requests")
    sys.exit(2)


DEFAULT_URL = "https://verity-production-1e44.up.railway.app"

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
RESET = "\033[0m"


def _resolve_secret(arg: Optional[str]) -> str:
    """--secret 해석. `env:NAME` 형식이면 그 env 를 읽고, 없으면 RAILWAY_SHARED_SECRET."""
    if arg and arg.startswith("env:"):
        name = arg[4:].strip()
        return (os.environ.get(name) or "").strip().strip('"')
    if arg:
        return arg.strip().strip('"')
    return (os.environ.get("RAILWAY_SHARED_SECRET") or "").strip().strip('"')


def _call(
    method: str,
    url: str,
    headers: dict,
    json_body: Optional[dict] = None,
    params: Optional[dict] = None,
    timeout: float = 12.0,
) -> Tuple[int, dict, float]:
    t0 = time.time()
    try:
        resp = requests.request(
            method,
            url,
            headers=headers,
            json=json_body,
            params=params,
            timeout=timeout,
        )
    except requests.RequestException as e:
        return -1, {"_error": f"{type(e).__name__}: {e}"}, (time.time() - t0) * 1000
    ms = (time.time() - t0) * 1000
    try:
        body = resp.json() if resp.text else {}
    except Exception:
        body = {"_raw": resp.text[:300]}
    return resp.status_code, body, ms


def _ok(msg: str, detail: str = "") -> bool:
    print(f"{GREEN}  ✓{RESET} {msg}{(' — ' + DIM + detail + RESET) if detail else ''}")
    return True


def _fail(msg: str, detail: str = "") -> bool:
    print(f"{RED}  ✗{RESET} {msg}{(' — ' + detail) if detail else ''}")
    return False


def check_auth_missing(base_url: str) -> bool:
    """체크 1: X-Service-Auth 없음 → 401 또는 503 기대."""
    print(f"{CYAN}[1]{RESET} 인증 헤더 없음 → 401/503 기대")
    status, body, ms = _call("GET", f"{base_url}/api/order", headers={}, params={"market": "kr"})
    if status in (401, 503):
        return _ok(f"HTTP {status} ({ms:.0f}ms)", str(body)[:100])
    return _fail(f"HTTP {status} (기대 401/503)", str(body)[:200])


def check_auth_wrong(base_url: str) -> bool:
    """체크 2: X-Service-Auth 틀림 → 401 기대."""
    print(f"{CYAN}[2]{RESET} 잘못된 X-Service-Auth → 401 기대")
    status, body, ms = _call(
        "GET",
        f"{base_url}/api/order",
        headers={"X-Service-Auth": "definitely-wrong-value-xxx"},
        params={"market": "kr"},
    )
    if status == 401:
        return _ok(f"HTTP 401 ({ms:.0f}ms)", str(body)[:100])
    return _fail(f"HTTP {status} (기대 401)", str(body)[:200])


def check_balance(base_url: str, secret: str) -> bool:
    """체크 3: 올바른 secret 으로 잔고 조회 → 200 기대."""
    print(f"{CYAN}[3]{RESET} GET /api/order?market=kr (정상 인증) → 200 기대")
    status, body, ms = _call(
        "GET",
        f"{base_url}/api/order",
        headers={"X-Service-Auth": secret},
        params={"market": "kr"},
    )
    if status == 200:
        keys = list(body.keys()) if isinstance(body, dict) else []
        return _ok(f"HTTP 200 ({ms:.0f}ms)", f"keys={keys[:5]}")
    hint = ""
    if status in (500, 502):
        hint = " (KIS 키/계좌 미설정 가능 — --skip-balance 로 스킵)"
    return _fail(f"HTTP {status} (기대 200){hint}", str(body)[:200])


def check_validation_missing_ticker(base_url: str, secret: str) -> bool:
    """체크 4: ticker 누락 → 400 기대 (broker 미도달)."""
    print(f"{CYAN}[4]{RESET} POST ticker 누락 → 400 기대 (broker 미도달)")
    status, body, ms = _call(
        "POST",
        f"{base_url}/api/order",
        headers={"X-Service-Auth": secret},
        json_body={
            "market": "kr", "ticker": "", "side": "buy", "qty": 1, "price": 1,
        },
    )
    if status == 400:
        return _ok(f"HTTP 400 ({ms:.0f}ms)", str(body.get("message", ""))[:100])
    return _fail(f"HTTP {status} (기대 400 — 검증 실패)", str(body)[:200])


def check_validation_bad_side(base_url: str, secret: str) -> bool:
    """체크 5: side 이상 → 400 기대."""
    print(f"{CYAN}[5]{RESET} POST side=hold → 400 기대")
    status, body, ms = _call(
        "POST",
        f"{base_url}/api/order",
        headers={"X-Service-Auth": secret},
        json_body={
            "market": "kr", "ticker": "005930", "side": "hold", "qty": 1, "price": 1,
        },
    )
    if status == 400:
        return _ok(f"HTTP 400 ({ms:.0f}ms)", str(body.get("message", ""))[:100])
    return _fail(f"HTTP {status} (기대 400)", str(body)[:200])


def check_validation_zero_qty(base_url: str, secret: str) -> bool:
    """체크 6: qty=0 → 400 기대."""
    print(f"{CYAN}[6]{RESET} POST qty=0 → 400 기대")
    status, body, ms = _call(
        "POST",
        f"{base_url}/api/order",
        headers={"X-Service-Auth": secret},
        json_body={
            "market": "kr", "ticker": "005930", "side": "buy", "qty": 0, "price": 1,
        },
    )
    if status == 400:
        return _ok(f"HTTP 400 ({ms:.0f}ms)", str(body.get("message", ""))[:100])
    return _fail(f"HTTP {status} (기대 400)", str(body)[:200])


def main() -> int:
    ap = argparse.ArgumentParser(
        description="VERITY /api/order Railway 스모크 테스트 (실주문 미전송)"
    )
    ap.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Railway base URL (기본 {DEFAULT_URL})",
    )
    ap.add_argument(
        "--secret",
        default=None,
        help="RAILWAY_SHARED_SECRET 값. 'env:NAME' 으로 env 지정 가능. "
        "미지정 시 RAILWAY_SHARED_SECRET 환경변수 사용.",
    )
    ap.add_argument(
        "--skip-balance",
        action="store_true",
        help="KIS 미설정 환경에서 잔고 조회 체크를 건너뜀 (auth/validation 만 확인)",
    )
    args = ap.parse_args()

    base_url = args.url.rstrip("/")
    secret = _resolve_secret(args.secret)

    print(f"{CYAN}{'='*60}{RESET}")
    print(f"VERITY /api/order 스모크")
    print(f"URL   : {base_url}")
    print(f"Secret: {'(있음)' if secret else YELLOW + '(없음 — auth 체크만 가능)' + RESET}")
    print(f"{CYAN}{'='*60}{RESET}")

    results = []
    results.append(("auth_missing", check_auth_missing(base_url)))
    results.append(("auth_wrong", check_auth_wrong(base_url)))

    if not secret:
        print(f"\n{YELLOW}⚠ secret 미지정 — 인증 필요한 체크 스킵{RESET}")
    else:
        if not args.skip_balance:
            results.append(("balance", check_balance(base_url, secret)))
        else:
            print(f"\n{DIM}[3] balance check skipped (--skip-balance){RESET}")
        results.append(("val_missing_ticker", check_validation_missing_ticker(base_url, secret)))
        results.append(("val_bad_side", check_validation_bad_side(base_url, secret)))
        results.append(("val_zero_qty", check_validation_zero_qty(base_url, secret)))

    print(f"\n{CYAN}{'─'*60}{RESET}")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    if passed == total:
        print(f"{GREEN}전체 통과: {passed}/{total}{RESET}")
        return 0
    print(f"{RED}실패: {total - passed}/{total}{RESET}")
    for name, ok in results:
        marker = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        print(f"  {marker} {name}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
