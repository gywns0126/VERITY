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


def analyze(hours_window: int = 24) -> Dict[str, Any]:
    """직전 N시간 cron 결과 종합 분석."""
    findings: List[str] = []
    severity = "PASS"  # PASS / WARNING / FAIL

    # 1) daily_analysis_full
    daily_runs = _gh_run_list("daily_analysis_full.yml", limit=10)
    daily_recent = _filter_recent(daily_runs, hours_window)
    daily_full_runs = [r for r in daily_recent if r.get("status") == "completed"]

    daily_full_fail = [r for r in daily_full_runs if r.get("conclusion") != "success"]
    daily_summary = {
        "total": len(daily_full_runs),
        "success": len([r for r in daily_full_runs if r.get("conclusion") == "success"]),
        "failure": len(daily_full_fail),
    }

    if daily_full_fail:
        severity = "FAIL"
        findings.append(
            f"daily_analysis_full fail {daily_summary['failure']}건 "
            f"(최근: {daily_full_fail[0].get('displayTitle', '?')})"
        )
    elif daily_summary["total"] == 0:
        severity = "WARNING" if severity != "FAIL" else severity
        findings.append(f"daily_analysis_full {hours_window}h 내 실행 없음")

    # 2) universe_scan
    uni_runs = _gh_run_list("universe_scan.yml", limit=5)
    uni_recent = _filter_recent(uni_runs, hours_window)
    uni_completed = [r for r in uni_recent if r.get("status") == "completed"]
    uni_fail = [r for r in uni_completed if r.get("conclusion") != "success"]

    uni_summary = {
        "total": len(uni_completed),
        "success": len([r for r in uni_completed if r.get("conclusion") == "success"]),
        "failure": len(uni_fail),
    }
    if uni_fail:
        severity = "FAIL"
        findings.append(f"universe_scan fail {uni_summary['failure']}건")

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
    uni_snap = _load_json("data/universe_candidates.json")
    if uni_snap:
        diag = uni_snap.get("diagnostics", {})
        cand = diag.get("candidates_count", 0)
        kr = diag.get("kr_count", 0)
        us = diag.get("us_count", 0)
        if cand < 30:
            severity = "WARNING" if severity == "PASS" else severity
            findings.append(f"universe_candidates {cand}건 (<30 임계)")
        if us == 0:
            severity = "WARNING" if severity == "PASS" else severity
            findings.append(f"universe US 0건 (yf wrapper 결함 의심)")
    else:
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
            if macro_age_h > 2:
                severity = "WARNING" if severity == "PASS" else severity
                findings.append(f"macro_snapshot stale {macro_age_h:.1f}h (>2h)")
        except ValueError:
            pass

    # 7) Claude final_review (STEP 10.8, 2026-05-11 박음) — 종합 검수 verdict
    portfolio = _load_json("data/portfolio.json")
    final_review = (portfolio or {}).get("claude_final_review") or {}
    final_verdict = final_review.get("claude_final_verdict")
    final_score = final_review.get("review_score")
    if final_verdict == "REVIEW_REQUIRED":
        severity = "FAIL"
        findings.append(f"Claude 종합 검수 = REVIEW_REQUIRED (score {final_score})")
    elif final_verdict == "CAUTION":
        severity = "WARNING" if severity == "PASS" else severity
        findings.append(f"Claude 종합 검수 = CAUTION (score {final_score})")
    elif not final_verdict:
        # full mode 가 직전에 안 돌았거나 STEP 10.8 호출 실패. 단독 WARNING X (다른 cron 활동 정상이면 무시)
        pass

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
        "claude_final_verdict": final_verdict,
        "claude_final_score": final_score,
        "claude_final_concerns": (final_review.get("concerns") or [])[:2],
        "window_hours": hours_window,
        "checked_at": _now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }


def _emoji(severity: str) -> str:
    return {"PASS": "✅", "WARNING": "🟡", "FAIL": "🔴"}.get(severity, "•")


def _format_summary(report: Dict[str, Any]) -> List[str]:
    s = report["severity"]
    lines = [
        f"<b>{_emoji(s)} cron health — {s}</b>",
        f"<i>직전 {report['window_hours']}h, checked {report['checked_at']}</i>",
        "",
        f"<b>daily_analysis_full</b>: success {report['daily_summary']['success']}/{report['daily_summary']['total']}, fail {report['daily_summary']['failure']}",
        f"<b>universe_scan</b>: success {report['universe_scan_summary']['success']}/{report['universe_scan_summary']['total']}",
        f"<b>macro_collect</b>: total {report['macro_collect_summary']['total']}, fail_rate {report['macro_collect_summary']['fail_rate']:.1%}",
    ]
    if report.get("universe_diag"):
        d = report["universe_diag"]
        lines.append(
            f"<b>candidates</b>: {d.get('candidates_count', '?')}개 "
            f"(KR {d.get('kr_count', '?')} + US {d.get('us_count', '?')})"
        )
    if report.get("macro_age_h") is not None:
        lines.append(f"<b>macro 신선도</b>: {report['macro_age_h']}h")
    rm = report["runtime_metrics"]
    lines.append(f"<b>yf_fail_max</b>: {rm['yf_fail_max']:.1%} / <b>rate_limit_max</b>: {rm['rate_limit_max']}")

    # Claude 종합 검수 (STEP 10.8)
    cv = report.get("claude_final_verdict")
    if cv:
        cs = report.get("claude_final_score", "?")
        lines.append(f"<b>🤖 Claude 검수</b>: {cv} (score {cs})")
        cc = report.get("claude_final_concerns", [])
        for c in cc[:2]:
            lines.append(f"  · {c[:80]}")

    if report["findings"]:
        lines.append("")
        lines.append("<b>발견</b>:")
        for f in report["findings"]:
            lines.append(f"• {f}")

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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=int, default=24, help="lookback window 시간")
    p.add_argument("--notify", action="store_true", help="텔레그램 push")
    p.add_argument("--always-notify", action="store_true", help="PASS 도 push (default WARNING/FAIL 만)")
    args = p.parse_args()

    report = analyze(hours_window=args.hours)
    lines = _format_summary(report)
    print("\n".join(lines))

    should_notify = args.notify and (args.always_notify or report["severity"] != "PASS")
    if should_notify:
        _notify_telegram(lines)

    return 0 if report["severity"] != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
