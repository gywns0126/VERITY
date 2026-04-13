"""
KIS WebSocket 클라이언트 — 실시간 호가/체결 구독.

KIS OpenAPI WebSocket 프로토콜:
  - 접속키: POST /oauth2/Approval → approval_key
  - TR ID: 호가 H0STASP0, 체결 H0STCNT0
  - 데이터: '|' 구분 파이프라인 포맷 (헤더 | 바디)
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set

import requests
import websocket

from server.config import (
    IS_PAPER,
    KIS_APP_KEY,
    KIS_APP_SECRET,
    KIS_BASE_URL,
    KIS_WS_URL,
)

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

# 호가 필드 순서 (H0STASP0 output)
# 매도호가10~1, 매수호가1~10, 매도잔량10~1, 매수잔량1~10, 총매도잔량, 총매수잔량, ...
_ASK_PRICE_FIELDS = [f"askp{i}" for i in range(10, 0, -1)]
_BID_PRICE_FIELDS = [f"bidp{i}" for i in range(1, 11)]
_ASK_VOL_FIELDS = [f"askp_rsqn{i}" for i in range(10, 0, -1)]
_BID_VOL_FIELDS = [f"bidp_rsqn{i}" for i in range(1, 11)]

# 체결 필드 순서 (H0STCNT0 output)
_TRADE_FIELDS = [
    "mksc_shrn_iscd",  # 종목코드
    "stck_cntg_hour",  # 체결시각
    "stck_prpr",       # 현재가
    "prdy_vrss_sign",  # 전일대비부호
    "prdy_vrss",       # 전일대비
    "prdy_ctrt",       # 전일대비율
    "wghn_avrg_stck_prc",  # 가중평균가
    "stck_oprc",       # 시가
    "stck_hgpr",       # 고가
    "stck_lwpr",       # 저가
    "askp1",           # 매도호가1
    "bidp1",           # 매수호가1
    "cntg_vol",        # 체결거래량
    "acml_vol",        # 누적거래량
    "acml_tr_pbmn",    # 누적거래대금
    "seln_cntg_csnu",  # 매도체결건수
    "shnu_cntg_csnu",  # 매수체결건수
    "ntby_cntg_csnu",  # 순매수체결건수
    "cttr",            # 체결강도
    "seln_cntg_smtn",  # 총매도수량
    "shnu_cntg_smtn",  # 총매수수량
    "ccld_dvsn",       # 체결구분 (1:매수, 5:매도)
    "shnu_rate",       # 매수비율
    "prdy_vol_vrss_acml_vol_rate",  # 전일거래량대비비율
    "oprc_hour",       # 시가시각
    "oprc_vrss_prpr_sign",
    "oprc_vrss_prpr",
    "hgpr_hour",
    "hgpr_vrss_prpr_sign",
    "hgpr_vrss_prpr",
    "lwpr_hour",
    "lwpr_vrss_prpr_sign",
    "lwpr_vrss_prpr",
    "bsop_date",       # 영업일자
    "new_mkop_cls_code",
    "trht_yn",         # 거래정지여부
    "askp_rsqn1",
    "bidp_rsqn1",
    "total_askp_rsqn",
    "total_bidp_rsqn",
    "vol_tnrt",        # 거래량회전율
    "prdy_smns_hour_acml_vol",
    "prdy_smns_hour_acml_vol_rate",
    "hour_cls_code",
    "mrkt_trtm_cls_code",
    "vi_stnd_prc",
]


class KISWebSocketClient:
    """KIS 실시간 WebSocket 클라이언트."""

    def __init__(self) -> None:
        self._approval_key: Optional[str] = None
        self._ws: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._connected = False
        self._subscribed: Set[str] = set()
        self._pending_subs: Set[str] = set()

        # 최신 스냅샷 캐시: ticker -> dict
        self.orderbook_cache: Dict[str, dict] = {}
        self.trade_cache: Dict[str, list] = defaultdict(list)
        self.strength_cache: Dict[str, float] = {}

        # SSE 브로드캐스트용 콜백
        self._listeners: List[Callable[[dict], Any]] = []

        self._reconnect_delay = 1
        self._max_reconnect_delay = 60
        self._should_run = False
        self._start_time = time.time()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def subscribed_tickers(self) -> List[str]:
        return sorted(self._subscribed)

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time

    def add_listener(self, cb: Callable[[dict], Any]) -> None:
        self._listeners.append(cb)

    def remove_listener(self, cb: Callable[[dict], Any]) -> None:
        try:
            self._listeners.remove(cb)
        except ValueError:
            pass

    def _broadcast(self, event: dict) -> None:
        for cb in self._listeners:
            try:
                cb(event)
            except Exception:
                pass

    # ── 인증 ──

    def _get_approval_key(self) -> str:
        """WebSocket 접속키 발급."""
        url = f"{KIS_BASE_URL}/oauth2/Approval"
        body = {
            "grant_type": "client_credentials",
            "appkey": KIS_APP_KEY,
            "secretkey": KIS_APP_SECRET,
        }
        resp = requests.post(url, json=body, timeout=10)
        resp.raise_for_status()
        key = resp.json().get("approval_key", "")
        if not key:
            raise RuntimeError("KIS WebSocket 접속키 발급 실패")
        logger.info("KIS WebSocket 접속키 발급 완료")
        return key

    # ── 구독 메시지 생성 ──

    def _sub_msg(self, tr_id: str, ticker: str, sub: bool = True) -> str:
        return json.dumps({
            "header": {
                "approval_key": self._approval_key,
                "custtype": "P",
                "tr_type": "1" if sub else "2",
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": tr_id,
                    "tr_key": ticker,
                },
            },
        })

    # ── 파싱 ──

    def _parse_orderbook(self, ticker: str, body: str) -> dict:
        """H0STASP0 호가 데이터 파싱."""
        parts = body.split("^")
        if len(parts) < 43:
            return {}

        _int = lambda idx: int(parts[idx]) if idx < len(parts) and parts[idx] else 0

        asks = []
        bids = []
        for i in range(10):
            ask_price = _int(i)
            bid_price = _int(10 + i)
            ask_vol = _int(20 + i)
            bid_vol = _int(30 + i)
            if ask_price > 0:
                asks.append({"price": ask_price, "volume": ask_vol, "side": "ask"})
            if bid_price > 0:
                bids.append({"price": bid_price, "volume": bid_vol, "side": "bid"})

        total_ask = _int(40)
        total_bid = _int(41)
        now_str = datetime.now(KST).isoformat()

        snapshot = {
            "ticker": ticker,
            "asks": asks,
            "bids": bids,
            "total_ask_vol": total_ask,
            "total_bid_vol": total_bid,
            "timestamp": now_str,
        }
        self.orderbook_cache[ticker] = snapshot
        return snapshot

    def _parse_trade(self, body: str) -> dict:
        """H0STCNT0 체결 데이터 파싱."""
        parts = body.split("^")
        if len(parts) < 20:
            return {}

        def _safe(idx: int, default: str = "0") -> str:
            return parts[idx] if idx < len(parts) and parts[idx] else default

        ticker = _safe(0, "")
        hour_raw = _safe(1, "")
        price = int(_safe(2))
        sign = _safe(3, "3")
        change = int(_safe(4))
        change_pct = float(_safe(5))
        vol = int(_safe(12))
        # sign: 1=상한,2=상승,3=보합,4=하한,5=하락
        side = "buy" if sign in ("1", "2") else ("sell" if sign in ("4", "5") else "neutral")

        strength = float(_safe(18)) if len(parts) > 18 else 0

        time_fmt = f"{hour_raw[:2]}:{hour_raw[2:4]}:{hour_raw[4:6]}" if len(hour_raw) >= 6 else hour_raw

        trade = {
            "ticker": ticker,
            "time": time_fmt,
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "volume": vol,
            "side": side,
        }

        # 캐시 업데이트 (최근 50건)
        self.trade_cache[ticker].insert(0, trade)
        self.trade_cache[ticker] = self.trade_cache[ticker][:50]
        self.strength_cache[ticker] = strength

        return trade

    # ── WebSocket 이벤트 핸들러 ──

    def _on_open(self, ws: websocket.WebSocket) -> None:
        logger.info("KIS WebSocket 연결 성공")
        self._connected = True
        self._reconnect_delay = 1

        for ticker in self._pending_subs | self._subscribed:
            ws.send(self._sub_msg("H0STASP0", ticker))
            ws.send(self._sub_msg("H0STCNT0", ticker))
            self._subscribed.add(ticker)
            time.sleep(0.05)
        self._pending_subs.clear()
        logger.info("구독 완료: %s", sorted(self._subscribed))

    def _on_message(self, ws: websocket.WebSocket, message: str) -> None:
        if not message:
            return

        # JSON 응답 (구독 확인 등)
        if message.startswith("{"):
            try:
                j = json.loads(message)
                header = j.get("header", {})
                tr_id = header.get("tr_id", "")
                if header.get("tr_type") == "3":
                    logger.info("PINGPONG 수신 → 응답")
                    ws.send(message)
                    return
                msg_code = j.get("body", {}).get("msg_cd", "")
                logger.debug("KIS WS 응답: tr_id=%s msg_cd=%s", tr_id, msg_code)
            except json.JSONDecodeError:
                pass
            return

        # 파이프 구분 데이터 (호가/체결)
        tokens = message.split("|")
        if len(tokens) < 4:
            return

        tr_id = tokens[1]
        count = int(tokens[2]) if tokens[2].isdigit() else 1
        body = tokens[3]

        if tr_id == "H0STASP0":
            ticker_from_body = body.split("^")[0] if "^" in body else ""
            ticker = ticker_from_body or "unknown"
            snapshot = self._parse_orderbook(ticker, body)
            if snapshot:
                self._broadcast({"type": "orderbook", "ticker": ticker, "data": snapshot})

        elif tr_id == "H0STCNT0":
            trade = self._parse_trade(body)
            if trade:
                self._broadcast({"type": "trade", "ticker": trade["ticker"], "data": trade})

    def _on_error(self, ws: websocket.WebSocket, error: Exception) -> None:
        logger.error("KIS WebSocket 에러: %s", error)

    def _on_close(self, ws: websocket.WebSocket, code: int, reason: str) -> None:
        logger.warning("KIS WebSocket 종료: code=%s reason=%s", code, reason)
        self._connected = False
        if self._should_run:
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        delay = min(self._reconnect_delay, self._max_reconnect_delay)
        logger.info("%.1f초 후 재연결 시도...", delay)
        time.sleep(delay)
        self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
        if self._should_run:
            self._connect()

    # ── 연결/종료 ──

    def _connect(self) -> None:
        try:
            if not self._approval_key:
                self._approval_key = self._get_approval_key()
        except Exception as e:
            logger.error("접속키 발급 실패: %s", e)
            if self._should_run:
                self._schedule_reconnect()
            return

        self._ws = websocket.WebSocketApp(
            KIS_WS_URL,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._ws.run_forever(ping_interval=30, ping_timeout=10)

    def start(self) -> None:
        """백그라운드 스레드에서 WebSocket 시작."""
        if not KIS_APP_KEY or not KIS_APP_SECRET:
            logger.warning("KIS API 키 미설정 — WebSocket 미시작")
            return
        self._should_run = True
        self._start_time = time.time()
        self._ws_thread = threading.Thread(target=self._connect, daemon=True)
        self._ws_thread.start()
        logger.info("KIS WebSocket 클라이언트 시작 (URL: %s)", KIS_WS_URL)

    def stop(self) -> None:
        """WebSocket 종료."""
        self._should_run = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        logger.info("KIS WebSocket 클라이언트 종료")

    def subscribe(self, tickers: List[str]) -> None:
        """종목 구독 추가. 연결 전이면 pending에 저장."""
        new = set(tickers) - self._subscribed
        if not new:
            return
        if self._connected and self._ws:
            for tk in new:
                self._ws.send(self._sub_msg("H0STASP0", tk))
                self._ws.send(self._sub_msg("H0STCNT0", tk))
                self._subscribed.add(tk)
                time.sleep(0.05)
            logger.info("추가 구독: %s", sorted(new))
        else:
            self._pending_subs |= new
            logger.info("대기 구독 추가: %s", sorted(new))

    def unsubscribe(self, tickers: List[str]) -> None:
        """종목 구독 해제."""
        for tk in tickers:
            if tk in self._subscribed and self._connected and self._ws:
                self._ws.send(self._sub_msg("H0STASP0", tk, sub=False))
                self._ws.send(self._sub_msg("H0STCNT0", tk, sub=False))
            self._subscribed.discard(tk)
            self._pending_subs.discard(tk)

    def get_snapshot(self, ticker: str) -> dict:
        """특정 종목의 최신 호가+체결 캐시 반환."""
        return {
            "ticker": ticker,
            "orderbook": self.orderbook_cache.get(ticker),
            "trades": self.trade_cache.get(ticker, [])[:20],
            "strength_pct": self.strength_cache.get(ticker, 0),
            "timestamp": datetime.now(KST).isoformat(),
        }
