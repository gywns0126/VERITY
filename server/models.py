"""Pydantic 모델 — 호가/체결 데이터."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel


class Trade(BaseModel):
    time: str
    price: float
    change: float = 0
    change_pct: float = 0
    volume: int = 0
    side: Literal["buy", "sell", "neutral"] = "neutral"


class ConclusionSnapshot(BaseModel):
    ticker: str
    trades: List[Trade] = []
    strength_pct: float = 0
    total_buy_vol: int = 0
    total_sell_vol: int = 0
    timestamp: str = ""


class OrderbookRow(BaseModel):
    price: float
    volume: int = 0
    side: Literal["ask", "bid"] = "ask"


class OrderbookSnapshot(BaseModel):
    ticker: str
    asks: List[OrderbookRow] = []
    bids: List[OrderbookRow] = []
    total_ask_vol: int = 0
    total_bid_vol: int = 0
    timestamp: str = ""


class RealtimeEvent(BaseModel):
    """SSE로 전송하는 통합 이벤트."""
    type: Literal["orderbook", "trade", "snapshot"]
    ticker: str
    data: dict


class HealthResponse(BaseModel):
    status: str = "ok"
    ws_connected: bool = False
    subscribed_tickers: List[str] = []
    uptime_seconds: float = 0
