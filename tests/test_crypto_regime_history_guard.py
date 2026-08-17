# -*- coding: utf-8 -*-
"""crypto_regime_history 일 1회 가드 — 무엇을 기준으로 세는가.

2026-08-17 N=1 직후 실측으로 교정한 자리다. 최초 구현은 `coverage.range[-1]`(API 데이터의
마지막 날짜)로 판정했는데, 🚨 원본이 하루 늦게 갱신하면 수집해도 range 가 안 움직여
게이트가 계속 열린 채로 남는다 = 30분 크론에서 **하루 48회 외부 호출**(설계는 2회).
이제 우리가 쓴 `collected_at` 으로 판정한다 — 원본 지연과 무관하게 "오늘 한 번 시도했다".

mtime 기준도 금지다 — CI 는 매 run 체크아웃이라 항상 '방금' 이라 게이트가 영원히 거짓이 된다
(2026-08-15 `dart_corp_code.ensure_name_map` 이 정확히 그 형태로 죽어 있었다).
"""
from __future__ import annotations

import datetime as dt
import json
import os

from api.collectors import crypto_regime_history as m

KST = dt.timezone(dt.timedelta(hours=9))


def _write(tmp_path, collected_at, last_range_day):
    p = tmp_path / "h.json"
    p.write_text(json.dumps({
        "collected_at": collected_at,
        "coverage": {"range": ["2017-11-29", last_range_day]},
        "rows": [],
    }), encoding="utf-8")
    return str(p)


def test_skips_when_collected_today(tmp_path, monkeypatch):
    today = dt.datetime.now(KST).strftime("%Y-%m-%d")
    monkeypatch.setattr(m, "OUT", _write(tmp_path, f"{today}T09:00:00+09:00", today))
    assert m._already_today() is True


def test_runs_when_collected_yesterday(tmp_path, monkeypatch):
    y = (dt.datetime.now(KST) - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    today = dt.datetime.now(KST).strftime("%Y-%m-%d")
    monkeypatch.setattr(m, "OUT", _write(tmp_path, f"{y}T09:00:00+09:00", today))
    assert m._already_today() is False


def test_api_lag_does_not_reopen_gate(tmp_path, monkeypatch):
    """🚨 핵심 회귀: 원본이 하루 늦어도(range 가 어제) 오늘 수집했으면 생략한다."""
    today = dt.datetime.now(KST).strftime("%Y-%m-%d")
    y = (dt.datetime.now(KST) - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    monkeypatch.setattr(m, "OUT", _write(tmp_path, f"{today}T09:00:00+09:00", y))
    assert m._already_today() is True, "API 지연이 게이트를 다시 열면 하루 48회 호출 회귀"


def test_missing_file_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "OUT", str(tmp_path / "없음.json"))
    assert m._already_today() is False


def test_corrupt_file_runs(tmp_path, monkeypatch):
    p = tmp_path / "bad.json"
    p.write_text("{깨진", encoding="utf-8")
    monkeypatch.setattr(m, "OUT", str(p))
    assert m._already_today() is False, "파싱 실패는 fail-open(수집) 이어야 한다"


def test_guard_does_not_use_mtime(tmp_path, monkeypatch):
    """파일을 방금 만졌어도 collected_at 이 어제면 실행한다 (CI 체크아웃 함정)."""
    y = (dt.datetime.now(KST) - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    p = _write(tmp_path, f"{y}T09:00:00+09:00", y)
    os.utime(p, None)                      # mtime = 지금
    monkeypatch.setattr(m, "OUT", p)
    assert m._already_today() is False
