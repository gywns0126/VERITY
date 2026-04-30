"""Sprint 11 결함 7 — 오늘의 액션 3개 backend 검증."""
from __future__ import annotations

from api.intelligence.daily_actions import compute_daily_actions


def _rec(ticker, grade=None, brain_score=50, name=None):
    return {
        "ticker": ticker,
        "name": name or ticker,
        "price": 10000,
        "verity_brain": {
            "grade": grade,
            "brain_score": brain_score,
        },
    }


def _holding(ticker, return_pct=0.0):
    return {
        "ticker": ticker,
        "name": ticker,
        "buy_price": 10000,
        "current_price": 10000,
        "quantity": 100,
        "return_pct": return_pct,
        "buy_date": "2026-04-25",
    }


class TestBuyAction:
    def test_picks_highest_brain_score_buy(self):
        portfolio = {
            "recommendations": [
                _rec("A", "BUY", 65),
                _rec("B", "STRONG_BUY", 78),
                _rec("C", "BUY", 70),
            ],
            "vams": {"holdings": []},
        }
        a = compute_daily_actions(portfolio)
        assert a["buy"]["ticker"] == "B"  # 78 점, STRONG_BUY
        assert a["buy"]["action"] == "buy"

    def test_excludes_already_held(self):
        portfolio = {
            "recommendations": [
                _rec("HELD", "STRONG_BUY", 90),  # 보유 중
                _rec("FREE", "BUY", 70),
            ],
            "vams": {"holdings": [_holding("HELD")]},
        }
        a = compute_daily_actions(portfolio)
        assert a["buy"]["ticker"] == "FREE"  # HELD 제외

    def test_no_buy_when_no_buy_grade(self):
        portfolio = {
            "recommendations": [
                _rec("A", "WATCH", 60),
                _rec("B", "HOLD", 55),
            ],
            "vams": {"holdings": []},
        }
        a = compute_daily_actions(portfolio)
        assert a["buy"] is None


class TestSellAction:
    def test_picks_worst_holding_when_below_threshold(self):
        portfolio = {
            "recommendations": [],
            "vams": {
                "holdings": [
                    _holding("A", -5.0),  # 임계 -3% 초과
                    _holding("B", 1.0),
                    _holding("C", -2.0),  # 임계 미달
                ],
            },
        }
        a = compute_daily_actions(portfolio)
        assert a["sell"]["ticker"] == "A"
        assert "손실" in a["sell"]["reason"]

    def test_no_sell_when_all_above_threshold(self):
        """모든 holdings 가 -3% 이내 → sell 액션 없음."""
        portfolio = {
            "recommendations": [],
            "vams": {
                "holdings": [
                    _holding("A", -2.5),
                    _holding("B", 1.0),
                    _holding("C", -1.0),
                ],
            },
        }
        a = compute_daily_actions(portfolio)
        assert a["sell"] is None

    def test_no_sell_when_no_holdings(self):
        portfolio = {"recommendations": [], "vams": {"holdings": []}}
        a = compute_daily_actions(portfolio)
        assert a["sell"] is None


class TestWatchAction:
    def test_picks_highest_in_watch_range(self):
        portfolio = {
            "recommendations": [
                _rec("A", "WATCH", 58),
                _rec("B", "WATCH", 67),  # 최고 (55-69 영역)
                _rec("C", "WATCH", 70),  # 70+ 는 BUY 영역이라 watch 제외
                _rec("D", "WATCH", 45),  # 55 미만 제외
            ],
            "vams": {"holdings": []},
        }
        a = compute_daily_actions(portfolio)
        assert a["watch"]["ticker"] == "B"

    def test_excludes_buy_grade(self):
        """BUY/STRONG_BUY 등급은 buy 영역이지 watch 아님."""
        portfolio = {
            "recommendations": [
                _rec("A", "BUY", 65),  # BUY 등급이라 watch 제외
                _rec("B", "WATCH", 60),
            ],
            "vams": {"holdings": []},
        }
        a = compute_daily_actions(portfolio)
        assert a["watch"]["ticker"] == "B"

    def test_excludes_held(self):
        portfolio = {
            "recommendations": [
                _rec("HELD", "WATCH", 65),
                _rec("FREE", "WATCH", 60),
            ],
            "vams": {"holdings": [_holding("HELD")]},
        }
        a = compute_daily_actions(portfolio)
        assert a["watch"]["ticker"] == "FREE"


class TestEdgeCases:
    def test_no_portfolio(self):
        a = compute_daily_actions(None)
        assert a["buy"] is None and a["sell"] is None and a["watch"] is None

    def test_empty_portfolio(self):
        a = compute_daily_actions({})
        assert a["buy"] is None and a["sell"] is None and a["watch"] is None

    def test_no_recommendations(self):
        a = compute_daily_actions({"recommendations": [], "vams": {"holdings": []}})
        assert a["buy"] is None
        assert a["watch"] is None

    def test_meta_attached(self):
        portfolio = {
            "recommendations": [_rec("A", "BUY", 70)],
            "vams": {"holdings": []},
        }
        a = compute_daily_actions(portfolio)
        assert "_meta" in a
        assert a["_meta"]["buy_candidates_count"] == 1
        assert a["_meta"]["sell_threshold_pct"] == -3.0
