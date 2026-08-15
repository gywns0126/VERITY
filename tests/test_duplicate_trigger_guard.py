"""daily_analysis_full 중복 트리거 가드 회귀 테스트 (네트워크 0).

2026-08-15 신설. 이 워크플로는 트리거가 둘이다 — GH `schedule` + Vercel
`repository_dispatch`(2026-05-18 "schedule silent miss 회피" fallback). GH 가 정상
발화하면 **둘 다 돈다**. fallback 에 "본편이 이미 돌았나" 확인이 없었다.

실측 (GitHub API 표본 60건 / 20일): 중복 쌍 **16건**.
  예) 08-14T21:30 dispatch(실패 110분) + 21:49 schedule(성공 146분) = 슬롯 하나에 256분.
      두 번째는 concurrency 큐에서 96분 대기 후 시작했다.

🚨 이 테스트가 지키는 핵심 = **선행이 성공했을 때만 건너뛴다.**
   중복이 우연히 재시도 역할을 했다 — 08-14 는 dispatch 가 실패하고 schedule 이 성공해
   그날 산출물을 건졌다. 조건을 "선행이 존재하면 skip" 으로 넓히면 그 구제가 사라진다.

그리고 **fail-open** — 조회 실패·자기 run 미발견·판단 불가는 전부 실행이다.
슬롯을 비우는 것이 이 fallback 이 막으려던 사고다.
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys

import pytest
import yaml

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(_ROOT, ".github", "workflows", "daily_analysis_full.yml")
WF_UNIVERSE = os.path.join(_ROOT, ".github", "workflows", "universe_scan.yml")


def _wf_src() -> str:
    with open(WF, encoding="utf-8") as f:
        return f.read()


GUARD = os.path.join(_ROOT, "scripts", "ci", "duplicate_run_guard.py")


def _judge(runs, self_id, window="120"):
    """배포되는 스크립트 자체를 돌린다 — 사본 검사는 의미가 없다."""
    p = subprocess.run(
        [sys.executable, GUARD],
        input=json.dumps({"workflow_runs": runs}),
        capture_output=True, text=True,
        env={**os.environ, "SELF": str(self_id), "WINDOW_MIN": window},
    )
    assert p.returncode == 0, f"가드 실행 실패: {p.stderr[:300]}"
    m = re.search(r"^run=([01])$", p.stdout, re.M)
    assert m, f"run= 출력 없음: {p.stdout!r}"
    return m.group(1), p.stdout


def _run(rid, created, conclusion="success", event="schedule"):
    return {"id": rid, "created_at": created, "conclusion": conclusion,
            "status": "completed", "event": event}


# ── 핵심: 선행 성공일 때만 생략 ────────────────────────────────────────────

def test_skips_when_prior_run_succeeded():
    me = _run(2, "2026-08-15T05:00:00Z", None)
    prev = _run(1, "2026-08-15T04:30:00Z", "success", "repository_dispatch")
    verdict, out = _judge([me, prev], 2)
    assert verdict == "0", out
    assert "중복 실행 생략" in out


def test_runs_when_prior_run_failed():
    """🚨 08-14 실사례 — dispatch 실패 후 schedule 이 그날을 건졌다. 그 구제를 지운다면 회귀."""
    me = _run(2, "2026-08-15T05:00:00Z", None)
    prev = _run(1, "2026-08-15T04:30:00Z", "failure", "repository_dispatch")
    verdict, _ = _judge([me, prev], 2)
    assert verdict == "1"


def test_runs_when_prior_run_cancelled():
    me = _run(2, "2026-08-15T05:00:00Z", None)
    prev = _run(1, "2026-08-15T04:30:00Z", "cancelled", "repository_dispatch")
    assert _judge([me, prev], 2)[0] == "1"


def test_runs_when_prior_still_in_progress():
    """결론 미확정 = 성공 확인 불가 → 실행 (fail-open)."""
    me = _run(2, "2026-08-15T05:00:00Z", None)
    prev = {"id": 1, "created_at": "2026-08-15T04:30:00Z", "conclusion": None,
            "status": "in_progress", "event": "repository_dispatch"}
    assert _judge([me, prev], 2)[0] == "1"


# ── 창(window) 경계 ────────────────────────────────────────────────────────

def test_prior_outside_window_does_not_skip():
    """정규 슬롯 간격은 13.7h 이상이라 창 밖 성공분으로 생략되면 안 된다."""
    me = _run(2, "2026-08-15T05:00:00Z", None)
    old = _run(1, "2026-08-14T16:00:00Z", "success")
    assert _judge([me, old], 2)[0] == "1"


def test_future_run_does_not_skip():
    """자기보다 나중에 생성된 run 으로는 생략하지 않는다 (gap 음수)."""
    me = _run(2, "2026-08-15T05:00:00Z", None)
    later = _run(3, "2026-08-15T05:30:00Z", "success")
    assert _judge([me, later], 2)[0] == "1"


# ── fail-open ─────────────────────────────────────────────────────────────

def test_self_not_found_is_fail_open():
    assert _judge([_run(1, "2026-08-15T04:30:00Z", "success")], 999)[0] == "1"


def test_empty_list_is_fail_open():
    assert _judge([], 1)[0] == "1"


def test_malformed_payload_is_fail_open():
    p = subprocess.run(
        [sys.executable, GUARD], input="not json",
        capture_output=True, text=True,
        env={**os.environ, "SELF": "1", "WINDOW_MIN": "120"},
    )
    assert p.returncode == 0
    assert re.search(r"^run=1$", p.stdout, re.M), p.stdout


# ── 워크플로 배선 ──────────────────────────────────────────────────────────

def test_analyze_job_gated_on_guard():
    d = yaml.safe_load(_wf_src())
    jobs = d["jobs"]
    assert "guard" in jobs, "guard job 이 사라졌다"
    a = jobs["analyze"]
    assert a.get("needs") == "guard" or "guard" in (a.get("needs") or [])
    assert "needs.guard.outputs.run" in str(a.get("if", "")), a.get("if")
    assert jobs["guard"]["outputs"]["run"], "guard 출력 미배선"


def test_manual_dispatch_never_skipped():
    """수동 실행은 오퍼레이터 의도 — 가드 미적용."""
    src = _wf_src()
    assert 'github.event_name }}" = "workflow_dispatch"' in src
    seg = src.split("workflow_dispatch")[2][:200] if src.count("workflow_dispatch") > 2 else src
    assert "run=1" in seg


def test_workflow_calls_the_script_not_inline():
    """🚫 인라인 파이썬 금지 — YAML 블록 스칼라 들여쓰기가 깨져 워크플로가 무효가 된다.

    2026-08-15 작성 중 실측: 인라인으로 두었더니 yaml.safe_load 가 ScannerError 를 냈다.
    """
    src = _wf_src()
    assert "scripts/ci/duplicate_run_guard.py" in src
    assert "python3 -c '" not in src, "판정 로직이 인라인으로 되돌아왔다"
    yaml.safe_load(src)  # 파싱 자체가 회귀 가드


def test_guard_job_checks_out_repo():
    """스크립트를 쓰려면 체크아웃이 필요하다 — 빠지면 가드가 매번 실패한다."""
    d = yaml.safe_load(_wf_src())
    steps = d["jobs"]["guard"]["steps"]
    assert any("checkout" in str(s.get("uses", "")).lower() for s in steps)


def test_guard_does_not_touch_analyze_timeout():
    """🚨 analyze 의 240분 예산·워치독은 다른 세션 소관 — 가드가 건드리지 않는다."""
    d = yaml.safe_load(_wf_src())
    assert d["jobs"]["analyze"]["timeout-minutes"] == 240
    assert d["jobs"]["guard"]["timeout-minutes"] <= 10, "가드는 가벼워야 한다"


# ── universe_scan 동일 적용 (2026-08-15) ───────────────────────────────────
# 실측 중복 4건 / 20일, 4건 모두 양쪽 성공 = 순수 낭비(run 당 35~53분).
# 🚨 이 워크플로는 universe_candidates.json 생산자다 — 잘못 건너뛰면 daily_analysis 가
#   26h stale 게이트로 중단된다. 선행 '성공' 조건과 fail-open 이 그 방향을 막는다.

def _uni_src() -> str:
    with open(WF_UNIVERSE, encoding="utf-8") as f:
        return f.read()


def test_universe_scan_gated_on_guard():
    d = yaml.safe_load(_uni_src())
    jobs = d["jobs"]
    assert "guard" in jobs, "universe_scan 가드 job 이 없다"
    sc = jobs["scan"]
    assert sc.get("needs") == "guard" or "guard" in (sc.get("needs") or [])
    assert "needs.guard.outputs.run" in str(sc.get("if", ""))


def test_universe_scan_uses_shared_script():
    src = _uni_src()
    assert "scripts/ci/duplicate_run_guard.py" in src
    assert "python3 -c '" not in src, "판정 로직이 인라인으로 되돌아왔다"
    assert "universe_scan.yml/runs" in src, "자기 워크플로가 아닌 것을 조회하고 있다"
    yaml.safe_load(src)


def test_universe_scan_budget_untouched():
    """스캔 예산(60분)·자체 concurrency 그룹은 가드가 건드리지 않는다."""
    d = yaml.safe_load(_uni_src())
    assert d["jobs"]["scan"]["timeout-minutes"] == 60
    assert d["concurrency"]["group"] == "verity-universe-scan"
    assert d["concurrency"]["cancel-in-progress"] is False


def test_each_workflow_queries_its_own_runs():
    """가드가 남의 워크플로 run 을 보고 판단하면 엉뚱하게 생략된다."""
    assert "daily_analysis_full.yml/runs" in _wf_src()
    assert "universe_scan.yml/runs" not in _wf_src()
    assert "daily_analysis_full.yml/runs" not in _uni_src()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
