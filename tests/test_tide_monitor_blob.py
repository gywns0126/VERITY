# -*- coding: utf-8 -*-
"""TIDE 감시 경로 — 공개 blob 헬스 + gh 접근 갭 처리 (2026-08-05).

배경: gh run list 가 private TIDE 를 VERITY 스코프 토큰으로 조회해 66일째 'gh fail'
WARN 만 반복(data/infra_status.json 실측). 실패가 정보가 아니라 소음이었다.
계약: ① 헬스는 공개 blob 으로 본다 ② gh 접근 불가는 WARN 을 만들지 않되 관측 갭으로
명시한다(빌링 감지는 gh 경로가 유일하므로 은폐 금지).
"""
import importlib.util
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "infra_status_monitor", os.path.join(_ROOT, "scripts", "infra_status_monitor.py"))
mon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mon)


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def read(self):
        import json
        return json.dumps(self._p).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _blob(monkeypatch, payload):
    monkeypatch.setattr(mon.urllib.request, "urlopen", lambda *a, **k: _Resp(payload))


def test_blob_critical_is_reported(monkeypatch):
    _blob(monkeypatch, {"health": {"cron_status": "critical", "minutes_since_heartbeat": 30}})
    assert "critical" in (mon._check_tide_blob() or "")


def test_blob_stale_heartbeat_is_reported(monkeypatch):
    _blob(monkeypatch, {"health": {"cron_status": "healthy",
                                   "minutes_since_heartbeat": mon._TIDE_HB_STALE_MIN + 1}})
    assert "정지" in (mon._check_tide_blob() or "")


def test_blob_healthy_is_silent(monkeypatch):
    _blob(monkeypatch, {"health": {"cron_status": "healthy", "minutes_since_heartbeat": 5}})
    assert mon._check_tide_blob() is None


def test_blob_unreachable_is_reported(monkeypatch):
    def _boom(*a, **k):
        raise OSError("network down")
    monkeypatch.setattr(mon.urllib.request, "urlopen", _boom)
    assert "확인 불가" in (mon._check_tide_blob() or "")


def test_gh_failure_does_not_raise_warn_but_is_disclosed(monkeypatch):
    """CI 재현: gh 는 실패하고 blob 은 정상 → status OK, 단 빌링 관측 갭은 detail 에 노출."""
    _blob(monkeypatch, {"health": {"cron_status": "healthy", "minutes_since_heartbeat": 1}})

    def _gh_fail(*a, **k):
        raise mon.subprocess.CalledProcessError(1, "gh")
    monkeypatch.setattr(mon.subprocess, "check_output", _gh_fail)

    r = mon.check_external_repos()
    assert r["status"] == "OK"          # 소음 제거 — 반복 WARN 이 사라진다
    assert "빌링 감지 불가" in r["detail"]  # 관측 갭 은폐 금지


def test_blob_finding_still_raises_warn(monkeypatch):
    _blob(monkeypatch, {"health": {"cron_status": "critical", "minutes_since_heartbeat": 900}})

    def _gh_fail(*a, **k):
        raise mon.subprocess.CalledProcessError(1, "gh")
    monkeypatch.setattr(mon.subprocess, "check_output", _gh_fail)

    r = mon.check_external_repos()
    assert r["status"] == "WARN"
