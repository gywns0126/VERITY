"""yfinance_safe — yahoo finance API rate limit 대응 wrapper.

배경 (2026-05-10):
  daily_analysis_full 5/10 13:11 KST run 에서 1500 stage (1880 ticker) 처리 중
  yfinance "Too Many Requests" rate limit 발생 (728/1880 시점). sequential for loop +
  retry/backoff 부재 → 한번 rate limited 되면 후속 ticker 모두 fail → SIGTERM.

설계:
  - Too Many Requests / 429 인식 → exponential backoff retry (5s/15s/30s, max 3회)
  - process-level 누적 rate limit 카운터 → 임계 초과 시 cooler pause (60s)
  - silent skip 절대 금지 (feedback_data_collection_verification_mandatory)
    : 모든 retry / pause / 최종 fail 을 stderr 명시
  - metric 적재용 dict 인자 (yf_rate_limited 카운터)

호환:
  - yfinance 라이브러리 자체 retry 약함 — wrapper 가 명시 retry
  - 429 응답을 yfinance 가 던지는 방식: Exception message 에 "Too Many Requests"
    또는 "Rate limited" string 포함. requests.HTTPError(429) 또는
    yfinance.exceptions.YFRateLimitError (≥0.2.50) 직접 catch.
"""
from __future__ import annotations

import re
import sys
import threading
import time
from typing import Any, Callable, Optional


# 2026-05-18 — Yahoo Finance 가 GitHub Actions IP 차단 (local 정상 / cloud 404).
# curl_cffi 의 browser-like TLS fingerprint (chrome impersonate) 로 anti-bot 우회.
# yfinance 1.2.0 의 session arg 통해 inject.
try:
    from curl_cffi import requests as _cffi_requests
    _YF_SESSION = _cffi_requests.Session(impersonate="chrome")
except Exception:
    _YF_SESSION = None


def yf_ticker(ticker: str):
    """yf.Ticker(ticker, session=curl_cffi) — anti-bot session inject helper.

    호출처는 `from api.collectors.yfinance_safe import yf_ticker` 후 사용.
    session 없는 경우 (curl_cffi import fail) plain yf.Ticker fallback.
    """
    import yfinance as _yf
    if _YF_SESSION is not None:
        return _yf.Ticker(ticker, session=_YF_SESSION)
    return _yf.Ticker(ticker)


# rate limit 표식 패턴 — yfinance 실제 응답 정합. negation phrase ("not rate limit") 회피.
_RL_PATTERNS = (
    re.compile(r"\btoo\s+many\s+requests\b", re.IGNORECASE),
    re.compile(r"\b429\b"),
    re.compile(r"\brate[\s\-]?limit(ed)?\b", re.IGNORECASE),
)
_RL_NEGATION = re.compile(r"\bnot\s+(?:rate|429)", re.IGNORECASE)

# ────────────────────────────────────────────────────────
# Process-level state
# ────────────────────────────────────────────────────────

_lock = threading.Lock()
_state = {
    "rate_limit_count": 0,    # 누적 rate limit 발생 건수
    "last_rate_limit_ts": 0.0,  # 직전 rate limit unix ts
    "cooler_until_ts": 0.0,   # cooler pause 끝나는 ts
}

# 운영 임계값 — Phase 2-A 1500 stage 기준
RATE_LIMIT_BACKOFF_S = (5.0, 15.0, 30.0)  # exp-ish backoff per retry
MAX_RETRIES = len(RATE_LIMIT_BACKOFF_S)
COOLER_THRESHOLD_PER_MIN = 5    # 1분 내 rate limit 5건 이상이면 cooler 발동
COOLER_PAUSE_S = 60.0
RATE_LIMIT_WINDOW_S = 60.0      # cooler threshold 측정 윈도우


