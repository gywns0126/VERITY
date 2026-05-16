#!/usr/bin/env python3
"""로컬 자동매매 End-to-End 시뮬레이션 (토큰 불필요).

기존 data/portfolio.json + data/recommendations.json을 읽어
  1) TimingSignalWatcher로 전이 알림 메시지 생성
  2) AutoTrader(MockKISBroker)로 주문 계획/안전장치/실행 시뮬
  3) 텔레그램은 토큰 없으면 자동으로 콘솔 출력 폴백

사용법:
    python scripts/simulate_auto_trade.py
    python scripts/simulate_auto_trade.py --live-mock   # dry_run 대신 Mock 체결
    python scripts/simulate_auto_trade.py --allow-after-hours
    python scripts/simulate_auto_trade.py --reset-state
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

os.environ.setdefault("VERITY_MODE", "dev")
os.environ.setdefault("USE_MOCK_BROKER", "true")

from api.config import PORTFOLIO_PATH, RECOMMENDATIONS_PATH, DATA_DIR  # noqa: E402
from api.notifications.telegram import (  # noqa: E402
    send_auto_trade_blocked,
    send_auto_trade_filled,
    send_auto_trade_intent,
    send_timing_signal_alert,
)
from api.notifications.timing_signal_watcher import (  # noqa: E402
    _STATE_PATH as TIMING_STATE_PATH,
    run_timing_watcher,
)
from api.trading.auto_trader import run_auto_trade_cycle  # noqa: E402
from api.trading.mock_kis_broker import MockKISBroker  # noqa: E402


def _load_portfolio() -> Dict[str, Any]:
    if not os.path.exists(PORTFOLIO_PATH):
        print(f"[SIM] portfolio.json 없음: {PORTFOLIO_PATH}")
        return {}
    with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
        txt = f.read().replace("NaN", "null").replace("Infinity", "null")
    port = json.loads(txt)

    if os.path.exists(RECOMMENDATIONS_PATH):
        with open(RECOMMENDATIONS_PATH, "r", encoding="utf-8") as f:
            try:
                recs = json.load(f)
                if isinstance(recs, list) and recs:
                    port["recommendations"] = recs
            except json.JSONDecodeError:
                pass
    return port


def _print_header(title: str) -> None:
    bar = "=" * 70
    print(f"\n{bar}\n{title}\n{bar}")


def _print_table(rows, cols):
    if not rows:
        print("  (없음)")
        return
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    header = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)
    for r in rows:
        print(" | ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))


def main():
    parser = argparse.ArgumentParser(description="VERITY 자동매매 로컬 시뮬레이션")
    parser.add_argument("--live-mock", action="store_true",
                        help="AUTO_TRADE_DRY_RUN=false (Mock 브로커로 실제 체결 시뮬)")
    parser.add_argument("--allow-after-hours", action="store_true",
                        help="장외시간에도 주문 허용 (테스트용)")
    parser.add_argument("--min-safety", type=int, default=None)
    parser.add_argument("--min-timing", type=int, default=None)
    parser.add_argument("--max-per-stock", type=int, default=None)
    parser.add_argument("--max-daily", type=int, default=None)
    parser.add_argument("--initial-cash", type=int, default=None)
    parser.add_argument("--reset-state", action="store_true",
                        help="타이밍 state 초기화 (전이 알림 강제 재현)")
    args = parser.parse_args()

    os.environ["AUTO_TRADE_ENABLED"] = "true"
    os.environ["AUTO_TRADE_DRY_RUN"] = "false" if args.live_mock else "true"
    if args.allow_after_hours:
        os.environ["AUTO_TRADE_ALLOW_AFTER_HOURS"] = "true"
    if args.min_safety is not None:
        os.environ["AUTO_TRADE_MIN_SAFETY_SCORE"] = str(args.min_safety)
    if args.min_timing is not None:
        os.environ["AUTO_TRADE_MIN_TIMING_SCORE"] = str(args.min_timing)
    if args.max_per_stock is not None:
        os.environ["AUTO_TRADE_MAX_PER_STOCK_KRW"] = str(args.max_per_stock)
    if args.max_daily is not None:
        os.environ["AUTO_TRADE_MAX_DAILY_BUY_KRW"] = str(args.max_daily)

    if args.reset_state and os.path.exists(TIMING_STATE_PATH):
        os.remove(TIMING_STATE_PATH)
        print(f"[SIM] 타이밍 state 초기화: {TIMING_STATE_PATH}")

    _print_header("1) 포트폴리오 로드")
    portfolio = _load_portfolio()
    if not portfolio:
        print("[SIM] portfolio.json이 비어있어 시뮬레이션 중단.")
        return
    recs = portfolio.get("recommendations") or []
    holdings = portfolio.get("vams", {}).get("holdings") or []
    fx = float(portfolio.get("macro", {}).get("usd_krw", {}).get("value", 1350) or 1350)
    print(f"  추천 종목: {len(recs)}")
    print(f"  VAMS 보유: {len(holdings)}")
    print(f"  환율: {fx:.2f}원/USD")

    _print_header("2) 타이밍 시그널 전이 감지")
    transitions = run_timing_watcher(portfolio)
    print(f"  감지된 전이: {len(transitions)}")
    if transitions:
        _print_table(
            [{"name": t["name"], "from": t["from_action"],
              "to": t["to_action"], "held": "Y" if t["is_held"] else "",
              "score": t["score"]} for t in transitions[:10]],
            ["name", "from", "to", "held", "score"],
        )
        send_timing_signal_alert(transitions)
    else:
        print("  (전이 없음 — --reset-state로 강제 재현 가능)")

    _print_header("3) AutoTrader 주문 계획")
    broker = MockKISBroker.from_portfolio(
        initial_cash=args.initial_cash,
    )
    print(f"  MockBroker: 현금 {broker.cash:,.0f}원 | "
          f"국내보유 {len(broker.holdings_kr)} | 해외보유 {len(broker.holdings_us)}")

    result = run_auto_trade_cycle(portfolio, broker=broker)

    print(f"\n  마스터 스위치: {result['master_enabled']}")
    print(f"  DRY RUN: {result['dry_run']}")
    print(f"  계획된 주문: {len(result['orders'])}")
    print(f"  차단된 후보: {len(result['blocks'])}")
    print(f"  실행된 주문: {len(result['results'])}")

    if result["orders"]:
        print("\n  [ 주문 계획 ]")
        _print_table(
            [{"side": o["side"], "ticker": o["ticker"], "name": o["name"],
              "qty": o["qty"], "price": f"{o['price']:.0f}",
              "reason": (o["reason"] or "")[:40]} for o in result["orders"][:20]],
            ["side", "ticker", "name", "qty", "price", "reason"],
        )
        send_auto_trade_intent(result["orders"], dry_run=result["dry_run"])

    if result["blocks"]:
        print("\n  [ 차단 사유 ]")
        _print_table(
            [{"ticker": b.get("ticker", "-"), "name": b.get("name", "-"),
              "reason": (b.get("reason") or "")[:80]}
             for b in result["blocks"][:20]],
            ["ticker", "name", "reason"],
        )
        send_auto_trade_blocked(result["blocks"])

    if result["results"]:
        print("\n  [ 체결 결과 ]")
        _print_table(
            [{"side": r["side"], "ticker": r["ticker"],
              "qty": r.get("filled_qty", 0), "price": f"{r.get('filled_price', 0):.0f}",
              "status": r["status"], "order_id": r.get("order_id", "")}
             for r in result["results"][:20]],
            ["side", "ticker", "qty", "price", "status", "order_id"],
        )
        send_auto_trade_filled(result["results"])

    _print_header("4) MockBroker 최종 스냅샷")
    snap = broker.snapshot()
    print(f"  현금: {snap['cash']:,.0f}원")
    print(f"  국내 보유: {len(snap['holdings_kr'])}")
    for t, h in snap["holdings_kr"].items():
        print(f"    {t}: {h['qty']}주 @ {h['avg_price']:,.0f}")
    print(f"  해외 보유: {len(snap['holdings_us'])}")
    for t, h in snap["holdings_us"].items():
        print(f"    {t}: {h['qty']}주 @ ${h['avg_price']:.2f}")
    print(f"  총 주문 수: {snap['order_count']}")

    print(f"\n[SIM] 완료. mock_orders.log → {os.path.join(DATA_DIR, 'mock_orders.log')}")
    print(f"[SIM] auto_trade_history.json → {os.path.join(DATA_DIR, 'auto_trade_history.json')}")


if __name__ == "__main__":
    main()
