"""cron_health sweep CI 격상 검증 (2026-06-17).

배경: sweep 가 전 workflow 최신 실패를 잡지만 일괄 WARNING(🟡) → main CI 회귀
(tests.yml)가 transient cron noise 와 같은 등급에 묻혀 21h frustration.
_SWEEP_CI_CRITICAL allowlist 만 FAIL(🔴) 격상. 순수 헬퍼 단위 검증.
"""
import scripts.cron_health_monitor as m


def _fail(workflow, age_h=3.0):
    return {"workflow": workflow, "conclusion": "failure", "age_h": age_h, "title": "x"}


def test_empty_sweep_keeps_base_severity():
    assert m._sweep_severity_and_findings([], "PASS") == ("PASS", [])
    sev, f = m._sweep_severity_and_findings([], "WARNING")
    assert sev == "WARNING" and f == []


def test_ci_failure_escalates_to_fail():
    sev, findings = m._sweep_severity_and_findings([_fail("tests.yml")], "PASS")
    assert sev == "FAIL"
    assert any("🔴" in x and "tests.yml" in x and "CI 회귀" in x for x in findings)


def test_non_ci_failure_stays_warning():
    sev, findings = m._sweep_severity_and_findings([_fail("some_weekly.yml")], "PASS")
    assert sev == "WARNING"
    assert any("⚠" in x and "some_weekly.yml" in x for x in findings)
    assert all("🔴" not in x for x in findings)


def test_ci_failure_does_not_downgrade_existing_fail():
    sev, _ = m._sweep_severity_and_findings([_fail("tests.yml")], "FAIL")
    assert sev == "FAIL"


def test_non_ci_failure_does_not_downgrade_existing_fail():
    # base FAIL + non-CI sweep → FAIL 유지 (WARNING 로 다운그레이드 금지)
    sev, _ = m._sweep_severity_and_findings([_fail("some_weekly.yml")], "FAIL")
    assert sev == "FAIL"


def test_mixed_ci_and_non_ci_escalates_to_fail():
    sev, findings = m._sweep_severity_and_findings(
        [_fail("some_weekly.yml"), _fail("tests.yml")], "PASS"
    )
    assert sev == "FAIL"
    assert sum("🔴" in x for x in findings) == 1
    assert sum("⚠" in x for x in findings) == 1


def test_tests_yml_is_in_ci_allowlist_and_not_excluded():
    assert "tests.yml" in m._SWEEP_CI_CRITICAL
    assert "tests.yml" not in m._SWEEP_EXCLUDE


def test_rule7_audit_is_ci_critical():
    # RULE 7 자기산식 가설표기 게이트 = 결정론적 코드/콘텐츠 위반 → FAIL 격상
    assert "rule7_audit.yml" in m._SWEEP_CI_CRITICAL
    sev, findings = m._sweep_severity_and_findings([_fail("rule7_audit.yml")], "PASS")
    assert sev == "FAIL"
    assert any("🔴" in x and "rule7_audit.yml" in x for x in findings)


# ── _latest_completed_main_run: branch 오판 차단 (2026-07-23 false P0 회귀) ──

def _run(branch, conclusion, status="completed", ts="2026-07-23T04:00:00Z"):
    return {"headBranch": branch, "conclusion": conclusion, "status": status,
            "createdAt": ts, "displayTitle": "x"}


def test_pr_branch_failure_ignored_main_success_wins():
    # 버그 재현: PR 브랜치 실패(최신) + main 성공(직전) → main 성공 반환(회귀 아님).
    # newstab PR #142 tests.yml 실패가 main 회귀로 오판됐던 정확한 시나리오.
    runs = [
        _run("merge/newstab-into-main", "failure", ts="2026-07-23T04:01:00Z"),
        _run("main", "success", ts="2026-07-23T03:38:00Z"),
    ]
    latest = m._latest_completed_main_run(runs)
    assert latest is not None
    assert latest["headBranch"] == "main"
    assert latest["conclusion"] == "success"


def test_real_main_failure_still_caught():
    # main 최신 완료 run 이 failure → 반환(실 회귀는 여전히 잡힘).
    runs = [
        _run("main", "failure", ts="2026-07-23T05:00:00Z"),
        _run("main", "success", ts="2026-07-23T03:00:00Z"),
    ]
    latest = m._latest_completed_main_run(runs)
    assert latest is not None and latest["conclusion"] == "failure"


def test_no_main_run_returns_none():
    # 창 안에 main run 이 전무(전부 PR) → None (오탐 0, skip).
    runs = [
        _run("feat/x", "failure"),
        _run("fix/y", "success"),
    ]
    assert m._latest_completed_main_run(runs) is None


def test_in_progress_main_run_skipped():
    # main in_progress(미완료)는 건너뛰고 직전 완료 main run 판정.
    runs = [
        _run("main", None, status="in_progress", ts="2026-07-23T06:00:00Z"),
        _run("main", "failure", ts="2026-07-23T05:00:00Z"),
    ]
    latest = m._latest_completed_main_run(runs)
    assert latest is not None and latest["conclusion"] == "failure"
