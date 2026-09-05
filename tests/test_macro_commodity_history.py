import pandas as pd

from api.collectors import macro_data


def _history(values):
    return pd.DataFrame(
        {"Close": values},
        index=pd.date_range("2025-09-01", periods=len(values), freq="B"),
    )


def test_commodity_contract_covers_all_public_symbols() -> None:
    assert set(macro_data.COMMODITY_SPECS) == {
        "gold",
        "silver",
        "copper",
        "wti_oil",
        "brent",
        "natural_gas",
        "corn",
        "wheat",
        "soybean",
        "coffee",
        "sugar",
        "cotton",
    }


def test_commodity_payload_preserves_one_year_history_and_summary() -> None:
    values = [100 + index * 0.5 for index in range(220)]
    payload = macro_data._commodity_payload(_history(values), "GC=F", "금")

    assert payload["status"] == "ok"
    assert payload["observations"] == 220
    assert len(payload["history_daily"]) == 220
    assert len(payload["sparkline"]) == 30
    assert payload["history_daily"][0]["date"] == "2025-09-01"
    assert payload["data_date"] == payload["history_daily"][-1]["date"]
    assert payload["high_52w"] == max(values)
    assert payload["low_52w"] == min(values)


def test_commodity_bundle_uses_one_batch_request(monkeypatch) -> None:
    frame = pd.concat(
        {
            ticker: _history([100 + index for index in range(220)])
            for ticker, _name in macro_data.COMMODITY_SPECS.values()
        },
        axis=1,
    )
    calls = []

    def fake_download(**kwargs):
        calls.append(kwargs)
        return frame

    monkeypatch.setattr(macro_data.yf, "download", fake_download)
    monkeypatch.setattr(
        macro_data,
        "_get_commodity_with_history",
        lambda *_args: (_ for _ in ()).throw(AssertionError("unexpected fallback")),
    )

    result = macro_data._get_commodity_bundle()

    assert set(result) == set(macro_data.COMMODITY_SPECS)
    assert all(row["observations"] == 220 for row in result.values())
    assert len(calls) == 1
    assert calls[0]["period"] == "1y"
