import importlib.util
from pathlib import Path
import sys
import types


_PATH = Path(__file__).parents[1] / "vercel-api" / "api" / "portfolio_experiments.py"
sys.path.insert(0, str(_PATH.parent))
if "supabase_client" not in sys.modules:
    sys.modules["supabase_client"] = types.ModuleType("supabase_client")
_SPEC = importlib.util.spec_from_file_location("portfolio_experiments", _PATH)
pe = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(pe)


def test_clean_assets_requires_exact_total():
    assert pe._clean_assets([
        {"ticker": "005930", "name": "삼성전자", "market": "KR", "weight": 60},
        {"ticker": "SPY", "name": "S&P 500 ETF", "market": "US", "weight": 40},
    ]) == [
        {"ticker": "005930", "name": "삼성전자", "market": "KR", "weight": 60.0},
        {"ticker": "SPY", "name": "S&P 500 ETF", "market": "US", "weight": 40.0},
    ]
    assert pe._clean_assets([{"ticker": "005930", "weight": 90}]) is None


def test_public_item_sanitizes_assets_by_privacy():
    base = {
        "id": "e1", "user_id": "u1", "title": "실험", "start_date": "2020-01-02",
        "contribution": 300000, "frequency": "monthly", "rebalance": "yearly",
        "dividend_reinvest": True, "created_at": "2026-08-29T00:00:00Z",
        "assets": [{"ticker": "005930", "name": "삼성전자", "market": "KR", "weight": 100}],
    }
    profiles = {"u1": {"nickname": "학습자", "avatar": ""}}
    summary = pe._public_item({**base, "privacy": "summary"}, profiles)
    masked = pe._public_item({**base, "privacy": "masked"}, profiles)
    full = pe._public_item({**base, "privacy": "full"}, profiles)
    assert summary["assets"] == []
    assert masked["assets"] == [{"market": "KR", "weight": 100}]
    assert full["assets"][0]["ticker"] == "005930"
    assert full["result_status"] == "engine_not_connected"


def test_clean_assets_preserves_commodity_identity_without_quote_data():
    rows = pe._clean_assets([{
        "ticker": "CMD_GOLD",
        "name": "금 선물 연속물",
        "market": "원자재",
        "type": "commodity",
        "instrument_type": "continuous_future",
        "underlying_symbol": "GC=F",
        "weight": 100,
        "current_price": 999999,
    }])
    assert rows == [{
        "ticker": "CMD_GOLD",
        "name": "금 선물 연속물",
        "market": "원자재",
        "type": "commodity",
        "instrument_type": "continuous_future",
        "underlying_symbol": "GC=F",
        "weight": 100.0,
    }]
