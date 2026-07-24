"""insider_trades_public_builder 단위 테스트 — 자본변동(비매매) 필터."""
from __future__ import annotations

from api.builders.insider_trades_public_builder import _is_corporate_action, _int


def _row(chg, after, rate_after, irds):
    return {
        "sp_stock_lmp_irds_cnt": chg, "sp_stock_lmp_cnt": after,
        "sp_stock_lmp_rate": rate_after, "sp_stock_lmp_irds_rate": irds,
    }


def _ca(it):
    return _is_corporate_action(it, _int(it["sp_stock_lmp_irds_cnt"]), _int(it["sp_stock_lmp_cnt"]))


class TestCorporateActionFilter:
    def test_capital_reduction_is_non_trade(self):
        # 국일제지 감자: 89.14% 보유자, 소유비율 증감 0.00%, -9억주 → 매매 아님
        assert _ca(_row(-904_500_000, 100_500_000, 89.14, 0.00)) is True

    def test_bonus_issue_is_non_trade(self):
        # 대주주 무상증자: 소유비율 불변(0.00%)인데 대량 증가
        assert _ca(_row(2_000_000, 4_000_000, 12.5, 0.00)) is True

    def test_first_acquisition_large_float_is_trade(self):
        # 삼성 임원 첫취득(chg==after)이지만 지분 ~0% → 매매(오분류 방지 핵심)
        assert _ca(_row(13_419, 13_419, 0.00, 0.00)) is False

    def test_small_trade_large_float_is_trade(self):
        assert _ca(_row(40_579, 91_258, 0.00, 0.00)) is False

    def test_major_shareholder_real_buy_is_trade(self):
        # 국민연금 실매수 — 소유비율이 변함(+0.50%) → 매매
        assert _ca(_row(500_000, 5_000_000, 8.22, 0.50)) is False

    def test_major_shareholder_small_trade_is_trade(self):
        # ≥1% 보유자의 소액매매 — 비율 변동(-0.01%) → 매매
        assert _ca(_row(-10_000, 4_000_000, 12.5, -0.01)) is False

    def test_missing_rate_fields_is_trade(self):
        # 비율 필드 부재 → 판정 불가 → 매매로(보수적: 실매매 배제 안 함)
        assert _ca(_row(-904_500_000, 100_500_000, None, None)) is False
