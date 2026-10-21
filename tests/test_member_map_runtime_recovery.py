"""Offline recovery checks for the public DART runner."""
import importlib.util
import json
from pathlib import Path

import pytest

from api.collectors.member_map_refresh_store import RefreshStoreError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("recovery_runner", ROOT / "scripts/member-map/run-live-refresh.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.mark.parametrize("code", [
    "refresh-http-unavailable", "refresh-cache-conflict", "refresh-save-conflict", "refresh-lease-lost",
])
def test_transient_read_recovers_on_next_bounded_cycle(monkeypatch, capsys, code):
    from api.collectors import member_map_refresh_store as storage
    monkeypatch.setenv("DART_API_KEY", "synthetic")
    def background_store(*, background):
        assert background is True
        return object()
    monkeypatch.setattr(storage.RefreshStore, "from_environment", background_store)
    clock = [0]
    monkeypatch.setattr(runner.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    calls = []
    def cycle(*args):
        calls.append(clock[0])
        if len(calls) == 1:
            raise RefreshStoreError(code)
        return {"status": "success", "last_success_at": "2026-10-12T01:00:00+00:00"}
    monkeypatch.setattr(runner, "supabase_cycle", cycle)
    runner.run_supabase({"stocks": []}, 121)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert calls == [0, 120]
    assert [e["status"] for e in events] == ["degraded", "success"]
    assert events[0]["backoff_seconds"] == 120
    assert events[1]["last_success_at"] == "2026-10-12T01:00:00+00:00"


def test_unknown_and_auth_errors_stop_without_repeating(monkeypatch, capsys):
    from api.collectors import member_map_refresh_store as storage
    monkeypatch.setenv("DART_API_KEY", "synthetic")
    monkeypatch.setattr(storage.RefreshStore, "from_environment", lambda **_: object())
    calls = []
    def cycle(*args):
        calls.append(1)
        raise RefreshStoreError("refresh-auth-rejected")
    monkeypatch.setattr(runner, "supabase_cycle", cycle)
    with pytest.raises(RuntimeError, match="refresh-unclassified"):
        runner.run_supabase({"stocks": []}, 1000)
    assert len(calls) == 1
    event = json.loads(capsys.readouterr().out)
    assert event["status"] == "failed" and event["error_code"] == "refresh-auth-rejected"


@pytest.mark.parametrize("failure", ["store", "key"])
def test_initial_config_failure_emits_safe_terminal_event(monkeypatch, capsys, failure):
    from api.collectors import member_map_refresh_store as storage
    def store(**_):
        if failure == "store":
            raise RefreshStoreError("refresh-config-rejected")
        return object()
    monkeypatch.setattr(storage.RefreshStore, "from_environment", store)
    monkeypatch.delenv("DART_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="refresh-unclassified"):
        runner.run_supabase({"stocks": []}, 1000)
    event = json.loads(capsys.readouterr().out)
    assert event["attempt"] == 0 and event["status"] == "failed"
    assert event["error_code"] == "refresh-config-rejected"
    assert event["disabled_sources"] == ["SEC", "news"]


def test_ambiguous_save_is_never_replayed_inside_cycle(monkeypatch):
    calls = {"collect": 0, "save": 0, "read": 0}
    class Store:
        def read_states(self):
            calls["read"] += 1
            return {"DART": {}}
        def claim(self, *_):
            return {"status": "claimed", "state": {}, "generation": 1, "revision": 0}
        def renew(self, *_):
            return {"status": "renewed"}
        def save(self, *_):
            calls["save"] += 1
            raise RefreshStoreError("refresh-transport-timeout")
    monkeypatch.setattr(runner, "build_kr_universe", lambda *_: {"123456": "synthetic"})
    def collect(*args, **kwargs):
        calls["collect"] += 1
        return {"status": "error", "complete": False, "error": "transport_failure", "requests": 0}
    monkeypatch.setattr(runner, "collect_dart_delta", collect)
    with pytest.raises(RefreshStoreError, match="refresh-transport-timeout"):
        runner.supabase_cycle(Store(), {"stocks": []}, "synthetic", "owner",
                              "2026-10-12T01:00:00+00:00")
    assert calls == {"collect": 1, "save": 1, "read": 2}


def test_exponential_delay_caps_at_five_minutes(monkeypatch, capsys):
    from api.collectors import member_map_refresh_store as storage
    monkeypatch.setenv("DART_API_KEY", "synthetic")
    monkeypatch.setattr(storage.RefreshStore, "from_environment", lambda **_: object())
    clock = [0]
    monkeypatch.setattr(runner.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    def cycle(*args):
        raise RefreshStoreError("refresh-read-timeout")
    monkeypatch.setattr(runner, "supabase_cycle", cycle)
    runner.run_supabase({"stocks": []}, 661)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [event["backoff_seconds"] for event in events] == [120, 240, 300, 300]


def test_startup_catalog_delay_does_not_advance_next_collection_tick(monkeypatch, capsys):
    from api.collectors import member_map_refresh_store as storage
    clock, starts = [0.0], []
    monkeypatch.setenv("DART_API_KEY", "synthetic")
    monkeypatch.setattr(storage.RefreshStore, "from_environment", lambda **_: object())
    monkeypatch.setattr(runner.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    def catalog():
        clock[0] += .2
        return {}
    def cycle(*args):
        starts.append(clock[0])
        clock[0] += 9
        return {"status": "success"}
    monkeypatch.setattr(storage, "read_public_catalog", catalog)
    monkeypatch.setattr(runner, "supabase_cycle", cycle)
    runner.run_supabase(None, 241)
    assert starts == pytest.approx([.2, 120.2, 240.2])


@pytest.mark.parametrize("remaining, delay", [(0, 1), (1, 1), (5, 5), (300, 300),
                                              (None, 120), (True, 120), (-1, 120), (301, 120)])
def test_not_due_wait_is_bounded_and_relative_to_response(monkeypatch, capsys, remaining, delay):
    from api.collectors import member_map_refresh_store as storage
    clock, starts = [0.0], []
    monkeypatch.setenv("DART_API_KEY", "synthetic")
    monkeypatch.setattr(storage.RefreshStore, "from_environment", lambda **_: object())
    monkeypatch.setattr(runner.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    def cycle(*args):
        starts.append(clock[0])
        clock[0] += 4  # A slow read must not consume the server's remaining wait.
        if len(starts) == 1:
            return {"status": "not-due", "retry_after_seconds": remaining}
        return {"status": "success"}
    monkeypatch.setattr(runner, "supabase_cycle", cycle)
    expected = 4 + delay if type(remaining) is int and 0 <= remaining <= 300 else 120
    runner.run_supabase({}, expected + 1)
    assert starts == [0, expected]
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [event["status"] for event in events] == ["not-due", "success"]
    assert events[0]["last_success_at"] is None


def test_early_local_tick_returns_remaining_wait_without_claim(monkeypatch):
    class Store:
        def read_states(self):
            return {"DART": {"last_attempt_at": "2026-10-12T01:00:00.200000+00:00"}}
        def claim(self, *_):
            pytest.fail("Early boundary must not reserve another request batch")
    monkeypatch.setattr(runner, "build_kr_universe", lambda *_: {"123456": "synthetic"})
    result = runner.supabase_cycle(Store(), {}, "synthetic", "owner", "2026-10-12T01:02:00+00:00")
    assert result["status"] == "not-due" and result["requests"] == 0
    assert result["retry_after_seconds"] == 1


def test_database_due_guard_delay_survives_runner_boundary(monkeypatch):
    class Store:
        def read_states(self):
            return {"DART": {}}
        def claim(self, *_):
            return {"status": "not-due", "retry_after_seconds": 2}
    monkeypatch.setattr(runner, "build_kr_universe", lambda *_: {"123456": "synthetic"})
    monkeypatch.setattr(runner, "collect_dart_delta", lambda *a, **k: pytest.fail("DB guard must prevent collection"))
    result = runner.supabase_cycle(Store(), {}, "synthetic", "owner", "2026-10-12T01:02:00+00:00")
    assert result["status"] == "not-due" and result["retry_after_seconds"] == 2
    assert result["requests"] == 0
