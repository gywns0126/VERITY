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

    # 9) 🌀 dispatch_chain 안정성 (2026-05-17 P3-3 신설)
    # Vercel cron → repository_dispatch → 4 워크플로 chain. slot drop rate detect.
    # price_pulse 5분 cron 기대치 (시장 시간): KR 6시간 + US 6.5시간 ≈ 150건/평일, ~100-110/일 평균.
    # 24h 내 50건 미만 = WARN (silent skip 의심). 20건 미만 = FAIL.
    price_pulse_runs = _gh_run_list("price_pulse.yml", limit=200)
    price_pulse_24h = _filter_recent(price_pulse_runs, 24)
    price_pulse_success = [r for r in price_pulse_24h if r.get("conclusion") == "success"]
    pp_n_24h = len(price_pulse_success)
    pp_dispatch_summary = {
        "total_24h": len(price_pulse_24h),
        "success_24h": pp_n_24h,
    }
    now_wd = _now_kst().weekday()  # 0=Mon~6=Sun
    is_weekend = now_wd >= 5
    if not is_weekend:
        # 평일 baseline
        if pp_n_24h < 20:
            severity = "FAIL"
            findings.append(f"🌀 dispatch_chain price_pulse {pp_n_24h}회/24h (<20, FAIL 임계)")
        elif pp_n_24h < 50:
            severity = "WARNING" if severity == "PASS" else severity
            findings.append(f"⚠ dispatch_chain price_pulse {pp_n_24h}회/24h (<50, silent skip 의심)")
    # 주말 = 시장 마감, 발화 0 정상 (5/17 dispatch_pulse 시장 시간 가드 박힘)

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
        f"<b>daily_analysis_full</b>: success {report['daily_summary']['success']}/{report['daily_summary']['total']}, fail {report['daily_summary']['failure']}",
        f"<b>universe_scan</b>: success {report['universe_scan_summary']['success']}/{report['universe_scan_summary']['total']}",
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

    # Claude 종합 검수 (STEP 10.8)
    cv = report.get("claude_final_verdict")
    if cv:
        cs = report.get("claude_final_score", "?")
        lines.append(f"<b>🤖 Claude 검수</b>: {_esc(cv)} (score {_esc(cs)})")
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
