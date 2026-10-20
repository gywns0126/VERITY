"""Offline lifecycle checks; never import/start the broker or access the network."""
import asyncio
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "public_refresh_supervisor", Path(__file__).resolve().parents[1] / "server/member_map_refresh.py")
refresh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(refresh)


@pytest.mark.parametrize("flag", ["0", "", "true"])
def test_disabled_never_spawns_a_process(monkeypatch, flag):
    monkeypatch.setenv("MEMBER_MAP_LIVE_REFRESH_ENABLED", flag)
    async def forbidden(*args, **kwargs):
        pytest.fail("disabled worker spawned")
    monkeypatch.setattr(refresh.asyncio, "create_subprocess_exec", forbidden)
    asyncio.run(refresh.run())
    assert refresh.status() == {"enabled": False, "worker_alive": False}


def test_opt_in_child_is_data_only_and_shutdown_is_owned(monkeypatch):
    monkeypatch.setenv("MEMBER_MAP_LIVE_REFRESH_ENABLED", "1")
    for key in ("DART_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
                "OPENAI_API_KEY", "KIS_APP_KEY", "KIS_APP_SECRET", "ORDER_SECRET"):
        monkeypatch.setenv(key, "synthetic-" + key)
    seen = {}
    async def scenario():
        started, finished = asyncio.Event(), asyncio.Event()
        class Child:
            returncode = None
            def terminate(self):
                seen["terminated"] = True
                self.returncode = -15
                finished.set()
            def kill(self):
                pytest.fail("responsive child was killed")
            async def wait(self):
                await finished.wait()
                return self.returncode
        async def spawn(*command, **kwargs):
            seen.update(command=command, **kwargs)
            started.set()
            return Child()
        monkeypatch.setattr(refresh.asyncio, "create_subprocess_exec", spawn)
        task = asyncio.create_task(refresh.run())
        await started.wait()
        assert refresh.status()["worker_alive"]
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(scenario())
    assert seen["terminated"]
    assert seen["command"][2:] == (
        "--backend", "supabase", "--sources", "DART", "--execute-public",
        "--duration-seconds", "86400")
    assert set(seen["env"]) <= {"PATH", "LANG", "PYTHONUNBUFFERED", "PYTHONPATH",
                                  "DART_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"}
    assert refresh.status() == {"enabled": True, "worker_alive": False}
    copy = refresh.status(); copy["enabled"] = False
    assert refresh.status()["enabled"]


def test_failed_start_has_fixed_log_and_bounded_backoff(monkeypatch, caplog):
    monkeypatch.setenv("MEMBER_MAP_LIVE_REFRESH_ENABLED", "1")
    class End(Exception):
        pass
    seen = []
    async def spawn(*args, **kwargs):
        raise RuntimeError("private-key-not-for-logs")
    async def sleep(seconds):
        seen.append(seconds)
        raise End
    monkeypatch.setattr(refresh.asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(refresh.asyncio, "sleep", sleep)
    with pytest.raises(End):
        asyncio.run(refresh.run())
    assert seen == [120]
    assert "private-key-not-for-logs" not in caplog.text
    assert "worker-unavailable" in caplog.text
    assert not refresh.status()["worker_alive"]