def _is_rate_limit_error(e: BaseException) -> bool:
    """yfinance 의 rate limit 표식 식별. negation phrase 회피."""
    # yfinance ≥0.2.50 의 YFRateLimitError class 우선
    cls_name = type(e).__name__
    if "ratelimit" in cls_name.lower():
        return True
    msg = str(e or "")
    if not msg:
        return False
    if _RL_NEGATION.search(msg):
        return False
    return any(pat.search(msg) for pat in _RL_PATTERNS)


def _record_rate_limit() -> None:
    """rate limit 발생 기록 + cooler 발동 판단."""
    now = time.time()
    with _lock:
        _state["rate_limit_count"] += 1
        _state["last_rate_limit_ts"] = now
        # cooler — 직전 60s 내 rate limit 누적 ≥ threshold 면 process pause
        if _state["rate_limit_count"] >= COOLER_THRESHOLD_PER_MIN and (
            now - _state["cooler_until_ts"] > RATE_LIMIT_WINDOW_S
        ):
            _state["cooler_until_ts"] = now + COOLER_PAUSE_S
            sys.stderr.write(
                f"[yf_safe] COOLER 발동 — rate_limit 누적 {_state['rate_limit_count']}건, "
                f"{COOLER_PAUSE_S}s pause\n"
            )


def _wait_cooler_if_needed() -> None:
    """cooler 활성 시 그 끝까지 sleep."""
    with _lock:
        until = _state["cooler_until_ts"]
    now = time.time()
    if until > now:
        wait_s = until - now
        sys.stderr.write(f"[yf_safe] cooler wait {wait_s:.1f}s\n")
        time.sleep(wait_s)


def safe_yf_call(
    fn: Callable[[], Any],
    label: str = "",
    metrics: Optional[dict] = None,
    per_call_sleep_s: float = 0.05,
) -> Any:
    """yfinance call wrapper. rate limit retry + cooler pause + metric 적재.

    Args:
      fn: 0-arg callable (lambda 권장 — yf.Ticker(t).history(...) 등 lazy 호출).
      label: 진단 로그용 식별자 (ticker 또는 step 이름).
      metrics: 호출자 dict — yf_rate_limited 누적.
      per_call_sleep_s: 호출 직전 sleep (rate limit 예방, default 50ms).

    Returns:
      fn() 결과. 최종 fail 시 None.
    """
    _wait_cooler_if_needed()
    if per_call_sleep_s > 0:
        time.sleep(per_call_sleep_s)

    last_err: Optional[BaseException] = None
    for attempt in range(MAX_RETRIES + 1):  # 0..MAX_RETRIES (총 MAX+1 시도)
        try:
            return fn()
        except BaseException as e:
            last_err = e
            if _is_rate_limit_error(e):
                _record_rate_limit()
                if metrics is not None:
                    metrics["yf_rate_limited"] = metrics.get("yf_rate_limited", 0) + 1
                if attempt < MAX_RETRIES:
                    backoff_s = RATE_LIMIT_BACKOFF_S[attempt]
                    sys.stderr.write(
                        f"[yf_safe] rate_limited label={label} attempt={attempt + 1}/{MAX_RETRIES + 1} "
                        f"backoff={backoff_s}s\n"
                    )
                    time.sleep(backoff_s)
                    _wait_cooler_if_needed()  # cooler 활성될 수 있음
                    continue
                # 최종 fail — None 반환
                sys.stderr.write(
                    f"[yf_safe] rate_limited label={label} FINAL FAIL (after {MAX_RETRIES + 1} attempts)\n"
                )
                return None
            # rate limit 외 exception 은 retry X — 호출자 except path
            raise

    # unreachable in normal path
    if last_err and _is_rate_limit_error(last_err):
        return None
    raise last_err if last_err else RuntimeError(f"safe_yf_call({label}) unexpected end")


def get_state_snapshot() -> dict:
    """모니터링 / 테스트용. 적재 metrics 로 진단."""
    with _lock:
        return dict(_state)


def reset_state() -> None:
    """테스트용."""
    with _lock:
        _state["rate_limit_count"] = 0
        _state["last_rate_limit_ts"] = 0.0
        _state["cooler_until_ts"] = 0.0
