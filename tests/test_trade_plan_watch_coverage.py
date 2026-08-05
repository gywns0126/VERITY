# -*- coding: utf-8 -*-
"""매매 계획 커버리지 — WATCH 매수분에도 손절·익절 생성 (2026-08-05).

사전등록 = docs/PREREG_EXECUTION_PLAN_COVERAGE_2026_08_05.md
  PM 승인 "승인은 네 추천대로" — 안 (가) 단독 적용 확정.

사고: VAMS 는 WATCH 종목도 매수하는데 planner 는 BUY 에만 계획을 만들었다. BUY 가 하루
0~3건뿐이라 매수 종목 대다수가 손절·익절 없이 편입됐고, check_stop_loss 가 프로필 고정
−5% 로만 판정했다. 실측 MAE 평균 −9.6% 대비 −5% 는 노이즈 안이라 청산 12건이 전부 손절
(승률 20%·손익비 0.85).

계약: ① BUY·WATCH 는 **동일 산식**으로 계획 생성(신설 0) ② 진입 '활성' 판정은 BUY 전용
(계획 보유 ≠ 지금 매수) ③ 비중 한도는 등급별 기존값 유지 ④ CAUTION/AVOID 는 계획 없음
⑤ 임계(ATR 배수·R 배수) 무변경 — 조정은 재등록 대상(§3 동결).
"""
import pytest

from api.trade_planner import build_trade_plan_v0


def _stock(price=10_000, atr=300.0, rsi=45.0, bb_lower=9_500, ma20=10_200,
           bb_upper=10_800):
    # bb_upper 필수 — 없으면 planner 가 _skeleton 으로 조기 반환한다(가드 계약)
    return {
        "ticker": "000001", "name": "테스트", "price": price,
        "technical": {"atr_14d": atr, "rsi": rsi, "bb_lower": bb_lower, "ma20": ma20,
                      "bb_upper": bb_upper, "price": price},
    }


def _plan(rec, **kw):
    return build_trade_plan_v0(_stock(**kw), {"recommendation": rec})


@pytest.mark.parametrize("rec", ["BUY", "WATCH"])
def test_plan_generated_for_buy_and_watch(rec):
    """핵심 계약 — WATCH 도 계획을 갖는다(사슬 1·2단 해소)."""
    p = _plan(rec)
    assert p["stop_loss"] is not None
    assert p["exit_targets"] is not None
    assert p["entry_zone"] is not None


@pytest.mark.parametrize("rec", ["CAUTION", "AVOID"])
def test_no_plan_for_caution_avoid(rec):
    """매수 대상이 아닌 등급은 계획 없음 — 기존 동작 유지."""
    p = _plan(rec)
    assert p["stop_loss"] is None and p["exit_targets"] is None


def test_buy_and_watch_share_identical_formula():
    """산식 신설 0 — 같은 입력이면 손절·익절 값이 완전히 같아야 한다."""
    b, w = _plan("BUY"), _plan("WATCH")
    assert b["stop_loss"]["price"] == w["stop_loss"]["price"]
    assert b["stop_loss"]["stop_loss_pct"] == w["stop_loss"]["stop_loss_pct"]
    assert b["exit_targets"]["target_1"]["price"] == w["exit_targets"]["target_1"]["price"]
    assert b["exit_targets"]["target_2"]["price"] == w["exit_targets"]["target_2"]["price"]


def test_entry_active_stays_buy_only():
    """계획 보유 ≠ 지금 매수. 진입 활성 판정은 BUY 전용(등록 §1)."""
    good = dict(price=10_000, rsi=40.0, bb_lower=9_500, ma20=10_200)  # 진입 조건 충족
    assert _plan("BUY", **good)["entry_zone"]["active"] is True
    assert _plan("WATCH", **good)["entry_zone"]["active"] is False


def test_position_range_unchanged_per_grade():
    """비중 한도는 등급별 기존값 그대로 — 본 등록은 계획 유무만 다룬다."""
    assert _plan("BUY")["position_pct_range"]["max"] == 15
    assert _plan("WATCH")["position_pct_range"]["max"] == 5


def test_atr_dynamic_used_when_atr_present():
    p = _plan("WATCH", price=10_000, atr=300.0)
    sl = p["stop_loss"]
    assert sl["method"] == "atr_dynamic"
    assert sl["atr_value"] == 300.0
    # 손절 거리 = ATR × 배수 (임계 무변경 — 값 자체는 config 소유)
    assert sl["price"] < 10_000


def test_fallback_when_atr_missing():
    """ATR 부재 시 고정 fallback — 기존 계약 유지(WATCH 도 동일)."""
    p = _plan("WATCH", atr=None)
    assert p["stop_loss"]["method"] == "fixed_fallback"


def test_r_multiple_targets_derive_from_stop_distance():
    """익절 = 1R·2R (R = 진입가 − 손절가). 손절이 생겨야 익절이 성립한다."""
    p = _plan("WATCH", price=10_000, atr=300.0)
    entry, stop = 10_000, p["stop_loss"]["price"]
    r = entry - stop
    assert r > 0
    t1 = p["exit_targets"]["target_1"]["price"]
    assert t1 > entry
    assert abs((t1 - entry) - r * p["exit_targets"]["target_1"]["r_multiple"]) <= 1


def test_missing_indicators_return_skeleton():
    """BB/MA 결손 = 계획 산출 불가 → skeleton. WATCH 확장이 이 가드를 뚫지 않는다."""
    bad = {"ticker": "X", "price": 10_000, "technical": {"atr_14d": 300.0}}
    p = build_trade_plan_v0(bad, {"recommendation": "WATCH"})
    assert p["stop_loss"] is None
