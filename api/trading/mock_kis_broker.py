"""
Mock KIS Broker — 토큰 없이 로컬에서 자동매매 로직을 검증하기 위한 인메모리 가상 계좌.

KISBroker와 동일한 메서드 시그니처를 유지하여 auto_trader.py가 DI만 바꿔서
실/Mock 브로커를 자유롭게 스왑할 수 있게 한다.

사용 예:
    broker = MockKISBroker(initial_cash=10_000_000,
                           price_map={"005930": 72000, "000660": 130000})
    result = broker.place_order("005930", OrderSide.BUY, qty=10)

주문은 즉시 체결(체결가 = 지정가 또는 price_map 가격)되며,
data/mock_orders.log에 모든 이벤트가 append된다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, VAMS_INITIAL_CASH
from api.trading.kis_broker import OrderResult, OrderSide

KST = timezone(timedelta(hours=9))

_MOCK_LOG_PATH = os.path.join(DATA_DIR, "mock_orders.log")
_MOCK_STATE_PATH = os.path.join(DATA_DIR, "mock_broker_state.json")


@dataclass
class MockHolding:
    ticker: str
    qty: int
    avg_price: float
    currency: str = "KRW"
    market: str = "KR"


@dataclass
class MockOrder:
    order_id: str
    ticker: str
    side: str
    qty: int
    price: float
    order_type: str
    status: str
    timestamp: str
    market: str = "KR"
    excd: str = ""
    filled_qty: int = 0
    filled_price: float = 0.0
    pnl: float = 0.0


def _now_iso() -> str:
    return datetime.now(KST).isoformat()


def _append_log(event: Dict[str, Any]) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(_MOCK_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass


class MockKISBroker:
    """실 KISBroker의 하위셋 인터페이스를 가진 인메모리 브로커.

    AutoTrader가 쓰는 메서드만 우선 구현한다:
      - get_current_price
      - get_balance / overseas_balance
      - place_order / overseas_order
      - get_order_history / overseas_order_history
    """

    def __init__(
        self,
        initial_cash: int = VAMS_INITIAL_CASH,
        price_map: Optional[Dict[str, float]] = None,
        fx_rate: float = 1350.0,
        persist: bool = False,
    ):
        self.cash: float = float(initial_cash)
        self.price_map: Dict[str, float] = dict(price_map or {})
        self.fx_rate: float = float(fx_rate)
        self.holdings_kr: Dict[str, MockHolding] = {}
        self.holdings_us: Dict[str, MockHolding] = {}
        self.orders: List[MockOrder] = []
        self._order_seq: int = 1000
        self._persist: bool = persist
        if persist:
            self._load_state()

    @property
    def is_configured(self) -> bool:
        return True

    @property
    def has_account(self) -> bool:
        return True

    @property
    def is_paper(self) -> bool:
        return True

    @classmethod
    def from_portfolio(
        cls,
        portfolio_path: Optional[str] = None,
        recommendations_path: Optional[str] = None,
        initial_cash: Optional[int] = None,
    ) -> "MockKISBroker":
        """기존 data/portfolio.json의 VAMS 상태를 가져와 Mock 계좌를 초기화한다.

        추천 종목의 price를 price_map으로 로드하므로 곧바로 주문 시뮬레이션이 가능하다.
        """
        from api.config import PORTFOLIO_PATH, RECOMMENDATIONS_PATH

        portfolio_path = portfolio_path or PORTFOLIO_PATH
        recommendations_path = recommendations_path or RECOMMENDATIONS_PATH

        cash = initial_cash if initial_cash is not None else VAMS_INITIAL_CASH
        fx = 1350.0
        price_map: Dict[str, float] = {}

        try:
            with open(portfolio_path, "r", encoding="utf-8") as f:
                txt = f.read().replace("NaN", "null").replace("Infinity", "null")
            port = json.loads(txt)
            fx = float((port.get("macro", {}).get("usd_krw") or {}).get("value", 1350) or 1350)
            if initial_cash is None:
                cash = int(port.get("vams", {}).get("cash", cash) or cash)
        except Exception:
            port = {}

        try:
            with open(recommendations_path, "r", encoding="utf-8") as f:
                recs = json.load(f)
            for r in recs:
                t = str(r.get("ticker", "")).strip()
                p = r.get("price")
                if t and p:
                    try:
                        price_map[t] = float(p)
                    except (TypeError, ValueError):
                        pass
        except Exception:
            pass

        broker = cls(initial_cash=cash, price_map=price_map, fx_rate=fx)

        for h in port.get("vams", {}).get("holdings", []) if port else []:
            tk = str(h.get("ticker", "")).strip()
            if not tk:
                continue
            is_us = h.get("currency") == "USD"
            holding = MockHolding(
                ticker=tk,
                qty=int(h.get("quantity", 0) or 0),
                avg_price=float(h.get("buy_price", 0) or 0),
                currency="USD" if is_us else "KRW",
                market="US" if is_us else "KR",
            )
            if is_us:
                broker.holdings_us[tk] = holding
            else:
                broker.holdings_kr[tk] = holding

        return broker

    def _next_order_id(self) -> str:
        self._order_seq += 1
        return f"MOCK{self._order_seq:08d}"

    def set_price(self, ticker: str, price: float) -> None:
        self.price_map[ticker] = float(price)

    def _resolve_price(self, ticker: str, given: float = 0) -> float:
        if given and given > 0:
            return float(given)
        if ticker in self.price_map:
            return float(self.price_map[ticker])
        raise RuntimeError(f"MockBroker: {ticker} 가격 모름 (price_map 또는 지정가 필요)")

    # ──────────────────────────────────────────────
    # 시세 조회
    # ──────────────────────────────────────────────

    def get_current_price(self, ticker: str) -> Dict[str, Any]:
        price = self.price_map.get(ticker, 0)
        return {
            "stck_prpr": str(int(price)),
            "prdy_vrss": "0",
            "prdy_ctrt": "0",
            "acml_vol": "0",
        }

    def overseas_price(self, excd: str, ticker: str) -> Dict[str, Any]:
        price = self.price_map.get(ticker, 0)
        return {"last": str(price), "rate": "0", "diff": "0"}

    # ──────────────────────────────────────────────
    # 계좌 조회
    # ──────────────────────────────────────────────

    def get_balance(self) -> Dict[str, Any]:
        holdings = []
        total_eval = 0.0
        for h in self.holdings_kr.values():
            cur = self.price_map.get(h.ticker, h.avg_price)
            eval_amt = cur * h.qty
            total_eval += eval_amt
            holdings.append({
                "pdno": h.ticker,
                "prdt_name": h.ticker,
                "hldg_qty": str(h.qty),
                "pchs_avg_pric": str(h.avg_price),
                "prpr": str(int(cur)),
                "evlu_amt": str(int(eval_amt)),
                "evlu_pfls_amt": str(int((cur - h.avg_price) * h.qty)),
            })
        summary = {
            "dnca_tot_amt": str(int(self.cash)),
            "tot_evlu_amt": str(int(self.cash + total_eval)),
            "scts_evlu_amt": str(int(total_eval)),
        }
        return {"holdings": holdings, "summary": summary}

    def overseas_balance(self) -> List[Dict[str, Any]]:
        result = []
        for h in self.holdings_us.values():
            cur = self.price_map.get(h.ticker, h.avg_price)
            result.append({
                "ovrs_pdno": h.ticker,
                "ovrs_item_name": h.ticker,
                "ord_psbl_qty": str(h.qty),
                "pchs_avg_pric": f"{h.avg_price:.4f}",
                "now_pric2": f"{cur:.4f}",
                "frcr_evlu_pfls_amt": f"{(cur - h.avg_price) * h.qty:.2f}",
            })
        return result

    # ──────────────────────────────────────────────
    # 국내 주문
    # ──────────────────────────────────────────────

    def place_order(
        self,
        ticker: str,
        side: OrderSide,
        qty: int,
        price: int = 0,
        order_type: str = "00",
        context: Optional[Dict[str, Any]] = None,
    ) -> OrderResult:
        if qty <= 0:
            return OrderResult(success=False, message="qty <= 0")

        try:
            exec_price = self._resolve_price(ticker, price)
        except RuntimeError as e:
            return OrderResult(success=False, message=str(e))

        total = exec_price * qty
        order_id = self._next_order_id()

        if side == OrderSide.BUY:
            if total > self.cash:
                return OrderResult(
                    success=False,
                    order_id=order_id,
                    message=f"예수금 부족 ({total:,.0f} > {self.cash:,.0f})",
                )
            self.cash -= total
            existing = self.holdings_kr.get(ticker)
            if existing:
                new_qty = existing.qty + qty
                new_avg = (existing.avg_price * existing.qty + exec_price * qty) / new_qty
                existing.qty = new_qty
                existing.avg_price = new_avg
            else:
                self.holdings_kr[ticker] = MockHolding(
                    ticker=ticker, qty=qty, avg_price=exec_price,
                    currency="KRW", market="KR",
                )
            pnl = 0.0
        else:
            existing = self.holdings_kr.get(ticker)
            if not existing or existing.qty < qty:
                return OrderResult(
                    success=False, order_id=order_id,
                    message=f"매도 수량 부족 (보유 {existing.qty if existing else 0}주)",
                )
            pnl = (exec_price - existing.avg_price) * qty
            existing.qty -= qty
            self.cash += total
            if existing.qty == 0:
                del self.holdings_kr[ticker]

        order = MockOrder(
            order_id=order_id, ticker=ticker, side=side.value, qty=qty,
            price=exec_price, order_type=order_type, status="FILLED",
            timestamp=_now_iso(), market="KR",
            filled_qty=qty, filled_price=exec_price, pnl=pnl,
        )
        self.orders.append(order)
        _append_log({
            "event": "place_order", "market": "KR", "side": side.value,
            "ticker": ticker, "qty": qty, "price": exec_price,
            "order_id": order_id, "cash_after": self.cash, "pnl": pnl,
            "timestamp": order.timestamp,
        })
        if self._persist:
            self._save_state()
        return OrderResult(
            success=True, order_id=order_id,
            message="MOCK 체결 완료", filled_qty=qty, filled_price=exec_price,
            raw={"ODNO": order_id},
        )

    def overseas_order(
        self, excd: str, ticker: str, side: str,
        qty: int, price: float = 0, order_type: str = "00",
        context: Optional[Dict[str, Any]] = None,
    ) -> OrderResult:
        if qty <= 0:
            return OrderResult(success=False, message="qty <= 0")
        try:
            exec_price = self._resolve_price(ticker, price)
        except RuntimeError as e:
            return OrderResult(success=False, message=str(e))

        total_usd = exec_price * qty
        total_krw = total_usd * self.fx_rate
        order_id = self._next_order_id()

        if side == "buy":
            if total_krw > self.cash:
                return OrderResult(
                    success=False, order_id=order_id,
                    message=f"예수금 부족 (${total_usd:,.2f} × {self.fx_rate:.0f} > {self.cash:,.0f}원)",
                )
            self.cash -= total_krw
            existing = self.holdings_us.get(ticker)
            if existing:
                new_qty = existing.qty + qty
                new_avg = (existing.avg_price * existing.qty + exec_price * qty) / new_qty
                existing.qty = new_qty
                existing.avg_price = new_avg
            else:
                self.holdings_us[ticker] = MockHolding(
                    ticker=ticker, qty=qty, avg_price=exec_price,
                    currency="USD", market="US",
                )
            pnl = 0.0
        else:
            existing = self.holdings_us.get(ticker)
            if not existing or existing.qty < qty:
                return OrderResult(
                    success=False, order_id=order_id,
                    message=f"매도 수량 부족 (보유 {existing.qty if existing else 0}주)",
                )
            pnl = (exec_price - existing.avg_price) * qty * self.fx_rate
            existing.qty -= qty
            self.cash += total_krw
            if existing.qty == 0:
                del self.holdings_us[ticker]

        order = MockOrder(
            order_id=order_id, ticker=ticker, side=side, qty=qty,
            price=exec_price, order_type=order_type, status="FILLED",
            timestamp=_now_iso(), market="US", excd=excd,
            filled_qty=qty, filled_price=exec_price, pnl=pnl,
        )
        self.orders.append(order)
        _append_log({
            "event": "place_order", "market": "US", "excd": excd,
            "side": side, "ticker": ticker, "qty": qty, "price": exec_price,
            "order_id": order_id, "cash_after": self.cash, "pnl": pnl,
            "timestamp": order.timestamp,
        })
        if self._persist:
            self._save_state()
        return OrderResult(
            success=True, order_id=order_id,
            message="MOCK 체결 완료", filled_qty=qty, filled_price=exec_price,
            raw={"ODNO": order_id},
        )

    # ──────────────────────────────────────────────
    # 주문 이력
    # ──────────────────────────────────────────────

    def get_order_history(
        self, start_date: str = "", end_date: str = ""
    ) -> List[Dict[str, Any]]:
        return [self._order_to_kis_fmt(o) for o in self.orders if o.market == "KR"]

    def overseas_order_history(
        self, start_date: str = "", end_date: str = ""
    ) -> List[Dict[str, Any]]:
        return [self._order_to_kis_fmt(o) for o in self.orders if o.market == "US"]

    def _order_to_kis_fmt(self, o: MockOrder) -> Dict[str, Any]:
        return {
            "odno": o.order_id,
            "pdno": o.ticker,
            "ord_qty": str(o.qty),
            "tot_ccld_qty": str(o.filled_qty),
            "avg_prvs": f"{o.filled_price:.2f}",
            "sll_buy_dvsn_cd": "02" if o.side == "buy" else "01",
            "ord_tmd": o.timestamp,
            "prcs_stat_name": o.status,
        }

    # ──────────────────────────────────────────────
    # 지속성 (옵션)
    # ──────────────────────────────────────────────

    def _load_state(self) -> None:
        try:
            with open(_MOCK_STATE_PATH, "r", encoding="utf-8") as f:
                s = json.load(f)
            self.cash = float(s.get("cash", self.cash))
            self.holdings_kr = {
                t: MockHolding(**h) for t, h in s.get("holdings_kr", {}).items()
            }
            self.holdings_us = {
                t: MockHolding(**h) for t, h in s.get("holdings_us", {}).items()
            }
            self._order_seq = int(s.get("order_seq", self._order_seq))
        except Exception:
            pass

    def _save_state(self) -> None:
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(_MOCK_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "cash": self.cash,
                    "holdings_kr": {t: h.__dict__ for t, h in self.holdings_kr.items()},
                    "holdings_us": {t: h.__dict__ for t, h in self.holdings_us.items()},
                    "order_seq": self._order_seq,
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def snapshot(self) -> Dict[str, Any]:
        """현재 상태를 JSON으로 덤프 (디버깅용)."""
        return {
            "cash": self.cash,
            "holdings_kr": {t: h.__dict__ for t, h in self.holdings_kr.items()},
            "holdings_us": {t: h.__dict__ for t, h in self.holdings_us.items()},
            "order_count": len(self.orders),
            "last_order": self.orders[-1].__dict__ if self.orders else None,
        }
