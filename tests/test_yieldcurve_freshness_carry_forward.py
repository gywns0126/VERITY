from api.collectors import bonddata, bondus, yieldcurve


def test_forward_fill_preserves_observation_date():
    merged, carried = yieldcurve._forward_fill_curve(
        [], [{"tenor": "3Y", "yield": 3.816, "as_of": "20260826"}], ["3Y"]
    )

    assert carried == ["3Y"]
    assert merged == [
        {"tenor": "3Y", "yield": 3.816, "as_of": "20260826", "stale": True}
    ]


def test_kr_total_failure_preserves_freshness_contract(monkeypatch):
    previous = {
        "yield_curves": {
            "kr": {
                "curve": [{"tenor": "3Y", "yield": 3.816, "as_of": "20260826"}],
                "curve_as_of": "20260826",
            }
        },
        "kr_corp_spreads": {
            "date": "20260826",
            "collected_at": "2026-08-27T08:00:00+09:00",
            "grades": {"AA-": {"yield": 4.5, "as_of": "20260826"}},
        },
    }
    monkeypatch.setattr(bonddata, "get_bond_market_summary", lambda: {})
    monkeypatch.setattr(bondus, "get_us_bond_summary", lambda: {})

    out = yieldcurve.get_full_yield_curve_data(prev_bonds=previous)

    kr = out["yield_curves"]["kr"]
    assert kr["curve_as_of"] == "20260826"
    assert kr["curve"][0]["as_of"] == "20260826"
    assert kr["curve"][0]["stale"] is True
    assert out["kr_corp_spreads"]["date"] == "20260826"
    assert out["kr_corp_spreads"]["stale"] is True
