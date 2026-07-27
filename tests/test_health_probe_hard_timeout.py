"""프로브 1건 하드 상한 + 동시 실행 — 느린 프로브 하나가 진단 전체를 삼키는 것 차단.

2026-07-27 N=1 실측 후속. 전체 예산(deadline_ts)만으로는 못 막힘이 실운영에서 드러남:
deadline 은 프로브 "사이"에서만 평가되므로 단일 프로브가 늘어지면 무력.
  · run 30246412723 — dart 프로브 단독 197,727ms → 90s 예산 무력화 + 나머지 13 프로브 skip
    (= 감시 공백까지 동반)
  · run 30239950220 — 진단 428,589ms → realtime 10분 SIGTERM 재발
→ 프로브별 join timeout + 동시 실행. 진단 전체 wall clock 이 probe_timeout 한 겹으로 bound.
"""
import time

import api.health as health


def _fast(tag="ok"):
    return lambda: (True, tag)


def _slow(seconds):
    def _fn():
        time.sleep(seconds)
        return True, "늦게 도착"
    return _fn


def test_slow_probe_does_not_starve_others():
    """느린 프로브 1개가 나머지를 밀어내지 않아야 함 (동시 실행)."""
    specs = [
        ("slow", "Slow", _slow(5)),
        ("a", "A", _fast()),
        ("b", "B", _fast()),
        ("c", "C", _fast()),
    ]
    t0 = time.monotonic()
    res = health._probe_all(specs, probe_timeout=1)
    elapsed = time.monotonic() - t0

    assert res["slow"]["status"] == "timeout"
    # 순차였다면 slow 뒤의 a/b/c 가 전부 skip 됐을 자리
    for k in ("a", "b", "c"):
        assert res[k]["status"] == "ok", res[k]
    # wall clock = 상한 한 겹 (합산 아님)
    assert elapsed < 3, elapsed


def test_timeout_is_not_error():
    """상류 지연은 error 아님 — 종합 status 를 오염시키면 안 됨."""
    res = health._probe_all([("slow", "Slow", _slow(3))], probe_timeout=0.5)
    assert res["slow"]["status"] == "timeout"
    assert res["slow"]["status"] != "error"
    assert "미응답" in res["slow"]["detail"]


def test_deadline_still_skips_remaining():
    """전체 예산이 이미 끝났으면 남은 프로브는 실호출 없이 skipped."""
    hits = []

    def _tracked():
        hits.append(1)
        return True, "ok"

    res = health._probe_all(
        [("a", "A", _tracked), ("b", "B", _tracked)],
        probe_timeout=5,
        deadline_ts=time.time() - 1,
    )
    assert all(v["status"] == "skipped" for v in res.values())
    assert hits == []


def test_all_fast_probes_complete():
    res = health._probe_all([(f"k{i}", f"L{i}", _fast()) for i in range(6)], probe_timeout=5)
    assert len(res) == 6
    assert all(v["status"] == "ok" for v in res.values())


def test_probe_exception_still_error():
    """예외는 timeout 이 아니라 error 로 남아야 함 (실장애 감지 보존)."""
    def _boom():
        raise RuntimeError("상류 5xx")
    res = health._probe_all([("x", "X", _boom)], probe_timeout=5)
    assert res["x"]["status"] == "error"


def test_timeout_and_skipped_excluded_from_overall_errors(monkeypatch):
    """timeout/skipped 가 run_health_check 의 errors 로 승격되지 않아야 함."""
    monkeypatch.setattr(health, "check_api_health",
                        lambda **kw: {
                            "dart": {"status": "timeout", "latency_ms": 25000, "detail": "25s 내 미응답"},
                            "fred": {"status": "skipped", "latency_ms": 0, "detail": "예산 초과"},
                            "telegram": {"status": "ok", "latency_ms": 10, "detail": "정상"},
                        })
    monkeypatch.setattr(health, "check_github_worker", lambda: {"status": "ok", "detail": ""})
    monkeypatch.setattr(health, "check_data_recency", lambda: {"status": "ok", "files": {}})
    monkeypatch.setattr(health, "check_version_sync", lambda: {})

    res = health.run_health_check(budget_seconds=90, probe_timeout=25)
    assert res["errors"] == [], res["errors"]
    assert res["status"] == "ok"
