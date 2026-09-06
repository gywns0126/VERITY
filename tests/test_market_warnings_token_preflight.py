"""시장경보 수집의 공유 토큰 사전 확인 계약."""
from __future__ import annotations

from api.builders import market_warnings_public_builder as builder
from api.trading import kis_broker


def test_missing_shared_token_stops_before_ticker_loop(monkeypatch):
    calls = []

    class FakeBroker:
        def __init__(self, cache_only=False):
            assert cache_only is True

        def authenticate(self, force_refresh=False):
            calls.append(("authenticate", force_refresh))
            raise RuntimeError("shared token unavailable")

        def get_current_price(self, ticker):
            raise AssertionError("ticker loop must not start without a token")

    monkeypatch.setattr(kis_broker, "KISBroker", FakeBroker)
    monkeypatch.setattr(builder, "_kr_tickers", lambda: [{"ticker": "005930", "name": "삼성전자"}])

    assert builder.main() == 1
    assert calls == [("authenticate", False)]
