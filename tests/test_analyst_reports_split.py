"""STEP 5.87 분리 회귀 테스트 (네트워크 0 · LLM 0).

2026-08-14 신설. daily_analysis_full 이 4회 연속 실패한 원인은 run 117분 vs 워치독 110분
초과였고, 그 117분의 44%(51.4분)가 STEP 5.87 한 구간이었다. 수집·요약을 별도 cron
(scripts/analyst_reports_cron.py)으로 옮기고 본 파이프라인은 읽어서 붙이기만 하게 했다.

이 파일이 지키는 것 셋:
  ① 본 파이프라인에 **인라인 재수집이 부활하지 않는다.** 되살아나면 51분이 되돌아와
     같은 워치독 초과가 재발한다 — 그게 이 분리의 유일한 실패 모드다.
  ② 우선순위 티커 규칙이 옮겨진 뒤에도 동일하다 (운영 후보 KR + 운영 풀 KR, 순서 유지 dedupe).
     2026-05-18 A2 / 05-19 A2.1 fix 의 의도를 잃으면 매칭이 0/10 으로 되돌아간다.
  ③ 신 워크플로가 CLAUDE.md 7축·RULE 4 를 지킨다 (전용 concurrency group, 파일별 git add).
"""
from __future__ import annotations

import json
import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

MAIN_PY = os.path.join(_ROOT, "api", "main.py")
CRON_PY = os.path.join(_ROOT, "scripts", "analyst_reports_cron.py")
WF_YML = os.path.join(_ROOT, ".github", "workflows", "analyst_reports.yml")


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


# ── ① 인라인 재수집 부활 금지 ──────────────────────────────────────────────

def test_pipeline_does_not_collect_or_summarize_inline():
    """main.py 는 리포트를 수집하거나 요약하지 않는다 — 읽어서 붙이기만."""
    src = _read(MAIN_PY)
    assert "scout_reports(" not in src, (
        "main.py 에 scout_reports 호출이 되살아났다 — 51분이 파이프라인으로 되돌아온다")
    assert "run_report_summarizer(" not in src, (
        "main.py 에 run_report_summarizer 호출이 되살아났다 — 51분 재유입")
    # import 자체도 없어야 한다 (되살리기 쉬운 상태를 남기지 않는다)
    assert "from api.collectors.ReportScout import" not in src
    assert "from api.analyzers.report_summarizer import run_report_summarizer" not in src


def test_pipeline_reads_summaries_file():
    """분리 후에도 attach 경로는 살아 있어야 한다 (Brain 컴포넌트 유지)."""
    src = _read(MAIN_PY)
    assert "SUMMARIES_PATH" in src
    assert "analyst_report_summary" in src
    # 신선도 이탈을 조용히 넘기지 않는다
    assert "stale" in src.split("[5.87]")[1][:1500]


def test_separated_runner_owns_collection():
    """분리 러너가 수집·요약을 실제로 수행한다."""
    src = _read(CRON_PY)
    assert "scout_reports(" in src
    assert "run_report_summarizer(" in src


# ── ② 우선순위 규칙 보존 ───────────────────────────────────────────────────

