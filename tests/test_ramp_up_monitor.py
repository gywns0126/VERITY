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


class TestW3Wiring:
    """W3 wiring (2026-05-21) — kr_first_call_ms / rate_limit_violations 라이브 인자 통합."""

    def test_kr_first_call_and_rate_limit_persisted(self, monkeypatch, tmp_path):
        # log_run_with_estimate 가 **extra_kw 로 받은 W3 인자를 row 에 전달하는지 검증.
        monkeypatch.setattr(rm, "LOG_PATH", tmp_path / "log.jsonl")
        rm.log_run_with_estimate(
            mode="full",
            ramp_up_stage=500,
            execution_time_seconds=120.0,
            yfinance_failure_rate=0.0,
            kr_first_call_ms=842,
            rate_limit_violations=2,
        )
        rec = json.loads((tmp_path / "log.jsonl").read_text().splitlines()[-1])
        assert rec["kr_first_call_duration_ms"] == 842
        assert rec["rate_limit_violations"] == 2
        # 2 < max(3, attempted*1%) 임계 → rate_limit 트리거 미발동
        assert not any("rate_limit_exceeded" in t for t in rec["fail_triggers"])


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

    def test_time_overrun_suppressed_at_stage_0(self, monkeypatch, tmp_path):
        """Stage 0 (core 모드, ramp-up 미작동) 에서는 wall-clock overrun 으로
        알람이 발화하지 않아야 한다 — 롤백할 단계가 없어 의미 없음."""
        monkeypatch.setattr(rm, "LOG_PATH", tmp_path / "log.jsonl")
        result = rm.log_runtime_load(
            mode="quick", ramp_up_stage=0,
            execution_time_seconds=46.0,
            estimated_time_seconds=24.0,  # 91% over
        )
        assert "execution_time_50pct_overrun" not in result["fail_triggers"]
        assert result["should_alert"] is False

    def test_rate_limit_trigger_absolute_floor(self, monkeypatch, tmp_path):
        # yf_attempted 미제공 → threshold = max(3, 0) = 3. 3 violations = trigger.
        monkeypatch.setattr(rm, "LOG_PATH", tmp_path / "log.jsonl")
        result = rm.log_runtime_load(
            mode="full", ramp_up_stage=5000,
            execution_time_seconds=300.0,
            rate_limit_violations=3,
        )
        assert any("rate_limit_exceeded" in t for t in result["fail_triggers"])

    def test_rate_limit_ratio_suppresses_5000_universe(self, monkeypatch, tmp_path):
        # 2026-05-25 RULE 7: 5000 universe (~1869 attempted) 에서 12 violations = 0.64%.
        # max(3, 1869*0.01=18) = 18. 12 < 18 → trigger 미발동 (chronic alarm 차단).
        monkeypatch.setattr(rm, "LOG_PATH", tmp_path / "log.jsonl")
        result = rm.log_runtime_load(
            mode="full", ramp_up_stage=5000,
            execution_time_seconds=983.5,
            rate_limit_violations=12,
            extra={"yf_attempted": 1869, "yf_failed": 1},
        )
        assert not any("rate_limit_exceeded" in t for t in result["fail_triggers"])

    def test_rate_limit_ratio_triggers_real_burst(self, monkeypatch, tmp_path):
        # 5000 universe 에서 20 violations / 1869 = 1.07% = 진짜 폭주 → trigger.
        monkeypatch.setattr(rm, "LOG_PATH", tmp_path / "log.jsonl")
        result = rm.log_runtime_load(
            mode="full", ramp_up_stage=5000,
            execution_time_seconds=1100.0,
            rate_limit_violations=20,
            extra={"yf_attempted": 1869, "yf_failed": 5},
        )
        assert any("rate_limit_exceeded" in t for t in result["fail_triggers"])

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


class TestStageScopedBaseline:
    """log_run_with_estimate baseline = 같은 stage 이전 run 만 (2026-05-09 fix)."""

    def test_baseline_excludes_other_stages(self, monkeypatch, tmp_path):
        """stage 1500 baseline 은 stage 500 historical 평균 무시."""
        log_path = tmp_path / "runtime_load_log.jsonl"
        from api.observability import ramp_up_monitor as m
        monkeypatch.setattr(m, "LOG_PATH", log_path)

        # Seed: stage 500 이전 5회 (50s 평균), stage 1500 이전 0건
        for i in range(5):
            m.log_runtime_load(mode="full", ramp_up_stage=500,
                               execution_time_seconds=50.0, estimated_time_seconds=None)

        # stage 1500 첫 run 163.9s — 같은 stage baseline 0건이라 estimated=None
        # 기존 결함이면 stage 500 평균 50s 대비 163.9 = 3.27x → overrun 트리거
        # fix 후엔 estimated=None → 알람 비활성
        out = m.log_run_with_estimate(
            mode="full", ramp_up_stage=1500, execution_time_seconds=163.9
        )
        # 디스크 마지막 row 확인
        rows = log_path.read_text().strip().splitlines()
        last = json.loads(rows[-1])
        assert last["ramp_up_stage"] == 1500
        assert last["estimated_time_seconds"] is None
        assert "execution_time_50pct_overrun" not in last["fail_triggers"]

    def test_baseline_uses_same_stage_average(self, monkeypatch, tmp_path):
        """stage 1500 이전 같은 stage 5회 누적 후 baseline 활성."""
        log_path = tmp_path / "runtime_load_log.jsonl"
        from api.observability import ramp_up_monitor as m
        monkeypatch.setattr(m, "LOG_PATH", log_path)

        # 노이즈: stage 500 이전 5회 (50s) — fix 후 baseline 에서 무시되어야
        for _ in range(5):
            m.log_runtime_load(mode="full", ramp_up_stage=500,
                               execution_time_seconds=50.0, estimated_time_seconds=None)
        # 진짜 baseline: stage 1500 이전 5회 (160s 평균)
        for _ in range(5):
            m.log_runtime_load(mode="full", ramp_up_stage=1500,
                               execution_time_seconds=160.0, estimated_time_seconds=None)

        # stage 1500 추가 run 163.9s — 1.5x 임계 = 240s. 163.9 < 240 → no overrun
        m.log_run_with_estimate(
            mode="full", ramp_up_stage=1500, execution_time_seconds=163.9
        )
        rows = log_path.read_text().strip().splitlines()
        last = json.loads(rows[-1])
        assert last["estimated_time_seconds"] == 160.0  # stage 1500 5회 평균
        assert "execution_time_50pct_overrun" not in last["fail_triggers"]

    def test_baseline_triggers_when_truly_overrun_at_same_stage(self, monkeypatch, tmp_path):
        """같은 stage baseline 대비 진짜 1.5x 초과 시만 트리거."""
        log_path = tmp_path / "runtime_load_log.jsonl"
        from api.observability import ramp_up_monitor as m
        monkeypatch.setattr(m, "LOG_PATH", log_path)

        for _ in range(5):
            m.log_runtime_load(mode="full", ramp_up_stage=1500,
                               execution_time_seconds=100.0, estimated_time_seconds=None)
        # 161s = 1.61x → 1.5x 임계 초과 → 트리거
        m.log_run_with_estimate(
            mode="full", ramp_up_stage=1500, execution_time_seconds=161.0
        )
        rows = log_path.read_text().strip().splitlines()
        last = json.loads(rows[-1])
        assert last["estimated_time_seconds"] == 100.0
        assert "execution_time_50pct_overrun" in last["fail_triggers"]
