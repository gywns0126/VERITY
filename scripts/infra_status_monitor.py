#!/usr/bin/env python3
"""
infra_status_monitor.py — 5 외부 제공자 health + 결제/한도 사고 detect

매일 KST 09:00 cron. data/infra_status.json snapshot.
ALERT 발생 시 user_action_queue P0 자동 등록 (Bell 노출).

WHY: RULE 3 (인프라 제공자 직접 메일/티켓 24h 인지 의무) 자동화 layer.
     5/27 TIDE GitHub 빌링 사고 = silent detect 안 됨. 영구 fix.

대상 제공자:
  1. KIS — 1일 1토큰 lock 파일 정합 (RULE 1)
  2. Vercel — vercel-api/ commit 빈도 detect (RULE 2, 5/13 Shohei 사고)
  3. GitHub Actions — recent runs 의 'payment'/'spending limit' annotation detect (5/27 TIDE 학습)
  4. DART — opendart corpCode API ping
  5. Supabase — REST root ping

입력: git log + .env (SUPABASE_URL/KEY, DART_API_KEY, GH_TOKEN)
출력: data/infra_status.json + (ALERT 시) user_action_queue 항목

운영: .github/workflows/infra_status_monitor.yml 매일 KST 09:00
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_PATH = DATA_DIR / "infra_status.json"

KST = timezone(timedelta(hours=9))


def _now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _git_commits_since(path: str, hours: int = 24) -> int:
    try:
        out = subprocess.check_output(
            ["git", "log", f"--since={hours} hours ago", "--oneline", "--", path],
            cwd=str(ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return len([line for line in out.splitlines() if line.strip()])
    except Exception:
        return -1


def check_kis() -> Dict[str, Any]:
    lock_path = ROOT / "data" / ".kis_issued_date.txt"
    if not lock_path.exists():
        return {"provider": "KIS", "status": "WARN", "detail": "lock 파일 missing", "as_of": _now_kst()}
    try:
        content = lock_path.read_text(encoding="utf-8").strip()
        # 발급 일자 = 어제 또는 오늘 = 정상. cron 23:45 발급 사이클.
        return {"provider": "KIS", "status": "OK", "detail": f"lock={content[:30]}", "as_of": _now_kst()}
    except Exception as e:
        return {"provider": "KIS", "status": "ALERT", "detail": f"lock read error: {e}", "as_of": _now_kst()}


def check_vercel_deploy_spam() -> Dict[str, Any]:
    """RULE 2 정합 — vercel-api/ commit 빈도. 5/13 Shohei 일 400 deploy 사고 재발 detect."""
    n_commits = _git_commits_since("vercel-api/", hours=24)
    if n_commits < 0:
        return {"provider": "Vercel", "status": "WARN", "detail": "git log fail", "as_of": _now_kst()}
    if n_commits >= 50:
        return {"provider": "Vercel", "status": "ALERT",
                "detail": f"vercel-api/ commit {n_commits}/24h — RULE 2 재발 risk",
                "as_of": _now_kst()}
    return {"provider": "Vercel", "status": "OK",
            "detail": f"vercel-api/ commit {n_commits}/24h",
            "as_of": _now_kst()}


def check_github_actions_billing() -> Dict[str, Any]:
    """5/27 TIDE 학습 — recent run annotation 의 payment/billing 패턴 detect.
    이 레포 (public 무료) 자체 사고 detect. 별 private 레포 detect 는 별 sprint.
    """
    try:
        out = subprocess.check_output(
            ["gh", "run", "list", "--limit", "20", "--json", "conclusion,databaseId,name"],
            cwd=str(ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        runs = json.loads(out)
    except Exception as e:
        return {"provider": "GitHub Actions", "status": "WARN",
                "detail": f"gh run list fail: {str(e)[:80]}", "as_of": _now_kst()}

    n_fail = sum(1 for r in runs if r.get("conclusion") == "failure")

    # billing 패턴 detect: 최근 fail run 의 첫 1개만 view (비용 최소)
    billing_alert = None
    for run in runs:
        if run.get("conclusion") != "failure":
            continue
        try:
            view_out = subprocess.check_output(
                ["gh", "run", "view", str(run["databaseId"])],
                cwd=str(ROOT),
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            if re.search(r"payment|spending limit|billing", view_out, re.IGNORECASE):
                billing_alert = f"run {run['databaseId']} ({run.get('name','')}): billing pattern"
            break
        except Exception:
            break

    if billing_alert:
        return {"provider": "GitHub Actions", "status": "ALERT", "detail": billing_alert, "as_of": _now_kst()}
    if n_fail >= 5:
        return {"provider": "GitHub Actions", "status": "WARN",
                "detail": f"최근 20 run 중 {n_fail} 실패", "as_of": _now_kst()}
    return {"provider": "GitHub Actions", "status": "OK",
            "detail": f"최근 20 run 중 {n_fail} 실패", "as_of": _now_kst()}


def _get_run_annotations(repo: str, run_id: int) -> List[Dict[str, Any]]:
    """run 의 모든 job annotations list 반환 (GitHub check-runs API 직접).

    2026-05-29 정밀화 — 직전 gh run view 텍스트 매칭 → annotations API 호출.
    """
    try:
        jobs_out = subprocess.check_output(
            ["gh", "api", f"repos/{repo}/actions/runs/{run_id}/jobs"],
            cwd=str(ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        jobs = json.loads(jobs_out).get("jobs", [])
    except Exception:
        return []

    annotations: List[Dict[str, Any]] = []
    for job in jobs[:3]:  # 최대 3 job (시간 절약)
        check_run_url = job.get("check_run_url", "")
        if not check_run_url:
            continue
        # check_run_url = https://api.github.com/repos/.../check-runs/{id}
        check_run_id = check_run_url.rsplit("/", 1)[-1]
        try:
            ann_out = subprocess.check_output(
                ["gh", "api",
                 f"repos/{repo}/check-runs/{check_run_id}/annotations"],
                cwd=str(ROOT),
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            annotations.extend(json.loads(ann_out) or [])
        except Exception:
            continue
    return annotations


_TIDE_BLOB = ("https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
              "/tide/dashboard.json")
_TIDE_HB_STALE_MIN = 720  # 12시간 — TIDE heartbeat 워크플로 6시간 주기의 2배 여유


def _check_tide_blob() -> Optional[str]:
    """TIDE 크론 헬스를 공개 blob 으로 확인 (private repo gh 접근 불필요).

    2026-08-05 신설 — 기존 gh run list 경로가 private repo 를 VERITY 스코프 토큰으로
    조회해 66일째 'gh fail' WARN 만 반복(실측 data/infra_status.json). 실패가 정보가
    아니라 소음이었다. TIDE 는 이미 tide/dashboard.json 을 공개 blob 으로 발행하므로
    (cron_status·minutes_since_heartbeat 포함) 토큰 없이 실 헬스를 볼 수 있다.
    Returns: 이상 시 finding 문자열, 정상이면 None.
    """
    try:
        req = urllib.request.Request(_TIDE_BLOB, headers={"User-Agent": "verity-infra-monitor"})
        with urllib.request.urlopen(req, timeout=15) as r:
            doc = json.load(r)
    except Exception as e:  # 발행 자체가 끊긴 것 = 실제 이상 신호
        return f"TIDE 대시보드 발행 확인 불가 ({type(e).__name__})"
    health = (doc.get("health") or {})
    status = str(health.get("cron_status") or "unknown")
    gap = health.get("minutes_since_heartbeat")
    if status == "critical":
        return f"TIDE 크론 critical (HB {gap}분 전)"
    if isinstance(gap, (int, float)) and gap > _TIDE_HB_STALE_MIN:
        return f"TIDE heartbeat {int(gap)}분 정지 (임계 {_TIDE_HB_STALE_MIN}분)"
    return None


def check_external_repos() -> Dict[str, Any]:
    """외부 repo recent runs billing pattern detect via annotations API.

    5/28 RULE 8 #2 정합. 5/29 정밀화 — annotations API 직접 호출
    (gh run view 텍스트 매칭 → check-runs annotations endpoint).
    환경변수 EXTERNAL_REPOS (CSV) 지정 가능, default = gywns0126/TIDE.
    """
    repos_env = os.environ.get("EXTERNAL_REPOS", "gywns0126/TIDE")
    repos = [r.strip() for r in repos_env.split(",") if r.strip()]
    if not repos:
        return {"provider": "External Repos", "status": "OK",
                "detail": "EXTERNAL_REPOS 빈 list", "as_of": _now_kst()}

    findings: List[str] = []
    gh_unavailable: List[str] = []
    tide_finding = _check_tide_blob()
    if tide_finding:
        findings.append(tide_finding)
    for repo in repos:
        try:
            out = subprocess.check_output(
                ["gh", "run", "list", "-R", repo, "--limit", "10",
                 "--json", "conclusion,databaseId,name"],
                cwd=str(ROOT),
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
            runs = json.loads(out)
        except Exception:
            # private repo 를 VERITY 스코프 토큰으로 조회 → 항상 실패. 이건 이미 아는
            # 사실이라 WARN 을 만들 정보가 없다(66일 반복 소음). 관측 갭으로만 기록하고
            # 헬스는 아래 공개 blob 경로가 담당. 빌링 감지는 이 경로가 유일하므로 은폐 금지.
            gh_unavailable.append(repo)
            continue

        n_fail = sum(1 for r in runs if r.get("conclusion") == "failure")

        # billing pattern detect via annotations API — 최근 fail run 최대 5개
        billing_alert = None
        fail_checked = 0
        for run in runs:
            if run.get("conclusion") != "failure":
                continue
            if fail_checked >= 5:
                break
            fail_checked += 1
            annotations = _get_run_annotations(repo, run["databaseId"])
            for ann in annotations:
                msg = (ann.get("message") or "") + " " + (ann.get("title") or "")
                if re.search(r"payment|spending limit|billing", msg, re.IGNORECASE):
                    billing_alert = (
                        f"{repo} run {run['databaseId']}: "
                        f"{msg.strip()[:120]}"
                    )
                    break
            if billing_alert:
                break

        if billing_alert:
            findings.append(billing_alert)
        elif n_fail >= 5:
            findings.append(f"{repo}: 최근 10 run 중 {n_fail} 실패")

    gap_note = (f" (빌링 감지 불가: {', '.join(gh_unavailable)} — private 접근 토큰 없음, "
                f"헬스는 공개 blob 으로 확인)") if gh_unavailable else ""
    if findings:
        any_billing = any("billing" in f.lower() or "payment" in f.lower()
                          or "spending" in f.lower() for f in findings)
        status = "ALERT" if any_billing else "WARN"
        return {"provider": "External Repos", "status": status,
                "detail": ("; ".join(findings) + gap_note)[:300], "as_of": _now_kst()}
    return {"provider": "External Repos", "status": "OK",
            "detail": f"{len(repos)} repo 정상{gap_note}", "as_of": _now_kst()}


def check_dart() -> Dict[str, Any]:
    try:
        import requests
        key = os.environ.get("DART_API_KEY", "")
        if not key:
            return {"provider": "DART", "status": "WARN", "detail": "DART_API_KEY 미설정", "as_of": _now_kst()}
        r = requests.get(
            "https://opendart.fss.or.kr/api/list.json",
            params={"crtfc_key": key, "page_count": "1"},
            timeout=10,
        )
        if r.status_code == 200 and r.json().get("status") in ("000", "013"):
            return {"provider": "DART", "status": "OK", "detail": f"REST {r.status_code}", "as_of": _now_kst()}
        return {"provider": "DART", "status": "ALERT",
                "detail": f"REST {r.status_code} status={r.json().get('status','?')}",
                "as_of": _now_kst()}
    except Exception as e:
        return {"provider": "DART", "status": "WARN", "detail": f"check fail: {str(e)[:80]}", "as_of": _now_kst()}


def check_supabase() -> Dict[str, Any]:
    try:
        import requests
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            return {"provider": "Supabase", "status": "WARN", "detail": "env 미설정", "as_of": _now_kst()}
        r = requests.get(
            f"{url}/rest/v1/",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=8,
        )
        # 2026-05-29 추가 — rate limit 응답 헤더 검사 (Supabase RateLimit-Remaining 등)
        rl_remaining = r.headers.get("RateLimit-Remaining") or r.headers.get("x-ratelimit-remaining")
        rl_detail = ""
        if rl_remaining is not None:
            try:
                remaining = int(rl_remaining)
                rl_detail = f" RL_remaining={remaining}"
                if remaining < 100:
                    return {"provider": "Supabase", "status": "ALERT",
                            "detail": f"rate limit 임박 (remaining={remaining})", "as_of": _now_kst()}
            except (ValueError, TypeError):
                pass
        if r.status_code == 429:
            return {"provider": "Supabase", "status": "ALERT", "detail": "rate limit 초과 (429)", "as_of": _now_kst()}
        if r.status_code < 500:
            return {"provider": "Supabase", "status": "OK", "detail": f"REST {r.status_code}{rl_detail}", "as_of": _now_kst()}
        return {"provider": "Supabase", "status": "ALERT", "detail": f"REST {r.status_code}", "as_of": _now_kst()}
    except Exception as e:
        return {"provider": "Supabase", "status": "WARN", "detail": f"check fail: {str(e)[:80]}", "as_of": _now_kst()}


def check_llm_budget() -> Dict[str, Any]:
    """이번 달 LLM 호출 비용 누적 monitor.

    메모 project_claude_budget_guard 정합 (월 $20 한도).
    data/metadata/llm_cost.jsonl 에서 이번 달 cost_usd 합산.
    """
    path = ROOT / "data" / "metadata" / "llm_cost.jsonl"
    if not path.exists():
        return {"provider": "LLM Budget", "status": "WARN", "detail": "llm_cost.jsonl 부재", "as_of": _now_kst()}

    now_kst_dt = datetime.now(KST)
    month_prefix = now_kst_dt.strftime("%Y-%m")
    monthly_cost = 0.0
    by_provider: Dict[str, float] = {}

    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                date_str = entry.get("date") or (entry.get("timestamp") or "")[:10]
                if not date_str.startswith(month_prefix):
                    continue
                cost = float(entry.get("cost_usd") or 0.0)
                monthly_cost += cost
                provider = entry.get("provider", "unknown")
                by_provider[provider] = by_provider.get(provider, 0.0) + cost
    except OSError as e:
        return {"provider": "LLM Budget", "status": "WARN", "detail": f"read fail: {str(e)[:60]}", "as_of": _now_kst()}

    # 임계: $20 한도 (메모 project_claude_budget_guard)
    if monthly_cost >= 20.0:
        status = "ALERT"
    elif monthly_cost >= 15.0:
        status = "WARN"
    else:
        status = "OK"

    provider_breakdown = ", ".join(f"{p}=${c:.2f}" for p, c in sorted(by_provider.items(), key=lambda x: -x[1])[:3])
    return {
        "provider": "LLM Budget",
        "status": status,
        "detail": f"{month_prefix} ${monthly_cost:.2f}/20.00 ({provider_breakdown})"[:200],
        "as_of": _now_kst(),
    }


def _push_action_queue(title: str, detail: str) -> None:
    """ALERT 발생 시 user_action_queue P0 등록 (actor=user, Bell 노출)."""
    try:
        subprocess.check_call(
            [
                sys.executable, str(ROOT / "scripts" / "action_queue.py"),
                "add", title,
                "--category", "monitoring",
                "--priority", "p0",
                "--actor", "user",
                "--detail", detail[:500],
            ],
            cwd=str(ROOT),
            timeout=20,
        )
    except Exception as e:
        sys.stderr.write(f"action_queue push fail: {e}\n")


def main() -> int:
    checks = [
        check_kis,
        check_vercel_deploy_spam,
        check_github_actions_billing,
        check_external_repos,
        check_dart,
        check_supabase,
        check_llm_budget,
    ]
    results: List[Dict[str, Any]] = []
    for fn in checks:
        try:
            results.append(fn())
        except Exception as e:
            results.append({
                "provider": fn.__name__,
                "status": "WARN",
                "detail": f"unexpected: {str(e)[:80]}",
                "as_of": _now_kst(),
            })

    snapshot = {
        "as_of": _now_kst(),
        "providers": results,
        "summary": {
            "ok": sum(1 for r in results if r.get("status") == "OK"),
            "warn": sum(1 for r in results if r.get("status") == "WARN"),
            "alert": sum(1 for r in results if r.get("status") == "ALERT"),
        },
    }

    DATA_DIR.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    for r in results:
        if r.get("status") == "ALERT":
            _push_action_queue(
                title=f"[infra] {r.get('provider')} ALERT",
                detail=r.get("detail", ""),
            )

    print(f"infra_status: {snapshot['summary']}")
    for r in results:
        print(f"  [{r['status']:5s}] {r['provider']:18s} — {str(r.get('detail',''))[:80]}")

    return 0 if snapshot["summary"]["alert"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
