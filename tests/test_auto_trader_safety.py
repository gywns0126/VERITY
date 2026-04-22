"""AutoTrader 실자금 전 필수 안전 시나리오.

기존 test_auto_trader.py 는 기본 흐름(주문 계획·안전장치·실행) 커버.
이 파일은 "실전에서 실제로 발생해 계좌를 날릴 수 있는" 경로만 집중:
  1. 킬스위치 파일 레벨 통합 (파일 생성/삭제가 실제로 차단/해제하는가)
  2. 브로커 예외 raise → FAILED 기록 + 잔고 불변
  3. 브로커 success=False → FAILED 기록 + 잔고 불변
  4. 일일 한도에 오늘 누적 매수 반영 (하루 2회 실행 시 한도 초과 방지)
  5. 빈 orders 리스트 방어 (no-op 확인)
  6. history 파일 손상 → 빈 리스트 복구 + 사이클 진행
"""
from datetime import datetime, timedelta, timezone

import pytest

from api.trading.auto_trader import (
    TradeOrder,
    apply_safety_limits,
    execute,
    is_killswitch_active,
    load_history,
    save_history,
)
from api.trading.kis_broker import OrderResult, OrderSide
from api.trading.mock_kis_broker import MockKISBroker

KST = timezone(timedelta(hours=9))


def _trading_hour(now=None):
    n = now or datetime.now(KST)
    while n.weekday() >= 5:
        n -= timedelta(days=1)
    return n.replace(hour=11, minute=0, second=0, microsecond=0)


# ──────────────────────────────────────────────
# 1. 킬스위치 파일 레벨 통합
# ──────────────────────────────────────────────

def test_killswitch_file_creates_and_blocks(_isolate_data_dir):
    """파일 직접 생성 → is_killswitch_active True → apply_safety_limits 전체 차단."""
    ks_path = _isolate_data_dir / ".auto_trade_paused"
    ks_path.touch()

    assert is_killswitch_active() is True

    orders = [TradeOrder(side="BUY", ticker="005930", name="삼성", qty=1,
                         price=70000, market="KR")]
    passed, blocks = apply_safety_limits(orders, now=_trading_hour())
    assert passed == []
    assert all("킬스위치" in b["reason"] for b in blocks)


def test_killswitch_file_removal_restores_trading(_isolate_data_dir):
    """파일 삭제 → 차단 해제 → 다시 정상 통과."""
    ks_path = _isolate_data_dir / ".auto_trade_paused"
    ks_path.touch()
    assert is_killswitch_active() is True

    ks_path.unlink()
    assert is_killswitch_active() is False

    orders = [TradeOrder(side="BUY", ticker="005930", name="삼성", qty=1,
                         price=70000, market="KR")]
    passed, _ = apply_safety_limits(orders, now=_trading_hour())
    assert len(passed) == 1


# ──────────────────────────────────────────────
# 2. 브로커 예외 raise → FAILED 기록
# ──────────────────────────────────────────────

class _ExplodingBroker(MockKISBroker):
    """네트워크/API 장애 시뮬 — place_order 호출 즉시 예외."""
    def place_order(self, *args, **kwargs):
        raise ConnectionError("simulated network failure")


def test_broker_exception_records_failed_and_preserves_cash(_isolate_data_dir):
    """예외가 밖으로 새지 않고 FAILED status 로 기록. 다음 주문은 정상 시도."""
    broker = _ExplodingBroker(initial_cash=10_000_000,
                              price_map={"005930": 70000, "000660": 50000})

    orders = [
        TradeOrder(side="BUY", ticker="005930", name="삼성", qty=3,
                   price=70000, market="KR"),
        TradeOrder(side="BUY", ticker="000660", name="SK", qty=2,
                   price=50000, market="KR"),
    ]

    # execute 는 예외를 밖으로 올리면 안 됨
    results = execute(orders, broker, dry_run=False)

    assert len(results) == 2
    assert all(r["status"] == "FAILED" for r in results)
    assert all(r["success"] is False for r in results)
    assert "simulated" in results[0]["message"]
    # 잔고가 예외로 인해 불완전한 상태로 남지 않음
    assert broker.cash == 10_000_000
    # history 에도 FAILED 로 기록됨
    hist = load_history()
    assert len(hist) == 2
    assert all(h["status"] == "FAILED" for h in hist)


# ──────────────────────────────────────────────
# 3. 브로커 success=False → FAILED 기록
# ──────────────────────────────────────────────

