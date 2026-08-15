"""
KIS 실시간 호가/체결/분봉 중계 서버.

FastAPI + SSE — 토픽 기반 라우팅, idle 종목 자동 해제, 1분봉 집계.
$5 Railway 플랜 최적화.
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, List, Optional, Set

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from server.config import (
    ALLOWED_ORIGINS,
    ALLOWED_ORIGIN_REGEX,
    CLEANUP_INTERVAL,
    IDLE_UNSUB_TTL,
    PORT,
    SSE_QUEUE_SIZE,
)
from server.kis_rest_client import (
    fetch_daily, fetch_minute, fetch_weekly, fetch_monthly, fetch_full_history, fetch_orderbook,
    fetch_price, fetch_trades, fetch_program_trade, fetch_index, fetch_index_daily,
    fetch_us_index_daily, fetch_us_price, place_kr_order,
    place_us_order, get_balance, token_status, BrokerMismatch,
)
from server.kis_ws_client import KISWebSocketClient
from server.security import start_security

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ws_client = KISWebSocketClient()

# 배포 관측 태그 — /health 로 어떤 커밋 계열이 떠 있는지 판별 (2026-08-03 배포 추적 사고:
# uptime_seconds 는 WS 연결 uptime 이라 배포판별 불가였음). 서버 변경 시 갱신.
BUILD_TAG = "2026-08-05-usidx"


def _order_auth_fail_response(request: Request) -> Optional[JSONResponse]:
    """Railway /api/order 엔드포인트 인증 (fail-closed).

    Vercel ↔ Railway 서버 간 공유 비밀로 주문 API 를 보호한다. 서비스 시작 이전의
    기존 경로(ORDER_SECRET + Authorization Bearer)는 마이그레이션 편의를 위해 legacy
    경로로만 허용한다. 실자금 주문 활성화 전에는 RAILWAY_SHARED_SECRET 로 통일하고
    ORDER_SECRET 를 제거할 것.

    정책:
      1. 두 secret 모두 미설정 → 503 (fail-closed, 서비스 불가 명시)
      2. X-Service-Auth == RAILWAY_SHARED_SECRET → 통과 (primary)
      3. Authorization: Bearer ORDER_SECRET → 통과 (legacy, deprecation 예정)
      4. 둘 다 불일치 → 401
    """
    primary = os.environ.get("RAILWAY_SHARED_SECRET", "").strip().strip('"')
    legacy = os.environ.get("ORDER_SECRET", "").strip().strip('"')

    # 1) 아무 secret 도 설정 안 됨 → fail-closed.
    #    과거엔 None 반환(통과)이었으나 2026-04-23 에 실자금 주문 보호를 위해 전환.
    if not primary and not legacy:
        return JSONResponse(
            {
                "error": "Service unavailable",
                "detail": "RAILWAY_SHARED_SECRET 미설정 — 주문 API 비활성",
            },
            status_code=503,
        )

    # 2) Primary: X-Service-Auth 헤더 (Vercel 쪽 order.py 가 보내는 방식)
    if primary:
        provided = (request.headers.get("X-Service-Auth") or "").strip()
        if provided and hmac.compare_digest(
            provided.encode("utf-8"), primary.encode("utf-8")
        ):
            return None

    # 3) Legacy: Authorization: Bearer ORDER_SECRET (deprecation 예정)
    if legacy:
        auth = (request.headers.get("Authorization") or "").strip()
        expected = f"Bearer {legacy}"
        if hmac.compare_digest(auth.encode("utf-8"), expected.encode("utf-8")):
            logger.warning(
                "ORDER_SECRET (legacy) 경로로 인증 통과 — "
                "RAILWAY_SHARED_SECRET 로 마이그레이션 권장"
            )
            return None

    # 4) 어느 쪽도 맞지 않음
    return JSONResponse({"error": "Unauthorized"}, status_code=401)

# ── 토픽 기반 SSE 큐 ──
# ticker → set of queues (종목별 라우팅)
_ticker_queues: Dict[str, List[asyncio.Queue]] = defaultdict(list)
# /stream/all 용
_all_queues: List[asyncio.Queue] = []
_queue_lock = asyncio.Lock()


def _on_ws_event(event: dict) -> None:
    """WebSocket 이벤트를 관련 SSE 큐에만 전달 (토픽 기반)."""
    ticker = event.get("ticker", "")

    # 종목별 큐에 전달
    dead = []
    for q in _ticker_queues.get(ticker, []):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _ticker_queues[ticker].remove(q)
        except ValueError:
            pass

    # /stream/all 큐에 전달
    dead_all = []
    for q in _all_queues:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead_all.append(q)
    for q in dead_all:
        try:
            _all_queues.remove(q)
        except ValueError:
            pass


async def _cleanup_idle_tickers() -> None:
    """주기적으로 idle 종목 구독 해제 → WS 슬롯 확보."""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        try:
            idle = ws_client.get_idle_tickers(IDLE_UNSUB_TTL)
            # 활성 SSE 연결이 있는 종목은 제외
            active_tickers: Set[str] = set(_ticker_queues.keys())
            to_unsub = [t for t in idle if t not in active_tickers]
            if to_unsub:
                logger.info("idle 종목 해제: %s", to_unsub)
                ws_client.unsubscribe(to_unsub)
        except Exception as e:
            logger.error("cleanup 오류: %s", e)


async def _approval_key_refresher() -> None:
    """접속키 만료 전 선제적 재연결. 22시간마다 WS를 끊고 새 키로 재접속."""
    while True:
        await asyncio.sleep(22 * 3600)
        try:
            if ws_client.connected:
                logger.info("[KeyRefresh] 접속키 갱신을 위해 WebSocket 재연결 시작")
                ws_client.force_reconnect()
        except Exception as e:
            logger.error("[KeyRefresh] 재연결 실패: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 — 구독 없이 WS만 연결."""
    # 주문 API 인증 상태 고지 (운영 가시성)
    _primary = os.environ.get("RAILWAY_SHARED_SECRET", "").strip().strip('"')
    _legacy = os.environ.get("ORDER_SECRET", "").strip().strip('"')
    if not _primary and not _legacy:
        logger.critical(
            "RAILWAY_SHARED_SECRET 미설정 — /api/order fail-closed 로 503 반환 중"
        )
    elif _primary:
        logger.info("주문 API 인증: X-Service-Auth (RAILWAY_SHARED_SECRET)")
        if _legacy:
            logger.warning(
                "ORDER_SECRET (legacy) 도 설정됨 — 마이그레이션 완료 후 제거 권장"
            )
    else:
        logger.warning(
            "ORDER_SECRET (legacy) 단독 사용 중 — RAILWAY_SHARED_SECRET 로 전환 권장"
        )

    ws_client.add_listener(_on_ws_event)
    ws_client.start()

    cleanup_task = asyncio.create_task(_cleanup_idle_tickers())
    refresh_task = asyncio.create_task(_approval_key_refresher())

    yield

    refresh_task.cancel()
    cleanup_task.cancel()
    ws_client.stop()
    ws_client.remove_listener(_on_ws_event)


