"""네이버 해외증시 코드 수집 대상 계약."""
from __future__ import annotations

import json

from api.collectors import us_naver_code as collector


def test_us_tickers_excludes_synthetic_indices_and_domestic_etfs(tmp_path, monkeypatch):
    path = tmp_path / "universe_search.json"
    path.write_text(json.dumps({
        "stocks": [
            {"ticker": "AAPL", "market": "US"},
            {"ticker": "BRK-B", "market": "US"},
            {"ticker": "VOO", "market": "ETF"},
            {"ticker": "069500", "market": "ETF"},
            {"ticker": "IDX_IT 서비스", "market": "지수", "type": "index"},
            {"ticker": "RATES_US", "market": "채권", "type": "rates"},
            {"ticker": "AAPL", "market": "US"},
        ]
    }), encoding="utf-8")
    monkeypatch.setattr(collector, "UNIVERSE_PATH", str(path))

    assert collector._us_tickers() == ["AAPL", "BRK-B", "VOO"]


def test_probe_rejects_invalid_path_without_network(monkeypatch):
    called = False

    def fake_open(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("network must not be reached")

    monkeypatch.setattr(collector.urllib.request, "urlopen", fake_open)
    assert collector._NAVER_TICKER_RE.fullmatch("IDX_IT 서비스") is None
    assert called is False
