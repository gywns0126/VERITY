import pytest

from api.vams.engine import _assert_exit_state_matches_ledger


def _portfolio(*tickers):
    return {"vams": {"holdings": [{"ticker": t, "quantity": 5} for t in tickers]}}


def test_stale_portfolio_after_committed_sell_is_rejected():
    history = [
        {"type": "BUY", "ticker": "204610", "quantity": 83, "date": "2026-06-26"},
        {"type": "SELL", "ticker": "204610", "quantity": 83,
         "pnl": 64633, "date": "2026-08-13 08:40"},
    ]

    with pytest.raises(RuntimeError, match="204610"):
        _assert_exit_state_matches_ledger(_portfolio("204610"), history)


def test_open_position_is_allowed():
    history = [
        {"type": "BUY", "ticker": "204610", "quantity": 83, "date": "2026-06-26"},
        {"type": "PARTIAL_SELL", "ticker": "204610", "sold_qty": 35,
         "partial_pnl": 1000, "date": "2026-08-07"},
    ]

    _assert_exit_state_matches_ledger(_portfolio("204610"), history)


def test_new_install_without_history_is_allowed():
    _assert_exit_state_matches_ledger(_portfolio("NEW"), [])
