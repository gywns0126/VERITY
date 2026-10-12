"""Optional public-only refresh child; independent of the price relay workers."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
import sys

_LOGGER = logging.getLogger(__name__)
_STATUS = {"enabled": False, "worker_alive": False}
_ROOT = Path(__file__).resolve().parents[1]


def status():
    """No credentials, cursors, source bodies or member identifiers in health."""
    return _STATUS.copy()


async def run():
    """Supervise only our child; preserve existing WS and KIS lifecycle."""
    enabled = os.environ.get("MEMBER_MAP_LIVE_REFRESH_ENABLED") == "1"
    _STATUS.update(enabled=enabled, worker_alive=False)
    if not enabled:
        return
    # The data worker must not inherit broker, trading or AI credentials.
    child_env = {key: os.environ[key] for key in (
        "PATH", "LANG", "DART_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"
    ) if key in os.environ}
    child_env.update(PYTHONUNBUFFERED="1", PYTHONPATH=str(_ROOT))
    command = (sys.executable, str(_ROOT / "scripts/member-map/run-live-refresh.py"),
               "--backend", "supabase", "--sources", "DART", "--execute-public",
               "--duration-seconds", "86400")
    while True:
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command, cwd=str(_ROOT), env=child_env)
            _STATUS["worker_alive"] = True
            code = await process.wait()
            _LOGGER.warning("member map refresh child stopped [exit=%s]", code)
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.warning("member map refresh child unavailable [worker-unavailable]")
        finally:
            _STATUS["worker_alive"] = False
            if process is not None and process.returncode is None:
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=10)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass
        # Database lease/cursor/quota are retained across this restart.
        await asyncio.sleep(30)
