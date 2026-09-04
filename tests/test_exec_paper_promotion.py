import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.promote_exec_paper_to_portfolio import PromotionError, promote_exec_paper


def _documents():
    price_snapshot = {
        "source": "portfolio.recommendations.current_price",
        "as_of": "2026-09-04T16:39:34+09:00",
        "market_clock_state": "after_close_clock",
        "holiday_calendar": "not_connected",
    }
    denominator = {
        "kr_candidate_n": 17,
        "eligible_n": 9,
        "selected_n": 9,
    }
    state = {
        "version": "v1-ranked-forward-20260901",
        "formula_version": "brain-current/fact-v1.1-20260823",
        "cash": 10_000_000.0,
        "positions": {},
        "pending": [{"side": "buy", "ticker": "005930"}],
        "target_tickers": ["005930"],
        "market_sessions": 1,
        "trades": 0,
        "price_snapshot": price_snapshot,
        "last_denominator": denominator,
        "last_flags": ["waiting_new_market_snapshot"],
    }
    summary = {
        "as_of": "2026-09-04T16:52:18+09:00",
        "status": "RUNNING",
        "version": state["version"],
        "formula_version": state["formula_version"],
        "capital_mode": "paper_only",
        "real_orders": 0,
        "cash": 10_000_000,
        "positions": {},
        "targets": [{"ticker": "005930", "name": "삼성전자"}],
        "target_holdings": 1,
        "pending": 1,
        "trades_total": 0,
        "market_sessions": 1,
        "price_snapshot": price_snapshot,
        "denominator": denominator,
        "flags": ["waiting_new_market_snapshot", "already_ran_today"],
    }
    production = {
        "updated_at": "2026-09-04T06:33:26+09:00",
        "vams": {"total_asset": 9_900_000},
        "recommendations": [{"ticker": "old"}],
        "exec_paper": {"market_sessions": 99},
    }
    staging = {
        "updated_at": "2026-09-04T16:39:34+09:00",
        "vams": {"total_asset": 1},
        "recommendations": [{"ticker": "staging-only"}],
        "exec_paper": summary,
    }
    return production, staging, state


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_promotes_only_validated_exec_paper_field(tmp_path):
    production, staging, state = _documents()
    original = deepcopy(production)
    prod_path = tmp_path / "portfolio.json"
    dev_path = tmp_path / "portfolio.dev.json"
    state_path = tmp_path / "exec_paper_state.json"
    _write(prod_path, production)
    _write(dev_path, staging)
    _write(state_path, state)

    promoted = promote_exec_paper(dev_path, prod_path, state_path)
    saved = json.loads(prod_path.read_text(encoding="utf-8"))

    assert promoted == staging["exec_paper"]
    assert saved["exec_paper"] == staging["exec_paper"]
    assert {key: value for key, value in saved.items() if key != "exec_paper"} == {
        key: value for key, value in original.items() if key != "exec_paper"
    }
    assert saved["vams"] != staging["vams"]
    assert saved["recommendations"] != staging["recommendations"]


@pytest.mark.parametrize(
    ("target", "value"),
    [
        ("market_sessions", 2),
        ("pending", 0),
        ("real_orders", 1),
    ],
)
def test_rejects_mismatch_without_changing_destination(tmp_path, target, value):
    production, staging, state = _documents()
    staging["exec_paper"][target] = value
    prod_path = tmp_path / "portfolio.json"
    dev_path = tmp_path / "portfolio.dev.json"
    state_path = tmp_path / "exec_paper_state.json"
    _write(prod_path, production)
    _write(dev_path, staging)
    _write(state_path, state)
    before = prod_path.read_bytes()

    with pytest.raises(PromotionError):
        promote_exec_paper(dev_path, prod_path, state_path)

    assert prod_path.read_bytes() == before


def test_rejects_summary_from_an_older_staging_run(tmp_path):
    production, staging, state = _documents()
    staging["updated_at"] = "2026-09-04T17:10:00+09:00"
    prod_path = tmp_path / "portfolio.json"
    dev_path = tmp_path / "portfolio.dev.json"
    state_path = tmp_path / "exec_paper_state.json"
    _write(prod_path, production)
    _write(dev_path, staging)
    _write(state_path, state)
    before = prod_path.read_bytes()

    with pytest.raises(PromotionError, match="predates"):
        promote_exec_paper(dev_path, prod_path, state_path)

    assert prod_path.read_bytes() == before