app = FastAPI(
    title="VERITY Realtime Relay",
    description="KIS 실시간 호가/체결/분봉 SSE 중계 — $5 플랜 최적화",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=256)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # 🚨 2026-08-15 — 옛 설정은 allow_origins=["*"] 로 배포돼 있었다(실측 확인).
    #   시세 라우트가 무인증이라 브라우저 경유 제3자 사용까지 열려 있던 상태다.
    #   regex 는 Framer 퍼블리시·프리뷰 서브도메인 + 로컬 개발용 — 공개 컴포넌트가
    #   EventSource 로 /stream/{ticker} 에 붙으므로 빠뜨리면 라이브 차트가 죽는다.
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# IP 침입 시도 추적 · 자동 차단 (방어층). CORS 뒤 등록 = 스캔/차단을 바깥에서 먼저 처리.
# Supabase blocked_ips 공유(Vercel 과 단일 블록리스트). SEC_DISABLED=1 이면 관측만.
start_security(app)


# ── 엔드포인트 ──


@app.get("/health")
async def health():
    import time as _t
    key_age = _t.time() - ws_client._approval_key_issued_at if ws_client._approval_key_issued_at else 0
    key_remaining = max(0, ws_client._APPROVAL_KEY_TTL - key_age) if key_age > 0 else 0
    return {
        "status": "ok",
        "build": BUILD_TAG,
        "ws_connected": ws_client.connected,
        "subscribed_tickers": ws_client.subscribed_tickers,
        "subscribed_count": len(ws_client.subscribed_tickers),
        "sse_connections": sum(len(qs) for qs in _ticker_queues.values()) + len(_all_queues),
        "uptime_seconds": round(ws_client.uptime, 1),
        "approval_key_age_hours": round(key_age / 3600, 1),
        "approval_key_remaining_hours": round(key_remaining / 3600, 1),
        # RULE 1 관측성 — Railway REST 토큰 모드. rule1_ok=False = 자체 발급(P0).
        "kis_rest_token": token_status(),
    }


