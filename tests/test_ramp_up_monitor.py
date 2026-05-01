"""ramp_up_monitor 단위 테스트 (Phase 2-A)."""
from __future__ import annotations

import json
from pathlib import Path

from api.observability import ramp_up_monitor as rm


class TestLogRuntimeLoad:
    def test_basic_log(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rm, "LOG_PATH", tmp_path / "runtime_load_log.jsonl")
        result = rm.log_runtime_load(
            mode="full",
            ramp_up_stage=500,
            execution_time_seconds=120.5,
            yfinance_failure_rate=0.001,
            kr_max_workers_used=30,
            us_max_workers_used=50,
        )
        assert result["logged"] is True
        assert result["fail_triggers"] == []
        assert result["should_alert"] is False
        # file exists with 1 line
        lines = (tmp_path / "runtime_load_log.jsonl").read_text().splitlines()
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["mode"] == "full"
        assert rec["ramp_up_stage"] == 500


class TestFailTriggers:
    def test_yfinance_fail_rate_trigger(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rm, "LOG_PATH", tmp_path / "log.jsonl")
        result = rm.log_runtime_load(
            mode="full", ramp_up_stage=1500,
            execution_time_seconds=180.0,
            yfinance_failure_rate=0.10,  # 10% > 5%
        )
        assert "yfinance_fail_rate>5%" in result["fail_triggers"]
        assert result["should_alert"] is True

    def test_dart_fail_rate_trigger(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rm, "LOG_PATH", tmp_path / "log.jsonl")
        result = rm.log_runtime_load(
            mode="full", ramp_up_stage=1500,
            execution_time_seconds=180.0,
            dart_failure_rate=0.08,
        )
        assert "dart_fail_rate>5%" in result["fail_triggers"]

    def test_time_overrun_trigger(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rm, "LOG_PATH", tmp_path / "log.jsonl")
        result = rm.log_runtime_load(
            mode="full", ramp_up_stage=3000,
            execution_time_seconds=400.0,
            estimated_time_seconds=200.0,  # 100% over → > 50%
        )
        assert "execution_time_50pct_overrun" in result["fail_triggers"]

    def test_rate_limit_trigger(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rm, "LOG_PATH", tmp_path / "log.jsonl")
        result = rm.log_runtime_load(
            mode="full", ramp_up_stage=5000,
            execution_time_seconds=300.0,
            rate_limit_violations=3,
        )
        assert "rate_limit_3_consecutive" in result["fail_triggers"]

    def test_multiple_triggers(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rm, "LOG_PATH", tmp_path / "log.jsonl")
        result = rm.log_runtime_load(
            mode="full", ramp_up_stage=5000,
            execution_time_seconds=600.0,
            estimated_time_seconds=200.0,
            yfinance_failure_rate=0.07,
            rate_limit_violations=5,
        )
        assert len(result["fail_triggers"]) >= 3


class TestStageHelpers:
    def test_default_stage_500(self, monkeypatch):
        monkeypatch.delenv("UNIVERSE_RAMP_UP_STAGE", raising=False)
        assert rm.get_current_stage_from_env() == 500

    def test_valid_stages(self, monkeypatch):
        for stage in (500, 1500, 3000, 5000):
            monkeypatch.setenv("UNIVERSE_RAMP_UP_STAGE", str(stage))
            assert rm.get_current_stage_from_env() == stage

    def test_invalid_stage_falls_back_to_500(self, monkeypatch):
        monkeypatch.setenv("UNIVERSE_RAMP_UP_STAGE", "777")
        assert rm.get_current_stage_from_env() == 500

    def test_auto_disabled_default(self, monkeypatch):
        monkeypatch.delenv("UNIVERSE_RAMP_UP_AUTO", raising=False)
        assert rm.is_auto_rampup_disabled() is True

    def test_auto_enabled(self, monkeypatch):
        monkeypatch.setenv("UNIVERSE_RAMP_UP_AUTO", "True")
        assert rm.is_auto_rampup_disabled() is False


class TestRecentRuns:
    def test_empty_returns_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rm, "LOG_PATH", tmp_path / "absent.jsonl")
        assert rm.get_recent_runs() == []

    def test_returns_recent(self, monkeypatch, tmp_path):
        log = tmp_path / "log.jsonl"
        monkeypatch.setattr(rm, "LOG_PATH", log)
        for i in range(5):
            rm.log_runtime_load(mode="full", ramp_up_stage=500, execution_time_seconds=float(i))
        recent = rm.get_recent_runs(limit=3)
        assert len(recent) == 3
        assert recent[-1]["execution_time_seconds"] == 4.0
