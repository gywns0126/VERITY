"""Synthetic balance/quote outage regressions; no live services or token files."""
import asyncio
import os
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
import requests


@pytest.fixture
def relay(monkeypatch, tmp_path):
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **kw: False)
    for name in tuple(os.environ):
        if name.startswith(("KIS_", "SUPABASE_", "RAILWAY_", "ORDER_")):
            monkeypatch.delenv(name, raising=False)

    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected external request")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(requests, "get", forbidden)
    monkeypatch.setattr(requests, "post", forbidden)
    import server.security as security

    monkeypatch.setattr(security, "start_security", lambda app: None)
    from server import kis_rest_client as k, main as m

    # Other routing tests reload k; keep the route's exception identity in sync.
    monkeypatch.setattr(m, "BrokerMismatch", k.BrokerMismatch)
    monkeypatch.setattr(m, "get_balance", k.get_balance)
    monkeypatch.setattr(k, "_account_parts_for", lambda broker: ("12345678", "01"))
    monkeypatch.setattr(k, "_headers", lambda *a: {})
    monkeypatch.setattr(k, "_TOKEN_CACHE_PATH", str(tmp_path / "absent-token.json"))
    monkeypatch.setattr(k, "_token", None)
    monkeypatch.setattr(k, "_token_expires", 0)
    monkeypatch.setattr(k, "_token_source", "none")
    monkeypatch.setenv("RAILWAY_SHARED_SECRET", "synthetic-service-auth")
    return m, k


def balance_response(m, market):
    async def call():
        # ASGI transport does not start lifespan/WS connections or open a socket.
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=m.app), base_url="http://synthetic"
        ) as client:
            return await client.get(
                "/api/order", params={"market": market},
                headers={"X-Service-Auth": "synthetic-service-auth", "X-Verity-Broker": "operator"},
            )
    return asyncio.run(call())


@pytest.mark.parametrize("market", ["kr", "us"])
@pytest.mark.parametrize("failure", ["token", "timeout", "http", "json"])
def test_balance_failure_is_sanitized_502(relay, monkeypatch, caplog, market, failure):
    m, k = relay
    sensitive = "CANO=12345678&access_token=DO_NOT_LOG"
    if failure == "token":
        monkeypatch.setattr(k, "_headers", Mock(side_effect=RuntimeError(sensitive)))
        get = Mock(side_effect=AssertionError("KIS GET must not run without headers"))
    else:
        response = Mock()
        get = Mock(return_value=response)
        if failure == "timeout":
            get.side_effect = requests.Timeout(sensitive)
        elif failure == "http":
            response.raise_for_status.side_effect = requests.HTTPError(sensitive)
        else:
            response.json.side_effect = ValueError(sensitive)
    monkeypatch.setattr(requests, "get", get)

    response = balance_response(m, market)
    assert response.status_code == 502
    assert response.json() == {"error": "KIS balance unavailable"}
    assert sensitive not in caplog.text
    assert "12345678" not in caplog.text
    assert get.call_count == (0 if failure == "token" else 1)


@pytest.mark.parametrize("market", ["kr", "us"])
@pytest.mark.parametrize("payload", [
    None, [], {}, {"rt_cd": "1", "msg1": "DO_NOT_LOG"}, {"rt_cd": "0"},
    {"rt_cd": "0", "output1": None, "output2": {}},
    {"rt_cd": "0", "output1": [], "output2": None},
])
def test_balance_invalid_envelope_is_not_an_empty_account(relay, monkeypatch, caplog, market, payload):
    m, _ = relay
    monkeypatch.setattr(requests, "get", Mock(return_value=Mock(json=lambda: payload)))
    response = balance_response(m, market)
    assert response.status_code == 502
    assert response.json() == {"error": "KIS balance unavailable"}
    assert "DO_NOT_LOG" not in caplog.text


@pytest.mark.parametrize("market,summary", [
    ("kr", [{"dnca_tot_amt": "0", "tot_evlu_amt": "0", "evlu_pfls_smtl_amt": "0"}]),
    ("kr", [{"dnca_tot_amt": 0, "tot_evlu_amt": 100.5, "evlu_pfls_smtl_amt": -1}]),
    ("us", {"frcr_pchs_amt1": "0", "ovrs_tot_pfls": "0"}),
    ("us", [{"frcr_pchs_amt1": "0", "ovrs_tot_pfls": "0"}]),
])
@pytest.mark.parametrize("holdings", [[], [{"pdno": "SYNTHETIC", "hldg_qty": "1"}]])
def test_balance_success_envelope_is_preserved(relay, monkeypatch, market, summary, holdings):
    m, _ = relay
    payload = {"rt_cd": "0", "output1": holdings, "output2": summary, "msg_cd": "SUCCESS"}
    monkeypatch.setattr(requests, "get", Mock(return_value=Mock(json=lambda: payload)))
    response = balance_response(m, market)
    assert response.status_code == 200
    assert response.json() == payload


@pytest.mark.parametrize("market", ["kr", "us"])
@pytest.mark.parametrize("summary", [[], {}, [{}], [None], ["invalid"], "invalid"])
def test_balance_empty_or_malformed_summary_is_unavailable(relay, monkeypatch, market, summary):
    m, _ = relay
    payload = {"rt_cd": "0", "output1": [], "output2": summary}
    monkeypatch.setattr(requests, "get", Mock(return_value=Mock(json=lambda: payload)))
    response = balance_response(m, market)
    assert response.status_code == 502
    assert response.json() == {"error": "KIS balance unavailable"}