def test_priority_tickers_rule(tmp_path, monkeypatch):
    """운영 후보 KR + 운영 풀 KR, 순서 유지 dedupe, USD 제외, 6자리 zero-pad."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("arc", CRON_PY)
    arc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arc)

    monkeypatch.setattr(arc, "load_universe_candidates", None, raising=False)

    fake_snap = {"candidates": [
        {"ticker": "005930", "currency": "KRW"},
        {"ticker": "AAPL", "currency": "USD"},      # USD 제외
        {"ticker": "3550", "currency": "KRW"},       # zero-pad
        {"ticker": "005930", "currency": "KRW"},     # 중복
    ]}
    import api.utils.universe_candidates as uc
    monkeypatch.setattr(uc, "load_universe_candidates", lambda **k: fake_snap)

    recs = [
        {"ticker": "000660", "currency": "KRW"},
        {"ticker": "005930", "currency": "KRW"},     # 후보와 중복 → dedupe
        {"ticker": "TSLA", "currency": "USD"},       # 제외
    ]
    rp = tmp_path / "recommendations.json"
    rp.write_text(json.dumps(recs), encoding="utf-8")
    monkeypatch.setattr(arc, "RECOMMENDATIONS", str(rp))

    got = arc._priority_tickers()
    assert got == ["005930", "003550", "000660"], got
    assert all(len(t) == 6 and t.isdigit() for t in got)


def test_kr6_normalizer():
    import importlib.util
    spec = importlib.util.spec_from_file_location("arc2", CRON_PY)
    arc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arc)
    assert arc._kr6("5930") == "005930"
    assert arc._kr6("005930.KS") == "005930"
    assert arc._kr6("AAPL") == ""
    assert arc._kr6(None) == ""


# ── 전량 실패 가드 ─────────────────────────────────────────────────────────

def test_total_failure_guard_present():
    """건수 0인데 성공 종료하면 신선도 보드가 초록불로 통과한다 — exit 1 이어야 한다."""
    src = _read(CRON_PY)
    assert "return 1" in src
    assert "전량 실패" in src
    # dev/staging 은 mock 이 0을 주는 게 정상 → 가드 예외
    assert 'VERITY_MODE' in src and '"dev", "staging"' in src


# ── ③ 워크플로 규율 (CLAUDE.md 7축 / RULE 4) ───────────────────────────────

def test_workflow_uses_dedicated_concurrency_group():
    """verity-data-write 공유 금지 — 그룹당 pending 1개라 축출 사고가 난다."""
    src = _read(WF_YML)
    assert "group: verity-analyst-reports" in src
    assert "verity-data-write" not in re.sub(r"^\s*#.*$", "", src, flags=re.M)
    # 50분 작업이라 중도 취소하면 그날 산출물이 사라진다
    assert "cancel-in-progress: false" in src


def test_workflow_git_add_is_per_file():
    """RULE 4 — 글롭 묶음 금지. 미매칭 시 원자적 전체 실패(8/9 사고)."""
    src = _read(WF_YML)
    # 실제 셸 명령 줄만 — 주석(#) 안의 'git add' 언급은 제외한다.
    real = []
    for line in src.splitlines():
        s = line.strip()
        if s.startswith("#") or not s.startswith("git add "):
            continue
        real.append(s[len("git add "):].split("2>")[0].strip())
    assert "data/analyst_reports.json" in real
    assert "data/report_summaries.json" in real
    for a in real:
        assert "*" not in a, f"글롭 사용 금지: {a}"
        assert len(a.split()) == 1, f"한 줄 다중 add 금지: {a}"


def test_workflow_runs_before_consumers():
    """소비자(universe_scan 15:30 · daily_analysis_full 16:50 KST)보다 앞서야 한다."""
    import yaml
    with open(WF_YML, encoding="utf-8") as f:
        d = yaml.safe_load(f)
    sched = (d.get(True) or d.get("on") or {}).get("schedule")
    assert sched, "schedule 누락"
    minute, hour = sched[0]["cron"].split()[:2]
    kst_hour = (int(hour) + 9) % 24
    assert kst_hour < 15, f"KST {kst_hour}시 — universe_scan(15:30)보다 앞서야 한다"
    assert minute != "0", "정각 회피 (혼잡 시간대 정각에 76개 cron 이 몰린다)"


def test_workflow_timeout_covers_measured_duration():
    """실측 51.4분 + 마진. 너무 짧으면 매일 잘리고, 너무 길면 러너를 오래 점유한다."""
    import yaml
    with open(WF_YML, encoding="utf-8") as f:
        d = yaml.safe_load(f)
    t = d["jobs"]["collect"]["timeout-minutes"]
    assert 60 <= t <= 90, t


def test_no_kis_usage_in_new_workflow():
    """RULE 1 — 신 워크플로가 KIS 토큰 발급 경로를 만들지 않는다."""
    wf = _read(WF_YML)
    cron = _read(CRON_PY)
    for src in (wf, cron):
        assert "KIS_" not in src
        assert "kis_broker" not in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