@app.get("/tickers")
async def tickers():
    return {"tickers": ws_client.subscribed_tickers}


@app.get("/snapshot/{ticker}")
async def snapshot(ticker: str):
    tk = ticker.strip().zfill(6)
    return ws_client.get_snapshot(tk)


@app.get("/candles/{ticker}")
async def candles(ticker: str):
    """종목의 당일 1분봉 캔들 데이터."""
    tk = ticker.strip().zfill(6)
    ws_client.touch(tk)
    data = ws_client.get_candles(tk)
    return {"ticker": tk, "candles": data, "count": len(data)}


# /quotes per-IP 레이트리밋 — 🚨 RULE 1/보안(2026-08-02 자기검수 저촉점 fix):
#   무인증 브라우저 엔드포인트라 제3자가 오퍼레이터 KIS 토큰으로 무제한 조회 = 쿼터 남용 방어.
#   (브라우저 클라는 RAILWAY_SHARED_SECRET 를 안전 보관 불가 → 인증 대신 per-IP 스로틀.)
_quote_rl: Dict[str, list] = defaultdict(list)
_QUOTE_MAX, _QUOTE_WIN = 30, 60  # IP당 60초 30회

def _quote_rate_ok(ip: str) -> bool:
    import time as _t
    now = _t.monotonic()
    hits = _quote_rl[ip]
    hits[:] = [h for h in hits if h > now - _QUOTE_WIN]
    if len(hits) >= _QUOTE_MAX:
        return False
    hits.append(now)
    return True


@app.get("/quotes")
async def quotes(request: Request, tickers: str = Query("", description="쉼표구분 종목코드 (최대 15)")):
    """오퍼레이터 실시간 시세 배치 — 현재가·등락률·거래량·OHLC.
    🚨 RULE 1: fetch_price = KIS_SHARED_TOKEN 순수 소비자(공유 store 읽기만, 토큰 발급 절대 X).
      배포 시 Railway KIS_SHARED_TOKEN=1 필수(미설정=legacy self-issue fail-open, 6/17 클래스).
    per-IP 레이트리밋으로 쿼터 남용 차단. 본인 이용 실시간 시세."""
    from datetime import datetime, timezone, timedelta
    ip = request.client.host if request.client else "unknown"
    if not _quote_rate_ok(ip):
        return JSONResponse({"error": "rate_limited", "quotes": {}, "count": 0}, status_code=429)
    kst = timezone(timedelta(hours=9))
    codes = [t.strip().zfill(6) for t in tickers.split(",") if t.strip()][:15]
    out: Dict[str, dict] = {}
    for code in codes:
        try:
            q = fetch_price(code)
            if q and q.get("price"):
                out[code] = q
        except Exception:
            pass
    return {"quotes": out, "count": len(out), "asof": datetime.now(kst).isoformat(timespec="seconds")}


