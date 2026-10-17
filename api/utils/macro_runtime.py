"""Shared cooperative budget and safe stage timing for macro collection."""
from contextlib import contextmanager
from contextvars import ContextVar
import sys
import time

_DEADLINE = ContextVar("macro_collection_deadline", default=None)


class CollectionDeadline(TimeoutError):
    pass


@contextmanager
def collection_budget(seconds):
    parent = _DEADLINE.get()
    deadline = time.monotonic() + max(0, seconds)
    token = _DEADLINE.set(min(parent, deadline) if parent is not None else deadline)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def request_timeout(default):
    """Do not start another request after the shared collection budget expires.

    Socket timeouts are not a hard wall-clock kill of a running response.
    """
    deadline = _DEADLINE.get()
    if deadline is None:
        return default
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise CollectionDeadline("macro collection budget exhausted")
    return min(default, remaining)


def timed_source(label, fn):
    """Labels contain only fixed source identifiers, never URLs, keys or bodies."""
    started = time.monotonic()
    sys.stderr.write(f"[macro_source] source={label} phase=start\n")
    outcome = "returned"
    try:
        request_timeout(1)
        return fn()
    except CollectionDeadline:
        outcome = "deadline"
        raise
    except Exception as error:
        outcome = type(error).__name__
        raise
    finally:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        sys.stderr.write(f"[macro_source] source={label} phase=end outcome={outcome} elapsed_ms={elapsed_ms}\n")
