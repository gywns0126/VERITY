"""코어 화이트리스트 = hard_floor 면제 경로가 실제로 작동하는지 (2026-08-24).

사고 = 에스텍(069510)이 일평균 거래대금 하한(1억원) 경계에 걸려 수집 유니버스에서 빠졌고,
재무·분기추이·내부자·포렌식·리포트 **9개 산출물 전부에서 누락**됐다(조인 15섹션).
🚨 발행↔수집 union 은 순환이라 둘 다에 없는 종목을 새로 못 들인다 — 코어가 유일한 진입로다.
"""
from api.analyzers.hard_floor import apply_hard_floor


def _passes(stock):
    """`passes` 는 `hard_floor_metadata` 안에 있다 — 최상위에서 찾으면 None 이 나와 조용히 통과한다."""
    return (apply_hard_floor(stock).get("hard_floor_metadata") or {}).get("passes")
from api.collectors.stock_data import ALL_STOCKS, KOSDAQ_MAJOR
from api.collectors.universe_builder import _load_core_pools


def test_estec_is_core():
    assert "069510.KQ" in KOSDAQ_MAJOR, "에스텍 코어 등재가 사라졌다 (PM 2026-08-24 승인분)"
    kr_core, _ = _load_core_pools()
    assert "069510" in kr_core, "코어 목록이 6자리 집합으로 전파되지 않았다"


def test_core_exempts_liquidity_floor():
    """에스텍의 실측 유동성(중앙값 0.45억)으로도 코어면 통과해야 한다."""
    thin = {
        "ticker": "069510", "name": "에스텍", "market": "KOSDAQ",
        "market_cap": 140_084_400_000,      # 1,400억 — Rule 1 은 원래 통과
        "trading_value": 45_000_000,        # 0.45억 — Rule 3 하한(1억) 미달
        "is_core": True,
    }
    assert _passes(thin) is True, "코어인데 유동성 하한에 걸렸다"


def test_non_core_thin_stock_still_blocked():
    """면제는 코어 한정 — 아니면 종전대로 막혀야 한다(하한 자체를 낮춘 게 아니다)."""
    thin = {
        "ticker": "999999", "name": "테스트", "market": "KOSDAQ",
        "market_cap": 140_084_400_000, "trading_value": 45_000_000, "is_core": False,
    }
    assert _passes(thin) is False, "하한이 통째로 풀렸다"


def test_core_count_is_46():
    """🚨 분모를 굳혀 둔다 — 코어가 조용히 늘거나 줄면 이 테스트가 신고한다."""
    assert len(ALL_STOCKS) == 46, f"코어 {len(ALL_STOCKS)}개 (기대 46 = KOSPI 30 + KOSDAQ 16)"
