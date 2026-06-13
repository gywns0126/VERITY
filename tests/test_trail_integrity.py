"""trail_integrity 무결성 감사기 테스트.

2026-06-13 신설. 결정-trail 의 gap/손실/품질 검출 로직 검증.
"""
import json
import os
import tempfile

import pytest

from api.observability import trail_integrity as ti


def test_business_day_gaps_detects_missing_weekdays():
    import datetime as dt
    dates = [dt.date(2026, 4, 5), dt.date(2026, 4, 8)]  # 4/6(월) 4/7(화) 빠짐
    gaps = ti._business_day_gaps(dates)
    assert "2026-04-06" in gaps and "2026-04-07" in gaps
    assert "2026-04-05" not in gaps  # 일요일 시작점은 제외


def test_business_day_gaps_skips_weekend():
    import datetime as dt
    # 금(4/10) -> 월(4/13): 주말만 사이 = gap 0
    dates = [dt.date(2026, 4, 10), dt.date(2026, 4, 13)]
    assert ti._business_day_gaps(dates) == []


def test_business_day_gaps_continuous():
    import datetime as dt
    dates = [dt.date(2026, 4, 6), dt.date(2026, 4, 7), dt.date(2026, 4, 8)]
    assert ti._business_day_gaps(dates) == []


def test_jsonl_count_and_parse_fail(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text('{"a":1}\n{"a":2}\nNOT_JSON\n{"a":3,"ts":"x"}\n', encoding="utf-8")
    info = ti._jsonl_count_and_last_ts(str(p), "ts")
    assert info["count"] == 4
    assert info["parse_fail"] == 1
    assert info["last_ts"] == "x"


def test_check_trail_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ti, "DATA_DIR", str(tmp_path))
    out = ti._check_trail("nope.jsonl", "jsonl", None, {})
    assert out["ok"] is False
    assert "파일 부재" in out["issues"]


def test_check_trail_shrink_detected(tmp_path, monkeypatch):
    monkeypatch.setattr(ti, "DATA_DIR", str(tmp_path))
    p = tmp_path / "t.jsonl"
    p.write_text('{"a":1}\n{"a":2}\n', encoding="utf-8")
    # baseline 이 3 이었는데 지금 2 = 축소 손실
    out = ti._check_trail("t.jsonl", "jsonl", None, {"t.jsonl": {"size": 3}})
    assert out["ok"] is False
    assert any("축소" in i for i in out["issues"])


def test_check_trail_growth_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(ti, "DATA_DIR", str(tmp_path))
    p = tmp_path / "t.jsonl"
    p.write_text('{"a":1}\n{"a":2}\n{"a":3}\n', encoding="utf-8")
    out = ti._check_trail("t.jsonl", "jsonl", None, {"t.jsonl": {"size": 2}})
    assert out["ok"] is True
    assert out["size"] == 3


def test_audit_severity_on_corrupt_history(tmp_path, monkeypatch):
    monkeypatch.setattr(ti, "DATA_DIR", str(tmp_path))
    hist_dir = tmp_path / "history"
    hist_dir.mkdir()
    monkeypatch.setattr(ti, "HISTORY_DIR", str(hist_dir))
    monkeypatch.setattr(ti, "META_DIR", str(tmp_path / "metadata"))
    # 손상된 최신 스냅샷
    (hist_dir / "2026-06-13.json").write_text("{ broken", encoding="utf-8")
    result = ti.audit()
    assert result["severity"] == "FAIL"
    assert any("파싱불가" in f for f in result["findings"])


def test_update_baseline_skips_on_fail(tmp_path, monkeypatch):
    monkeypatch.setattr(ti, "META_DIR", str(tmp_path))
    monkeypatch.setattr(ti, "_BASELINE_PATH", str(tmp_path / "bl.json"))
    ti.update_baseline({"severity": "FAIL", "trails": [{"trail": "x", "ok": True, "size": 5}]})
    assert not os.path.exists(str(tmp_path / "bl.json"))  # FAIL 은 baseline 미갱신


def test_update_baseline_writes_on_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(ti, "META_DIR", str(tmp_path))
    monkeypatch.setattr(ti, "_BASELINE_PATH", str(tmp_path / "bl.json"))
    ti.update_baseline({"severity": "PASS", "trails": [{"trail": "x", "ok": True, "size": 5}]})
    bl = json.loads((tmp_path / "bl.json").read_text())
    assert bl["x"]["size"] == 5
