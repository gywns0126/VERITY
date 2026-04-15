"""
KIS WebSocket 클라이언트 — 실시간 호가/체결 구독 + 1분봉 집계.

KIS OpenAPI WebSocket 프로토콜:
  - 접속키: POST /oauth2/Approval → approval_key
  - TR ID: 호가 H0STASP0, 체결 H0STCNT0
  - 데이터: '|' 구분 파이프라인 포맷 (헤더 | 바디)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set

import requests
import websocket

from server.config import (
    KIS_APP_KEY,
    KIS_APP_SECRET,
    KIS_BASE_URL,
    KIS_WS_URL,
    MAX_CANDLE_MINUTES,
    MAX_SUBS,
)

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

_APPROVAL_CACHE_PATH = os.path.join(
    os.environ.get("XDG_CACHE_HOME", "/tmp"),
    "verity_kis_approval_key.json",
)

_TRADE_FIELDS = [
    "mksc_shrn_iscd", "stck_cntg_hour", "stck_prpr", "prdy_vrss_sign",
    "prdy_vrss", "prdy_ctrt", "wghn_avrg_stck_prc", "stck_oprc",
    "stck_hgpr", "stck_lwpr", "askp1", "bidp1", "cntg_vol", "acml_vol",
    "acml_tr_pbmn", "seln_cntg_csnu", "shnu_cntg_csnu", "ntby_cntg_csnu",
    "cttr", "seln_cntg_smtn", "shnu_cntg_smtn", "ccld_dvsn", "shnu_rate",
    "prdy_vol_vrss_acml_vol_rate", "oprc_hour",
    "oprc_vrss_prpr_sign", "oprc_vrss_prpr", "hgpr_hour",
    "hgpr_vrss_prpr_sign", "hgpr_vrss_prpr", "lwpr_hour",
    "lwpr_vrss_prpr_sign", "lwpr_vrss_prpr", "bsop_date",
    "new_mkop_cls_code", "trht_yn", "askp_rsqn1", "bidp_rsqn1",
    "total_askp_rsqn", "total_bidp_rsqn", "vol_tnrt",
    "prdy_smns_hour_acml_vol", "prdy_smns_hour_acml_vol_rate",
    "hour_cls_code", "mrkt_trtm_cls_code", "vi_stnd_prc",
]


class KISWebSocketClient:
    """KIS 실시간 WebSocket 클라이언트 — 1분봉 집계 + idle 자동 해제."""

    def __init__(self) -> None:
        self._approval_key: Optional[str] = None
        self._approval_key_issued_at: float = 0.0
        self._ws: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._connected = False
        self._subscribed: Set[str] = set()
        self._pending_subs: Set[str] = set()

        self.orderbook_cache: Dict[str, dict] = {}
        self.trade_cache: Dict[str, list] = defaultdict(list)
        self.strength_cache: Dict[str, float] = {}

        # 1분봉 집계: ticker → list of {time, o, h, l, c, vol}
        self.candle_cache: Dict[str, list] = defaultdict(list)
        # 현재 진행중인 1분봉: ticker → {minute_key, o, h, l, c, vol}
        self._live_candle: Dict[str, dict] = {}

        # 종목별 마지막 접근 시간 (SSE 클라이언트가 요청한 시간)
        self.last_access: Dict[str, float] = {}

        self._listeners: List[Callable[[dict], Any]] = []
        self._reconnect_delay = 1
        self._max_reconnect_delay = 60
        self._should_run = False
        self._start_time = time.time()

    # 접속키 유효시간: 발급 후 23시간까지 안전하게 사용 (24시간 만료)
    _APPROVAL_KEY_TTL = 23 * 3600

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

    def touch(self, ticker: str) -> None:
        """종목 접근 시간 갱신."""
        self.last_access[ticker] = time.time()

    def get_idle_tickers(self, ttl: int) -> List[str]:
        """TTL 초과한 idle 종목 목록."""
        now = time.time()
        idle = []
        for tk in list(self._subscribed):
            last = self.last_access.get(tk, 0)
            if last > 0 and (now - last) > ttl:
                idle.append(tk)
        return idle

    # ── 인증 ──

    def _is_approval_key_valid(self) -> bool:
        if not self._approval_key:
            return False
        return (time.time() - self._approval_key_issued_at) < self._APPROVAL_KEY_TTL

    def _load_cached_approval_key(self) -> bool:
        """디스크 캐시에서 유효한 접속키를 로드. 성공 시 True."""
        try:
            with open(_APPROVAL_CACHE_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            key = cached.get("approval_key", "")
            issued_at = cached.get("issued_at", 0)
            app_key = cached.get("app_key", "")
            if key and issued_at and app_key == KIS_APP_KEY:
                age = time.time() - issued_at
                if age < self._APPROVAL_KEY_TTL:
                    self._approval_key = key
                    self._approval_key_issued_at = issued_at
                    logger.info("WebSocket 접속키 디스크 캐시 적중 (남은: %.0f분)", (self._APPROVAL_KEY_TTL - age) / 60)
                    return True
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            pass
        except Exception as e:
            logger.debug("접속키 캐시 로드 실패 (무시): %s", e)
        return False

    def _save_cached_approval_key(self) -> None:
        """현재 접속키를 디스크에 저장."""
        try:
            os.makedirs(os.path.dirname(_APPROVAL_CACHE_PATH) or "/tmp", exist_ok=True)
            with open(_APPROVAL_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "approval_key": self._approval_key,
                    "issued_at": self._approval_key_issued_at,
                    "app_key": KIS_APP_KEY,
                }, f)
        except Exception as e:
            logger.debug("접속키 캐시 저장 실패 (무시): %s", e)

    def _get_approval_key(self, force: bool = False) -> str:
        if not force and self._is_approval_key_valid():
            return self._approval_key  # type: ignore
        if not force and self._load_cached_approval_key():
            return self._approval_key  # type: ignore
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
        self._approval_key = key
        self._approval_key_issued_at = time.time()
        self._save_cached_approval_key()
        age_h = (time.time() - self._start_time) / 3600
        logger.info("KIS WebSocket 접속키 신규 발급 (서버 가동 %.1f시간)", age_h)
        return key

    # ── 구독 메시지 ──

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

    # ── 1분봉 집계 ──

    def _update_candle(self, ticker: str, price: int, volume: int, time_str: str) -> Optional[dict]:
        """체결 데이터로 1분봉 갱신. 분이 바뀌면 완성된 캔들 반환."""
        minute_key = time_str[:5] if len(time_str) >= 5 else time_str  # "09:30"

        live = self._live_candle.get(ticker)
        completed = None

        if live and live["minute_key"] != minute_key:
            completed = {
                "time": live["minute_key"],
                "o": live["o"], "h": live["h"],
                "l": live["l"], "c": live["c"],
                "vol": live["vol"],
            }
            candles = self.candle_cache[ticker]
            candles.append(completed)
            if len(candles) > MAX_CANDLE_MINUTES:
                self.candle_cache[ticker] = candles[-MAX_CANDLE_MINUTES:]
            self._live_candle[ticker] = {
                "minute_key": minute_key,
                "o": price, "h": price, "l": price, "c": price,
                "vol": volume,
            }
        elif not live:
            self._live_candle[ticker] = {
                "minute_key": minute_key,
                "o": price, "h": price, "l": price, "c": price,
                "vol": volume,
            }
        else:
            live["h"] = max(live["h"], price)
            live["l"] = min(live["l"], price)
            live["c"] = price
            live["vol"] += volume

        return completed

    def get_candles(self, ticker: str) -> list:
        """완성된 캔들 + 현재 진행중 캔들 포함."""
        result = list(self.candle_cache.get(ticker, []))
        live = self._live_candle.get(ticker)
        if live:
            result.append({
                "time": live["minute_key"],
                "o": live["o"], "h": live["h"],
                "l": live["l"], "c": live["c"],
                "vol": live["vol"],
                "live": True,
            })
        return result

    # ── 파싱 ──

    def _parse_orderbook(self, ticker: str, body: str) -> dict:
        parts = body.split("^")
        if len(parts) < 43:
            return {}

        _int = lambda idx: int(parts[idx]) if idx < len(parts) and parts[idx] else 0

        asks, bids = [], []
        for i in range(10):
            ask_price, bid_price = _int(i), _int(10 + i)
            ask_vol, bid_vol = _int(20 + i), _int(30 + i)
            if ask_price > 0:
                asks.append({"price": ask_price, "volume": ask_vol, "side": "ask"})
            if bid_price > 0:
                bids.append({"price": bid_price, "volume": bid_vol, "side": "bid"})

        snapshot = {
            "ticker": ticker,
            "asks": asks,
            "bids": bids,
            "total_ask_vol": _int(40),
            "total_bid_vol": _int(41),
            "timestamp": datetime.now(KST).isoformat(),
        }
        self.orderbook_cache[ticker] = snapshot
        return snapshot

    def _parse_trade(self, body: str) -> dict:
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

        self.trade_cache[ticker].insert(0, trade)
        self.trade_cache[ticker] = self.trade_cache[ticker][:30]
        self.strength_cache[ticker] = strength

        completed_candle = self._update_candle(ticker, price, vol, time_fmt)

        return trade, completed_candle

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
        logger.info("구독 완료: %d종목 %s", len(self._subscribed), sorted(self._subscribed)[:5])

    def _on_message(self, ws: websocket.WebSocket, message: str) -> None:
        if not message:
            return

        if message.startswith("{"):
            try:
                j = json.loads(message)
                header = j.get("header", {})
                if header.get("tr_type") == "3":
                    ws.send(message)
                    return
            except json.JSONDecodeError:
                pass
            return

        tokens = message.split("|")
        if len(tokens) < 4:
            return

        tr_id = tokens[1]
        body = tokens[3]

        if tr_id == "H0STASP0":
            ticker = body.split("^")[0] if "^" in body else ""
            snapshot = self._parse_orderbook(ticker or "unknown", body)
            if snapshot:
                self._broadcast({"type": "orderbook", "ticker": ticker, "data": snapshot})

        elif tr_id == "H0STCNT0":
            result = self._parse_trade(body)
            if result:
                trade, completed_candle = result
                self._broadcast({"type": "trade", "ticker": trade["ticker"], "data": trade})
                if completed_candle:
                    self._broadcast({
                        "type": "candle",
                        "ticker": trade["ticker"],
                        "data": completed_candle,
                    })

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
        if not KIS_APP_KEY or not KIS_APP_SECRET:
            logger.warning("KIS API 키 미설정 — WebSocket 미시작")
            return
        self._should_run = True
        self._start_time = time.time()
        self._ws_thread = threading.Thread(target=self._connect, daemon=True)
        self._ws_thread.start()
        logger.info("KIS WebSocket 클라이언트 시작 (URL: %s)", KIS_WS_URL)

    def stop(self) -> None:
        self._should_run = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        logger.info("KIS WebSocket 클라이언트 종료")

    def force_reconnect(self) -> None:
        """접속키 갱신을 위한 강제 재연결. 기존 구독은 유지."""
        logger.info("접속키 만료 전 강제 재연결 — 기존 구독 %d종목 유지", len(self._subscribed))
        self._approval_key = None
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    def subscribe(self, tickers: List[str]) -> None:
        new = set(tickers) - self._subscribed
        if not new:
            return

        # MAX_SUBS 초과 시 가장 오래된 idle 종목부터 해제
        overflow = (len(self._subscribed) + len(new)) - MAX_SUBS
        if overflow > 0:
            candidates = sorted(
                self._subscribed,
                key=lambda t: self.last_access.get(t, 0),
            )
            to_unsub = candidates[:overflow]
            if to_unsub:
                logger.info("구독 슬롯 확보: %s 해제", to_unsub)
                self.unsubscribe(to_unsub)

        if self._connected and self._ws:
            for tk in new:
                self._ws.send(self._sub_msg("H0STASP0", tk))
                self._ws.send(self._sub_msg("H0STCNT0", tk))
                self._subscribed.add(tk)
                self.last_access[tk] = time.time()
                time.sleep(0.05)
            logger.info("추가 구독: %s (총 %d)", sorted(new), len(self._subscribed))
        else:
            self._pending_subs |= new
            for tk in new:
                self.last_access[tk] = time.time()

    def unsubscribe(self, tickers: List[str]) -> None:
        for tk in tickers:
            if tk in self._subscribed and self._connected and self._ws:
                self._ws.send(self._sub_msg("H0STASP0", tk, sub=False))
                self._ws.send(self._sub_msg("H0STCNT0", tk, sub=False))
            self._subscribed.discard(tk)
            self._pending_subs.discard(tk)
            self.orderbook_cache.pop(tk, None)
            self.trade_cache.pop(tk, None)
            self.candle_cache.pop(tk, None)
            self._live_candle.pop(tk, None)
        if tickers:
            logger.info("구독 해제: %s (남은 %d)", tickers, len(self._subscribed))

    def get_snapshot(self, ticker: str) -> dict:
        self.touch(ticker)
        return {
            "ticker": ticker,
            "orderbook": self.orderbook_cache.get(ticker),
            "trades": self.trade_cache.get(ticker, [])[:15],
            "strength_pct": self.strength_cache.get(ticker, 0),
            "timestamp": datetime.now(KST).isoformat(),
        }