@app.get("/us_quotes")
async def us_quotes(request: Request,
                    tickers: str = Query("", description="쉼표구분 US 심볼 (최대 10)"),
                    excd: str = Query("", description="거래소 강제 지정 (NAS/NYS/AMS). 미지정=자동 탐색")):
    """오퍼레이터 US 실시간 시세 — KIS 해외 현재체결가(HHDFS00000300).

    🚨 2026-08-09 신설. 이전까지 US 종목은 가격 축이 0 이라 챗이 가격을 근거로 말할 수
      없었다. KIS 해외 API 는 이미 있었고 **소비 경로만** 없었다.
    🚨 RULE 1: /quotes 와 동일하게 KIS_SHARED_TOKEN 순수 소비자다(발급 절대 X).
      로컬에서 직접 부르지 않고 여기 두는 이유 = 로컬 앱키와 GH 발급 앱키가 달라
      로컬 호출은 자체 발급을 요구하게 되고, 그건 하루 2토큰이다.
    🚨 KR /quotes 는 건드리지 않았다 — 거긴 zfill(6) 이 전제라 US 를 섞으면 KR 이 깨진다.
      상한 10 (거래소 자동 탐색이 심볼당 최대 3 콜이라 /quotes 15 보다 낮게 잡는다).
    """
    from datetime import datetime, timezone, timedelta
    ip = request.client.host if request.client else "unknown"
    if not _quote_rate_ok(ip):
        return JSONResponse({"error": "rate_limited", "quotes": {}, "count": 0}, status_code=429)
    kst = timezone(timedelta(hours=9))
    syms = [t.strip().upper() for t in tickers.split(",") if t.strip()][:10]
    ex = (excd or "").strip().upper()
    out: Dict[str, dict] = {}
    for s in syms:
        try:
            q = fetch_us_price(s, ex)
            if q and q.get("price"):
                out[s] = q
        except Exception:
            pass
    return {"quotes": out, "count": len(out),
            "asof": datetime.now(kst).isoformat(timespec="seconds")}


@app.post("/subscribe")
async def subscribe(request: Request):
    body = await request.json()
    new_tickers = body.get("tickers", [])
    if not new_tickers:
        return JSONResponse({"error": "tickers 필드 필요"}, status_code=400)

    cleaned = [str(t).strip().zfill(6) for t in new_tickers]
    ws_client.subscribe(cleaned[:10])
    return {
        "subscribed": cleaned,
        "total": len(ws_client.subscribed_tickers),
    }


# ── /chart 응답 캐시 (2026-08-15) ───────────────────────────────────────────
# 🚨 왜: 이 라우트만 KIS REST 를 **요청마다 직접** 호출했다. 토큰만 캐시하고 응답은 안 했다.
#   증폭이 크다 — 기본값 type=all 은 한 요청에 KIS 5콜(daily·minute·price·orderbook·trades)이다.
#   엔드포인트는 무인증이고 URL 이 public repo 에 그대로 있다
#   (framer-components/public-probe/RealtimeChartProbe.tsx · api/intelligence/ticker_facts.py).
#   즉 제3자 트래픽이 오퍼레이터 계정의 KIS 쿼터를 먹고, 유량 초과 시 재시도·백오프 코드가
#   없어 **오퍼레이터 본인 조회가 먼저 죽는다.**
#   CORS 를 닫아도(2026-08-15) 이 벡터는 안 막힌다 — CORS 는 브라우저 정책이라 curl 은 통과한다.
#
#   대조: /quotes·/us_quotes 는 이미 per-IP 레이트리밋(60초 30회)이 있고,
#        /snapshot·/candles 는 WS 메모리 상태를 읽어 KIS 를 안 건드린다. 이 라우트만 무방비였다.
#
#   레이트리밋 대신 캐시를 택한 이유: IP 기준 제한은 Vercel 공용 egress 를 함께 막을 위험이
#   있는데, 캐시는 트래픽 출처와 무관하게 KIS 호출 상한을 만들고 오퍼레이터 응답도 빨라진다.
_chart_cache: Dict[str, tuple] = {}          # key -> (expire_ts, payload)
_chart_locks: Dict[str, asyncio.Lock] = {}   # key -> 동시요청 합류용
_CHART_CACHE_MAX = 512
# 타입별 TTL(초). 실시간성이 필요한 축만 짧게 둔다 — 5초는 체감 0이면서 초당 KIS 콜을 1로 묶는다.
_CHART_TTL = {
    "price": 5, "all": 5, "minute": 5,
    "daily": 60, "weekly": 300, "monthly": 300, "full": 900,
}


def _chart_cache_get(key: str):
    hit = _chart_cache.get(key)
    if not hit:
        return None
    expire_ts, payload = hit
    if time.monotonic() >= expire_ts:
        _chart_cache.pop(key, None)
        return None
    return payload


