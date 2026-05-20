"""cron_health_monitor — daily_analysis_full + universe_scan + macro_collect 점검.

배경 (2026-05-10):
  5/10 1500/5000 stage SIGTERM 결함 후 universe_scan + macro_collect 분리.
  5/11 평일 schedule 부터 새 cron 흐름 적용. 자동 점검 + 텔레그램 verdict.

입력 (feedback_scheduled_routine_input_first 정합):
  - data/metadata/runtime_load_log.jsonl  (universe + daily_analysis 적재)
  - data/macro_snapshot.json              (macro_collect 결과)
  - data/universe_candidates.json         (universe_scan 결과)
  - GitHub API run list                   (workflow run status)

출력:
  - stdout: 일별 요약 + verdict
  - 텔레그램: --notify flag 시 bypass_quiet alert

Verdict:
  PASS    — 모든 cron success + 임계 안
  WARNING — 일부 metric 임계 초과 (yf_fail > 5%, candidate < 30 등)
  FAIL    — cron failure / SIGTERM / 0건 candidates 등
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

KST = timezone(timedelta(hours=9))
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _now_kst() -> datetime:
    return datetime.now(KST)


def _gh_run_list(workflow: str, limit: int = 5) -> List[Dict[str, Any]]:
    """gh CLI 로 직전 workflow run list."""
    try:
        result = subprocess.run(
            ["gh", "run", "list", f"--workflow={workflow}", "--limit", str(limit), "--json",
             "databaseId,status,conclusion,createdAt,startedAt,updatedAt,event,displayTitle"],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0:
            sys.stderr.write(f"[cron_health] gh run list 실패: {result.stderr}\n")
            return []
        return json.loads(result.stdout) or []
    except Exception as e:
        sys.stderr.write(f"[cron_health] gh CLI 호출 실패: {e}\n")
        return []


def _load_runtime_log() -> List[Dict[str, Any]]:
    path = os.path.join(_REPO_ROOT, "data", "metadata", "runtime_load_log.jsonl")
    if not os.path.isfile(path):
        return []
    out: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


def _load_json(path: str) -> Optional[Dict[str, Any]]:
    full = os.path.join(_REPO_ROOT, path)
    if not os.path.isfile(full):
        return None
    try:
        with open(full, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _filter_recent(entries: List[Dict[str, Any]], hours: int, ts_key: str = "createdAt") -> List[Dict[str, Any]]:
    cutoff = _now_kst() - timedelta(hours=hours)
    out = []
    for e in entries:
        ts_str = e.get(ts_key, "")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=KST)
        if ts >= cutoff:
            out.append(e)
    return out


def _drop_resolved_fails(
    completed_runs: List[Dict[str, Any]],
    fails: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """fail 후 같은 workflow 의 success 가 떨어지면 resolved 로 간주.

    2026-05-18 박힘 — 24h 윈도우 fail count 가 fix 이후에도 빨간불 유지하는
    frustration 증폭 결함. e.g. universe_scan FAIL 16:17 + FAIL 16:28 후
    f95ad860 numba fix → SUCCESS 16:31. 옛 logic = 5/18 16:00 까지 빨간불 유지.
    신: latest_success_ts 이전 fail = resolved (alert 대상에서 drop),
        이후 fail = current (실제 결함 alert 유지).
    success 0 = drop X (전부 current).
    """
    sorted_runs = sorted(completed_runs, key=lambda r: r.get("createdAt", ""))
    latest_success_ts = ""
    for r in sorted_runs:
        if r.get("conclusion") == "success":
            latest_success_ts = r.get("createdAt", "") or latest_success_ts
    if not latest_success_ts:
        return list(fails)
    return [f for f in fails if (f.get("createdAt", "") or "") > latest_success_ts]


def _split_fail_vs_cancel(
    bad_runs: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """conclusion 분리: 실 결함(failure/timed_out) vs 취소(cancelled).

    2026-05-18 박힘 — cancellation = 코드 결함 아님 (concurrency / 수동 stop /
    runner 이슈). 옛 logic = `conclusion != 'success'` 단일 묶음 → cancel 1건도
    FAIL 격상. 신: real_fail 만 FAIL 격상, cancel 은 >3/24h 임계에서만 WARNING.
    """
    real_fail = [
        r for r in bad_runs
        if r.get("conclusion") in ("failure", "timed_out", "startup_failure")
    ]
    cancelled = [r for r in bad_runs if r.get("conclusion") == "cancelled"]
    return real_fail, cancelled


def _is_run_on_kst_weekend(run: Dict[str, Any]) -> bool:
    """workflow run 의 createdAt 이 KST 토/일 인지 검사.

    2026-05-18 박힘 — 현재 weekday 만 검사하던 옛 logic 결함.
    Sun 07:09 KST 발생한 daily_analysis_full fail 이 Mon 00:55 KST 모니터에
    잡힐 때 (24h 윈도우 포함) is_weekend=False 라 FAIL 격상. 실제는 KRX 휴장
    transient → fail 의 발생 시각 기준 weekday 검사로 교정.
    """
    ts_str = run.get("createdAt", "")
    if not ts_str:
        return False
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=KST)
    ts_kst = ts.astimezone(KST)
    return ts_kst.weekday() >= 5


def _count_expected_price_pulse_in_window(now_utc: datetime, hours: int = 24) -> int:
    """직전 N시간 윈도우 내 price_pulse 발화 예상 슬롯 수.

    2026-05-18 박힘 — 현재 weekday 만 보는 옛 dispatch_chain 검사 결함.
    Mon 00:00~09:00 KST = is_weekend=False 인데 직전 24h = 일요일+토 후반 = 시장 0.
    옛 logic = 무조건 FAIL → false alarm. 정공법 = dispatch_pulse._resolve_events
    logic 을 윈도우 내 매 5분 슬롯 simulate → 발화 예상 슬롯 수 산출.
    expected=0 → skip alarm (정상 baseline), actual<expected*0.5 → FAIL.
    """
    start = now_utc - timedelta(hours=hours)
    cursor = start
    count = 0
    while cursor < now_utc:
        py_wd = cursor.weekday()  # 0=Mon..6=Sun
        is_weekday = py_wd <= 4
        is_sun_thu = py_wd in (6, 0, 1, 2, 3)
        hour = cursor.hour
        minute = cursor.minute
        # dispatch_pulse._resolve_events 의 price_pulse 게이트 정합
        kr_pre = (hour == 23 and minute >= 30 and is_sun_thu)
        kr_main = ((hour <= 5) or (hour == 6 and minute <= 40)) and is_weekday
        us_main = (
            (hour == 13 and minute >= 30) or
            (14 <= hour <= 19) or
            (hour == 20 and minute == 0)
        ) and is_weekday
        if kr_pre or kr_main or us_main:
            count += 1
        cursor += timedelta(minutes=5)
    return count


def _count_expected_daily_full_in_window(now_utc: datetime, hours: int = 24) -> int:
    """직전 N시간 윈도우 내 daily_analysis_full 발화 예상 슬롯 수 (UTC schedule 기준).

    2026-05-18 박힘 — 월요일 KST 00:00~16:07 사이 = 직전 24h 가 일요일+토 후반,
    실 cron 도래 0건 정상인데 옛 logic ('total==0 + not is_weekend → WARNING')
    이 매 월요일 false alarm 발화. 정공법 = schedule 시각 simulate → expected=0 시 suppress.

    cron schedule (.github/workflows/daily_analysis_full.yml:10-25):
      - '7 7 * * 1-5'   UTC Mon~Fri 07:07 = KST 16:07 (KR 마감 full)
      - '30 21 * * 2-5' UTC Tue~Fri 21:30 = KST 06:30 Wed~Sat (US 마감 full)
      - '7 0 * * 6'     UTC Sat 00:07 = KST 09:07 Sat (주간 리포트)
    월간/분기/반기/연간은 sparse → 무시 (false negative 무시 가능 수준).
    """
    start = now_utc - timedelta(hours=hours)
    cursor = start.replace(second=0, microsecond=0)
    count = 0
    while cursor < now_utc:
        wd = cursor.weekday()  # UTC weekday (0=Mon..6=Sun)
        hh = cursor.hour
        mm = cursor.minute
        # '7 7 * * 1-5' UTC Mon~Fri 07:07
        if wd <= 4 and hh == 7 and mm == 7:
            count += 1
        # '30 21 * * 2-5' UTC Tue~Fri 21:30
        elif wd in (1, 2, 3, 4) and hh == 21 and mm == 30:
            count += 1
        # '7 0 * * 6' UTC Sat 00:07
        elif wd == 5 and hh == 0 and mm == 7:
            count += 1
        cursor += timedelta(minutes=1)
    return count


def analyze(hours_window: int = 24) -> Dict[str, Any]:
    """직전 N시간 cron 결과 종합 분석.

    2026-05-17 weekday 정합 fix ([[feedback_weekday_check_mandatory]] 같은 패턴 학습):
      - universe_scan cron = 평일 (월~금) KST 15:30 만 → 토/일 도래 0 = 정상 baseline
      - daily_analysis_full KR mode = cron 월~금, US mode = 화~토 (UTC) → 일요일 = 도래 거의 0,
        도래 시 KRX 휴장 → KRX API transient fail expected
      - weekend = severity FAIL 결정 영향 X (정상 baseline, 알림 noise 차단)
    """
    findings: List[str] = []
    severity = "PASS"  # PASS / WARNING / FAIL

    # 주말 / 휴장일 detect — 일요일 = KR/US 둘 다 휴장, 토요일 = US 단축 + KR 휴장
    _now = _now_kst()
    _weekday = _now.weekday()  # 0=Mon ~ 5=Sat 6=Sun
    is_weekend = _weekday >= 5  # 토/일

    # 1) daily_analysis_full
    daily_runs = _gh_run_list("daily_analysis_full.yml", limit=10)
    daily_recent = _filter_recent(daily_runs, hours_window)
    daily_full_runs = [r for r in daily_recent if r.get("status") == "completed"]

    daily_full_bad = [r for r in daily_full_runs if r.get("conclusion") != "success"]
    # 2026-05-18 박힘 — cancel ≠ real fail 분리 + latest_success 이후 fail 만 alert.
    _real_fail_all, _cancel_all = _split_fail_vs_cancel(daily_full_bad)
    daily_full_fail = _drop_resolved_fails(daily_full_runs, _real_fail_all)
    daily_cancel = _cancel_all  # cancel = 빈도 임계만, supersede 무관
    daily_summary = {
        "total": len(daily_full_runs),
        "success": len([r for r in daily_full_runs if r.get("conclusion") == "success"]),
        "failure": len(daily_full_fail),
        "cancelled": len(daily_cancel),
        "resolved_fail": len(_real_fail_all) - len(daily_full_fail),
    }

    if daily_full_fail:
        # 2026-05-18 fix — fail 의 발생 시각 (createdAt) 기준 weekday 검사.
        # 옛: 현재 weekday 만 검사 → Sun 발생 fail 이 Mon 00-09 KST 모니터에 잡히면 FAIL 격상.
        # 신: fail 마다 KST weekday 검사 → 모든 fail 이 주말 = WARNING, 평일 fail 존재 = FAIL.
        weekend_fails = [r for r in daily_full_fail if _is_run_on_kst_weekend(r)]
        weekday_fails = [r for r in daily_full_fail if not _is_run_on_kst_weekend(r)]
        if weekday_fails:
            severity = "FAIL"
            findings.append(
                f"daily_analysis_full fail {len(weekday_fails)}건 "
                f"(최근: {weekday_fails[0].get('displayTitle', '?')})"
            )
        if weekend_fails:
            severity = "WARNING" if severity == "PASS" else severity
            findings.append(
                f"daily_analysis_full 주말 fail {len(weekend_fails)}건 "
                f"(KRX 휴장 transient 의심)"
            )
    if len(daily_cancel) >= 3:
        severity = "WARNING" if severity == "PASS" else severity
        findings.append(
            f"daily_analysis_full cancel {len(daily_cancel)}건/24h "
            f"(>3건 = concurrency/runner 이슈 의심)"
        )
    elif daily_summary["total"] == 0:
        # 2026-05-18 fix — 옛: 평일이면 무조건 WARNING. 월요일 00:00~16:07 KST 사이
        # = 직전 24h 가 일요일+토 후반 = expected=0 인데 false alarm 발화.
        # 신: schedule UTC 시각 simulate → expected=0 시 suppress.
        _now_utc = _now.astimezone(timezone.utc)
        expected_daily_full = _count_expected_daily_full_in_window(_now_utc, hours=hours_window)
        if expected_daily_full == 0:
            # 도래 예정 슬롯 0 = 정상 baseline (alarm suppress)
            pass
        else:
            severity = "WARNING" if severity != "FAIL" else severity
            findings.append(
                f"daily_analysis_full {hours_window}h 내 실행 없음 "
                f"(expected={expected_daily_full})"
            )

    # 2) universe_scan
    uni_runs = _gh_run_list("universe_scan.yml", limit=10)
    uni_recent = _filter_recent(uni_runs, hours_window)
    uni_completed = [r for r in uni_recent if r.get("status") == "completed"]
    uni_bad = [r for r in uni_completed if r.get("conclusion") != "success"]
    # 2026-05-18 박힘 — cancel ≠ real fail 분리 + latest_success 이후 fail 만 alert.
    _uni_real_all, _uni_cancel = _split_fail_vs_cancel(uni_bad)
    uni_fail = _drop_resolved_fails(uni_completed, _uni_real_all)

    uni_summary = {
        "total": len(uni_completed),
        "success": len([r for r in uni_completed if r.get("conclusion") == "success"]),
        "failure": len(uni_fail),
        "cancelled": len(_uni_cancel),
        "resolved_fail": len(_uni_real_all) - len(uni_fail),
    }
    if uni_fail:
        if is_weekend:
            severity = "WARNING" if severity == "PASS" else severity
            findings.append(f"universe_scan fail {uni_summary['failure']}건 (주말 transient 의심)")
        else:
            severity = "FAIL"
            findings.append(f"universe_scan fail {uni_summary['failure']}건")
    if len(_uni_cancel) >= 3:
        severity = "WARNING" if severity == "PASS" else severity
        findings.append(
            f"universe_scan cancel {len(_uni_cancel)}건/24h "
            f"(>3건 = concurrency/runner 이슈 의심)"
        )
    # universe_scan 도래 0 = 평일/주말 무관 정상 baseline (universe_scan cron = 평일 KST 15:30 만,
    # 토/일 = 도래 0 정상 / 평일 15:30 전 = 도래 0 정상). 알림 X.

    # 3) macro_collect
    macro_runs = _gh_run_list("macro_collect.yml", limit=10)
    macro_recent = _filter_recent(macro_runs, hours_window)
    macro_completed = [r for r in macro_recent if r.get("status") == "completed"]
    macro_fail_rate = (
        len([r for r in macro_completed if r.get("conclusion") != "success"]) / len(macro_completed)
        if macro_completed else 0.0
    )
    macro_summary = {
        "total": len(macro_completed),
        "fail_rate": round(macro_fail_rate, 3),
    }
    if macro_fail_rate > 0.2 and len(macro_completed) >= 5:
        severity = "WARNING" if severity == "PASS" else severity
        findings.append(f"macro_collect fail_rate {macro_fail_rate:.0%} (≥20%)")

    # 4) runtime_load_log 최근 entry
    rt_log = _load_runtime_log()
    rt_recent: List[Dict[str, Any]] = []
    cutoff = _now_kst() - timedelta(hours=hours_window)
    for r in rt_log:
        try:
            ts = datetime.fromisoformat(r.get("run_id", ""))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=KST)
            if ts >= cutoff:
                rt_recent.append(r)
        except (ValueError, TypeError):
            continue

    yf_fail_max = max((r.get("yfinance_failure_rate", 0) or 0) for r in rt_recent) if rt_recent else 0
    rate_limit_max = max((r.get("rate_limit_violations", 0) or 0) for r in rt_recent) if rt_recent else 0
    triggers_seen = set()
    for r in rt_recent:
        for t in (r.get("fail_triggers") or []):
            triggers_seen.add(t)

    if yf_fail_max > 0.05:
        severity = "WARNING" if severity == "PASS" else severity
        findings.append(f"yf_fail_max {yf_fail_max:.1%} (>5%)")
    if rate_limit_max > 0:
        findings.append(f"rate_limit {rate_limit_max}건 (wrapper cooler 정상 동작 의미일 수도)")
    if triggers_seen:
        # execution_time_50pct_overrun 만 단독은 baseline 산식 결함 가능 — INFO 레벨
        critical_triggers = triggers_seen - {"execution_time_50pct_overrun"}
        if critical_triggers:
            severity = "FAIL" if severity != "FAIL" else severity
            findings.append(f"fail_triggers: {', '.join(sorted(critical_triggers))}")

    # 5) universe_candidates 신선도
    # 2026-05-17 임계 정합 fix — funnel 1-4 미구현 (commit 5b10a44, 5/11 박힘) → 25건 = 의도된 baseline.
    # 옛 30 임계 = funnel 의도 (5,000→1,000→300→100→25) 정합인데 현재 5,000→25 직접 압축 = 25 정상.
    # 진짜 결함 = 20 미만 (funnel 정공법 후 실측에서 25 이상 baseline) 또는 KR/US 비대칭.
    # [[project_stock_filter_v0_enhancement]] + [[project_funnel_5stage_sprint]] 정합.
    uni_snap = _load_json("data/universe_candidates.json")
    if uni_snap:
        diag = uni_snap.get("diagnostics", {})
        cand = diag.get("candidates_count", 0)
        kr = diag.get("kr_count", 0)
        us = diag.get("us_count", 0)
        if cand < 20:
            severity = "WARNING" if severity == "PASS" else severity
            findings.append(f"universe_candidates {cand}건 (<20 진짜 결함 임계, funnel 미구현 baseline=25)")
        if us == 0:
            severity = "WARNING" if severity == "PASS" else severity
            findings.append(f"universe US 0건 (yf wrapper 결함 의심)")
    elif not is_weekend:
        # 평일에만 없음 = 진짜 결함. 주말 = 옛 universe_candidates 그대로 (force_orphan publish-data 갱신 안 함)
        findings.append("universe_candidates.json 없음 (universe_scan 첫 cron 전 또는 fail)")

    # 6) macro_snapshot 신선도
    macro_snap = _load_json("data/macro_snapshot.json")
    macro_age_h: Optional[float] = None
    if macro_snap:
        ts_str = macro_snap.get("collected_at", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=KST)
            macro_age_h = (_now_kst() - ts).total_seconds() / 3600
            # 2026-05-18 임계 완화 — macro_collect GH cron */30 silent skip 빈발 ([[feedback_gh_short_cron_silent_skip]]),
            # 24h commit 빈도 ~33% (16/48 expected). 평균 gap ~70분, max ~3.5h. 매크로는 일/주 변화 → 3h stale 허용.
            # 실제 baseline 운영 1주일 후 재조정 (3h → 2h 회귀 후보).
            if macro_age_h > 3:
                severity = "WARNING" if severity == "PASS" else severity
                findings.append(f"macro_snapshot stale {macro_age_h:.1f}h (>3h)")
        except ValueError:
            pass

    # 6.5) fred_health 신선도 sentinel (2026-05-20 신설 — 5/18 silent gap 사고 학습)
    # [[project_fred_health_gap_2026_05_18]]: 5/18 macro_collect 8회 success 인데 fred_health.jsonl
    # ~11h 신규 entry 0 (sprint commit 폭주 중 rebase drop / GH */30 silent skip 의심). 당시 우연 발견.
    # fred_health 는 macro_collect (*/30) + full analysis 가 매번 _log_fred_health 로 append → 정상이면
    # 최신 entry age < 1h. macro_collect success 가 있는데 fred entry 가 stale = 적재 decoupling 신호.
    # macro success guard: macro_collect 자체 down 은 step 3 가 이미 알람 → 중복 회피 (success ≥3 일 때만).
    # 정합: [[feedback_data_collection_verification_mandatory]] (silent skip 자동 detect), CLAUDE.md RULE 4.
    fred_age_h: Optional[float] = None
    macro_success_n = len([r for r in macro_completed if r.get("conclusion") == "success"])
    fred_path = os.path.join(_REPO_ROOT, "data", "metadata", "fred_health.jsonl")
    try:
        last_ts = None
        with open(fred_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ts_raw = json.loads(line).get("ts_utc")
                except (ValueError, TypeError):
                    continue
                # ISO8601 UTC (...Z) = lexicographic sort = 시간순. append-order 무관하게 max 추적.
                if ts_raw and (last_ts is None or ts_raw > last_ts):
                    last_ts = ts_raw
        if last_ts:
            ts = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            fred_age_h = (_now_kst() - ts.astimezone(KST)).total_seconds() / 3600
            if fred_age_h > 3 and macro_success_n >= 3:
                severity = "WARNING" if severity == "PASS" else severity
                findings.append(
                    f"fred_health stale {fred_age_h:.1f}h 인데 macro_collect success "
                    f"{macro_success_n}회/24h (적재 decoupling = 5/18 silent gap 패턴 의심)"
                )
    except FileNotFoundError:
        pass
    except Exception as e:
        findings.append(f"fred_health 신선도 점검 실패: {type(e).__name__}: {e}")

    # 7) Claude final_review (STEP 10.8, 2026-05-11 박음) — 종합 시장 검수 verdict
    #
    # 2026-05-20 PM 결정 (A안 분리) — Claude 검수는 severity (🔴/🟡) 를 흔들지 않는다.
    # WHY: 검수 verdict (REVIEW_REQUIRED/CAUTION) 는 LLM 의 시장 환경 판단 (CAPE %ile /
    #      USD-KRW / 등급 정합) 으로 인프라 health 와 직교. score (62/72) 는 claude_analyst.py
    #      에 하드코딩 임계 없이 LLM 이 자체 부여 = 재현 불가능한 soft 신호.
    #      이 soft 신호가 hard ops 알림 (KIS 토큰 / yf_fail / dispatch_chain) 과 같은 🔴 로
    #      합쳐지면 진짜 P0 가 시장 caution 에 묻히고 alert fatigue 발생 (5/20 FAIL = 인프라
    #      전부 녹색인데 USD-KRW 1505 caution 한 줄로 🔴).
    # DATA: 5/19 score 72 (CAUTION/🟡) → 5/20 score 62 (REVIEW_REQUIRED/🔴), 동일 시장.
    #       인프라 지표 (daily 4/4, macro 0% fail, macro 0.17h, yf 0.1%) 는 양일 모두 정상.
    # EXPECTED: cron health 🔴/🟡 = 인프라 전용. 시장 caution 은 별도 라벨 줄로만 노출하고
    #       정기 시황은 hourly_pulse 채널이 담당. 인프라 녹색 + 시장 caution = 알림 미발화 (정상).
    # 정합: [[feedback_no_new_llm_narrative_features]] (LLM 판단 회의), CLAUDE.md RULE 6.
    portfolio = _load_json("data/portfolio.json")
    final_review = (portfolio or {}).get("claude_final_review") or {}
    final_verdict = final_review.get("claude_final_verdict")
    final_score = final_review.get("review_score")
    # NOTE: final_verdict 는 severity 에 영향 X (인프라 직교). 별도 라벨 줄 (_format_summary)
    #       + jsonl persist 로만 노출. findings (= severity 근거 목록) 에는 싣지 않음.

    # 8) 🚨 KIS 토큰 발급 추적 (2026-05-16 5분 폭주 사고 후 신설)
    # data/.kis_issued_date.txt commit 수 24h 내 = 발급 횟수 proxy.
    # ABSOLUTE: 1일 1토큰. 2회 = WARNING, ≥3회 = FAIL (계좌 제재 위험).
    import subprocess as _sp
    kis_lock_commits_24h = -1
    try:
        _result = _sp.run(
            ["git", "log", "--since=24 hours ago", "--pretty=format:%H",
             "--", "data/.kis_issued_date.txt"],
            capture_output=True, text=True, timeout=10
        )
        kis_lock_commits_24h = len([l for l in _result.stdout.strip().split("\n") if l]) \
            if _result.stdout.strip() else 0
    except Exception as e:
        findings.append(f"KIS lock commit 추적 실패: {e}")

    if kis_lock_commits_24h >= 3:
        severity = "FAIL"
        findings.append(
            f"🚨 KIS 토큰 발급 {kis_lock_commits_24h}회/24h "
            f"(1일 1토큰 ABSOLUTE 위반, 계좌 제재 위험)"
        )
    elif kis_lock_commits_24h == 2:
        severity = "WARNING" if severity == "PASS" else severity
        findings.append(
            f"⚠ KIS 토큰 발급 {kis_lock_commits_24h}회/24h "
            f"(baseline 1회. force_refresh + backup source 동시 발급 의심)"
        )

    # 9) 🌀 dispatch_chain 안정성 (2026-05-17 P3-3 신설, 2026-05-18 expected-slot 정합 fix)
    # Vercel cron → repository_dispatch → 4 워크플로 chain. slot drop rate detect.
    #
    # 2026-05-18 fix — 옛 logic = 현재 weekday 만 검사 (is_weekend=True → skip).
    # Mon 00:00~09:00 KST = is_weekend=False 인데 직전 24h = 일+토 후반 = 시장 0 → false FAIL.
    # 정공법 = 윈도우 내 dispatch_pulse._resolve_events 슬롯 simulate → 예상 발화 수 산출.
    # expected=0 → skip alarm (정상 baseline), actual<expected*0.5 → FAIL, *0.8 → WARNING.
    price_pulse_runs = _gh_run_list("price_pulse.yml", limit=200)
    price_pulse_24h = _filter_recent(price_pulse_runs, 24)
    price_pulse_success = [r for r in price_pulse_24h if r.get("conclusion") == "success"]
    pp_n_24h = len(price_pulse_success)
    now_utc = datetime.now(timezone.utc)
    pp_expected_24h = _count_expected_price_pulse_in_window(now_utc, hours=24)
    pp_dispatch_summary = {
        "total_24h": len(price_pulse_24h),
        "success_24h": pp_n_24h,
        "expected_24h": pp_expected_24h,
    }
    if pp_expected_24h > 0:
        ratio = pp_n_24h / pp_expected_24h
        if ratio < 0.5:
            severity = "FAIL"
            findings.append(
                f"🌀 dispatch_chain price_pulse {pp_n_24h}/{pp_expected_24h}회/24h "
                f"(ratio {ratio:.0%} <50%, FAIL 임계)"
            )
        elif ratio < 0.8:
            severity = "WARNING" if severity == "PASS" else severity
            findings.append(
                f"⚠ dispatch_chain price_pulse {pp_n_24h}/{pp_expected_24h}회/24h "
                f"(ratio {ratio:.0%} <80%, silent skip 의심)"
            )
    # expected=0 = 직전 24h 시장 시간 부재 (주말 + 월 09:00 전 + 시장 마감 후 = 정상 baseline)

    # 10) 2028 Vision metric — Antifragility + FOMO Score 분기별 측정
    # (Perplexity Q6 학계 자문 정합). 운영 누적 부족 시 산식 산출 못 함 — 정상.
    # 분기별 cron 시점 (3/1, 6/1, 9/1, 12/1) 만 발화. 평시 = skip (성능 부담 회피).
    antifragility_result = None
    fomo_result = None
    now_kst_dt = _now_kst()
    is_quarter_start = now_kst_dt.day == 1 and now_kst_dt.month in (3, 6, 9, 12)
    if is_quarter_start:
        try:
            from api.quant.antifragility import assess_antifragility, append_ledger as af_append
            from api.quant.fomo_score import compute_fomo_score, load_vams_history, append_ledger as fomo_append
            # VAMS history → 일별 수익률 (proxy)
            hist = load_vams_history()
            if hist:
                # FOMO Score
                fomo_result = compute_fomo_score(hist, days_window=90)
                fomo_append({"ts_kst": now_kst_dt.isoformat(timespec="seconds"), **fomo_result})
                if fomo_result.get("fomo_score") is not None and fomo_result["fomo_score"] > 0.3:
                    severity = "WARNING" if severity == "PASS" else severity
                    findings.append(
                        f"🧘 FOMO Score {fomo_result['fomo_score']:+.2f} "
                        f"({fomo_result['interpretation']})"
                    )
                # Antifragility (return series 추정 — VAMS history 의 trade outcome 활용)
                # 운영 누적 부족 시 None — 별 sprint 에서 정밀 산출
                # 본 hook = 큐 트리거만, 산식 자체는 별 호출
        except Exception as e:
            findings.append(f"vision metric 산출 실패: {type(e).__name__}: {e}")

    return {
        "severity": severity,
        "findings": findings,
        "daily_summary": daily_summary,
        "universe_scan_summary": uni_summary,
        "macro_collect_summary": macro_summary,
        "runtime_metrics": {
            "yf_fail_max": yf_fail_max,
            "rate_limit_max": rate_limit_max,
            "fail_triggers_seen": sorted(triggers_seen),
            "rt_log_count": len(rt_recent),
        },
        "universe_diag": (uni_snap or {}).get("diagnostics", {}) if uni_snap else None,
        "macro_age_h": round(macro_age_h, 2) if macro_age_h is not None else None,
        "fred_age_h": round(fred_age_h, 2) if fred_age_h is not None else None,
        "claude_final_verdict": final_verdict,
        "claude_final_score": final_score,
        "claude_final_concerns": (final_review.get("concerns") or [])[:2],
        "kis_lock_commits_24h": kis_lock_commits_24h,
        "dispatch_chain_summary": pp_dispatch_summary,
        "vision_metric": {
            "is_quarter_start": is_quarter_start,
            "fomo_score": fomo_result,
            "antifragility": antifragility_result,
        },
        "window_hours": hours_window,
        "checked_at": _now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }


def _emoji(severity: str) -> str:
    return {"PASS": "✅", "WARNING": "🟡", "FAIL": "🔴"}.get(severity, "•")


def _esc(text: Any) -> str:
    """2026-05-17 fix — telegram parse_mode=HTML 정합.

    findings 의 변수 부분 (e.g. "universe_candidates 25건 (<30 임계)") 의 `<` 가
    HTML start tag 로 parse 됨 → "Unsupported start tag" 400 error → exit 1.
    `<` `>` `&` 3개 escape (HTML 표준).
    """
    from html import escape as _html_escape
    return _html_escape(str(text), quote=False)


def _format_summary(report: Dict[str, Any]) -> List[str]:
    s = report["severity"]
    lines = [
        f"<b>{_emoji(s)} cron health — {_esc(s)}</b>",
        f"<i>직전 {_esc(report['window_hours'])}h, checked {_esc(report['checked_at'])}</i>",
        "",
        f"<b>daily_analysis_full</b>: success {report['daily_summary']['success']}/{report['daily_summary']['total']}, fail {report['daily_summary']['failure']}"
        + (f" (resolved {report['daily_summary'].get('resolved_fail', 0)})" if report['daily_summary'].get('resolved_fail') else "")
        + (f" / cancel {report['daily_summary'].get('cancelled', 0)}" if report['daily_summary'].get('cancelled') else ""),
        f"<b>universe_scan</b>: success {report['universe_scan_summary']['success']}/{report['universe_scan_summary']['total']}"
        + (f", fail {report['universe_scan_summary'].get('failure', 0)}" if report['universe_scan_summary'].get('failure') else "")
        + (f" (resolved {report['universe_scan_summary'].get('resolved_fail', 0)})" if report['universe_scan_summary'].get('resolved_fail') else "")
        + (f" / cancel {report['universe_scan_summary'].get('cancelled', 0)}" if report['universe_scan_summary'].get('cancelled') else ""),
        f"<b>macro_collect</b>: total {report['macro_collect_summary']['total']}, fail_rate {report['macro_collect_summary']['fail_rate']:.1%}",
    ]
    if report.get("universe_diag"):
        d = report["universe_diag"]
        lines.append(
            f"<b>candidates</b>: {_esc(d.get('candidates_count', '?'))}개 "
            f"(KR {_esc(d.get('kr_count', '?'))} + US {_esc(d.get('us_count', '?'))})"
        )
    if report.get("macro_age_h") is not None:
        lines.append(f"<b>macro 신선도</b>: {report['macro_age_h']}h")
    rm = report["runtime_metrics"]
    lines.append(f"<b>yf_fail_max</b>: {rm['yf_fail_max']:.1%} / <b>rate_limit_max</b>: {rm['rate_limit_max']}")

    # Claude 시장 검수 (STEP 10.8) — health status (🔴/🟡) 와 직교한 별도 시장 판단 줄.
    # 2026-05-20 A안 분리: severity 에 영향 X. "시장검수" 라벨로 인프라 health 와 구분.
    cv = report.get("claude_final_verdict")
    if cv:
        cs = report.get("claude_final_score", "?")
        lines.append(f"<b>🤖 Claude 시장검수</b>: {_esc(cv)} (score {_esc(cs)}) <i>· health 무관</i>")
        cc = report.get("claude_final_concerns", [])
        for c in cc[:2]:
            lines.append(f"  · {_esc(c[:80])}")

    if report["findings"]:
        lines.append("")
        lines.append("<b>발견</b>:")
        for f in report["findings"]:
            lines.append(f"• {_esc(f)}")

    return lines


def _notify_telegram(lines: List[str]) -> None:
    try:
        sys.path.insert(0, _REPO_ROOT)
        from api.notifications.telegram import send_message
        msg = "\n".join(lines)
        send_message(msg, dedupe=False, bypass_quiet=True)
        sys.stderr.write("[cron_health] telegram sent\n")
    except Exception as e:
        sys.stderr.write(f"[cron_health] telegram FAIL: {e}\n")


def _persist_report(report: Dict[str, Any]) -> None:
    """2026-05-17 Phase 3 audit fix — cron_health 결과 jsonl persist.

    옛 구현 = 텔레그램 push 만 + stdout 출력 휘발. 운영자가 과거 trend 추적 불가
    (어제 detect 했는지 / 어떤 결함이 반복인지). jsonl append 박아 SystemHealthBar
    surface 가능 + 사후 audit 가능.

    silent skip 차단 — feedback_data_collection_verification_mandatory 정합.
    """
    path = os.path.join(_REPO_ROOT, "data", "metadata", "cron_health.jsonl")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # 경량 entry — 큰 nested 산출물 제외 (findings 만 + summary scalar)
        entry = {
            "ts_kst": report.get("checked_at"),
            "severity": report.get("severity"),
            "findings": report.get("findings") or [],
            "window_hours": report.get("window_hours"),
            "daily_summary": report.get("daily_summary"),
            "universe_scan_summary": report.get("universe_scan_summary"),
            "macro_collect_summary": report.get("macro_collect_summary"),
            "kis_lock_commits_24h": report.get("kis_lock_commits_24h"),
            "claude_final_verdict": report.get("claude_final_verdict"),
            "claude_final_score": report.get("claude_final_score"),
            "dispatch_chain_summary": report.get("dispatch_chain_summary"),
            "macro_age_h": report.get("macro_age_h"),
            "fred_age_h": report.get("fred_age_h"),
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        sys.stderr.write(f"[cron_health] persisted to {os.path.basename(path)}\n")
    except Exception as e:
        # 명시 stderr — silent skip X
        sys.stderr.write(f"[cron_health] persist FAIL: {type(e).__name__}: {e}\n")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=int, default=24, help="lookback window 시간")
    p.add_argument("--notify", action="store_true", help="텔레그램 push")
    p.add_argument("--always-notify", action="store_true", help="PASS 도 push (default WARNING/FAIL 만)")
    args = p.parse_args()

    report = analyze(hours_window=args.hours)
    lines = _format_summary(report)
    print("\n".join(lines))

    # 2026-05-17 Phase 3 — jsonl persist (텔레그램 push 와 별개, 항상 append)
    _persist_report(report)

    should_notify = args.notify and (args.always_notify or report["severity"] != "PASS")
    if should_notify:
        _notify_telegram(lines)

    return 0 if report["severity"] != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
