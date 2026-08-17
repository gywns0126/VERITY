# -*- coding: utf-8 -*-
"""VAMS 노출 가드 None 입력 회귀 (2026-08-17).

사고: daily_analysis 가 5연속 실패했다.

    File "api/vams/engine.py", line 556, in _check_portfolio_exposure
      portfolio_beta_sum += h_beta * h_pct
    TypeError: unsupported operand type(s) for *: 'NoneType' and 'float'

원인은 `dict.get(k, default)` 를 값 검증으로 쓴 것이다. 그것은 **키 부재**만 막고
"키는 있는데 값이 None" 은 통과시킨다. cc18f344f(8/11)가 포트폴리오 가드 입력을
영속하려고 `"beta": stock.get("beta")` 를 저장했는데 추천 파이프라인에 beta 키가
없어 전 보유 종목이 `beta=None` 으로 적재됐고(실측 10/10), 다음 매수 판정에서 터졌다.

가드를 살리려던 커밋이 파이프라인을 죽인 형태다. 그리고 None→1.0 대체는 crash 는
막지만 베타 상한 가드를 **판정력 0 인 채로 통과**시키므로, 대체분을 신고하지 않으면
가드가 살아 있는 것처럼 보인다 ([[feedback_silent_total_failure_guard]]).
"""
import api.vams.engine as eng
from api.vams.engine import _check_portfolio_exposure, _num


def _pf(holdings):
    return {"vams": {"total_asset": 10_000_000, "cash": 3_000_000, "holdings": holdings}}


def test_num_folds_none_and_garbage():
    assert _num(None, 1.0) == 1.0
    assert _num("", 1.0) == 1.0
    assert _num("abc", 1.0) == 1.0
    assert _num(float("nan"), 1.0) == 1.0
    assert _num("3", 1.0) == 3.0
    assert _num(2.5, 1.0) == 2.5


def test_all_none_beta_does_not_crash():
    """사고 재현 — 전 보유 beta=None + 후보 beta=None."""
    pf = _pf([
        {"ticker": "035420", "current_price": 228000.0, "quantity": 2, "beta": None, "sector": None},
        {"ticker": "GOOGL", "current_price": 489230.57, "quantity": 1, "beta": None, "sector": None},
    ])
    res = _check_portfolio_exposure(pf, {"ticker": "DVN", "sector": None, "beta": None})
    assert res["blocked"] is False


def test_none_price_or_quantity_does_not_crash():
    """가격·수량도 같은 함정 — 키는 있고 값이 None."""
    pf = _pf([{"ticker": "X", "current_price": None, "quantity": None, "beta": None, "sector": None}])
    res = _check_portfolio_exposure(pf, {"ticker": "Y", "sector": None, "beta": None})
    assert res["blocked"] is False


def test_beta_gap_is_reported_not_silent(capsys):
    """결측을 1.0 으로 덮되 **조용히** 덮지 않는다 — 신고가 없으면 가드가 살아 보인다."""
    pf = _pf([
        {"ticker": "A", "current_price": 100.0, "quantity": 1, "beta": None, "sector": None},
        {"ticker": "B", "current_price": 100.0, "quantity": 1, "beta": 1.2, "sector": None},
    ])
    _check_portfolio_exposure(pf, {"ticker": "C", "sector": None, "beta": None})
    out = capsys.readouterr().out
    assert "베타 결측" in out and "1/2" in out


def test_real_beta_still_blocks_over_cap():
    """대체가 진짜 베타를 가리지 않는다 — 값이 있으면 상한이 그대로 작동해야 한다."""
    over = eng.VAMS_MAX_PORTFOLIO_BETA + 1.0
    pf = _pf([{"ticker": "A", "current_price": 1_000_000.0, "quantity": 5,
               "beta": over, "sector": "Tech"}])
    res = _check_portfolio_exposure(pf, {"ticker": "C", "sector": "Energy", "beta": over})
    assert res["blocked"] is True and "베타" in res["reason"]