@pytest.mark.parametrize("field", ["dnca_tot_amt", "tot_evlu_amt", "evlu_pfls_smtl_amt"])
@pytest.mark.parametrize("invalid", ["missing", None, "", "NaN", "Infinity", True, "invalid"])
def test_kr_balance_requires_finite_card_amounts(relay, monkeypatch, field, invalid):
    m, _ = relay
    summary = {"dnca_tot_amt": "0", "tot_evlu_amt": "0", "evlu_pfls_smtl_amt": "0"}
    if invalid == "missing":
        summary.pop(field)
    else:
        summary[field] = invalid
    payload = {"rt_cd": "0", "output1": [], "output2": [summary]}
    monkeypatch.setattr(requests, "get", Mock(return_value=Mock(json=lambda: payload)))
    response = balance_response(m, "kr")
    assert response.status_code == 502
    assert response.json() == {"error": "KIS balance unavailable"}


def test_kr_balance_requires_summary_list(relay, monkeypatch):
    m, _ = relay
    payload = {"rt_cd": "0", "output1": [], "output2": {
        "dnca_tot_amt": "0", "tot_evlu_amt": "0", "evlu_pfls_smtl_amt": "0",
    }}
    monkeypatch.setattr(requests, "get", Mock(return_value=Mock(json=lambda: payload)))
    assert balance_response(m, "kr").status_code == 502


def test_balance_preserves_broker_mismatch_and_sanitizes_route(relay, monkeypatch, caplog):
    m, k = relay
    error = k.BrokerMismatch("DO_NOT_LOG")
    monkeypatch.setattr(k, "_headers", Mock(side_effect=error))
    with pytest.raises(k.BrokerMismatch) as caught:
        k.get_balance("kr", "operator")
    assert caught.value is error
    response = balance_response(m, "kr")
    assert response.status_code == 403
    assert response.json() == {"error": "KIS account routing mismatch"}
    assert "DO_NOT_LOG" not in caplog.text


def test_non_balance_get_keeps_existing_fallback(relay, monkeypatch):
    _, k = relay
    monkeypatch.setattr(k, "_headers", Mock(side_effect=RuntimeError("synthetic failure")))
    assert k._get("/synthetic-quote", "synthetic", {}) == {}


@pytest.mark.parametrize("row_kind", ["absent", "expired", "fingerprint"])
def test_consumer_balance_cannot_reuse_invalid_token_or_issue(relay, monkeypatch, row_kind):
    _, k = relay
    monkeypatch.setenv("KIS_SHARED_TOKEN", "1")
    monkeypatch.setattr(k, "SUPABASE_URL", "https://synthetic.invalid")
    monkeypatch.setattr(k, "SUPABASE_SERVICE_ROLE_KEY", "synthetic")
    monkeypatch.setattr(k, "KIS_APP_KEY", "synthetic-key")
    monkeypatch.setattr(k, "_token", "expired-synthetic")
    monkeypatch.setattr(k, "_token_expires", 1)
    row = None if row_kind == "absent" else {
        "access_token": "synthetic", "app_key_fp": k._app_key_fp(),
        "expires_at": "2000-01-01T00:00:00+00:00",
    }
    if row_kind == "fingerprint":
        row.update(app_key_fp="wrong", expires_at="2099-01-01T00:00:00+00:00")
    monkeypatch.setattr(k, "_read_shared_token", lambda: row)
    monkeypatch.setattr(k, "_load_cached_token", lambda: False)
    monkeypatch.setattr(k, "_headers", lambda *a: {"authorization": k._get_token()})
    with pytest.raises(RuntimeError, match="^KIS balance unavailable$"):
        k.get_balance()
    assert k._token_expires == 1


@pytest.mark.parametrize("route,fetch,kwargs", [
    ("quotes", "fetch_price", {"tickers": "1,2"}),
    ("us_quotes", "fetch_us_price", {"tickers": "a,b", "excd": "nas"}),
])
def test_health_runs_while_quote_worker_is_blocked(relay, monkeypatch, route, fetch, kwargs):
    m, _ = relay
    released = threading.Event()
    calls = []
    monkeypatch.setattr(m, "_quote_rate_ok", lambda ip: True)

    async def run():
        loop = asyncio.get_running_loop()
        entered = asyncio.Event()
        loop_thread = threading.get_ident()

        def blocked(*args):
            calls.append((args, threading.get_ident()))
            loop.call_soon_threadsafe(entered.set)
            if not released.wait(2):
                raise RuntimeError("worker watchdog elapsed")
            return {"price": 1}

        monkeypatch.setattr(m, fetch, blocked)
        task = asyncio.create_task(getattr(m, route)(
            SimpleNamespace(client=SimpleNamespace(host="synthetic")), **kwargs
        ))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert not task.done(), "quote handler blocked the event loop"
            assert (await asyncio.wait_for(m.health(), 0.5))["status"] == "ok"
        finally:
            released.set()
            result = await task
        assert result["count"] == 2
        assert len(calls) == 2
        assert all(worker != loop_thread for _, worker in calls)
        assert [args for args, _ in calls] == (
            [("000001",), ("000002",)] if route == "quotes" else [("A", "NAS"), ("B", "NAS")]
        )
    asyncio.run(run())
