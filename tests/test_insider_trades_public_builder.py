"""insider_trades_public_builder 단위 테스트 — 자본변동(비매매) 필터."""
from __future__ import annotations

import json
from datetime import datetime

import api.builders.insider_trades_public_builder as builder
from api.builders.insider_trades_public_builder import _aggregate, _is_corporate_action, _int


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


class TestAggregateWindow:
    """🚨 2026-08-20 — elestock 는 bgn_de/end_de 를 무시하고 자체 약 2년 롤링 창을 준다(실측).

    파라미터 무시 = 000660 3회 대조(없음 / 20260701~20260820 / 20260819 단일일자) 전부 559건 동일.
    '전 기간'이 아니라 약 2년인 근거 = 5종목 최古 rcept_dt 가 전부 today-730d 직후
    (005930 2024-08-26 · 005380 2024-08-22 · 000660 2024-09-02).
    🚨 그래서 API 창 집계는 오래된 행이 빠지며 흔들린다 — 같은 날 08:15 559건 → 18:11 558건인데
    *_365d 는 두 run 모두 59,122/315건으로 동일했다. 창은 우리가 rcept_dt 로 잡아야 하고,
    _meta.window_days=365 는 그 전까지 거짓 신고였다. 이 클래스가 그 계약을 고정한다.
    """

    @staticmethod
    def _r(date, chg, after=10_000, rate_after=0.0, irds=0.0, rc="1"):
        return {
            "rcept_dt": date, "rcept_no": rc, "repror": "홍길동",
            "isu_exctv_ofcps": "담당", "isu_exctv_rgist_at": "비등기임원",
            "sp_stock_lmp_irds_cnt": chg, "sp_stock_lmp_cnt": after,
            "sp_stock_lmp_rate": rate_after, "sp_stock_lmp_irds_rate": irds,
        }

    def test_lifetime_and_365d_diverge(self):
        # 하이닉스형 = 창 밖 대량 + 창 안 소량. 두 집계가 갈려야 창 필터가 실제로 작동한 것.
        rows = [
            self._r("2024-09-02", 500_000),   # 창 밖
            self._r("2025-02-04", -100_000),  # 창 밖
            self._r("2026-07-31", 3_620),     # 창 안
            self._r("2026-07-01", -1_500),    # 창 안
        ]
        trades, agg = _aggregate(rows, "2025-08-20")
        assert agg["net_change"] == 402_120        # 전 기간
        assert agg["buy_n"] == 2 and agg["sell_n"] == 2
        assert agg["total"] == 4
        assert agg["net_change_365d"] == 2_120     # 최근 365일만
        assert agg["buy_n_365d"] == 1 and agg["sell_n_365d"] == 1
        assert agg["total_365d"] == 2

    def test_trades_sorted_newest_first(self):
        rows = [self._r("2025-01-07", 10), self._r("2026-07-31", 20), self._r("2026-01-07", 30)]
        trades, _ = _aggregate(rows, "2025-08-20")
        assert [t["date"] for t in trades] == ["2026-07-31", "2026-01-07", "2025-01-07"]

    def test_corporate_action_excluded_from_both_nets_but_counted_in_total(self):
        # 감자(비매매)는 전 기간·365일 net/건수 모두에서 빠지고 total 에만 남는다(기존 정의 유지).
        rows = [
            self._r("2026-07-31", -904_500_000, after=100_500_000, rate_after=89.14, irds=0.00),
            self._r("2026-07-01", 1_000),
        ]
        _, agg = _aggregate(rows, "2025-08-20")
        assert agg["net_change"] == 1_000 and agg["net_change_365d"] == 1_000
        assert agg["sell_n"] == 0 and agg["sell_n_365d"] == 0
        assert agg["total"] == 2 and agg["total_365d"] == 2

    def test_empty_rcept_dt_is_out_of_window(self):
        # 날짜 부재 = 창 판정 불가 → 창 집계에서 제외(전 기간에는 남긴다)
        _, agg = _aggregate([self._r("", 777)], "2025-08-20")
        assert agg["net_change"] == 777
        assert agg["net_change_365d"] == 0 and agg["total_365d"] == 0

    def test_cutoff_is_inclusive(self):
        _, agg = _aggregate([self._r("2025-08-20", 5)], "2025-08-20")
        assert agg["net_change_365d"] == 5


def test_half_day_rotation_uses_distinct_batches(tmp_path, monkeypatch):
    universe = {
        "stocks": [{"ticker": f"{i:06d}", "name": str(i)} for i in range(1, 31)]
    }
    recs = [{"ticker": "000001", "name": "priority"}]
    uni_path = tmp_path / "stock_report_public.json"
    rec_path = tmp_path / "recommendations.json"
    uni_path.write_text(json.dumps(universe), encoding="utf-8")
    rec_path.write_text(json.dumps(recs), encoding="utf-8")
    monkeypatch.setattr(builder, "UNIVERSE_PATH", str(uni_path))
    monkeypatch.setattr(builder, "REC_PATH", str(rec_path))
    monkeypatch.setattr(builder, "MAX_CALLS", 6)

    monkeypatch.setattr(builder, "_now_kst", lambda: datetime(2026, 9, 2, 6, 30))
    morning = [x["ticker"] for x in builder._ordered_universe()[:6]]
    monkeypatch.setattr(builder, "_now_kst", lambda: datetime(2026, 9, 2, 16, 50))
    afternoon = [x["ticker"] for x in builder._ordered_universe()[:6]]

    assert morning[0] == afternoon[0] == "000001"
    assert set(morning[1:]).isdisjoint(afternoon[1:])


def test_workflow_caps_insider_runtime_and_calls():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    src = (root / ".github" / "workflows" / "daily_analysis_full.yml").read_text(encoding="utf-8")
    block = src.split("- name: 공개 내부자거래 빌드", 1)[1].split("- name:", 1)[0]
    assert "INSIDER_MAX_SECONDS: '600'" in block
    assert "INSIDER_MAX_CALLS: '300'" in block
