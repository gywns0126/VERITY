"""Private Nest API regression: in-memory DB only; never writes member records."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


class NestReliability(unittest.TestCase):
    def setUp(self):
        self.previous = {k: v for k, v in sys.modules.items() if k == "api" or k.startswith("api.")}
        self.sb = types.ModuleType("api.supabase_client")
        self.sb.is_configured = lambda: True
        self.sb.verify_jwt = lambda token: "account-A" if token == "test" else None
        api = types.ModuleType("api")
        api.__path__ = [str(ROOT / "vercel-api/api")]
        api.supabase_client = self.sb
        sys.modules["api"] = api
        sys.modules["api.supabase_client"] = self.sb
        self.modules = {}
        for name in ("nest_validation", "holdings", "trades"):
            spec = importlib.util.spec_from_file_location("api." + name, ROOT / "vercel-api/api" / (name + ".py"))
            mod = importlib.util.module_from_spec(spec)
            sys.modules["api." + name] = mod
            spec.loader.exec_module(mod)
            self.modules[name] = mod

    def tearDown(self):
        for key in list(sys.modules):
            if key == "api" or key.startswith("api."):
                sys.modules.pop(key)
        sys.modules.update(self.previous)

    def request(self, name, method, payload=None, token="test", select=None):
        self.sb.select = select or Mock(return_value=[])
        self.sb.insert = Mock(side_effect=lambda table, data, **kw: data)
        self.sb.update = Mock(return_value=[{"id": "own"}])
        self.sb.delete = Mock()
        h = object.__new__(self.modules[name].handler)
        body = json.dumps(payload).encode()
        h.headers = {"Authorization": "Bearer " + token, "Content-Length": str(len(body))}
        h.client_address = ("local-test", 0)
        h.rfile, h.wfile = io.BytesIO(body), io.BytesIO()
        h.send_response = lambda code: setattr(h, "status", code)
        headers = {}
        h.send_header = lambda k, v: headers.update({k: v})
        h.end_headers = lambda: None
        getattr(h, "do_" + method)()
        self.assertEqual(headers.get("Cache-Control"), "private, no-store")
        return h.status, json.loads(h.wfile.getvalue())

    def payload(self):
        return dict(ticker="TSM", market="us", shares=10, avg_cost=150, price=150,
                    side="buy", traded_at="2026-09-14", user_id="spoofed-B")

    def test_auth_and_owned_mutations(self):
        for name in ("holdings", "trades"):
            for method in ("GET", "POST", "PATCH", "DELETE"):
                with self.subTest(name=name, method=method):
                    self.assertEqual(self.request(name, method, token="bad")[0], 401)
                    self.sb.select.assert_not_called()
                    self.sb.insert.assert_not_called()
            self.request(name, "POST", self.payload())
            self.assertEqual(self.sb.insert.call_args.args[1]["user_id"], "account-A")
            self.assertEqual(self.sb.insert.call_args.kwargs["user_jwt"], "test")
            self.request(name, "PATCH", {"id": "other", "shares": 3})
            self.assertEqual(self.sb.update.call_args.args[1], {"id": "other", "user_id": "account-A"})
            self.request(name, "DELETE", {"id": "other"})
            self.assertEqual(self.sb.delete.call_args.args[1], {"id": "other", "user_id": "account-A"})

    def test_invalid_shapes(self):
        for name in ("holdings", "trades"):
            for payload in (None, [], "bad", True, {"id": ""}):
                for method in ("POST", "PATCH", "DELETE"):
                    with self.subTest(name=name, payload=payload, method=method):
                        self.assertEqual(self.request(name, method, payload)[0], 400)

    def test_nonpositive_and_nonfinite(self):
        for name, field in (("holdings", "avg_cost"), ("holdings", "shares"), ("trades", "price"), ("trades", "shares")):
            for value in (0, -1, "", "NaN", "Infinity", None, False, "oops"):
                for method in ("POST", "PATCH"):
                    with self.subTest(name=name, field=field, value=value, method=method):
                        payload = self.payload() if method == "POST" else {"id": "own"}
                        payload[field] = value
                        self.assertEqual(self.request(name, method, payload)[0], 400)

    def test_formatted_numbers_and_adr(self):
        for name, field in (("holdings", "avg_cost"), ("trades", "price")):
            payload = {**self.payload(), field: "2,000,000원"}
            code, result = self.request(name, "POST", payload)
            self.assertIn(code, (200, 201))
            self.assertEqual(result[field], 2000000)
            self.assertEqual(result["ticker"], "TSM")

    def test_asset_validation(self):
        for name in ("holdings", "trades"):
            for ticker, market in (("CMD_GOLD", "kr"), ("CMD_GOLD", "원자재"), ("TSM", "unknown"), ("TSM,or(id.gt.0)", "us")):
                self.assertEqual(self.request(name, "POST", {**self.payload(), "ticker": ticker, "market": market})[0], 400)

    def test_read_pagination_and_empty(self):
        for name in ("holdings", "trades"):
            pages = [[{"id": "0001"}], [{"id": "0002"}], []]
            select = Mock(side_effect=pages)
            code, data = self.request(name, "GET", select=select)
            self.assertEqual(code, 200)
            rows = data if name == "holdings" else data["trades"]
            self.assertEqual(len(rows), 2)
            self.assertEqual(select.call_args_list[1].args[1]["id"], "gt.0001")
            self.assertTrue(all(c.args[1]["user_id"] == "eq.account-A" and c.kwargs["user_jwt"] == "test" for c in select.call_args_list))

    def test_not_configured_is_not_empty(self):
        self.sb.is_configured = lambda: False
        for name in ("holdings", "trades"):
            self.assertEqual(self.request(name, "GET")[0], 503)

    def test_retry_idempotency(self):
        payload = {**self.payload(), "request_id": "11111111-1111-4111-8111-111111111111"}
        _, saved = self.request("trades", "POST", payload)
        code, again = self.request("trades", "POST", payload, select=Mock(return_value=[saved]))
        self.assertEqual(code, 200)
        self.assertEqual(saved, again)
        self.sb.insert.assert_not_called()
        code, _ = self.request("trades", "POST", {**payload, "shares": 11}, select=Mock(return_value=[saved]))
        self.assertEqual(code, 409)
        self.sb.insert.assert_not_called()

    def test_realized_and_unmatched_sales(self):
        trades = [dict(ticker="TSM", market="us", side="buy", shares=10, price=100),
                  dict(ticker="TSM", market="us", side="buy", shares=10, price=200),
                  dict(ticker="TSM", market="us", side="sell", shares=25, price=200),
                  dict(ticker="005930", market="kr", side="sell", shares=1, price=100)]
        result = self.modules["trades"]._compute_summary(trades)
        self.assertEqual(result["unmatched_sell_shares"], 6)
        self.assertEqual(result["realized_by_currency"], {"USD": 1000, "KRW": 0})
        self.assertIsNone(result["total_realized_pnl"])

    def test_invalid_dates(self):
        for value in ("2026-02-30", "20260914", "bad"):
            self.assertEqual(self.request("trades", "POST", {**self.payload(), "traded_at": value})[0], 400)


if __name__ == "__main__":
    unittest.main()
