"""Offline producer regressions: never combine incompatible accounting contexts."""
from copy import deepcopy
from unittest.mock import Mock, patch

import pytest

from api.collectors.sec_edgar import _coherent_operands, get_financial_facts


def row(value=100, **changes):
    data = {"val": value, "end": "2025-12-31", "filed": "2026-03-01",
            "accn": "0000000123-26-000001", "form": "10-K"}
    data.update(changes)
    return data


def concept(*rows):
    return {"units": {"USD": list(rows)}}


def facts(**changes):
    result = {"LongTermDebt": concept(row(40)), "ShortTermBorrowings": concept(row(10)),
              "StockholdersEquity": concept(row(100)), "AssetsCurrent": concept(row(200)),
              "LiabilitiesCurrent": concept(row(80)),
              "NetCashProvidedByUsedInOperatingActivities": concept(row(70, start="2025-01-01")),
              "PaymentsToAcquirePropertyPlantAndEquipment": concept(row(20, start="2025-01-01"))}
    result.update(changes)
    return result


def produce(data):
    response = Mock()
    response.json.return_value = {"cik": 123, "facts": {"us-gaap": data}}
    with patch("api.collectors.sec_edgar._resolve_cik", return_value="0000000123"), \
         patch("api.collectors.sec_edgar._throttle"), \
         patch("api.collectors.sec_edgar._SESSION.get", return_value=response):
        return get_financial_facts("ABC", "offline-test")


def test_matching_current_context_produces_ratios_and_cashflow():
    result = produce(facts())
    assert (result["debt_ratio"], result["total_debt"], result["current_ratio"], result["fcf"]) == (50, 50, 250, 50)
    assert result["_source_rejections"] == {}


def test_current_alternative_beats_deprecated_nonzero_debt():
    result = produce(facts(LongTermDebt=concept(row(999, end="2011-12-31")),
                           LongTermDebtNoncurrent=concept(row(40))))
    assert result["debt_ratio"] == 50
    assert result["_source_evidence"]["debt_ratio"]["inputs"][0]["concept"] == "LongTermDebtNoncurrent"


def test_noncurrent_plus_current_bundle_keeps_its_own_definition():
    result = produce(facts(LongTermDebt=concept(row(999, end="2019-12-31")),
                           ShortTermBorrowings=concept(row(58, end="2020-12-31")),
                           LongTermDebtNoncurrent=concept(row(1742)), DebtCurrent=concept(row(48)),
                           StockholdersEquity=concept(row(4274))))
    assert result["total_debt"] == 1790
    assert result["debt_ratio"] == 41.9
    evidence = result["_source_evidence"]["debt_ratio"]
    assert evidence["definition"] == "noncurrent_plus_current_debt_over_equity"
    assert [r["concept"] for r in evidence["inputs"]] == ["LongTermDebtNoncurrent", "DebtCurrent", "StockholdersEquity"]


def test_current_debt_is_not_added_to_total_long_term_debt():
    result = produce(facts(ShortTermBorrowings=concept(), DebtCurrent=concept(row(48))))
    assert result["debt_ratio"] is None  # No Noncurrent concept: possible overlap is not guessed.


@pytest.mark.parametrize("changes", [
    {"LongTermDebt": concept(row(999, end="2011-12-31"))},
    {"ShortTermBorrowings": concept()},
    {"StockholdersEquity": concept(row(100, accn="other-disclosure"))},
    {"LongTermDebt": concept(row(40), row(41))},
    {"LongTermDebt": concept(row(True))},
    {"LongTermDebt": concept(row(float("inf")))},
])
def test_incompatible_or_absent_debt_operands_are_not_zero_or_old_fallback(changes):
    result = produce(facts(**changes))
    assert result["debt_ratio"] is None
    assert result["total_debt"] is None
    assert result["_source_rejections"]["debt_ratio"]["reason"]


def test_explicit_reported_zero_remains_valid():
    result = produce(facts(LongTermDebt=concept(row(0)), ShortTermBorrowings=concept(row(0))))
    assert result["debt_ratio"] == 0
    assert result["total_debt"] == 0


@pytest.mark.parametrize("changes", [
    {"PaymentsToAcquirePropertyPlantAndEquipment": concept()},
    {"PaymentsToAcquirePropertyPlantAndEquipment": concept(row(20, start="2025-10-01"))},
    {"PaymentsToAcquirePropertyPlantAndEquipment": concept(row(20, start="2024-01-01", end="2024-12-31"))},
])
def test_fcf_requires_both_full_year_operands(changes):
    result = produce(facts(**changes))
    assert result["fcf"] is None
    assert result["_source_rejections"]["fcf"]["reason"]


def test_current_ratio_requires_same_balance_date():
    result = produce(facts(AssetsCurrent=concept(row(200, end="2024-12-31"))))
    assert result["current_ratio"] is None
    assert result["working_capital"] is None


def test_input_order_and_input_objects_remain_stable():
    data = facts(LongTermDebt=concept(row(40), row(45, end="2024-12-31")))
    before = deepcopy(data)
    assert produce(data)["debt_ratio"] == 50
    assert data == before


def test_no_fallback_to_old_complete_disclosure_when_latest_is_incomplete():
    data = {"A": concept(row(1), row(2, end="2024-12-31", accn="old")),
            "B": concept(row(3, end="2024-12-31", accn="old"))}
    chosen, rejected = _coherent_operands(data, [("A",), ("B",)], instant=True)
    assert chosen is None
    assert rejected["end"] == "2025-12-31"
