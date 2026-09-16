from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.refresh_nps_overview import nps, refresh

ROOT = Path(__file__).resolve().parents[1]


def inputs():
    current = json.loads((ROOT / "data/nps_holdings.json").read_text())
    fund = json.loads((ROOT / "data/nps_fund_overview.json").read_text())
    return current, fund, nps._asset_mix()


def test_refresh_preserves_every_non_overview_field():
    current, fund, mix = inputs()
    before = deepcopy(current)
    out = refresh(current, fund, mix, "2026-09-16T15:00:00+09:00")
    for key in current.keys() - {"fund", "asset_mix", "generated_at"}:
        assert out[key] == current[key], key
    assert current == before
    assert out["fund"] == fund
    assert out["asset_mix"] == mix


def test_refresh_is_idempotent():
    current, fund, mix = inputs()
    out = refresh(current, fund, mix, "2026-09-16T15:00:00+09:00")
    assert refresh(out, fund, mix, "2026-09-17T15:00:00+09:00") == out


def test_rejects_period_rollback():
    current, fund, mix = inputs()
    current["fund"]["as_of"] = "2099-12-31"
    with pytest.raises(ValueError, match="backwards"):
        refresh(current, fund, mix, "unused")


@pytest.mark.parametrize("change,error", [
    ("mix_period", "periods differ"),
    ("return_period", "return period"),
    ("aum", "AUM differ"),
    ("count", "count mismatch"),
])
def test_rejects_inconsistent_inputs(change, error):
    current, fund, mix = inputs()
    if change == "mix_period":
        mix[0]["as_of"] = "2020년 1월"
    elif change == "return_period":
        fund["return_period_end"] = "2020-01-31"
    elif change == "aum":
        fund["aum_krw_trillion"] += 1
    else:
        current["count"] += 1
    with pytest.raises(ValueError, match=error):
        refresh(current, fund, mix, "unused")


def test_june_source_values_and_periods_are_not_mixed():
    _, fund, mix = inputs()
    assert fund["as_of"] == fund["return_period_end"] == "2026-06-30"
    assert fund["return_cumulative_period_end"] == "2025-12-31"
    assert fund["aum_krw_trillion"] == 1865.6
    assert fund["return_total_pct"] == 27.22
    assert fund["asset_returns_pct"] == {
        "국내주식": 107.37, "해외주식": 17.81, "국내채권": -3.0,
        "해외채권": 9.22, "대체투자": 9.6,
    }
    assert {r["name"]: r["pct"] for r in mix[0]["mix"]} == {
        "국내주식": 29.1, "해외주식": 35.4, "국내채권": 15.4,
        "해외채권": 5.9, "대체투자": 14.0, "단기자금": 0.2, "복지·기타": 0.0,
    }
    # The official table reports welfare/other together. Do not invent a split.
    assert len(mix[0]["mix"]) == 7
