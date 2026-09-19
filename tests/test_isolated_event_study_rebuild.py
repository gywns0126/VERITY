import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("rebuild", Path(__file__).parents[1] / "scripts/rebuild_local_lake_artifacts.py")
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)


def payload(stocks=None):
    stocks = stocks if stocks is not None else {"000001": {}, "TEST": {}}
    return {"stocks": stocks, "_meta": {"stock_count": len(stocks), "kr_count": 1,
                                      "us_count": 1, "generated_at": "original"}}


def test_unchanged_comparison_does_not_mutate_original_timestamp():
    old = payload()
    new = payload()
    new["_meta"]["generated_at"] = "new"
    assert job.content(old) == job.content(new)
    assert old["_meta"]["generated_at"] == "original"


@pytest.mark.parametrize("bad", [payload({}), payload({"TEST": {}}), {"stocks": []}, {
    "stocks": {"000001": {}, "TEST": {}},
    "_meta": {"stock_count": 99, "kr_count": 1, "us_count": 1},
}])
def test_loss_or_corruption_never_publishes(bad):
    with pytest.raises(ValueError):
        job.validate(payload(), bad)


def test_existing_issuers_preserved():
    job.validate(payload(), payload())
