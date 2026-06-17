"""macro_snapshot stale-ok degrade 기본값 검증 (2026-06-17).

배경: GitHub schedule throttle 로 macro_collect cron 이 30분 의도 대비 ~5h 로
드물게 실행 → strict load(max_stale_minutes=45) 거의 항상 miss → inline fetch.
inline fetch 타임아웃/실패 시 빈 {} 로 떨어지면 실데이터 공백 (deadman switch 검사).
load_macro_snapshot_stale_ok 가 신선도 무관 디스크 snapshot 을 degrade 기본값으로 공급.
"""
import json

import api.utils.macro_snapshot as m


def _write_snap(tmp_path, monkeypatch, payload):
    p = tmp_path / "macro_snapshot.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(m, "SNAPSHOT_PATH", str(p))
    m.reset_cache()


def test_stale_ok_returns_snapshot_regardless_of_age(tmp_path, monkeypatch):
    # 1년 전 = strict load 라면 stale miss, stale_ok 는 그대로 반환
    _write_snap(tmp_path, monkeypatch, {
        "collected_at": "2025-06-17T19:13:55+09:00",
        "macro": {"usd_krw": {"value": 1380.0}},
        "bonds": {"us_10y": {"value": 4.3}},
    })
    # strict 는 stale 로 miss
    assert m.load_macro_snapshot(max_stale_minutes=45) is None
    # stale_ok 는 실데이터 반환
    snap = m.load_macro_snapshot_stale_ok()
    assert snap is not None
    assert snap["macro"]["usd_krw"]["value"] == 1380.0
    assert snap["bonds"]["us_10y"]["value"] == 4.3


def test_stale_ok_returns_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "SNAPSHOT_PATH", str(tmp_path / "nonexistent.json"))
    m.reset_cache()
    assert m.load_macro_snapshot_stale_ok() is None


def test_stale_ok_survives_corrupt_json(tmp_path, monkeypatch):
    p = tmp_path / "macro_snapshot.json"
    p.write_text("{ not valid json", encoding="utf-8")
    monkeypatch.setattr(m, "SNAPSHOT_PATH", str(p))
    m.reset_cache()
    assert m.load_macro_snapshot_stale_ok() is None
