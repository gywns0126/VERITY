"""Server-side live-order policy contract."""

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]


def _load_order(monkeypatch, mode: str = "advised"):
    monkeypatch.setenv("ORDER_POLICY_MODE", mode)
    monkeypatch.delenv("ORDER_ALLOW_MEMORY_FALLBACK", raising=False)
    api_pkg = types.ModuleType("api")
    api_pkg.__path__ = []
    sb = types.ModuleType("api.supabase_client")
    sb.SUPABASE_URL = "https://example.supabase.co"
    sb.SUPABASE_ANON_KEY = "anon"
    sb.select = lambda *args, **kwargs: []
    sb.verify_jwt = lambda jwt: None
    api_pkg.supabase_client = sb
    monkeypatch.setitem(sys.modules, "api", api_pkg)
    monkeypatch.setitem(sys.modules, "api.supabase_client", sb)
    spec = importlib.util.spec_from_file_location(
        "order_policy_under_test",
        ROOT / "vercel-api" / "api" / "order.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _order(side: str = "BUY", qty: int = 1, price: int = 70_000) -> dict:
    return {
        "ticker": "005930",
        "side": side,
        "qty": qty,
        "price": price,
        "order_type": "00",
        "market": "kr",
    }


def _balance(cash: int = 800_000) -> dict:
    return {
        "output1": [
            {"pdno": "005930", "hldg_qty": "1", "prpr": "70000", "evlu_amt": "70000"},
            {"pdno": "000660", "hldg_qty": "1", "prpr": "130000", "evlu_amt": "130000"},
        ],
        "output2": [{"dnca_tot_amt": str(cash), "tot_evlu_amt": "1000000"}],
    }


def _quote(price: int = 70_000) -> dict:
    return {"price": price, "upper_limit": 91_000, "lower_limit": 49_000}


def test_advised_policy_accepts_live_bounded_order(monkeypatch) -> None:
    mod = _load_order(monkeypatch)
    ok, reason, snapshot = mod._evaluate_order_policy(
        _order(), {"seed_krw": 1_000_000}, _balance(), _quote(), market_open=True
    )
    assert ok, reason
    assert snapshot["mode"] == "advised"
    assert snapshot["capital_profile"] == "micro"
    assert snapshot["post_name_pct"] == 0.14
    assert snapshot["post_total_pct"] == 0.27
    assert snapshot["executor"]["is_executor"] is True


def test_policy_rejects_price_band_cash_and_exposure(monkeypatch) -> None:
    mod = _load_order(monkeypatch)
    ok, reason, _ = mod._evaluate_order_policy(
        _order(price=80_000), {"seed_krw": 1_000_000}, _balance(), _quote(), market_open=True
    )
    assert not ok and "price" in reason

    ok, reason, _ = mod._evaluate_order_policy(
        _order(qty=2), {"seed_krw": 1_000_000}, _balance(cash=100_000), _quote(), market_open=True
    )
    assert not ok and reason == "insufficient cash"

    ok, reason, _ = mod._evaluate_order_policy(
        _order(qty=3), {"seed_krw": 1_000_000}, _balance(), _quote(), market_open=True
    )
    assert not ok and "single-name" in reason


def test_policy_rejects_oversell_and_closed_market(monkeypatch) -> None:
    mod = _load_order(monkeypatch)
    ok, reason, _ = mod._evaluate_order_policy(
        _order(side="SELL", qty=2), {"seed_krw": 1_000_000}, _balance(), _quote(), market_open=True
    )
    assert not ok and reason == "sell quantity exceeds live holdings"

    ok, reason, _ = mod._evaluate_order_policy(
        _order(), {"seed_krw": 1_000_000}, _balance(), _quote(), market_open=False
    )
    assert not ok and reason == "KR market is closed"


def test_manual_mode_requires_reason(monkeypatch) -> None:
    mod = _load_order(monkeypatch, mode="manual")
    ok, reason, _ = mod._evaluate_order_policy(
        _order(), {"seed_krw": 1_000_000}, _balance(), _quote(), market_open=True
    )
    assert not ok and reason == "manual mode requires override_reason"

    ok, reason, snapshot = mod._evaluate_order_policy(
        _order(), {"seed_krw": 1_000_000}, _balance(), _quote(),
        override_reason="PM reviewed", market_open=True,
    )
    assert ok, reason
    assert snapshot["override_reason"] == "PM reviewed"


def test_enforced_mode_requires_current_target(monkeypatch) -> None:
    mod = _load_order(monkeypatch, mode="enforced")
    ok, reason, _ = mod._evaluate_order_policy(
        _order(), {"seed_krw": 1_000_000}, _balance(), _quote(), market_open=True
    )
    assert not ok and reason == "current moderation target unavailable"

    moderation = {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weights": {"005930": 0.20},
        "method": "test-target-v1",
    }
    ok, reason, snapshot = mod._evaluate_order_policy(
        _order(), {"seed_krw": 1_000_000}, _balance(), _quote(),
        moderation=moderation, market_open=True,
    )
    assert ok, reason
    assert snapshot["target_current"] is True
    assert snapshot["target_weight"] == 0.20


def test_durable_ledger_is_required_by_default(monkeypatch) -> None:
    mod = _load_order(monkeypatch)
    mod.sb.SUPABASE_URL = ""
    order = _order()
    user = {"jwt": "jwt", "limits": {"daily_order_count_limit": 5}}
    assert mod._shared_reserve(user, order, {"mode": "advised"}) == (
        False,
        "order safety ledger unavailable",
    )


def test_policy_input_fetch_requires_fresh_timestamped_quote(monkeypatch) -> None:
    mod = _load_order(monkeypatch)
    handler = object.__new__(mod.handler)
    handler._proxy_headers = lambda user: {"X-Verity-Broker": "operator"}
    responses = [
        (200, _balance()),
        (200, {
            "quotes": {"005930": _quote()},
            "asof": datetime.now(timezone.utc).isoformat(),
        }),
    ]

    class Response:
        def __init__(self, status, payload):
            self.status_code = status
            self._payload = payload

        def json(self):
            return self._payload

    def get(*args, **kwargs):
        status, payload = responses.pop(0)
        return Response(status, payload)

    monkeypatch.setattr(mod.requests, "get", get)
    balance, quote, reason = handler._fetch_policy_inputs(
        {"user_id": "u", "limits": {"broker_slug": "operator"}}, _order()
    )
    assert reason == ""
    assert balance["output2"][0]["tot_evlu_amt"] == "1000000"
    assert quote["price"] == 70_000


def test_policy_input_fetch_rejects_stale_quote(monkeypatch) -> None:
    mod = _load_order(monkeypatch)
    handler = object.__new__(mod.handler)
    handler._proxy_headers = lambda user: {"X-Verity-Broker": "operator"}
    stale = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - 300, timezone.utc)
    responses = [
        (200, _balance()),
        (200, {"quotes": {"005930": _quote()}, "asof": stale.isoformat()}),
    ]

    class Response:
        def __init__(self, status, payload):
            self.status_code = status
            self._payload = payload

        def json(self):
            return self._payload

    monkeypatch.setattr(
        mod.requests,
        "get",
        lambda *args, **kwargs: Response(*responses.pop(0)),
    )
    balance, quote, reason = handler._fetch_policy_inputs(
        {"user_id": "u", "limits": {"broker_slug": "operator"}}, _order()
    )
    assert balance is None and quote is None
    assert reason == "live quote is stale"
