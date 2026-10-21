import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("rebuild", Path(__file__).parents[1] / "scripts/rebuild_local_lake_artifacts.py")
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)


def issuer():
    # The producer emits only issuers with a nonempty dated event history.
    return {"name": "fixture", "events": [{"type": "historical", "tone": "neutral", "count": 1,
        "occurrences": [{"date": "2020-01-02", "report_nm": "fixture", "base_date": "2020-01-02",
                         "ret_1d": 1.0, "ret_5d": 2.0, "ret_20d": 3.0, "ret_60d": 4.0}]}]}


def payload(stocks=None):
    stocks = stocks if stocks is not None else {"000001": issuer(), "TEST": issuer()}
    return {"stocks": stocks, "_meta": {"stock_count": len(stocks),
        "kr_count": sum(ticker.isdigit() for ticker in stocks),
        "us_count": sum(not ticker.isdigit() for ticker in stocks),
        "occurrence_count": sum(len(group["occurrences"]) for stock in stocks.values()
                                for group in stock.get("events", [])),
        "generated_at": "original"}}


def corrupt_count():
    doc = payload()
    doc["_meta"]["stock_count"] = 99
    return doc


def test_unchanged_comparison_does_not_mutate_original_timestamp():
    old = payload()
    new = payload()
    new["_meta"]["generated_at"] = "new"
    assert job.content(old) == job.content(new)
    assert old["_meta"]["generated_at"] == "original"


@pytest.mark.parametrize("bad", [payload({}), payload({"TEST": {}}), {"stocks": []},
                               corrupt_count(), payload({"000001": {}, "TEST": {}})])
def test_loss_or_corruption_never_publishes(bad):
    with pytest.raises(ValueError):
        job.validate(payload(), bad)


def test_existing_issuers_preserved():
    job.validate(payload(), payload())


def test_existing_valid_issuer_loss_still_fails_closed():
    old = payload({"000001": issuer(), "000002": issuer(), "TEST": issuer()})
    with pytest.raises(ValueError, match="Refusing loss of 1 previously published issuers"):
        job.validate(old, payload())
