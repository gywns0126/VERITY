"""
KIS 실시간 호가/체결/분봉 중계 서버.

FastAPI + SSE — 토픽 기반 라우팅, idle 종목 자동 해제, 1분봉 집계.
$5 Railway 플랜 최적화.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, List, Set

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from server.config import (
    ALLOWED_ORIGINS,
    CLEANUP_INTERVAL,
    IDLE_UNSUB_TTL,
    PORT,
    SSE_QUEUE_SIZE,
)
from server.kis_ws_client import KISWebSocketClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ws_client = KISWebSocketClient()

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 — 구독 없이 WS만 연결."""
    ws_client.add_listener(_on_ws_event)
    ws_client.start()

    cleanup_task = asyncio.create_task(_cleanup_idle_tickers())

    yield

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
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── 엔드포인트 ──


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "ws_connected": ws_client.connected,
        "subscribed_tickers": ws_client.subscribed_tickers,
        "subscribed_count": len(ws_client.subscribed_tickers),
        "sse_connections": sum(len(qs) for qs in _ticker_queues.values()) + len(_all_queues),
        "uptime_seconds": round(ws_client.uptime, 1),
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
