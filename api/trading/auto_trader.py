"""
Auto Trader — recommendations + timing 시그널을 KIS 주문으로 변환 실행.

Broker는 DI로 주입받으므로 MockKISBroker(로컬 검증)와 KISBroker(실거래)를
동일 로직으로 처리한다.

흐름:
  1. plan_orders(portfolio) → 주문 계획 (매수/매도) + 차단 사유
  2. apply_safety_limits() → 일일 한도·킬스위치·장시간·드라이런 체크
  3. execute(orders, broker) → 주문 제출 (Mock/실) → 결과 수집
  4. 이력 저장 → data/auto_trade_history.json

안전장치 (환경변수):
  AUTO_TRADE_ENABLED                (기본 false)  마스터 스위치
  AUTO_TRADE_DRY_RUN                (기본 true)   주문 제출 직전 차단
  AUTO_TRADE_MAX_DAILY_BUY_KRW      (기본 500,000)
  AUTO_TRADE_MAX_PER_STOCK_KRW      (기본 200,000)
  AUTO_TRADE_ALLOW_OVERSEAS         (기본 false)
  AUTO_TRADE_MIN_SAFETY_SCORE       (기본 70)
  AUTO_TRADE_MIN_TIMING_SCORE       (기본 70)
  AUTO_TRADE_ALLOW_AFTER_HOURS      (기본 false)  장외시간 주문 허용

킬스위치 파일: data/.auto_trade_paused  (존재 시 전체 중단)
이력 파일:     data/auto_trade_history.json
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from api.config import DATA_DIR
from api.trading.kis_broker import OrderResult, OrderSide

KST = timezone(timedelta(hours=9))

_KILLSWITCH_PATH = os.path.join(DATA_DIR, ".auto_trade_paused")
_HISTORY_PATH = os.path.join(DATA_DIR, "auto_trade_history.json")


@dataclass
class TradeOrder:
    side: str  # "BUY" or "SELL"
    ticker: str
    name: str
    qty: int
    price: float
    market: str = "KR"  # "KR" or "US"
    excd: str = ""  # 해외: NAS/NYS/...
    reason: str = ""
    safety_score: int = 0
    timing_score: int = 0
    currency: str = "KRW"

    def notional_krw(self, fx_rate: float = 1350.0) -> float:
        if self.currency == "USD":
            return self.price * self.qty * fx_rate
        return self.price * self.qty


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _now(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now(KST)


def is_killswitch_active() -> bool:
    return os.path.exists(_KILLSWITCH_PATH)


def activate_killswitch() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_KILLSWITCH_PATH, "w", encoding="utf-8") as f:
        f.write(datetime.now(KST).isoformat())


def deactivate_killswitch() -> None:
    try:
        os.remove(_KILLSWITCH_PATH)
    except FileNotFoundError:
        pass


def is_kr_market_open(now: Optional[datetime] = None) -> bool:
    """한국 주식시장 정규장 여부 (09:00-15:30 KST, 월-금)."""
    n = _now(now)
    if n.weekday() >= 5:
        return False
    open_t = n.replace(hour=9, minute=0, second=0, microsecond=0)
    close_t = n.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_t <= n <= close_t


def is_us_market_open(now: Optional[datetime] = None) -> bool:
    """미국 주식시장 정규장 여부 (KST 기준 23:30 ~ 익일 06:00, 여름시간 22:30 ~ 05:00 근사)."""
    n = _now(now)
    if n.weekday() == 5 or (n.weekday() == 6 and n.hour < 23):
        return False
    hour = n.hour + n.minute / 60.0
    return hour >= 22.5 or hour <= 6.0


# ──────────────────────────────────────────────
# 주문 계획
# ──────────────────────────────────────────────

def plan_orders(
    portfolio: Dict[str, Any],
    broker: Any,
    now: Optional[datetime] = None,
) -> Tuple[List[TradeOrder], List[Dict[str, Any]]]:
    """portfolio.recommendations와 현재 잔고를 비교해 주문 계획 생성.

    Returns:
        (orders, blocks): 실행할 주문과 차단된 후보 목록
    """
    recs = portfolio.get("recommendations") or []
    vams_holdings = portfolio.get("vams", {}).get("holdings") or []
    fx_rate = float(portfolio.get("macro", {}).get("usd_krw", {}).get("value", 1350) or 1350)

    min_safety = _env_int("AUTO_TRADE_MIN_SAFETY_SCORE", 70)
    min_timing = _env_int("AUTO_TRADE_MIN_TIMING_SCORE", 70)
    max_per_stock = _env_int("AUTO_TRADE_MAX_PER_STOCK_KRW", 200_000)
    allow_overseas = _env_bool("AUTO_TRADE_ALLOW_OVERSEAS", False)
    require_buy_rec = _env_bool("AUTO_TRADE_REQUIRE_BUY_REC", False)

    try:
        balance = broker.get_balance()
        held_kr = {str(h.get("pdno", "")).strip() for h in balance.get("holdings", [])}
    except Exception:
        held_kr = {str(h.get("ticker", "")).strip() for h in vams_holdings
                   if h.get("currency") != "USD"}

    try:
        overseas_rows = broker.overseas_balance() if allow_overseas else []
        held_us = {str(h.get("ovrs_pdno", "")).strip() for h in overseas_rows}
    except Exception:
        held_us = {str(h.get("ticker", "")).strip() for h in vams_holdings
                   if h.get("currency") == "USD"}

    orders: List[TradeOrder] = []
    blocks: List[Dict[str, Any]] = []

    for r in recs:
        ticker = str(r.get("ticker", "")).strip()
        if not ticker:
            continue
        name = str(r.get("name", ticker))
        rec = str(r.get("recommendation", "")).upper()
        timing = r.get("timing") or {}
        action = str(timing.get("action", "HOLD")).upper()
        t_score = int(timing.get("timing_score", 0) or 0)
        safety = int(r.get("safety_score", 0) or 0)
        currency = str(r.get("currency", "KRW")).upper()
        price = float(r.get("price", 0) or 0)
        market = "US" if currency == "USD" else "KR"
        excd = r.get("excd") or r.get("exchange") or (
            "NAS" if market == "US" else ""
        )

        if market == "US" and not allow_overseas:
            blocks.append({
                "ticker": ticker, "name": name,
                "reason": "해외주식 자동매매 비활성 (AUTO_TRADE_ALLOW_OVERSEAS=false)",
            })
            continue

        if price <= 0:
            blocks.append({"ticker": ticker, "name": name, "reason": "가격 정보 없음"})
            continue

        held = ticker in (held_us if market == "US" else held_kr)

        if require_buy_rec:
            is_buy_signal = rec in ("BUY", "STRONG_BUY") and action in ("BUY", "STRONG_BUY")
        else:
            is_buy_signal = (
                action == "STRONG_BUY"
                or (action == "BUY" and rec in ("BUY", "STRONG_BUY"))
            )
        is_sell_signal = action in ("SELL", "STRONG_SELL")

        if is_buy_signal and not held:
            if safety < min_safety:
                blocks.append({
                    "ticker": ticker, "name": name,
                    "reason": f"안심점수 {safety} < {min_safety}",
                })
                continue
            if t_score < min_timing:
                blocks.append({
                    "ticker": ticker, "name": name,
                    "reason": f"타이밍점수 {t_score} < {min_timing}",
                })
                continue

            notional_krw = price * fx_rate if currency == "USD" else price
            if notional_krw <= 0:
                blocks.append({"ticker": ticker, "name": name, "reason": "단가 환산 실패"})
                continue

            qty = max(1, int(max_per_stock // notional_krw))
            if qty <= 0:
                blocks.append({
                    "ticker": ticker, "name": name,
                    "reason": f"한도 초과 (1주 {notional_krw:,.0f}원 > {max_per_stock:,}원)",
                })
                continue

            orders.append(TradeOrder(
                side="BUY", ticker=ticker, name=name, qty=qty, price=price,
                market=market, excd=excd, currency=currency,
                reason=f"{rec} / 타이밍 {t_score} / 안심 {safety}",
                safety_score=safety, timing_score=t_score,
            ))

        elif is_sell_signal and held:
            holding_qty = 0
            if market == "US":
                for h in overseas_rows:
                    if str(h.get("ovrs_pdno", "")).strip() == ticker:
                        holding_qty = int(h.get("ord_psbl_qty", 0) or 0)
                        break
            else:
                for h in balance.get("holdings", []):
                    if str(h.get("pdno", "")).strip() == ticker:
                        holding_qty = int(h.get("hldg_qty", 0) or 0)
                        break
            if holding_qty <= 0:
                blocks.append({
                    "ticker": ticker, "name": name,
                    "reason": "매도 대상이나 보유 수량 0",
                })
                continue

            orders.append(TradeOrder(
                side="SELL", ticker=ticker, name=name, qty=holding_qty, price=price,
                market=market, excd=excd, currency=currency,
                reason=f"타이밍 {action} / 점수 {t_score}",
                safety_score=safety, timing_score=t_score,
            ))

    return orders, blocks


# ──────────────────────────────────────────────
# 안전장치
# ──────────────────────────────────────────────

def apply_safety_limits(
    orders: List[TradeOrder],
    fx_rate: float = 1350.0,
    now: Optional[datetime] = None,
    force_allow_after_hours: Optional[bool] = None,
) -> Tuple[List[TradeOrder], List[Dict[str, Any]]]:
    """킬스위치·장시간·일일 한도 등을 적용해 실행 가능 주문만 필터링."""
    blocks: List[Dict[str, Any]] = []
    if not orders:
        return [], blocks

    if is_killswitch_active():
        blocks.extend({
            "ticker": o.ticker, "name": o.name,
            "reason": "킬스위치 활성화 (.auto_trade_paused)",
        } for o in orders)
        return [], blocks

    allow_after_hours = (
        force_allow_after_hours
        if force_allow_after_hours is not None
        else _env_bool("AUTO_TRADE_ALLOW_AFTER_HOURS", False)
    )

    max_daily_buy = _env_int("AUTO_TRADE_MAX_DAILY_BUY_KRW", 500_000)
    today_spent = _today_buy_spent_krw()
    remaining = max(0, max_daily_buy - today_spent)

    passed: List[TradeOrder] = []
    for o in orders:
        if o.market == "KR" and not allow_after_hours and not is_kr_market_open(now):
            blocks.append({
                "ticker": o.ticker, "name": o.name,
                "reason": "한국 장외시간 — 주문 차단",
            })
            continue
        if o.market == "US" and not allow_after_hours and not is_us_market_open(now):
            blocks.append({
                "ticker": o.ticker, "name": o.name,
                "reason": "미국 장외시간 — 주문 차단",
            })
            continue

        if o.side == "BUY":
            cost = o.notional_krw(fx_rate)
            if cost > remaining:
                blocks.append({
                    "ticker": o.ticker, "name": o.name,
                    "reason": f"일일 매수 한도 초과 (누적 {today_spent:,.0f} + {cost:,.0f} > {max_daily_buy:,})",
                })
                continue
            remaining -= cost

        passed.append(o)

    return passed, blocks


def _today_buy_spent_krw() -> float:
    history = load_history()
    today = datetime.now(KST).strftime("%Y-%m-%d")
    total = 0.0
    for rec in history:
        if rec.get("date", "").startswith(today) and rec.get("side") == "BUY" and rec.get("status") == "FILLED":
            total += float(rec.get("notional_krw", 0) or 0)
    return total


# ──────────────────────────────────────────────
# 실행
# ──────────────────────────────────────────────

def _log_backtest_gap_safe(ticker: str, signal_price: float, fill_price: float,
                            note: str = "") -> None:
    """주문 체결 시 시그널 가격 vs 체결가 갭 누적. 실패는 무시."""
    try:
        from api.metadata import backtest_gap
        backtest_gap.log_gap(
            ticker=ticker,
            backtest_entry_price=signal_price,  # 시그널 발생 시점 가격 = 백테스트 진입가 가정
            sim_entry_price=fill_price,         # 실제 체결가 (mock 또는 실거래)
            note=note,
        )
    except Exception as e:
        logger.debug("backtest_gap 기록 실패: %s", e)


def execute(
    orders: List[TradeOrder],
    broker: Any,
    dry_run: bool = True,
    fx_rate: float = 1350.0,
) -> List[Dict[str, Any]]:
    """주문 실행. dry_run=True면 broker 호출 없이 intent만 기록.

    Returns:
        결과 리스트 [{order_id, filled_qty, filled_price, pnl, success, message, ...}]
    """
    results: List[Dict[str, Any]] = []
    history = load_history()

    for o in orders:
        base_record = {
            "date": datetime.now(KST).isoformat(),
            "side": o.side,
            "ticker": o.ticker,
            "name": o.name,
            "qty": o.qty,
            "price": o.price,
            "market": o.market,
            "currency": o.currency,
            "notional_krw": o.notional_krw(fx_rate),
            "reason": o.reason,
            "dry_run": dry_run,
        }

        if dry_run:
            result = {
                **base_record,
                "status": "DRY_RUN",
                "order_id": f"DRY{len(history) + len(results) + 1:08d}",
                "filled_qty": o.qty,
                "filled_price": o.price,
                "pnl": 0,
                "success": True,
                "message": "DRY_RUN — 실주문 미전송",
            }
        else:
            # auto_trader 는 VAMS 시그널 기반 자동 매매 — source=VAMS_SIGNAL 명시
            trade_context = {
                "source": "VAMS_SIGNAL",
                "reason": getattr(o, "reason", None) or f"VAMS auto-trade {o.side}",
                "brain_grade": getattr(o, "brain_grade", None),
                "brain_score": getattr(o, "brain_score", None),
                "regime": getattr(o, "regime", None),
                "vams_profile": getattr(o, "profile", None),
            }
            try:
                if o.market == "KR":
                    side_enum = OrderSide.BUY if o.side == "BUY" else OrderSide.SELL
                    res: OrderResult = broker.place_order(
                        ticker=o.ticker, side=side_enum, qty=o.qty,
                        price=int(o.price), order_type="00",
                        context=trade_context,
                    )
                else:
                    res = broker.overseas_order(
                        excd=o.excd or "NAS", ticker=o.ticker,
                        side=o.side.lower(), qty=o.qty, price=o.price,
                        order_type="00",
                        context=trade_context,
                    )
                result = {
                    **base_record,
                    "status": "FILLED" if res.success else "FAILED",
                    "order_id": res.order_id or "",
                    "filled_qty": res.filled_qty or o.qty,
                    "filled_price": res.filled_price or o.price,
                    "success": res.success,
                    "message": res.message,
                    "pnl": (getattr(res, "raw", {}) or {}).get("pnl", 0),
                }
                # backtest_gap 호출자 연결 — 시그널 가격(o.price) vs 체결가(res.filled_price) 갭 측정
                if res.success and o.price and res.filled_price:
                    _log_backtest_gap_safe(
                        ticker=o.ticker,
                        signal_price=float(o.price),
                        fill_price=float(res.filled_price),
                        note=f"VAMS auto-trade {o.side}",
                    )
            except Exception as e:
                result = {
                    **base_record,
                    "status": "FAILED", "order_id": "",
                    "filled_qty": 0, "filled_price": 0,
                    "success": False, "message": str(e)[:200], "pnl": 0,
                }

        results.append(result)
        history.append(result)

    save_history(history)
    return results


# ──────────────────────────────────────────────
# 이력
# ──────────────────────────────────────────────

def load_history() -> List[Dict[str, Any]]:
    try:
        with open(_HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history: List[Dict[str, Any]]) -> None:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass


# ──────────────────────────────────────────────
# 통합 엔트리
# ──────────────────────────────────────────────

def run_auto_trade_cycle(
    portfolio: Dict[str, Any],
    broker: Optional[Any] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """포트폴리오 한 사이클. Broker 미지정 시 factory로 자동 선택.

    Returns: {orders, blocks, results, master_enabled, dry_run}
    """
    from api.trading import get_broker

    master_enabled = _env_bool("AUTO_TRADE_ENABLED", False)
    dry_run = _env_bool("AUTO_TRADE_DRY_RUN", True)

    if broker is None:
        broker = get_broker()

    fx_rate = float(portfolio.get("macro", {}).get("usd_krw", {}).get("value", 1350) or 1350)

    orders, plan_blocks = plan_orders(portfolio, broker, now=now)

    if not master_enabled:
        return {
            "orders": [asdict(o) for o in orders],
            "blocks": plan_blocks + [{"reason": "AUTO_TRADE_ENABLED=false — 마스터 스위치 OFF"}],
            "results": [],
            "master_enabled": False,
            "dry_run": dry_run,
        }

    passed, safety_blocks = apply_safety_limits(orders, fx_rate=fx_rate, now=now)
    results = execute(passed, broker, dry_run=dry_run, fx_rate=fx_rate)

    return {
        "orders": [asdict(o) for o in orders],
        "passed": [asdict(o) for o in passed],
        "blocks": plan_blocks + safety_blocks,
        "results": results,
        "master_enabled": True,
        "dry_run": dry_run,
    }
