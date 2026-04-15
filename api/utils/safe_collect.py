"""
순차 파이프라인을 유지하면서 개별 collector에 타임아웃을 적용하는 헬퍼.

ThreadPoolExecutor(max_workers=1)로 감싸서 hang 되는 collector가
전체 파이프라인을 멈추지 못하게 한다.
"""
from __future__ import annotations

import traceback
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
    """collector 함수를 타임아웃 격리 하에 실행한다.

    Parameters
    ----------
    fn : 실행할 collector 함수
    *args, **kwargs : fn에 전달할 인자
    name : 로깅/알림에 쓰이는 이름 (없으면 fn.__name__)
    timeout : 초 단위 제한. 0이면 제한 없이 실행.
    default : 실패 시 반환할 기본값
    notify : 실패/타임아웃 시 호출할 콜백 (메시지 문자열 전달)
    """
    label = name or getattr(fn, "__name__", "unknown")
    if default is None:
        default = {}

    if timeout <= 0:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            msg = f"❌ {label} 오류: {e}"
            print(f"  {msg}")
            if notify:
                _safe_notify(notify, msg)
            return default

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            msg = f"⏱ {label} 타임아웃 ({timeout}s) — 스킵"
            print(f"  {msg}")
            if notify:
                _safe_notify(notify, msg)
            future.cancel()
            return default
        except Exception as e:
            msg = f"❌ {label} 오류: {e}"
            print(f"  {msg}")
            if notify:
                _safe_notify(notify, msg)
            return default


def _safe_notify(notify_fn: Callable[[str], None], msg: str) -> None:
    try:
        notify_fn(msg)
    except Exception:
        pass
