"""Order policy database rollout must remain expansion-contract and fail closed."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPAND = ROOT / "supabase" / "migrations" / "035_order_policy_ledger.sql"
CONTRACT = ROOT / "supabase" / "migrations" / "036_retire_legacy_order_reservation_rpc.sql"


def test_expand_phase_does_not_delete_legacy_objects() -> None:
    sql = EXPAND.read_text(encoding="utf-8").upper()
    assert "DROP FUNCTION" not in sql
    assert "DROP CONSTRAINT" not in sql
    assert "P_POLICY_SNAPSHOT JSONB" in sql
    assert "INSERT INTO PUBLIC.ORDER_RESERVATIONS" in sql


def test_contract_phase_keeps_old_signature_as_fail_closed_stub() -> None:
    sql = CONTRACT.read_text(encoding="utf-8").upper()
    assert "DROP FUNCTION" not in sql
    assert "P_ORDER_HASH TEXT" in sql and "P_DAILY_LIMIT INTEGER" in sql
    assert "RAISE EXCEPTION" in sql
    assert "LEGACY ORDER RESERVATION RPC DISABLED" in sql
