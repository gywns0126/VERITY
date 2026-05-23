"""dart_metrics 회귀 가드 (W3 4/4, 2026-05-23).

검증:
  1. DART status 분류 (성공 화이트리스트 000/013 / 그 외 실패 / 011·020 rate_limited)
  2. compute_dart_failure_rate (attempted=0 → 0.0)
  3. stock_filter._log_w1_runtime 통합 — dart_metrics drain + jsonl 적재
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from api.observability.dart_metrics import (
    compute_dart_failure_rate,
    get_dart_snapshot,
    record_dart_call,
    reset_dart_state,
)


@pytest.fixture(autouse=True)
def _reset_state():
    reset_dart_state()
    yield
    reset_dart_state()


def test_empty_state_returns_zero():
    assert compute_dart_failure_rate() == 0.0
    assert get_dart_snapshot() == {
        "dart_attempted": 0,
        "dart_failed": 0,
        "dart_rate_limited": 0,
    }


def test_success_statuses_no_failure():
    record_dart_call("000")
    record_dart_call("000")
    record_dart_call("013")  # 데이터없음 = 성공
    snap = get_dart_snapshot()
    assert snap == {"dart_attempted": 3, "dart_failed": 0, "dart_rate_limited": 0}
    assert compute_dart_failure_rate() == 0.0


def test_rate_limit_counts_in_both_buckets():
    record_dart_call("000")
    record_dart_call("020")
    record_dart_call("011")
    snap = get_dart_snapshot()
    assert snap == {"dart_attempted": 3, "dart_failed": 2, "dart_rate_limited": 2}
    assert abs(compute_dart_failure_rate() - 2 / 3) < 1e-9


def test_timeout_error_sentinels_count_as_failure():
    record_dart_call("000")
    record_dart_call("timeout")
    record_dart_call("error")
    record_dart_call("900")
    snap = get_dart_snapshot()
    assert snap == {"dart_attempted": 4, "dart_failed": 3, "dart_rate_limited": 0}


def test_unknown_status_counts_as_failure():
    record_dart_call("")
    record_dart_call(None)  # type: ignore[arg-type]
    snap = get_dart_snapshot()
    assert snap == {"dart_attempted": 2, "dart_failed": 2, "dart_rate_limited": 0}


def test_log_w1_runtime_drains_dart_metrics(monkeypatch):
    """stock_filter._log_w1_runtime 가 dart_metrics 를 jsonl 에 적재하는지."""
    # 텔레그램 차단 (테스트 격리)
    monkeypatch.setenv("VERITY_MODE", "dev")

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
        with patch("api.observability.ramp_up_monitor.LOG_PATH", tmp_path):
            from api.analyzers.stock_filter import _log_w1_runtime

            record_dart_call("000")
            record_dart_call("000")
            record_dart_call("020")  # rate limit fail
            record_dart_call("900")  # generic fail

            _log_w1_runtime(
                stage=500,
                elapsed=42.0,
                market_scope="all",
                metrics={
                    "yf_failure_rate": 0.0,
                    "yf_attempted": 100,
                    "yf_failed": 0,
                    "yf_rate_limited": 0,
                    "kr_first_call_ms": 500,
                },
            )

            lines = tmp_path.read_text().strip().splitlines()
            assert lines, "expected at least one jsonl entry"
            rec = json.loads(lines[-1])

            assert abs(rec["dart_failure_rate"] - 0.5) < 1e-9
            assert "dart_fail_rate>5%" in rec["fail_triggers"]
            assert rec["extra"]["dart_attempted"] == 4
            assert rec["extra"]["dart_failed"] == 2
            assert rec["extra"]["dart_rate_limited"] == 1
    finally:
        os.unlink(tmp_path)


def test_dartscout_call_records_status(monkeypatch):
    """DartScout._call 이 success/fail 양쪽 모두 record_dart_call 호출하는지."""
    import api.collectors.DartScout as ds

    class _FakeResp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    # API_DELAY=0.5 sleep skip
    monkeypatch.setattr(ds.time, "sleep", lambda *_a, **_k: None)

    # 1) 성공 ("000")
    monkeypatch.setattr(ds._SESSION, "get", lambda *a, **kw: _FakeResp({"status": "000", "list": [{"x": 1}]}))
    out = ds._call("list.json", {"corp_code": "X"})
    assert out["status"] == "000"
    assert get_dart_snapshot()["dart_attempted"] == 1
    assert get_dart_snapshot()["dart_failed"] == 0

    # 2) 데이터없음 ("013") = 성공
    monkeypatch.setattr(ds._SESSION, "get", lambda *a, **kw: _FakeResp({"status": "013"}))
    out = ds._call("list.json", {"corp_code": "X"})
    assert out["status"] == "013"
    snap = get_dart_snapshot()
    assert snap["dart_attempted"] == 2 and snap["dart_failed"] == 0

    # 3) Rate limit ("020")
    monkeypatch.setattr(ds._SESSION, "get", lambda *a, **kw: _FakeResp({"status": "020", "message": "rate"}))
    out = ds._call("list.json", {"corp_code": "X"})
    assert out["status"] == "020"
    snap = get_dart_snapshot()
    assert snap["dart_attempted"] == 3
    assert snap["dart_failed"] == 1
    assert snap["dart_rate_limited"] == 1
