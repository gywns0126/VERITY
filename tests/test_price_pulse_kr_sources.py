import io
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.cron import price_pulse as pulse


class Saturday(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 28, 5, 3, tzinfo=pulse.KST).astimezone(tz)


@pytest.fixture
def yahoo_metadata():
    return {
        "symbol": "257720.KQ", "exchangeName": "KOE", "currency": "KRW",
        "exchangeTimezoneName": "Asia/Seoul", "regularMarketPrice": 30250,
        "regularMarketTime": 1795761009,
    }


def stub_yahoo(monkeypatch, meta):
    requests = []

    def get(request, timeout):
        requests.append(request.full_url)
        return io.BytesIO(json.dumps({"chart": {"result": [{"meta": meta}], "error": None}}).encode())

    monkeypatch.setattr(pulse, "urlopen", get)
    return requests


def test_pulse_preserves_partial_kis_and_reads_only_registered_missing_symbol(tmp_path, monkeypatch, yahoo_metadata):
    monkeypatch.setattr(pulse, "datetime", Saturday)
    requests = stub_yahoo(monkeypatch, yahoo_metadata)
    minute_calls = []

    class Broker:
        def __init__(self, *, cache_only):
            assert cache_only
            self.is_configured = True

        def authenticate(self, *, force_refresh):
            assert not force_refresh

        def get_minute_chart(self, ticker, *, time_from, include_prev):
            minute_calls.append((ticker, time_from, include_prev))
            if ticker != "005930":
                return []
            return [{"stck_bsop_date": "20261127", "stck_cntg_hour": "153000",
                     "cntg_vol": "1", "stck_prpr": "179100"}]

    monkeypatch.setitem(sys.modules, "api.trading.kis_broker", SimpleNamespace(KISBroker=Broker))
    monkeypatch.setattr(pulse, "fetch_yahoo_quotes", lambda symbols: {})
    monkeypatch.setattr(pulse, "_DATA", str(tmp_path))
    monkeypatch.setattr(pulse, "_OUT", str(tmp_path / "pulse.json"))
    monkeypatch.setattr(pulse, "_PORTFOLIO", str(tmp_path / "portfolio.json"))
    monkeypatch.setattr(pulse, "_RECS", str(tmp_path / "recs.json"))
    (tmp_path / "recs.json").write_text(json.dumps([{"ticker": t} for t in [5930, "257720", "999999"]]))
    (tmp_path / "kr_listed.json").write_text(json.dumps({"005930": {"market": "KS"}, "257720": {"market": "KQ"}}))

    assert pulse.main() == 0
    result = json.loads((tmp_path / "pulse.json").read_text())
    assert minute_calls == [("005930", "153000", "Y"), ("257720", "153000", "Y")]
    assert len(requests) == 1 and "/257720.KQ?" in requests[0]
    assert result["prices"] == {"005930": 179100, "257720": 30250}
    assert result["kr_quotes"]["005930"] == {"symbol": "005930.KS", "source": "kis",
        "observed_at": "2026-11-27T15:30:00+09:00", "price": 179100}
    assert result["kr_quotes"]["257720"] == {"symbol": "257720.KQ", "source": "yahoo",
        "observed_at": "2026-11-27T15:30:09+09:00", "price": 30250}
    assert result["counts"]["kr"] == 2 and result["counts"]["kr_requested"] == 3


@pytest.mark.parametrize("overrides", [
    {"symbol": "257720.KS"}, {"exchangeName": "KSC"}, {"currency": "USD"},
    {"regularMarketTime": 1795674609}, {"regularMarketTime": None},
])
def test_mismatched_and_stale_yahoo_records_never_enter_prices(monkeypatch, yahoo_metadata, overrides):
    monkeypatch.setattr(pulse, "datetime", Saturday)
    monkeypatch.setattr(pulse, "fetch_kis_prices", lambda symbols: {})
    stub_yahoo(monkeypatch, {**yahoo_metadata, **overrides})
    assert pulse.collect_kr_quotes({"257720"}, {"257720": {"market": "KQ"}}) == {}


def test_verified_kospi_yahoo_and_empty_kis_minutes(monkeypatch, yahoo_metadata):
    monkeypatch.setattr(pulse, "datetime", Saturday)
    monkeypatch.setattr(pulse, "fetch_kis_prices", lambda symbols: {})
    requests = stub_yahoo(monkeypatch, {**yahoo_metadata, "symbol": "005930.KS", "exchangeName": "KSC",
                                       "regularMarketPrice": 179100, "regularMarketTime": 1795761004})
    result = pulse.collect_kr_quotes({"005930"}, {"005930": {"market": "KS"}})
    assert result["005930"]["observed_at"] == "2026-11-27T15:30:04+09:00"
    assert len(requests) == 1 and "/005930.KS?" in requests[0]
    assert not pulse._latest_kis_quote([{"stck_prpr": "43500"},
        {"stck_bsop_date": "20261127", "stck_cntg_hour": "153000", "cntg_vol": "0", "stck_prpr": "43500"}],
        "257720.KQ")


def test_registered_alphanumeric_code_keeps_its_leading_zeros(monkeypatch):
    monkeypatch.setattr(pulse, "datetime", Saturday)
    quote = {"source": "kis", "symbol": "0068Y0.KQ", "observed_at": "2026-11-27T15:30:00+09:00",
             "price": 2000}

    def kis(symbols):
        assert symbols == {"0068Y0": "0068Y0.KQ"}
        return {"0068Y0": quote}

    monkeypatch.setattr(pulse, "fetch_kis_prices", kis)
    monkeypatch.setattr(pulse, "_yahoo_kr_quote", lambda _: pytest.fail("KIS quote was replaced"))
    assert pulse.collect_kr_quotes({"0068Y0"}, {"0068Y0": {"market": "KQ"}}) == {"0068Y0": quote}


@pytest.mark.parametrize("observed_at", ["2026-11-27T11:05:00+09:00", "2026-11-27T11:10:00+09:00"])
def test_same_session_delayed_or_conflicting_quote_cannot_roll_raw_pulse_back(tmp_path, monkeypatch, observed_at):
    class Intraday(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 27, 11, 15, tzinfo=pulse.KST).astimezone(tz)

    monkeypatch.setattr(pulse, "datetime", Intraday)
    old = {"price": 34000, "symbol": "257720.KQ", "source": "kis", "observed_at": "2026-11-27T11:10:00+09:00"}
    late = {**old, "price": 31000, "source": "yahoo", "observed_at": observed_at}
    out = tmp_path / "pulse.json"
    out.write_text(json.dumps({"kr_quotes": {"257720": old}, "prices": {"257720": old["price"]}}))
    monkeypatch.setattr(pulse, "_OUT", str(out))
    monkeypatch.setattr(pulse, "_DATA", str(tmp_path))
    monkeypatch.setattr(pulse, "_RECS", str(tmp_path / "recs.json"))
    monkeypatch.setattr(pulse, "_PORTFOLIO", str(tmp_path / "portfolio.json"))
    (tmp_path / "recs.json").write_text(json.dumps([{"ticker": "257720"}]))
    (tmp_path / "kr_listed.json").write_text(json.dumps({"257720": {"market": "KQ"}}))
    monkeypatch.setattr(pulse, "fetch_yahoo_quotes", lambda symbols: {})
    monkeypatch.setattr(pulse, "collect_kr_quotes", lambda tickers, listed: {"257720": late})
    assert pulse.main() == 0
    updated = json.loads(out.read_text())
    assert updated["kr_quotes"]["257720"] == old and updated["prices"]["257720"] == 34000
