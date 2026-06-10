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