def test_broker_insufficient_cash_fails_safely(_isolate_data_dir):
    """잔고 부족으로 브로커가 success=False 반환 → FAILED, 잔고 보존."""
    broker = MockKISBroker(initial_cash=50_000,  # 주문 총액 대비 터무니없이 부족
                           price_map={"005930": 70000})

    orders = [TradeOrder(side="BUY", ticker="005930", name="삼성", qty=3,
                         price=70000, market="KR")]

    results = execute(orders, broker, dry_run=False)

    assert results[0]["status"] == "FAILED"
    assert results[0]["success"] is False
    # 체결 안 됐으니 잔고 그대로
    assert broker.cash == 50_000
    assert "005930" not in broker.holdings_kr


def test_broker_oversell_fails_safely(_isolate_data_dir):
    """보유 수량 초과 매도 → success=False, 보유 수량 그대로."""
    from api.trading.mock_kis_broker import MockHolding
    broker = MockKISBroker(initial_cash=0, price_map={"005930": 70000})
    broker.holdings_kr["005930"] = MockHolding(
        ticker="005930", qty=5, avg_price=60000,
    )

    orders = [TradeOrder(side="SELL", ticker="005930", name="삼성", qty=10,
                         price=70000, market="KR")]
    results = execute(orders, broker, dry_run=False)

    assert results[0]["status"] == "FAILED"
    # 보유 그대로
    assert broker.holdings_kr["005930"].qty == 5


# ──────────────────────────────────────────────
# 4. 일일 한도에 오늘 누적 매수 반영
# ──────────────────────────────────────────────

def test_daily_limit_counts_todays_filled_history(_isolate_data_dir, monkeypatch):
    """어제·오늘 history 혼재 상태에서 오늘 매수만 한도에서 차감."""
    monkeypatch.setenv("AUTO_TRADE_MAX_DAILY_BUY_KRW", "1_000_000".replace("_", ""))

    today = datetime.now(KST).strftime("%Y-%m-%d")
    yesterday = (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")

    save_history([
        # 어제: 한도에 영향 주면 안 됨
        {"date": f"{yesterday}T10:00:00", "side": "BUY", "ticker": "000660",
         "status": "FILLED", "notional_krw": 900_000},
        # 오늘 FILLED 700k — 한도에서 차감
        {"date": f"{today}T10:00:00", "side": "BUY", "ticker": "051910",
         "status": "FILLED", "notional_krw": 700_000},
        # 오늘 DRY_RUN — 한도 계산에 포함되면 안 됨 (FILLED 만 집계)
        {"date": f"{today}T10:30:00", "side": "BUY", "ticker": "373220",
         "status": "DRY_RUN", "notional_krw": 500_000},
    ])

    # 350k 추가 주문 시도: 오늘 누적 700k + 350k = 1.05M > 1M → 차단
    orders = [TradeOrder(side="BUY", ticker="005930", name="삼성", qty=5,
                         price=70000, market="KR")]
    passed, blocks = apply_safety_limits(orders, now=_trading_hour())
    assert passed == []
    assert any("일일 매수 한도" in b["reason"] for b in blocks)

    # 200k 주문이면 700k + 200k = 900k < 1M → 통과
    orders_small = [TradeOrder(side="BUY", ticker="005930", name="삼성", qty=2,
                               price=100_000, market="KR")]
    passed_s, _ = apply_safety_limits(orders_small, now=_trading_hour())
    assert len(passed_s) == 1


# ──────────────────────────────────────────────
# 5. 빈 orders 방어
# ──────────────────────────────────────────────

def test_empty_orders_safe_noop(_isolate_data_dir):
    """apply_safety_limits + execute 모두 빈 입력에 no-op."""
    passed, blocks = apply_safety_limits([], now=_trading_hour())
    assert passed == [] and blocks == []

    broker = MockKISBroker(initial_cash=10_000_000, price_map={})
    results = execute([], broker, dry_run=False)
    assert results == []
    # history 도 변화 없음
    assert load_history() == []


# ──────────────────────────────────────────────
# 6. history 파일 손상 → 빈 리스트 복구
# ──────────────────────────────────────────────

def test_corrupt_history_file_recovers_to_empty(_isolate_data_dir):
    """깨진 JSON → load_history() 가 예외 대신 빈 리스트 반환. 사이클 진행 가능."""
    hist_path = _isolate_data_dir / "auto_trade_history.json"
    hist_path.write_text("{{{ corrupt json here", encoding="utf-8")

    # load_history 가 빈 리스트로 안전 복구
    assert load_history() == []

    # execute 는 이 상태에서도 정상 동작 (새 레코드 덮어쓰기)
    broker = MockKISBroker(initial_cash=10_000_000, price_map={"005930": 70000})
    orders = [TradeOrder(side="BUY", ticker="005930", name="삼성", qty=1,
                         price=70000, market="KR")]
    results = execute(orders, broker, dry_run=False)
    assert results[0]["status"] == "FILLED"

    # history 는 1건 (깨진 상태 무시하고 덮어씀)
    assert len(load_history()) == 1
