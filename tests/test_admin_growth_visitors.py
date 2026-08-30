"""관리자 방문자 집계의 날짜·재방문 회귀 방지."""

from datetime import datetime
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "vercel-api" / "api" / "admin.py"


def _load_admin():
    spec = importlib.util.spec_from_file_location("verity_admin_growth_test", ADMIN)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_visit_stats_counts_unique_and_returning_visitors() -> None:
    admin = _load_admin()
    now = datetime(2026, 8, 30, 12, 0, 0)
    rows = [
        {"visitor_id": "a", "visit_date": "2026-08-30", "visit_count": 1},
        {"visitor_id": "a", "visit_date": "2026-08-29", "visit_count": 2},
        {"visitor_id": "b", "visit_date": "2026-08-24", "visit_count": 1},
        {"visitor_id": "c", "visit_date": "2026-08-01", "visit_count": 1},
        {"visitor_id": "old", "visit_date": "2026-07-31", "visit_count": 9},
        {"visitor_id": "", "visit_date": "2026-08-30", "visit_count": 9},
        {"visitor_id": "bad", "visit_date": "not-a-date", "visit_count": 9},
    ]

    result = admin._visit_stats_from_rows(rows, now)

    assert result["status"] == "measured"
    assert result["today"] == 1
    assert result["d7"] == 2
    assert result["d30"] == 3
    assert result["returning_30d"] == 1
    assert result["return_rate_30d_pct"] == 33.3
    assert result["visitor_days_30d"] == 4
    assert result["visits_30d"] == 5
    assert len(result["daily"]) == 30


def test_visit_stats_empty_period_is_measured_zero() -> None:
    admin = _load_admin()
    result = admin._visit_stats_from_rows([], datetime(2026, 8, 30, 12, 0, 0))

    assert result["status"] == "measured"
    assert result["today"] == 0
    assert result["d7"] == 0
    assert result["d30"] == 0
    assert result["return_rate_30d_pct"] is None
    assert len(result["daily"]) == 30
