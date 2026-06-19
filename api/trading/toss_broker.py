"""toss_broker — 토스증권 Open API 클라이언트 (하이브리드 채택 2026-06-19).

배경: KIS 1일 1토큰 정책의 고통(7+ 사고)을 고빈도 시세/주문/계좌 경로에서 제거.
Toss = OAuth2 client_credentials, 24h 토큰. 단 "클라이언트당 유효 토큰 1개 +
재발급 시 기존 토큰 즉시 무효화" → 반드시 캐시 후 재사용. 캐시 없이 반복 발급 시
403 AUTH 보호 (2026-06-19 검수 중 4회 발급 → 403 확인). 캐시가 1순위 설계 원칙.

역할 분담 (하이브리드, PM 결정 2026-06-19):
- Toss: 시세(prices/candles/orderbook/trades/price-limits) + 종목정보(stocks/warnings)
        + 시장정보(exchange-rate/market-calendar) + 계좌(accounts/holdings) + 주문(추후)
- KIS:  1일 1회 리서치/수급 전용 축소 존치 (펀더멘털·수급 ~25종, Toss 무대체)

커버리지: KRX(KOSPI/KOSDAQ/NXT) + 미국. (KIS 의 HK/CN/JP/VN 은 Toss 미지원 = gap)

보안: client/secret = config(.env) 에서만. 토큰/시크릿 로그 노출 금지 (prefix 마스킹).
주문(POST /api/v1/orders)은 본 모듈 미구현 — 실계좌 + sandbox 부재 + 검증 미완(2027)
이므로 명시 게이트 도입 전까지 read-only 유지. 주문 추가 시 별도 PM 승인 의무.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests

from api.config import (
    TOSS_API_KEY,
    TOSS_OPENAPI_BASE_URL,
    TOSS_SECRET_KEY,
)

KST = timezone(timedelta(hours=9))

_TOKEN_CACHE_DIR = os.environ.get(
    "TOSS_TOKEN_CACHE_DIR", os.path.expanduser("~/.cache")
)
_TOKEN_CACHE_PATH = os.path.join(_TOKEN_CACHE_DIR, "verity_toss_token.json")

# expires_in(86399s) 에서 갱신 마진. 만료 60초 전 = 만료 취급.
_EXPIRY_MARGIN_SEC = 60
_DEFAULT_TIMEOUT = 15


def _mask(s: str) -> str:
    if not s:
        return "(empty)"
    return (s[:6] + "…" + s[-4:]) if len(s) > 12 else "***"


class TossAuthError(RuntimeError):
    """토큰 발급 실패 (403 AUTH 보호 / 401 / 잘못된 키)."""


class TossBroker:
    """토스증권 Open API read-only 클라이언트. 토큰 캐시 후 재사용.

    cache_only=True 면 발급을 시도하지 않고 캐시 토큰만 사용 (고빈도 소비자용 —
    재발급 폭주 차단). 캐시 만료/부재 시 TossAuthError.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        cache_only: bool = False,
    ) -> None:
        self.client_id = (client_id or TOSS_API_KEY or "").strip()
        self.client_secret = (client_secret or TOSS_SECRET_KEY or "").strip()
        self.base_url = (base_url or TOSS_OPENAPI_BASE_URL or "").rstrip("/")
        self.cache_only = cache_only
        self._token: str = ""
        self._token_expires: Optional[datetime] = None
        if not self.client_id or not self.client_secret:
            raise TossAuthError("TOSS_API_KEY / TOSS_SECRET_KEY 미설정")
        self._load_cached_token()

    # ── 토큰 lifecycle ──────────────────────────────────────────────
    def _load_cached_token(self) -> None:
        try:
            with open(_TOKEN_CACHE_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
        except FileNotFoundError:
            print(f"[toss_cache] file 없음: {_TOKEN_CACHE_PATH}", file=sys.stderr)
            return
        except (OSError, ValueError) as e:
            print(f"[toss_cache] parse error: {e}", file=sys.stderr)
            return
        token = cached.get("access_token", "")
        expires_str = cached.get("expires_at", "")
        cid = cached.get("client_id", "")
        if not token or not expires_str:
            print("[toss_cache] reject — token/expires 비어있음", file=sys.stderr)
            return
        if cid != self.client_id:
            print(
                f"[toss_cache] reject — client_id mismatch "
                f"cache={_mask(cid)} env={_mask(self.client_id)}",
                file=sys.stderr,
            )
            return
        try:
            expires = datetime.fromisoformat(expires_str)
        except ValueError:
            return
        if datetime.now(KST) < expires:
            self._token = token
            self._token_expires = expires
            print(
                f"[toss_cache] HIT — expires={expires.isoformat(timespec='seconds')}",
                file=sys.stderr,
            )
        else:
            print("[toss_cache] expired — 재발급 필요", file=sys.stderr)

    def _save_cached_token(self) -> None:
        try:
            os.makedirs(_TOKEN_CACHE_DIR, exist_ok=True)
            with open(_TOKEN_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "access_token": self._token,
                        "expires_at": self._token_expires.isoformat()
                        if self._token_expires
                        else "",
                        "client_id": self.client_id,
                    },
                    f,
                )
            os.chmod(_TOKEN_CACHE_PATH, 0o600)
            print(f"[toss_cache] SAVED — {_TOKEN_CACHE_PATH}", file=sys.stderr)
        except Exception as e:  # silent fail 금지
            print(f"[toss_cache] SAVE FAILED: {type(e).__name__}: {e}", file=sys.stderr)
            raise

    def _is_token_valid(self) -> bool:
        return bool(
            self._token
            and self._token_expires
            and datetime.now(KST) < self._token_expires
        )

    def authenticate(self, force_refresh: bool = False) -> str:
        """유효 캐시 토큰이 있으면 그대로, 없으면 1회 발급 후 캐시.

        cache_only=True 면 발급하지 않고, 캐시 없으면 TossAuthError.
        재발급 = 기존 토큰 즉시 무효화 → force_refresh 는 신중히 (소비자 동시 사용 시 401 유발).
        """
        if not force_refresh and self._is_token_valid():
            return self._token
        if self.cache_only:
            raise TossAuthError(
                "cache_only=True — 유효 캐시 토큰 없음 (발급 금지 모드)"
            )
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        try:
            r = requests.post(
                f"{self.base_url}/oauth2/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=_DEFAULT_TIMEOUT,
            )
        except requests.RequestException as e:
            raise TossAuthError(f"토큰 요청 실패: {e}") from e
        if r.status_code != 200:
            # 403 = 반복 발급 AUTH 보호. body 일부만 (시크릿 무관).
            raise TossAuthError(
                f"토큰 발급 HTTP {r.status_code}: {r.text[:200]}"
            )
        body = r.json()
        self._token = body.get("access_token", "")
        expires_in = int(body.get("expires_in", 0) or 0)
        self._token_expires = datetime.now(KST) + timedelta(
            seconds=max(0, expires_in - _EXPIRY_MARGIN_SEC)
        )
        if not self._token:
            raise TossAuthError("access_token 응답 누락")
        print(
            f"[toss_auth] 발급 OK — token={_mask(self._token)} "
            f"expires_in={expires_in}s",
            file=sys.stderr,
        )
        self._save_cached_token()
        return self._token

    # ── 공통 요청 ────────────────────────────────────────────────────
    def _get(
        self,
        path: str,
        params: Optional[dict] = None,
        account_seq: Optional[str] = None,
        _retry: bool = True,
    ) -> Any:
        token = self.authenticate()
        headers = {"Authorization": f"Bearer {token}"}
        if account_seq:
            headers["x-tossinvest-account"] = str(account_seq)
        try:
            r = requests.get(
                f"{self.base_url}{path}",
                params=params,
                headers=headers,
                timeout=_DEFAULT_TIMEOUT,
            )
        except requests.RequestException as e:
            raise RuntimeError(f"toss GET {path} 실패: {e}") from e
        # 401 = 토큰 만료/무효(타 발급으로 무효화 가능) → 1회 재발급 재시도.
        if r.status_code == 401 and _retry and not self.cache_only:
            print(f"[toss] 401 {path} — 토큰 재발급 후 1회 재시도", file=sys.stderr)
            self.authenticate(force_refresh=True)
            return self._get(path, params, account_seq, _retry=False)
        if r.status_code == 429:
            raise RuntimeError(f"toss GET {path} rate limit 429 (그룹 한도 초과)")
        if r.status_code != 200:
            raise RuntimeError(f"toss GET {path} HTTP {r.status_code}: {r.text[:200]}")
        return r.json()

    # ── 시세 (Market Data) ───────────────────────────────────────────
    def get_prices(self, symbols: list[str]) -> Any:
        """현재가 (≤200 종목 배치). symbols = 종목코드/티커 리스트.

        주의: 정확한 query 파라미터 형식은 첫 라이브 호출 시 검증 필요
        (스펙상 ≤200 symbols, 파라미터명 미확정 — 캐시 토큰 확보 후 튜닝).
        """
        return self._get("/api/v1/prices", params={"symbols": ",".join(symbols)})

    def get_candles(self, symbol: str, interval: str = "1d", count: int = 200) -> Any:
        """OHLCV 캔들 (interval=1m|1d, ≤200). 그래프용."""
        return self._get(
            "/api/v1/candles",
            params={"symbol": symbol, "interval": interval, "count": count},
        )

    def get_orderbook(self, symbol: str) -> Any:
        return self._get("/api/v1/orderbook", params={"symbol": symbol})

    def get_trades(self, symbol: str) -> Any:
        return self._get("/api/v1/trades", params={"symbol": symbol})

    def get_price_limits(self, symbol: str) -> Any:
        return self._get("/api/v1/price-limits", params={"symbol": symbol})

    # ── 종목정보 (Stock Info) ────────────────────────────────────────
    def get_stocks(self, symbols: list[str]) -> Any:
        return self._get("/api/v1/stocks", params={"symbols": ",".join(symbols)})

    def get_warnings(self, symbol: str) -> Any:
        """VI/과열/투자경고/거래정지 플래그 (KIS get_vi_status 대체 후보)."""
        return self._get(f"/api/v1/stocks/{symbol}/warnings")

    # ── 시장정보 (Market Info) ───────────────────────────────────────
    def get_exchange_rate(self, base_currency: str = "USD") -> Any:
        return self._get("/api/v1/exchange-rate", params={"baseCurrency": base_currency})

    def get_market_calendar(self, market: str = "KR") -> Any:
        """market = KR | US. 휴장일/장 세션 (pre/regular/after)."""
        return self._get(f"/api/v1/market-calendar/{market.upper()}")

    # ── 계좌·자산 (Account / Asset) — VERITY 전용 (개인 금융정보) ──────
    def get_accounts(self) -> Any:
        """계좌 목록. accountSeq 추출에 사용 (holdings 의 x-tossinvest-account)."""
        return self._get("/api/v1/accounts")

    def get_holdings(self, account_seq: str, symbol: Optional[str] = None) -> Any:
        """보유 종목·평가금액 (KR+US). account_seq = accounts 의 accountSeq.

        ⚠️ 개인 금융정보 — VERITY(개인 운영툴) 전용. 골든구스(공개) 노출 절대 금지.
        """
        params = {"symbol": symbol} if symbol else None
        return self._get("/api/v1/holdings", params=params, account_seq=account_seq)


_singleton: Optional[TossBroker] = None


def get_toss_broker(cache_only: bool = False) -> TossBroker:
    """프로세스 단일 인스턴스. 토큰 캐시 공유 (반복 발급 차단)."""
    global _singleton
    if _singleton is None:
        _singleton = TossBroker(cache_only=cache_only)
    return _singleton