def _chart_cache_put(key: str, payload, ttl: float) -> None:
    if len(_chart_cache) >= _CHART_CACHE_MAX:
        # 만료분 우선 정리, 그래도 넘치면 가장 이른 만료부터 버린다(무한 증가 방지).
        now = time.monotonic()
        for k in [k for k, (e, _) in _chart_cache.items() if e <= now]:
            _chart_cache.pop(k, None)
        while len(_chart_cache) >= _CHART_CACHE_MAX:
            _chart_cache.pop(min(_chart_cache, key=lambda k: _chart_cache[k][0]), None)
    _chart_cache[key] = (time.monotonic() + ttl, payload)


@app.get("/chart/{ticker}")
async def chart(ticker: str, type: str = Query("all")):
    """KIS REST 차트 데이터 — Railway 상주 토큰으로 KIS 알림 없이 조회.

    응답은 타입별 TTL 로 캐시한다(위 블록 참조). 동시 요청은 락으로 합류시켜
    캐시 미스 순간의 stampede 가 KIS 로 그대로 나가지 않게 한다.
    """
    tk = ticker.strip().zfill(6)
    ck = f"{tk}:{type}"
    cached = _chart_cache_get(ck)
    if cached is not None:
        return cached

    lock = _chart_locks.setdefault(ck, asyncio.Lock())
    async with lock:
        # 락 대기 중 앞선 요청이 채웠을 수 있다 — 재확인 후 진행.
        cached = _chart_cache_get(ck)
        if cached is not None:
            return cached
        payload, cacheable = await _chart_fetch(tk, type)
        if cacheable:
            _chart_cache_put(ck, payload, _CHART_TTL.get(type, 5))
        if len(_chart_locks) > _CHART_CACHE_MAX * 2:
            _chart_locks.clear()   # 락 딕셔너리 무한 증가 방지 (경합 시 잠깐 비효율일 뿐 안전)
        return payload


async def _chart_fetch(tk: str, type: str):
    """실제 조회. 반환 = (payload, 캐시해도 되는가).

    부분 실패(type=all 의 일부 축)나 오류 응답은 캐시하지 않는다 — 그러면 TTL 동안
    degrade 된 응답을 계속 돌려주게 된다.
    """
    loop = asyncio.get_event_loop()
    try:
        if type == "daily":
            data = await loop.run_in_executor(None, fetch_daily, tk)
            return {"daily": data}, True
        if type == "weekly":
            data = await loop.run_in_executor(None, fetch_weekly, tk)
            return {"weekly": data}, True
        if type == "monthly":
            data = await loop.run_in_executor(None, fetch_monthly, tk)
            return {"monthly": data}, True
        if type == "full":
            # 전체 상장 기간 월봉 (yfinance, KIS 무관) — IPO 까지. KIS 100건 캡 우회.
            data = await loop.run_in_executor(None, fetch_full_history, tk)
            return {"full": data}, True
        if type == "minute":
            data = await loop.run_in_executor(None, fetch_minute, tk)
            return {"minute": data}, True
        if type == "price":
            data = await loop.run_in_executor(None, fetch_price, tk)
            return {"price": data}, True
        # type == "all" — 한 요청에 KIS 5콜. 캐시 효과가 가장 큰 경로다.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            f_daily = loop.run_in_executor(ex, fetch_daily, tk)
            f_minute = loop.run_in_executor(ex, fetch_minute, tk)
            f_price = loop.run_in_executor(ex, fetch_price, tk)
            f_orderbook = loop.run_in_executor(ex, fetch_orderbook, tk)
            f_trades = loop.run_in_executor(ex, fetch_trades, tk)
            daily, minute, price, orderbook, trades = await asyncio.gather(
                f_daily, f_minute, f_price, f_orderbook, f_trades,
                return_exceptions=True,
            )
        parts = (daily, minute, price, orderbook, trades)
        payload = {
            "ticker": tk,
            "daily": daily if not isinstance(daily, Exception) else [],
            "minute": minute if not isinstance(minute, Exception) else [],
            "price": price if not isinstance(price, Exception) else {},
            "orderbook": orderbook if not isinstance(orderbook, Exception) else {},
            "trades": trades if not isinstance(trades, Exception) else [],
        }
        # 부분 실패는 캐시하지 않는다 — TTL 동안 degrade 된 응답을 계속 돌려주게 된다.
        return payload, not any(isinstance(p, Exception) for p in parts)
    except Exception as e:
        logger.error("chart 조회 실패 %s: %s", tk, e)
        return JSONResponse({"error": str(e)}, status_code=502), False


