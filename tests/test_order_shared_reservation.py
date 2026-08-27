"""실주문 중복·일일 한도 원장이 서버리스 공용 RPC를 우선하는지 검증."""

import importlib.util
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]


def _load_order(monkeypatch):
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
    spec = importlib.util.spec_from_file_location("order_under_test", ROOT / "vercel-api" / "api" / "order.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_shared_reservation_accepts_and_hashes(monkeypatch) -> None:
    mod = _load_order(monkeypatch)
    seen = {}

    class Response:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"ok": True, "reservation_id": "x"}

    def post(url, **kwargs):
        seen.update({"url": url, **kwargs})
        return Response()

    monkeypatch.setattr(mod.requests, "post", post)
    user = {"jwt": "jwt", "limits": {"daily_order_count_limit": 5}}
    order = {"ticker": "005930", "side": "BUY", "qty": 1, "price": 70000,
             "order_type": "00", "market": "kr"}

    assert mod._shared_reserve(user, order) == (True, "")
    assert seen["url"].endswith("/rest/v1/rpc/reserve_order_slot")
    assert len(seen["json"]["p_order_hash"]) == 64
    assert seen["json"]["p_daily_limit"] == 5


def test_shared_reservation_fails_closed_on_rpc_error(monkeypatch) -> None:
    mod = _load_order(monkeypatch)

    class Response:
        status_code = 500
        text = "upstream error"

    monkeypatch.setattr(mod.requests, "post", lambda *args, **kwargs: Response())
    user = {"jwt": "jwt", "limits": {"daily_order_count_limit": 5}}
    order = {"ticker": "005930", "side": "BUY", "qty": 1, "price": 70000,
             "order_type": "00", "market": "kr"}

    assert mod._shared_reserve(user, order) == (False, "order safety ledger unavailable")
