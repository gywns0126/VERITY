"""Shared cooperative budget and safe stage timing for macro collection."""
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from concurrent.futures import ThreadPoolExecutor, wait
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


def bounded_sources(sources, *, timeout, max_workers=1, reserve=0):
    """Return completed source results without waiting for late socket threads.

    Callers run inside the builder's disposable process: its hard deadline and
    process-group cleanup remain responsible for stopping late work. Contexts
    are copied per task so queued requests inherit the same parent deadline.
    """
    try:
        timeout = max(0, request_timeout(timeout + reserve) - reserve)
    except CollectionDeadline:
        timeout = 0
    if not sources or timeout <= 0:
        return {}

    def collect(fn):
        with collection_budget(timeout):
            return fn()

    executor = ThreadPoolExecutor(max_workers=max_workers)
    futures = {executor.submit(copy_context().run, collect, fn): label
               for label, fn in sources.items()}
    try:
        done, _ = wait(futures, timeout=timeout)
        results = {}
        for future in done:
            label = futures[future]
            try:
                results[label] = future.result()
            except Exception as error:
                sys.stderr.write(f"[macro_source] source={label} outcome={type(error).__name__}\n")
        for future in futures.keys() - done:
            sys.stderr.write(f"[macro_source] source={futures[future]} outcome=deadline\n")
        return results
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
