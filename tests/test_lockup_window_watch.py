# -*- coding: utf-8 -*-
"""락업 창 수급 관측 (2026-08-24 신설).

## 왜

PM 이 XE 를 매수했고 가장 가까운 관측점이 락업 최종만기 2026-10-24 다. 그 창에서 볼 것은
13G 지분 · 공매도 · FTD 세 축인데, 셋 다 **이미 수집되는 발행물**이라 신규 수집은 0 이다.
없던 것은 "그 종목의 그 창을 시계열로 남기는 자리" 뿐이었다.

## 여기서 고정하는 것

- 🚨 **판정 0.** 이 산출물에 등급·경보 문구·매매 시사가 들어가면 RULE 7 위반이다.
- 🚨 **결손을 0 으로 채우지 않는다.** 소스가 없으면 `missing` 에 **이름**으로 남긴다
  ([[feedback_silent_zero_fallback_looks_plausible]] — 0 폴백은 그럴듯해 보여서 오래 산다).
- 델타는 **직전 행 대비**로 같이 적는다. 읽는 사람이 파일 두 개를 대조하게 만들지 않는다.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _load(tmp_path, monkeypatch, holdings=None, short=None, pressure=None):
    spec = importlib.util.spec_from_file_location(
        "lkw", str(_ROOT / "scripts" / "watch" / "lockup_window_watch.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    data = tmp_path / "data"
    (data / "metadata").mkdir(parents=True)
    if holdings is not None:
        (data / "us_major_holdings.json").write_text(json.dumps(holdings), encoding="utf-8")
    if short is not None:
        (data / "us_short_interest.json").write_text(json.dumps(short), encoding="utf-8")
    if pressure is not None:
        (data / "us_short_pressure.json").write_text(json.dumps(pressure), encoding="utf-8")
    monkeypatch.setattr(m, "DATA", str(data))
    monkeypatch.setattr(m, "OUT", str(data / "metadata" / "lockup_watch.jsonl"))
    return m


W = {"ticker": "XE", "name": "X-energy, Inc.", "lockup_final": "2026-10-24", "note": "t"}

HOLD = {"stocks": [{"ticker": "XE", "total": 5, "n_13d": 0, "n_13g": 5,
                    "collected_at": "2026-08-17",
                    "filings": [{"filer": "Amazon.com, Inc.", "pct": 22.9, "shares": 65836948,
                                 "type": "13G", "date": "2026-08-06", "event_date": "06/30/2026"},
                                {"filer": "Ares Partners Holdco LLC", "pct": 12.3, "shares": 38263341,
                                 "type": "13G", "date": "2026-08-12", "event_date": "06/30/2026"}]}]}
SHORT = {"stocks": [{"ticker": "XE", "short_pct": 8.42, "short_pct_prior": 9.66,
                     "days_to_cover": 3.07, "shares_short": 17230467, "report_date": "2026-07-31"}]}
PRESS = {"_meta": {"short_volume_as_of": "20260821"},
         "map": {"XE": {"total_vol": 1961937, "short_ratio": 59.04,
                        "ftd_qty_max": 234838, "ftd_days": 12}}}


def test_snapshot_reads_all_three_axes(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch, HOLD, SHORT, PRESS)
    r = m.snapshot(W)
    assert r["n_13g"] == 5
    assert r["holders_pct_sum"] == 35.2          # 22.9 + 12.3
    assert r["short_pct"] == 8.42
    assert r["ftd_days"] == 12
    assert r["missing"] == []


def test_each_axis_carries_its_own_as_of(tmp_path, monkeypatch):
    """🚨 파일 생성시각이 그 종목의 기준일이 아니다 — 축마다 따로 적는다."""
    m = _load(tmp_path, monkeypatch, HOLD, SHORT, PRESS)
    r = m.snapshot(W)
    assert r["holdings_as_of"] == "2026-08-17"
    assert r["short_as_of"] == "2026-07-31"
    assert r["pressure_as_of"] == "20260821"


def test_missing_source_is_named_not_zeroed(tmp_path, monkeypatch):
    """🚨 결손을 0 으로 채우면 화면이 그럴듯해지고 오래 산다."""
    m = _load(tmp_path, monkeypatch, HOLD, SHORT, {"_meta": {}, "map": {}})
    r = m.snapshot(W)
    assert "short_pressure" in r["missing"]
    assert r["ftd_days"] is None                  # 0 이 아니다
    assert r["short_ratio"] is None


def test_absent_ticker_reports_all_three_missing(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch, {"stocks": []}, {"stocks": []}, {"_meta": {}, "map": {}})
    r = m.snapshot(W)
    assert set(r["missing"]) == {"major_holdings", "short_interest", "short_pressure"}


def test_delta_is_computed_against_the_previous_row(tmp_path, monkeypatch):
    m = _load(tmp_path, monkeypatch, HOLD, SHORT, PRESS)
    prev = m.snapshot(W)
    Path(m.OUT).write_text(json.dumps(prev, ensure_ascii=False) + "\n", encoding="utf-8")

    moved = json.loads(json.dumps(HOLD))
    moved["stocks"][0]["filings"][0]["pct"] = 18.0        # 아마존 22.9 → 18.0
    moved["stocks"][0]["filings"].pop(1)                   # Ares 이탈
    moved["stocks"][0]["n_13g"] = 4
    m2 = _load(tmp_path / "b", monkeypatch, moved, SHORT, PRESS)
    monkeypatch.setattr(m2, "OUT", m.OUT)
    r = m2.snapshot(W)
    assert r["delta"]["holders_pct_sum"] == pytest.approx(18.0 - 35.2, abs=1e-6)
    assert r["holders_exited"] == ["Ares Partners Holdco LLC"]
    assert r["holders_entered"] == []


def test_no_verdict_language_in_output(tmp_path, monkeypatch):
    """🚨 RULE 7 — 관측 기록에 판정·등급·매매 시사가 들어가면 안 된다."""
    m = _load(tmp_path, monkeypatch, HOLD, SHORT, PRESS)
    blob = json.dumps(m.snapshot(W), ensure_ascii=False)
    for banned in ("매수", "매도", "추천", "목표가", "등급", "위험도", "경보"):
        assert banned not in blob, f"판정 어휘 유입: {banned}"
    assert "판정" in blob and "0" in blob          # caveat 가 스스로 신고한다
