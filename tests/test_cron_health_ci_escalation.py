"""cron_health sweep CI 격상 검증 (2026-06-17).

배경: sweep 가 전 workflow 최신 실패를 잡지만 일괄 WARNING(🟡) → main CI 회귀
(tests.yml)가 transient cron noise 와 같은 등급에 묻혀 21h frustration.
_SWEEP_CI_CRITICAL allowlist 만 FAIL(🔴) 격상. 순수 헬퍼 단위 검증.
"""
import scripts.cron_health_monitor as m


def _fail(workflow, age_h=3.0, streak=1):
    return {"workflow": workflow, "conclusion": "failure", "age_h": age_h, "title": "x",
            "streak": streak}


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


# ── 연속 실패 격상 (2026-08-08): transient 1~2회 vs 스스로 낫지 않는 고장 구분 ──

def test_single_failure_stays_warning_no_streak_label():
    sev, findings = m._sweep_severity_and_findings([_fail("kr_chart_daily.yml", streak=1)], "PASS")
    assert sev == "WARNING"
    assert all("연속" not in x for x in findings)


def test_two_consecutive_labels_streak_but_stays_warning():
    # 러너 IP 추첨으로 두 슬롯 연달아 튕기는 것은 실측 정상 범위 — 라벨만 붙이고 격상 안 함.
    sev, findings = m._sweep_severity_and_findings([_fail("kr_chart_daily.yml", streak=2)], "PASS")
    assert sev == "WARNING"
    assert any("2연속" in x for x in findings)
    assert all("🔴" not in x for x in findings)


def test_three_consecutive_escalates_to_fail():
    sev, findings = m._sweep_severity_and_findings([_fail("some_weekly.yml", streak=3)], "PASS")
    assert sev == "FAIL"
    assert any("🔴" in x and "3연속" in x and "낫지 않는" in x for x in findings)


# ── 산출물 게이트 (2026-08-09): run 실패 ≠ 데이터 손실 ──

_MAP = {"kr_chart_daily.yml": ["kr_index_daily", "hot_stock"]}


def test_fresh_artifacts_block_escalation():
    # 8/9 07:23 실제 오보 재현 — kr_chart_daily 3연속 실패 + 스트림 전부 신선 = P0 아님.
    sev, findings = m._sweep_severity_and_findings(
        [_fail("kr_chart_daily.yml", streak=3)], "PASS", stale_ids=[], wf_streams=_MAP
    )
    assert sev == "WARNING"
    assert any("산출물은 신선" in x and "kr_index_daily" in x for x in findings)
    assert all("🔴" not in x for x in findings)


def test_stale_artifact_still_escalates():
    # 같은 3연속인데 스트림이 stale = 진짜 고장 → 격상.
    sev, findings = m._sweep_severity_and_findings(
        [_fail("kr_chart_daily.yml", streak=3)], "PASS",
        stale_ids=["kr_index_daily"], wf_streams=_MAP,
    )
    assert sev == "FAIL"
    assert any("🔴" in x for x in findings)


def test_unmapped_workflow_stays_strict():
    # 스트림 미등록 = 신선도를 증명할 수 없음 → 엄격 쪽(격상 유지).
    sev, _ = m._sweep_severity_and_findings(
        [_fail("some_weekly.yml", streak=3)], "PASS", stale_ids=[], wf_streams=_MAP
    )
    assert sev == "FAIL"


def test_freshness_unavailable_stays_strict():
    # freshness 판정 자체가 실패(stale_ids=None) → 격상 유지. 침묵으로 넘기지 않는다.
    sev, _ = m._sweep_severity_and_findings(
        [_fail("kr_chart_daily.yml", streak=3)], "PASS", stale_ids=None, wf_streams=_MAP
    )
    assert sev == "FAIL"


def test_workflow_stream_map_reads_real_registry():
    # 실 매니페스트 파싱 — kr_chart_daily 는 kr_index_daily·hot_stock 를 만든다.
    mp = m._workflow_stream_map()
    assert "kr_chart_daily.yml" in mp
    assert "kr_index_daily" in mp["kr_chart_daily.yml"]
    assert "crypto" in mp.get("crypto_collect.yml", [])
    assert "dividends_kr_ksd" in mp.get("dividend_ksd.yml", [])


def test_known_degraded_never_escalates():
    # 원인 확정 + 조치가 시간 대기(월 16~25일 재시도 창) = 매 회차 알림 금지.
    assert "nps_employment.yml" in m._SWEEP_KNOWN_DEGRADED
    sev, findings = m._sweep_severity_and_findings([_fail("nps_employment.yml", streak=9)], "PASS")
    assert sev == "WARNING"
    assert any("원인 확정" in x for x in findings)
    assert all("🔴" not in x for x in findings)


def test_missing_streak_key_defaults_safe():
    # streak 키 없는 옛 형태 dict = 격상 없음(기본 WARNING). 회귀 방어.
    legacy = {"workflow": "some_weekly.yml", "conclusion": "failure", "age_h": 2.0, "title": "x"}
    sev, _ = m._sweep_severity_and_findings([legacy], "PASS")
    assert sev == "WARNING"


def _r(branch, conclusion, status="completed"):
    return {"headBranch": branch, "conclusion": conclusion, "status": status,
            "createdAt": "2026-08-08T04:00:00Z", "displayTitle": "x"}


def test_streak_counts_only_completed_main_runs():
    runs = [_r("feat/x", "failure"),            # PR 브랜치 = 무시
            _r("main", None, status="in_progress"),  # 미완료 = 무시
            _r("main", "failure"), _r("main", "timed_out"), _r("main", "failure"),
            _r("main", "success"), _r("main", "failure")]
    assert m._main_failure_streak(runs) == 3


def test_streak_zero_when_latest_main_success():
    assert m._main_failure_streak([_r("main", "success"), _r("main", "failure")]) == 0


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
