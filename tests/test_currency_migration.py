# -*- coding: utf-8 -*-
"""보유 통화 정규화 마이그레이션 + 1R 영속화 (2026-08-06).

사고: 8/5 에 넣은 `_fx_norm` 이 **신규 매수에만** 적용돼 기존 보유의 exit_targets 가
원통화(USD)로 남았다. 스케일 가드가 fail-closed 로 작동해 미장 보유 3건은 부분익절
평가가 통째로 건너뛰어졌다. `measurement_audit.price_scale` 이 매일 신고했으나 로그에만
찍혀 아무도 읽지 않았다.

같은 날 발견된 두 번째 결함: `risk_per_share`(1R)가 `stop_loss` dict 에 담기지 않아
보유의 해당 필드가 **항상 None** 이었다 — R배수 체계 전체의 단위인데 저장이 안 됐다.

계약: ① 환율을 추정하지 않는다(buy_price/buy_price_original = 정확값) ② 멱등
③ 대역 밖·산출 불가는 변환하지 않고 보고 ④ 무차원 필드(%·R배수) 불변
⑤ 1R 이 실제로 저장되고 US 는 KRW 로 정규화된다.
"""
import pytest

from api.trade_planner import build_trade_plan_v0
from api.vams.currency_migration import migrate_holdings


def _us(fx=1400.0, t1=100.0, t2=110.0, **kw):
    h = {"ticker": "AAPL", "buy_price": 200.0 * fx, "buy_price_original": 200.0,
         "exit_targets": {"target_1": {"price": t1, "r_multiple": 1, "exit_pct": 50},
                          "target_2": {"price": t2, "r_multiple": 2, "exit_pct": 30},
                          "target_3": {"method": "trailing_stop", "trail_pct": 5}}}
    h.update(kw)
    return h


def _kr(**kw):
    h = {"ticker": "005930", "buy_price": 70000.0, "buy_price_original": 70000.0,
         "exit_targets": {"target_1": {"price": 75000, "r_multiple": 1}}}
    h.update(kw)
    return h


# ── 환율은 추정하지 않는다 ───────────────────────────────────────────

def test_fx_derived_exactly_not_guessed():
    """진입 환율 = buy_price / buy_price_original. 외부 환율표를 쓰지 않는다."""
    h = _us(fx=1442.07)
    rep = migrate_holdings([h])
    assert rep["converted"][0]["fx"] == 1442.07
    assert h["entry_fx_rate"] == 1442.07
    assert h["entry_currency"] == "USD"


def test_price_fields_converted():
    h = _us(fx=1400.0, t1=100.0, t2=110.0)
    migrate_holdings([h])
    assert h["exit_targets"]["target_1"]["price"] == 140000.0
    assert h["exit_targets"]["target_2"]["price"] == 154000.0


def test_dimensionless_fields_untouched():
    """% · R배수 · 수량은 통화 무관 — 건드리면 안 된다."""
    h = _us(fx=1400.0)
    migrate_holdings([h])
    t = h["exit_targets"]
    assert t["target_1"]["r_multiple"] == 1 and t["target_1"]["exit_pct"] == 50
    assert t["target_3"]["trail_pct"] == 5


def test_stop_price_and_risk_per_share_converted():
    h = _us(fx=1400.0, stop_price=180.0, risk_per_share=20.0)
    migrate_holdings([h])
    assert h["stop_price"] == 252000.0
    assert h["risk_per_share"] == 28000.0


# ── 멱등 ────────────────────────────────────────────────────────────

def test_idempotent_no_double_conversion():
    """🚨 두 번 돌려도 이중 변환되지 않는다 — 실계좌 장부라 되돌릴 수 없다."""
    h = _us(fx=1400.0, t1=100.0)
    migrate_holdings([h])
    once = h["exit_targets"]["target_1"]["price"]
    rep2 = migrate_holdings([h])
    assert h["exit_targets"]["target_1"]["price"] == once
    assert len(rep2["converted"]) == 0 and len(rep2["skipped"]) == 1


def test_already_marked_holding_skipped():
    h = _us(fx=1400.0, entry_currency="USD", entry_fx_rate=1400.0)
    rep = migrate_holdings([h])
    assert rep["skipped"] and not rep["converted"]


# ── KR 은 표식만 ────────────────────────────────────────────────────

def test_kr_marked_without_price_change():
    h = _kr()
    migrate_holdings([h])
    assert h["entry_currency"] == "KRW" and h["entry_fx_rate"] is None
    assert h["exit_targets"]["target_1"]["price"] == 75000     # 불변


def test_non_kr_ticker_with_fx_one_marked_krw():
    """티커가 6자리가 아니어도 내재 환율이 1.0 이면 이미 KRW 표기다."""
    h = _us(fx=1.0)
    migrate_holdings([h])
    assert h["entry_currency"] == "KRW"


# ── 추측 금지 ───────────────────────────────────────────────────────

def test_implausible_fx_not_converted():
    """대역 밖 환율은 변환하지 않고 보고만 — 잘못된 환율로 장부를 망가뜨리지 않는다."""
    h = _us(fx=50000.0)
    rep = migrate_holdings([h])
    assert not rep["converted"] and rep["unresolved"]
    assert h["exit_targets"]["target_1"]["price"] == 100.0     # 원본 보존
    assert "entry_currency" not in h                            # 표식도 남기지 않음