@app.get("/program/{market}")
async def program_trade(market: str = "K"):
    """KIS 프로그램매매 종합현황(시간) — KRX 스크래핑(해외IP+안티봇 차단) 대체.
    Railway 상주 토큰(read-only consumer)으로 조회. market: K(코스피)/Q(코스닥).
    raw output 반환 — collector 가 차익/비차익 순매수 매핑."""
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, fetch_program_trade, market.upper())
    return {"program": data}


@app.get("/index_quotes")
async def index_quotes():
    """KR 지수 실시간 — 코스피(0001)·코스닥(1001) 업종 현재지수 (PM 2026-08-03).
    KIS_SHARED_TOKEN 순수 소비자(발급 0, RULE 1). 값 0 = 프론트가 macro_snapshot 폴백."""
    # 🚨 main.py 는 모듈 스코프에 datetime 계열 임포트가 없다 — /quotes 처럼 지역 임포트 필수.
    #   (2026-08-03 500 사고 근인 = 이 누락의 NameError. py_compile 은 이름을 안 잡는다.)
    from datetime import datetime, timezone, timedelta
    loop = asyncio.get_event_loop()
    try:
        kospi, kosdaq = await asyncio.gather(
            loop.run_in_executor(None, fetch_index, "0001"),
            loop.run_in_executor(None, fetch_index, "1001"),
        )
    except Exception as e:  # 500 승격 금지 — 값 0 = 프론트 스냅샷 폴백 신호
        logger.error("index_quotes 실패: %s", e)
        kospi = kosdaq = {"price": 0.0, "change": 0.0, "change_pct": 0.0}
    kst = timezone(timedelta(hours=9))
    return {
        "quotes": {"kospi": kospi, "kosdaq": kosdaq},
        "asof": datetime.now(kst).isoformat(timespec="seconds"),
    }


@app.get("/index_daily/{index_cd}")
async def index_daily(index_cd: str):
    """KR 지수 일봉(90일) — 상세 차트 캔들용 (PM 2026-08-03 토스 대비 차트 격차)."""
    cd = index_cd if index_cd in ("0001", "1001") else "0001"
    loop = asyncio.get_event_loop()
    candles = await loop.run_in_executor(None, fetch_index_daily, cd)
    return {"candles": candles, "count": len(candles)}


@app.get("/us_index_daily/{key}")
async def us_index_daily(key: str):
    """미국 지수 일봉 — nasdaq/sp500/sox/dow (PM 2026-08-05 미장 정보량)."""
    loop = asyncio.get_event_loop()
    candles = await loop.run_in_executor(None, fetch_us_index_daily, key.lower())
    return {"candles": candles, "count": len(candles), "key": key.lower()}


@app.get("/api/order")
async def order_balance(request: Request, market: str = Query("kr")):
    """잔고 조회 — Railway 상주 토큰 사용."""
    denied = _order_auth_fail_response(request)
    if denied is not None:
        return denied
    # 🚨 주문과 동일하게 계좌를 라우팅한다. 라우팅 없이 두면 친구 로그인으로 오퍼레이터
    #   잔고·보유종목이 그대로 노출된다 — 주문 오라우팅과 같은 급의 사고.
    broker = (request.headers.get("X-Verity-Broker") or "").strip()
    if not broker:
        return JSONResponse({"error": "계좌 라우팅 헤더 누락 — 조회 거절"}, status_code=403)
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, get_balance, market.lower(), broker)
        return data
    except BrokerMismatch as e:
        logger.error("잔고 조회 거절 (계좌 라우팅): %s", e)
        return JSONResponse({"error": str(e)}, status_code=403)
    except Exception as e:
        logger.error("잔고 조회 실패: %s", e)
        return JSONResponse({"error": str(e)}, status_code=502)


