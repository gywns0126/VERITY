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