def test_missing_original_not_converted():
    h = {"ticker": "AAPL", "buy_price": 280000.0,
         "exit_targets": {"target_1": {"price": 100.0}}}
    rep = migrate_holdings([h])
    assert not rep["converted"] and rep["unresolved"]
    assert h["exit_targets"]["target_1"]["price"] == 100.0


def test_zero_original_not_converted():
    h = _us(fx=1400.0, buy_price_original=0)
    rep = migrate_holdings([h])
    assert rep["unresolved"] and not rep["converted"]


# ── 마이그레이션 후 스케일 가드를 통과한다 ───────────────────────────

def test_scale_ratio_falls_below_guard():
    """가드 임계는 10배 — 변환 전 1400배가 변환 후 정상 범위로 내려온다."""
    h = _us(fx=1400.0, t1=100.0)
    before = h["buy_price"] / h["exit_targets"]["target_1"]["price"]
    migrate_holdings([h])
    after = h["buy_price"] / h["exit_targets"]["target_1"]["price"]
    assert before > 10 and after < 10


# ── 1R 영속화 (같은 날 발견한 죽은 필드) ─────────────────────────────

def _stock(price=10_000, atr=300.0):
    return {"ticker": "000001", "name": "t", "price": price,
            "technical": {"atr_14d": atr, "rsi": 45.0, "bb_lower": 9_500, "ma20": 10_200,
                          "bb_upper": 10_800, "price": price}}


@pytest.mark.parametrize("atr", [300.0, None])
def test_risk_per_share_emitted_in_stop_loss(atr):
    """🚨 이전엔 지역 변수로만 존재해 보유의 risk_per_share 가 항상 None 이었다."""
    p = build_trade_plan_v0(_stock(atr=atr), {"recommendation": "BUY"})
    sl = p["stop_loss"]
    assert "risk_per_share" in sl
    assert sl["risk_per_share"] > 0


def test_risk_per_share_equals_entry_minus_stop():
    """1R = 진입가 − 손절가. 정의가 어긋나면 R배수 익절 전체가 틀어진다."""
    p = build_trade_plan_v0(_stock(price=10_000, atr=300.0), {"recommendation": "BUY"})
    sl = p["stop_loss"]
    assert abs(sl["risk_per_share"] - (10_000 - sl["price"])) < 0.01


def test_targets_derive_from_persisted_1r():
    p = build_trade_plan_v0(_stock(price=10_000, atr=300.0), {"recommendation": "BUY"})
    r = p["stop_loss"]["risk_per_share"]
    t1 = p["exit_targets"]["target_1"]["price"]
    assert abs((t1 - 10_000) - r * p["exit_targets"]["target_1"]["r_multiple"]) <= 1


def test_engine_fx_norm_covers_risk_per_share():
    """engine 의 정규화 키 집합과 마이그레이션 키 집합이 어긋나면 안 된다."""
    import inspect

    from api.vams import engine as EN
    from api.vams.currency_migration import _PRICE_KEYS
    src = inspect.getsource(EN.execute_buy)
    for k in _PRICE_KEYS:
        assert f'"{k}"' in src, f"engine._fx_norm 에 {k} 누락 — 진입/마이그레이션 규칙 불일치"


# ── 오염 시기 skip 기록 정리 ─────────────────────────────────────────

def test_contaminated_skip_records_purged():
    """통화 혼재 시기의 skipped_too_small 은 무효한 비교에서 나왔으므로 폐기한다."""
    h = _us(fx=1400.0, exit_history=[
        {"target_id": "target_1", "status": "skipped_too_small"},
        {"target_id": "target_2", "status": "skipped_too_small"}])
    rep = migrate_holdings([h])
    assert h["exit_history"] == []
    assert rep["converted"][0]["purged_skip_records"] == 2


def test_executed_records_never_purged():
    """🚨 executed = 실제 체결. 지우면 같은 물량을 두 번 파는 길이 열린다."""
    h = _us(fx=1400.0, exit_history=[
        {"target_id": "target_1", "status": "executed", "sold_qty": 2},
        {"target_id": "target_2", "status": "skipped_too_small"}])
    migrate_holdings([h])
    assert len(h["exit_history"]) == 1
    assert h["exit_history"][0]["status"] == "executed"


def test_kr_skip_records_kept():
    """KR 은 통화 혼재가 없었으므로 그 판단은 유효하다 — 건드리지 않는다."""
    h = _kr(exit_history=[{"target_id": "target_1", "status": "skipped_too_small"}])
    migrate_holdings([h])
    assert len(h["exit_history"]) == 1


# ── skip 이 영구 차단이 아니다 ───────────────────────────────────────

def test_skipped_does_not_block_reevaluation():
    """'지금 수량이 안 나눠짐'은 일시적 상태다 — 영구 차단이면 이후 어떤 가격에도 익절 0."""
    import inspect

    from api.vams import engine as EN
    src = inspect.getsource(EN.check_partial_exit)
    assert "skipped_target_ids" not in src
    assert "executed_target_ids" in src


def test_skip_record_written_once_only():
    """재평가를 허용하되 exit_history 가 매 run 증식하지 않는다."""
    import inspect

    from api.vams import engine as EN
    src = inspect.getsource(EN.execute_partial_sell)
    assert "skipped_too_small" in src
    # 중복 기록 방지 가드가 있어야 한다
    assert "any(" in src and "target_id" in src