@app.post("/api/order")
async def order_place(request: Request):
    """주문 실행 — Railway 상주 토큰 사용 (Vercel 토큰 발급 방지)."""
    denied = _order_auth_fail_response(request)
    if denied is not None:
        return denied
    body = await request.json()
    # 🚨 계좌 라우팅 — 출처는 Vercel 이 service_role 전용 컬럼(profiles.broker_slug)에서 읽어
    #   붙인 헤더다. **본문(body)에서 읽지 않는다** — 본문은 클라이언트가 조작할 수 있고,
    #   그러면 남의 계좌로 주문을 낼 수 있다. 헤더 구간은 X-Service-Auth 로 이미 신뢰됨.
    broker = (request.headers.get("X-Verity-Broker") or "").strip()
    if not broker:
        return JSONResponse(
            {"success": False, "message": "계좌 라우팅 헤더 누락 — 주문 거절"},
            status_code=403,
        )
    ticker = str(body.get("ticker", "")).strip()
    side = str(body.get("side", "")).lower()
    qty = int(body.get("qty", 0))
    price = body.get("price", 0)
    order_type = str(body.get("order_type", "00"))
    market = str(body.get("market", "kr")).lower()
    excd = str(body.get("excd", "NAS"))

    if not ticker:
        return JSONResponse({"success": False, "message": "ticker 필수"}, status_code=400)
    if side not in ("buy", "sell"):
        return JSONResponse({"success": False, "message": "side는 buy 또는 sell"}, status_code=400)
    if qty <= 0:
        return JSONResponse({"success": False, "message": "수량은 1 이상"}, status_code=400)

    loop = asyncio.get_event_loop()
    try:
        if market == "us":
            result = await loop.run_in_executor(
                None, place_us_order, excd, ticker, side, qty, float(price), order_type, broker,
            )
        else:
            result = await loop.run_in_executor(
                None, place_kr_order, ticker, side, qty, int(price), order_type, broker,
            )
        return result
    except BrokerMismatch as e:
        # 계좌 불일치 = 설정 문제이지 일시 장애가 아니다. 502 로 뭉개면 재시도를 유발한다.
        logger.error("주문 거절 (계좌 라우팅): %s", e)
        return JSONResponse({"success": False, "message": str(e)}, status_code=403)
    except Exception as e:
        logger.error("주문 실패: %s", e)
        return JSONResponse({"success": False, "message": str(e)}, status_code=502)


@app.get("/stream/{ticker}")
async def stream_ticker(ticker: str, request: Request):
    """종목별 실시간 SSE 스트림 — 토픽 기반 라우팅."""
    tk = ticker.strip().zfill(6)

    if tk not in ws_client.subscribed_tickers:
        ws_client.subscribe([tk])
    ws_client.touch(tk)

    async def event_generator() -> AsyncGenerator:
        queue: asyncio.Queue = asyncio.Queue(maxsize=SSE_QUEUE_SIZE)
        _ticker_queues[tk].append(queue)
        try:
            snap = ws_client.get_snapshot(tk)
            yield {"event": "snapshot", "data": json.dumps(snap, ensure_ascii=False)}

            # 기존 캔들 데이터도 초기 전송
            existing_candles = ws_client.get_candles(tk)
            if existing_candles:
                yield {
                    "event": "candles",
                    "data": json.dumps(existing_candles, ensure_ascii=False),
                }

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
                    ws_client.touch(tk)
                    continue

                evt_type = event.get("type", "trade")
                yield {
                    "event": evt_type,
                    "data": json.dumps(event.get("data", {}), ensure_ascii=False),
                }
        finally:
            try:
                _ticker_queues[tk].remove(queue)
            except ValueError:
                pass
            if not _ticker_queues[tk]:
                del _ticker_queues[tk]

    return EventSourceResponse(event_generator())


@app.get("/stream/all")
async def stream_all(request: Request):
    """전 종목 실시간 SSE 스트림."""

    async def event_generator() -> AsyncGenerator:
        queue: asyncio.Queue = asyncio.Queue(maxsize=SSE_QUEUE_SIZE * 3)
        _all_queues.append(queue)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
                    continue

                evt_type = event.get("type", "trade")
                yield {
                    "event": evt_type,
                    "data": json.dumps(
                        {"ticker": event.get("ticker"), **event.get("data", {})},
                        ensure_ascii=False,
                    ),
                }
        finally:
            try:
                _all_queues.remove(queue)
            except ValueError:
                pass

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.main:app", host="0.0.0.0", port=PORT, reload=False)
