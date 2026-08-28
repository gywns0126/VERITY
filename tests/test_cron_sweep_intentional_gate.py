"""`exit 1` 이 신호인 워크플로를 "고장" 으로 보고하지 않는지 고정한다 (2026-08-19).

## 왜

PM 이 받은 cron health FAIL 에 세 줄이 있었다:

    ⚠️ attribution_freshness_audit.yml 최신 run failure (102h 전) — 감시목록 밖 silent 실패
    ⚠️ self_assets_weekly.yml 최신 run failure (56h 전) — 감시목록 밖 silent 실패
    ⚠️ site_audit.yml 최신 run failure (56h 전) — 감시목록 밖 silent 실패

🚨 **셋 다 고장이 아니었다.** run 로그를 열어보니 전부 설계된 exit 1 이다:
  · attribution_freshness_audit — `귀속·신선도 감사 P0 발견 — run 로그/summary 확인` exit 1
  · self_assets_weekly          — cron_health=ALERT · vams_hit=WARN
    (yml 주석이 직접 명시: "스크립트가 ALERT 시 exit 1 해도 주간 trail 은 이미 디스크에 append")
  · site_audit                  — `[site_audit] FAIL N건 — exit 1 (게이트 빨강)`

즉 **조용하지 않았고 그게 신호였다.** "silent 실패" 라는 문구가 정반대를 말한 셈이다.
`conclusion == failure` 를 고장의 동의어로 쓴 것이 결함이다.

같은 날 같은 형태를 `alert_dispatcher` 에서도 고쳤다 — 비핵심 소스가 🔴 를 내던 것.
공통 원인 = **판정에 쓸 구분 정보를 갖고 있으면서 쓰지 않았다.**

🚨 등급만 내리고 삼키지 않는다. 문구를 "게이트 발동" 으로 바꿔 무엇을 보라고 지목한다.
"""
from __future__ import annotations

import sys, pathlib

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.cron_health_monitor import (  # noqa: E402
    _SWEEP_INTENTIONAL_GATE, _sweep_severity_and_findings,
)


def _wf(name, streak=1, age=6):
    return {"workflow": name, "conclusion": "failure", "age_h": age, "streak": streak}


def test_intentional_gates_are_not_called_silent_failure():
    wfs = [_wf(n) for n in _SWEEP_INTENTIONAL_GATE]
    sev, findings = _sweep_severity_and_findings(wfs, "PASS")
    joined = " ".join(findings)
    assert "silent 실패" not in joined, f"게이트 발동이 silent 실패로 보고됐다:\n{joined}"
    assert sev != "FAIL", f"의도된 게이트가 FAIL 로 격상됐다: {sev}"
    for n in _SWEEP_INTENTIONAL_GATE:
        assert any(n in f and "게이트 발동" in f for f in findings), f"{n} 미분류"


def test_intentional_gate_is_still_reported():
    """🚨 등급만 내린다 — 삼키면 진짜 발견을 놓친다."""
    sev, findings = _sweep_severity_and_findings([_wf("site_audit.yml")], "PASS")
    hit = [f for f in findings if "site_audit.yml" in f]
    assert hit, "게이트 발동이 통째로 사라졌다"
    assert "run 로그" in hit[0], "무엇을 보라는 지목이 없다"


def test_intentional_gate_not_escalated_by_streak():
    """3연속이어도 격상하지 않는다 — 감사가 계속 P0 를 찾는 것은 고장이 아니다."""
    sev, findings = _sweep_severity_and_findings([_wf("site_audit.yml", streak=5)], "PASS")
    assert sev != "FAIL", f"연속 게이트 발동이 FAIL 로 격상됐다: {sev}"
    assert not any("스스로 낫지 않는 고장" in f for f in findings)


def test_old_intentional_gate_does_not_keep_current_health_yellow():
    sev, findings = _sweep_severity_and_findings(
        [_wf("attribution_freshness_audit.yml", age=317)], "PASS"
    )
    assert sev == "PASS"
    assert findings == []


def test_real_breakage_still_escalates():
    """🚨 목적은 등급을 낮추는 게 아니다 — 미등록 워크플로 3연속은 여전히 🔴."""
    sev, findings = _sweep_severity_and_findings([_wf("unknown_thing.yml", streak=3)], "PASS")
    assert sev == "FAIL", f"진짜 고장이 강등됐다: {sev}"
    assert any("스스로 낫지 않는 고장" in f for f in findings)


def test_gate_list_entries_point_to_real_workflows():
    """목록이 실제 파일을 가리키는지 — 오타로 조용히 무력화되는 것을 막는다."""
    for name in _SWEEP_INTENTIONAL_GATE:
        assert (_ROOT / ".github" / "workflows" / name).exists(), f"{name} 파일 부재"
