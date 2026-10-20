"""Offline health and child supervision checks."""
import asyncio
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "recovery_supervisor", Path(__file__).resolve().parents[1] / "server/member_map_refresh.py")
refresh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refresh)


def event(**changes):
    value = {"checked_at": datetime.now(timezone.utc).isoformat(), "source": "DART", "attempt": 1,
             "last_success_at": None, "status": "degraded", "error_code": "refresh-http-unavailable",
             "backoff_seconds": 120, "disabled_sources": ["SEC", "news"], "ai_calls": 0,
             "blob_writes": 0, "screen_delivery_verified": False}
    value.update(changes)
    return json.dumps(value).encode()


def test_health_accepts_only_bounded_codes_and_fields():
    refresh._STATUS.clear()
    refresh._STATUS.update(enabled=True, worker_alive=True)
    refresh._accept_event(event())
    assert refresh.status()["worker_alive"] and refresh.status()["status"] == "degraded"
    before = refresh.status()
    refresh._accept_event(event(error_code="secret=do-not-log"))
    refresh._accept_event(event(private_payload="secret=do-not-log"))
    refresh._accept_event(event(status=["success"], error_code=["refresh-http-unavailable"]))
    refresh._accept_event(event(error_code=["refresh-http-unavailable"]))
    refresh._accept_event(event(status="success", error_code=None, last_success_at=None))
    refresh._accept_event(b"x" * 3000)
    assert refresh.status() == before
    assert "secret" not in json.dumps(refresh.status())


def test_public_iso_z_success_is_normalized_and_log_is_safe(caplog):
    refresh._STATUS.clear()
    refresh._STATUS.update(enabled=True, worker_alive=True)
    stamp = datetime.now(timezone.utc).isoformat()
    caplog.set_level("INFO")
    refresh._accept_event(event(status="success", error_code=None, backoff_seconds=None,
                                last_success_at=stamp.replace("+00:00", "Z"), checked_at=stamp))
    assert refresh.status()["status"] == "healthy"
    assert refresh.status()["last_success_at"] == stamp
    assert '"source_status":"success"' in caplog.text
    refresh._accept_event(event(error_code="credential=private"))
    assert "credential" not in caplog.text


def test_reader_continues_after_malformed_value():
    refresh._STATUS.clear()
    refresh._STATUS.update(enabled=True, worker_alive=True)
    async def scenario():
        stream = asyncio.StreamReader()
        stream.feed_data(event(status=["success"]) + b"\n")
        stream.feed_data(event(status="degraded") + b"\n")
        stream.feed_eof()
        await refresh._read_events(stream)
    asyncio.run(scenario())
    assert refresh.status()["source_status"] == "degraded"


def test_source_success_is_distinct_from_process_liveness():
    refresh._STATUS.clear()
    refresh._STATUS.update(enabled=True, worker_alive=True)
    stamp = datetime.now(timezone.utc).isoformat()
    refresh._accept_event(event(status="success", error_code=None, backoff_seconds=None,
                                last_success_at=stamp, checked_at=stamp))
    assert refresh.status()["status"] == "healthy"
    assert refresh.status()["last_success_at"] == stamp
    refresh._STATUS["worker_alive"] = False
    assert refresh.status()["last_success_at"] == stamp
    assert not refresh.status()["worker_alive"]


def test_old_success_not_due_is_degraded():
    refresh._STATUS.clear()
    refresh._STATUS.update(enabled=True, worker_alive=True)
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    refresh._accept_event(event(status="not-due", error_code=None, backoff_seconds=None,
                                last_success_at=old))
    assert refresh.status()["status"] == "degraded"
    assert refresh.status()["error_code"] == "source-stale"


def test_initial_terminal_event_stops_supervision(monkeypatch):
    monkeypatch.setenv("MEMBER_MAP_LIVE_REFRESH_ENABLED", "1")
    starts = []
    async def spawn(*args, **kwargs):
        starts.append(1)
        stream = asyncio.StreamReader()
        stream.feed_data(event(attempt=0, status="failed", error_code="refresh-config-rejected",
                               backoff_seconds=None))
        stream.feed_eof()
        class Child:
            stdout = stream
            returncode = 1
            async def wait(self):
                return 1
        return Child()
    monkeypatch.setattr(refresh.asyncio, "create_subprocess_exec", spawn)
    asyncio.run(refresh.run())
    assert starts == [1]
    assert refresh.status()["status"] == "failed"
    assert refresh.status()["error_code"] == "refresh-config-rejected"


def test_early_crash_backoff_and_safe_health(monkeypatch, caplog):
    monkeypatch.setenv("MEMBER_MAP_LIVE_REFRESH_ENABLED", "1")
    delays = []
    class End(Exception):
        pass
    async def spawn(*args, **kwargs):
        raise RuntimeError("secret=do-not-log")
    async def sleep(seconds):
        delays.append(seconds)
        if len(delays) == 3:
            raise End
    monkeypatch.setattr(refresh.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(refresh.asyncio, "sleep", sleep)
    with pytest.raises(End):
        asyncio.run(refresh.run())
    assert delays == [120, 240, 300]
    assert refresh.status()["status"] == "degraded"
    assert refresh.status()["checked_at"]
    assert refresh.status()["error_code"] == "worker-unavailable"
    assert "secret" not in caplog.text + json.dumps(refresh.status())


def test_cancel_cleans_up_owned_child_and_reader(monkeypatch):
    monkeypatch.setenv("MEMBER_MAP_LIVE_REFRESH_ENABLED", "1")
    seen = {}
    async def scenario():
        started, stopped = asyncio.Event(), asyncio.Event()
        stream = asyncio.StreamReader()
        class Child:
            returncode = None
            stdout = stream
            def terminate(self):
                seen["terminated"] = True
                self.returncode = -15
                stopped.set()
            def kill(self):
                pytest.fail("responsive child should terminate")
            async def wait(self):
                await stopped.wait()
                return self.returncode
        async def spawn(*args, **kwargs):
            seen["env"] = kwargs["env"]
            started.set()
            return Child()
        monkeypatch.setattr(refresh.asyncio, "create_subprocess_exec", spawn)
        task = asyncio.create_task(refresh.run())
        await started.wait()
        stream.feed_data(event())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(scenario())
    assert seen["terminated"]
    assert "KIS_APP_KEY" not in seen["env"] and "OPENAI_API_KEY" not in seen["env"]
    assert not refresh.status()["worker_alive"]
