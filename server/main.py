"""
KIS 실시간 호가/체결 중계 서버.

FastAPI + SSE로 KIS WebSocket 데이터를 Framer 클라이언트에 중계.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List, Optional

import requests
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from server.config import ALLOWED_ORIGINS, PORT, PORTFOLIO_URL
from server.kis_ws_client import KISWebSocketClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

ws_client = KISWebSocketClient()

# SSE 클라이언트용 비동기 큐 관리
_sse_queues: List[asyncio.Queue] = []


def _on_ws_event(event: dict) -> None:
    """WebSocket 이벤트를 모든 SSE 큐에 브로드캐스트."""
    dead = []
    for q in _sse_queues:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        try:
            _sse_queues.remove(q)
        except ValueError:
            pass


def _load_tickers_from_portfolio() -> List[str]:
    """portfolio.json에서 보유/추천 KR 종목 코드 추출."""
    if not PORTFOLIO_URL:
        return []
    try:
        resp = requests.get(PORTFOLIO_URL, timeout=15)
        resp.raise_for_status()
        text = resp.text.replace("NaN", "null").replace("Infinity", "null")
        data = json.loads(text)
    except Exception as e:
        logger.warning("portfolio.json 로드 실패: %s", e)
        return []

    tickers = []
    for s in data.get("recommendations") or []:
        if s.get("currency") != "USD":
            tickers.append(str(s.get("ticker", "")).zfill(6))
    for h in (data.get("vams", {}) or {}).get("holdings") or []:
        if h.get("currency") != "USD":
            tickers.append(str(h.get("ticker", "")).zfill(6))

    seen = set()
    unique = []
    for t in tickers:
        if t not in seen and t != "000000":
            seen.add(t)
            unique.append(t)
    return unique[:40]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 시 WebSocket 관리."""
    ws_client.add_listener(_on_ws_event)
    ws_client.start()

    # portfolio.json에서 종목 로드 → 구독
    await asyncio.sleep(2)
    tickers = _load_tickers_from_portfolio()
    if tickers:
        logger.info("portfolio.json에서 %d개 종목 구독: %s", len(tickers), tickers[:5])
        ws_client.subscribe(tickers)
    else:
        logger.warning("구독할 종목 없음 — /subscribe로 수동 추가 필요")

    yield

    ws_client.stop()
    ws_client.remove_listener(_on_ws_event)


app = FastAPI(
    title="VERITY Realtime Relay",
    description="KIS WebSocket 실시간 호가/체결 SSE 중계 서버",
    version="1.0.0",
    lifespan=lifespan,
)

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
        "uptime_seconds": round(ws_client.uptime, 1),
    }


@app.get("/tickers")
async def tickers():
    return {"tickers": ws_client.subscribed_tickers}


@app.get("/snapshot/{ticker}")
async def snapshot(ticker: str):
    """특정 종목의 최신 캐시된 호가+체결 스냅샷."""
    tk = ticker.strip().zfill(6)
    data = ws_client.get_snapshot(tk)
    return data


@app.post("/subscribe")
async def subscribe(request: Request):
    """종목 구독 추가. body: {"tickers": ["005930", "000660"]}"""
    body = await request.json()
    new_tickers = body.get("tickers", [])
    if not new_tickers:
        return JSONResponse({"error": "tickers 필드 필요"}, status_code=400)

    cleaned = [str(t).strip().zfill(6) for t in new_tickers]
    ws_client.subscribe(cleaned[:40])
    return {
        "subscribed": cleaned,
        "total": len(ws_client.subscribed_tickers),
    }


@app.get("/stream/{ticker}")
async def stream_ticker(ticker: str, request: Request):
    """특정 종목의 실시간 SSE 스트림."""
    tk = ticker.strip().zfill(6)

    # 구독 안 된 종목이면 자동 구독
    if tk not in ws_client.subscribed_tickers:
        ws_client.subscribe([tk])

    async def event_generator() -> AsyncGenerator:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        _sse_queues.append(queue)
        try:
            # 초기 스냅샷 전송
            snap = ws_client.get_snapshot(tk)
            yield {"event": "snapshot", "data": json.dumps(snap, ensure_ascii=False)}

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
                    continue

                if event.get("ticker") != tk:
                    continue

                evt_type = event.get("type", "trade")
                yield {
                    "event": evt_type,
                    "data": json.dumps(event.get("data", {}), ensure_ascii=False),
                }
        finally:
            try:
                _sse_queues.remove(queue)
            except ValueError:
                pass

    return EventSourceResponse(event_generator())


@app.get("/stream/all")
async def stream_all(request: Request):
    """전 종목 실시간 SSE 스트림."""

    async def event_generator() -> AsyncGenerator:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        _sse_queues.append(queue)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
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
                _sse_queues.remove(queue)
            except ValueError:
                pass

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server.main:app", host="0.0.0.0", port=PORT, reload=False)
