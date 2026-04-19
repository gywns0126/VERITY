"""
순차 파이프라인을 유지하면서 개별 collector에 타임아웃을 적용하는 헬퍼.

ThreadPoolExecutor(max_workers=1)로 감싸서 hang 되는 collector가
전체 파이프라인을 멈추지 못하게 한다.

주의: `with executor` 컨텍스트 매니저를 쓰면 TimeoutError 후에도
shutdown(wait=True)가 호출되어 타임아웃이 무의미해진다.
명시적 shutdown(wait=False, cancel_futures=True)로 즉시 반환 보장.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Callable

_DEFAULT_TIMEOUT = 60


def safe_collect(
    fn: Callable[..., Any],
    *args: Any,
    name: str = "",
    timeout: int = _DEFAULT_TIMEOUT,
    default: Any = None,
    notify: Callable[[str], None] | None = None,
    **kwargs: Any,
) -> Any:
    label = name or getattr(fn, "__name__", "unknown")
    if default is None:
        default = {}

    if timeout <= 0:
        try:
            result = fn(*args, **kwargs)
            return result if result is not None else default
        except Exception as e:
            msg = f"❌ {label} 오류: {e}"
            print(f"  {msg}")
            if notify:
                _safe_notify(notify, msg)
            return default

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn, *args, **kwargs)
    try:
        result = future.result(timeout=timeout)
        executor.shutdown(wait=False)
        return result if result is not None else default
    except TimeoutError:
        msg = f"⏱ {label} 타임아웃 ({timeout}s) — 스킵"
        print(f"  {msg}")
        if notify:
            _safe_notify(notify, msg)
        executor.shutdown(wait=False, cancel_futures=True)
        return default
    except Exception as e:
        msg = f"❌ {label} 오류: {e}"
        print(f"  {msg}")
        if notify:
            _safe_notify(notify, msg)
        executor.shutdown(wait=False)
        return default


def _safe_notify(notify_fn: Callable[[str], None], msg: str) -> None:
    try:
        notify_fn(msg)
    except Exception:
        pass
