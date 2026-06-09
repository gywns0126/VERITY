"""
Ramp-up Monitor — Phase 2-A 운영 가드 2 (2026-05-01)

매 cron 실행 시 다음 기록:
  - 현재 ramp-up 단계 (UNIVERSE_RAMP_UP_STAGE)
  - 실행 시간, 실패율, max_workers 사용값, cache_hit_rate
  - rate_limit_violations, kr_first_call_ms

실패 트리거 도달 시 텔레그램 CRITICAL + 자동 이전 단계 롤백 신호.

실패 트리거 (메모리 결정 4):
  - yfinance 실패율 > 5%
  - DART 실패율 > 5%
  - 실행 시간 추정값 대비 50% 초과
  - IP 차단 의심 신호 (rate_limit_violations >= 3)

rollback 자체는 사용자 수동 (UNIVERSE_RAMP_UP_AUTO=False 가 메모리 결정 4 의 "자동 ramp-up 금지").
모니터는 알림과 신호만 발생.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

LOG_PATH = Path("data/metadata/runtime_load_log.jsonl")

# 실패 트리거 임계 (결정 4)
FAIL_TRIGGER_YFINANCE_FAIL_RATE = 0.05
FAIL_TRIGGER_DART_FAIL_RATE = 0.05
FAIL_TRIGGER_TIME_OVERRUN_PCT = 0.50  # 추정 대비 +50%
FAIL_TRIGGER_RATE_LIMIT_HITS = 3       # 최소 절대값 (작은 universe 가드)
FAIL_TRIGGER_RATE_LIMIT_RATIO = 0.01   # yf_attempted 대비 1% (5000 universe scaling, 2026-05-25 RULE 7)
# dart_attempted < N 시 fail_rate trigger 비활성 (2026-05-29 RULE 7 PM 옵션 A 승인).
# post_main_dart_drain entry (N=수~수십) 가 1 실패로 16% 에 도달해 5/27, 5/28 매일 false positive
# 알람 양산. 실 universe_scan all (N≥1869) 은 0.0% 멀쩡. binomial CI 정합 — N<100 시
# 5% 임계는 통계 무의미 (CI ±10%p 이상).
FAIL_TRIGGER_DART_MIN_SAMPLE = 100


def _now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat()


def log_runtime_load(
    *,
    mode: str,
    ramp_up_stage: int,
    execution_time_seconds: float,
    yfinance_failure_rate: float = 0.0,
    dart_failure_rate: float = 0.0,
    kr_max_workers_used: int = 0,
    kr_first_call_ms: int = 0,
    cache_hit_rate: float = 0.0,
    us_max_workers_used: int = 0,
    rate_limit_violations: int = 0,
    estimated_time_seconds: Optional[float] = None,
    extra: Optional[dict] = None,
) -> dict:
    """runtime_load_log.jsonl 1줄 append + 실패 트리거 검사.

    Returns:
        {
          "logged": True,
          "fail_triggers": [list of str],  # 발동된 트리거
          "should_alert": bool,
        }
    """
    fail_triggers: list[str] = []
    dart_attempted_for_threshold = 0
    if extra and isinstance(extra, dict):
        try:
            dart_attempted_for_threshold = int(extra.get("dart_attempted", 0) or 0)
        except (TypeError, ValueError):
            dart_attempted_for_threshold = 0
    if yfinance_failure_rate > FAIL_TRIGGER_YFINANCE_FAIL_RATE:
        fail_triggers.append(f"yfinance_fail_rate>{FAIL_TRIGGER_YFINANCE_FAIL_RATE*100:.0f}%")
    if (
        dart_failure_rate > FAIL_TRIGGER_DART_FAIL_RATE
        and dart_attempted_for_threshold >= FAIL_TRIGGER_DART_MIN_SAMPLE
    ):
        fail_triggers.append(f"dart_fail_rate>{FAIL_TRIGGER_DART_FAIL_RATE*100:.0f}%")
    # Stage 0 = core 모드 (Phase 2-A 미작동). 롤백할 단계가 없으므로 wall-clock
    # overrun 알람은 의미 없는 노이즈. 실제 ramp-up 활성 (stage > 0) 일 때만 발화.
    # 2026-05-04: stage=0 에서 두 번 false positive (07:38, 21:21) 후 게이트 추가.
    if (
        ramp_up_stage > 0
        and estimated_time_seconds
        and execution_time_seconds > estimated_time_seconds * (1 + FAIL_TRIGGER_TIME_OVERRUN_PCT)
    ):
        fail_triggers.append("execution_time_50pct_overrun")
    yf_attempted_for_threshold = 0
    if extra and isinstance(extra, dict):
        try:
            yf_attempted_for_threshold = int(extra.get("yf_attempted", 0) or 0)
        except (TypeError, ValueError):
            yf_attempted_for_threshold = 0
    rate_limit_threshold = max(
        FAIL_TRIGGER_RATE_LIMIT_HITS,
        int(yf_attempted_for_threshold * FAIL_TRIGGER_RATE_LIMIT_RATIO),
    )
    if rate_limit_violations >= rate_limit_threshold:
        fail_triggers.append(
            f"rate_limit_exceeded_{rate_limit_violations}/{yf_attempted_for_threshold}"
        )

    # KR cascade 측정 보정계수 (참고용)
    kr_corrected_factor = 12.16  # run 25210604760 측정

    rec = {
        "run_id": _now_iso(),
        "mode": mode,
        "ramp_up_stage": ramp_up_stage,
        "execution_time_seconds": round(execution_time_seconds, 2),
        "yfinance_failure_rate": round(yfinance_failure_rate, 4),
        "dart_failure_rate": round(dart_failure_rate, 4),
        "kr_max_workers_used": kr_max_workers_used,
        "kr_first_call_duration_ms": kr_first_call_ms,
        "cache_hit_rate": round(cache_hit_rate, 4),
        "kr_corrected_factor": kr_corrected_factor,
        "us_max_workers_used": us_max_workers_used,
        "rate_limit_violations": rate_limit_violations,
        "fail_triggers": fail_triggers,
        "estimated_time_seconds": estimated_time_seconds,
    }
    if extra:
        rec["extra"] = extra

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    should_alert = len(fail_triggers) > 0

    # Telegram 발송 (있을 때만, 테스트 환경에서는 스킵)
    if should_alert and os.environ.get("VERITY_MODE") != "dev":
        try:
            from api.notifications.telegram import send_message
            text = (
                f"🚨 <b>Ramp-up Monitor — 실패 트리거 발동</b>\n"
                f"stage: {ramp_up_stage}\n"
                f"triggers: {', '.join(fail_triggers)}\n"
                f"yf_fail: {yfinance_failure_rate:.2%} / dart_fail: {dart_failure_rate:.2%}\n"
                f"exec_time: {execution_time_seconds:.1f}s\n"
                f"rate_limit_violations: {rate_limit_violations}\n"
                f"\n조치: UNIVERSE_RAMP_UP_STAGE 이전 단계로 수동 롤백 (자동 금지)"
            )
            send_message(text)
        except Exception:
            pass
    elif (not fail_triggers
          and ramp_up_stage > 0
          and os.environ.get("VERITY_MODE") != "dev"):
        # 자동 dismiss — 직전 run 알람 있었고 이번 정상 복귀 시 1회 발송.
        # 2026-05-09 추가됨 (사용자 false positive 알람 dismiss 자동화 요청).
        # 2026-05-27 fix — same market_scope entry 만 prev 비교 (post_main_dart_drain
        # entry 추가 후 cross-entry mismatch 회피, project_dart_drain_gap_2026_05_25 후속).
        # run_id 비교 추가 (옛 `is not rec` 는 file re-read 시 다른 object 라 항상 True).
        try:
            cur_scope = (rec.get("extra") or {}).get("market_scope")
            prev_runs = [
                r for r in get_recent_runs(limit=10)
                if r.get("run_id") != rec.get("run_id")
                and (r.get("extra") or {}).get("market_scope") == cur_scope
            ][:3]
            if prev_runs and prev_runs[0].get("fail_triggers"):
                from api.notifications.telegram import send_message
                prev_triggers = ", ".join(prev_runs[0]["fail_triggers"])
                dismiss_text = (
                    f"<b>Ramp-up Monitor — 정상 복귀</b>\n"
                    f"stage: {ramp_up_stage}\n"
                    f"이전 triggers: {prev_triggers} (dismiss)\n"
                    f"이번 exec_time: {execution_time_seconds:.1f}s\n"
                    f"yf_fail: {yfinance_failure_rate:.2%} / dart_fail: {dart_failure_rate:.2%}\n"
                    f"\n조치: 추가 작업 없음 (이전 알람은 운영 정상화로 해소)"
                )
                send_message(dismiss_text)
        except Exception:
            pass

    return {
        "logged": True,
        "fail_triggers": fail_triggers,
        "should_alert": should_alert,
        "rec": rec,
    }


def get_recent_runs(limit: int = 20) -> list[dict]:
    """최근 N개 실행 기록 반환 (모니터링/디버깅용)."""
    if not LOG_PATH.exists():
        return []
    with LOG_PATH.open() as f:
        lines = f.readlines()
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def get_current_stage_from_env() -> int:
    """환경변수 UNIVERSE_RAMP_UP_STAGE 조회. 미설정 시 500 (Stage 1)."""
    raw = os.environ.get("UNIVERSE_RAMP_UP_STAGE", "500").strip()
    try:
        v = int(raw)
        if v not in (500, 1500, 3000, 5000):
            return 500  # 비정상 값은 Stage 1 fallback
        return v
    except ValueError:
        return 500


def is_auto_rampup_disabled() -> bool:
    """UNIVERSE_RAMP_UP_AUTO=False 가 결정 4 의 "자동 ramp-up 금지"."""
    raw = os.environ.get("UNIVERSE_RAMP_UP_AUTO", "False").strip().lower()
    return raw not in ("true", "1", "yes")


def log_run_with_estimate(
    *,
    mode: str,
    ramp_up_stage: int,
    execution_time_seconds: float,
    estimate_window: int = 10,
    **extra_kw,
) -> dict:
    """W1 production hook helper — *같은 (stage, mode)* 이전 N회 평균을 estimated 로 자동 계산.

    2026-05-09 fix: 이전엔 stage 무관 N회 평균이라 stage transition (예: 500→1000)
    시 universe 1.5배 → 시간 1.5배 = 자연 비례 증가가 모두 50% overrun false positive.
    사용자 보고 "stage 500 일 때도 stage 1500 진입 시에도 같은 알람" → 룰 결함.
    fix: r.get("ramp_up_stage") == ramp_up_stage 필터 추가. 같은 stage baseline 만.

    2026-05-10 fix: mode=full (무거움 ~256s) + mode=full_us (가벼움 ~10s) 가 같은 stage
    안에 섞여서 baseline 평균이 mode=full 한테는 항상 50% overrun false positive.
    fix: r.get("mode") == mode 필터 추가. 같은 (stage, mode) baseline 만.

    grace: 같은 (stage, mode) 이전 run 0건이면 estimated=None → overrun 알람 비활성.

    silent 실패: 측정 자체가 main 흐름을 막지 않도록 모든 예외 swallow.
    """
    try:
        prev = get_recent_runs(limit=estimate_window * 4)  # stage+mode 필터 후 N개 확보용 buffer
        times = [
            r.get("execution_time_seconds")
            for r in prev
            if isinstance(r.get("execution_time_seconds"), (int, float))
            and r.get("ramp_up_stage") == ramp_up_stage  # 같은 stage 만
            and r.get("mode") == mode                    # 같은 mode 만 (5/10 fix)
        ][:estimate_window]
        # 2026-05-10 grace 강화 — N<3 시 estimated=None 으로 trigger 비활성.
        # 기존엔 N=0 만 grace 였는데 N=1~2 sample 로 평균하면 baseline 부정확,
        # 1500→5000 transition 후 첫 2 run 가 false positive 양산. 5/11~ 사이트
        # SystemHealthBar DATA PIPELINE 에 ⚠ execution_time_50pct_overrun 첫 표시.
        MIN_BASELINE_SAMPLES = 3
        if len(times) < MIN_BASELINE_SAMPLES:
            estimated = None  # warm-up — overrun trigger 비활성
        else:
            estimated = sum(times) / len(times)
        return log_runtime_load(
            mode=mode,
            ramp_up_stage=ramp_up_stage,
            execution_time_seconds=execution_time_seconds,
            estimated_time_seconds=estimated,
            **extra_kw,
        )
    except Exception as e:
        logger.warning(
            "[runtime_load] log_run_with_estimate 실패 — mode=%s stage=%s exec=%.2fs err=%s",
            mode, ramp_up_stage, execution_time_seconds, e,
            exc_info=True,
        )
        return {"logged": False, "fail_triggers": [], "should_alert": False, "error": str(e)}
