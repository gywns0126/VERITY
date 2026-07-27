"""KRX EOD 게시 전환 윈도 false-positive 방어 — _check_krx_open_api 직전영업일 재확인.

2026-06-10. 장 마감 후 KRX 가 당일 EOD 데이터를 게시하기 전, probe 1개(stk_bydd_trd)는 오늘-ok 라
bas_dd=오늘 선택되지만 18-sweep 은 오늘 403/empty → "권한없음 18" 키 오류처럼 오보. 직전 영업일이
정상이면 게시 전환 중(키 유효)으로 판정, 직전일도 forbidden 이면 진짜 error.
"""
import api.health as health


def _summary(ok, forbidden=0, empty=0, error=0, total=18):
    return {"summary": {"ok": ok, "forbidden": forbidden, "empty": empty,
                        "error": error, "total": total}, "bas_dd": ""}


def test_publish_window_race_reports_healthy(monkeypatch):
    monkeypatch.setattr(health, "KRX_API_KEY", "valid-key")
    monkeypatch.setattr(health, "_recent_bas_dd_krx", lambda: "20260610")
    monkeypatch.setattr(health, "_prev_published_bas_dd_krx", lambda b: "20260609")

    def fake_snap(bas_dd, max_rows_per_endpoint=1):
        s = _summary(0, forbidden=18) if bas_dd == "20260610" else _summary(18)
        s["bas_dd"] = bas_dd
        return s
    monkeypatch.setattr(health, "collect_krx_openapi_snapshot", fake_snap)

    ok, detail = health._check_krx_open_api()
    assert ok is True
    assert "게시 전환 중" in detail and "키 유효" in detail


def test_real_key_failure_still_errors(monkeypatch):
    # 오늘+직전일 모두 forbidden = 진짜 키/구독 실패 → error 유지
    monkeypatch.setattr(health, "KRX_API_KEY", "dead-key")
    monkeypatch.setattr(health, "_recent_bas_dd_krx", lambda: "20260610")
    monkeypatch.setattr(health, "_prev_published_bas_dd_krx", lambda b: "20260609")
    monkeypatch.setattr(health, "collect_krx_openapi_snapshot",
                        lambda bas_dd, max_rows_per_endpoint=1: {**_summary(0, forbidden=18), "bas_dd": bas_dd})

    ok, detail = health._check_krx_open_api()
    assert ok is False
    assert "권한없음" in detail


def test_normal_ok_unaffected(monkeypatch):
    monkeypatch.setattr(health, "KRX_API_KEY", "valid-key")
    monkeypatch.setattr(health, "_recent_bas_dd_krx", lambda: "20260609")
    monkeypatch.setattr(health, "collect_krx_openapi_snapshot",
                        lambda bas_dd, max_rows_per_endpoint=1: {**_summary(18), "bas_dd": bas_dd})
    ok, detail = health._check_krx_open_api()
    assert ok is True
    assert "게시 전환 중" not in detail


# ── 2026-07-27 추가 — "미게시(empty)" 를 장애로 오탐하던 갭 ────────────────────
# 관측: 월요일 장중 realtime run 전수가 `ok 2/18 (11%), 빈데이터 16, 권한없음 0, 오류 0
# (basDd=20260727)` → `종합: ERROR`. 같은 로그의 실 생산경로([1.5] Active 갱신)는 정상 5/5,
# krx_mktcap.json bas_dd 도 최신 거래일 정합 = 순수 오탐. 기존 가드는 forbidden/error 조건이라
# empty 우세 케이스를 못 잡았음. _request_krx 의미상 empty = HTTP 200 · rows 0 = 그 날짜 미게시.

def test_empty_dominant_is_not_outage(monkeypatch):
    """empty 우세 + 오류/권한없음 0 = 미게시 윈도. 정상 판정 + 추가 sweep 없음."""
    monkeypatch.setattr(health, "KRX_API_KEY", "valid-key")
    monkeypatch.setattr(health, "_recent_bas_dd_krx", lambda: "20260727")
    calls = []

    def fake_snap(bas_dd, max_rows_per_endpoint=1):
        calls.append(bas_dd)
        return {**_summary(2, empty=16), "bas_dd": bas_dd}
    monkeypatch.setattr(health, "collect_krx_openapi_snapshot", fake_snap)

    ok, detail = health._check_krx_open_api()
    assert ok is True
    assert "미게시" in detail
    # 진단 예산 보호 — 직전일 18-sweep 재확인을 타지 않아야 함
    assert len(calls) == 1


def test_empty_with_errors_still_errors(monkeypatch):
    """empty 우세여도 오류가 섞이면 직전일 재확인 경로 → 직전일도 깨지면 error."""
    monkeypatch.setattr(health, "KRX_API_KEY", "valid-key")
    monkeypatch.setattr(health, "_recent_bas_dd_krx", lambda: "20260727")
    monkeypatch.setattr(health, "_prev_published_bas_dd_krx", lambda b: "20260724")
    monkeypatch.setattr(health, "collect_krx_openapi_snapshot",
                        lambda bas_dd, max_rows_per_endpoint=1: {**_summary(2, empty=14, error=2),
                                                                 "bas_dd": bas_dd})
    ok, detail = health._check_krx_open_api()
    assert ok is False
    assert "degradation" in detail


# ── 2026-07-27 추가 — 진단 예산(_probe deadline) ────────────────────────────────
# realtime 런타임 상한 10분인데 자가진단이 125~345s 소모 → SIGTERM(2/8 run 실패).

def test_probe_skips_past_deadline():
    import time
    hits = []
    r = health._probe("X", lambda: (hits.append(1), (True, "실호출"))[1],
                      deadline_ts=time.time() - 1)
    assert r["status"] == "skipped"
    assert hits == []          # 실호출 0
    assert r["status"] != "error"   # overall status 오염 금지


def test_probe_unbounded_when_no_deadline():
    hits = []
    r = health._probe("X", lambda: (hits.append(1), (True, "ok"))[1])
    assert r["status"] == "ok" and len(hits) == 1
