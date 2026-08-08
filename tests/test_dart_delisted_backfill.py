# -*- coding: utf-8 -*-
"""dart_delisted_backfill 계약 테스트.

이 수집기가 조용히 실패하는 경로:
  ① 백테스트와 제외 규칙이 어긋나 유니버스가 갈라진다
  ② 이미 시계열이 있는 종목을 다시 긁어 DART 쿼터를 태운다
  ③ 응답 0건을 실패로 세어 재시도 루프에 갇힌다
  ④ 별 스키마 파일을 만들어 소비자가 분기한다
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.collectors import dart_delisted_backfill as bf  # noqa: E402


def _write_delisting(tmp_path, last_seen, first_seen=None):
    p = tmp_path / "kr_delisting.json"
    doc = {
        "as_of": "20260731",
        "last_seen": last_seen,
        "first_seen": first_seen or {t: "20200131" for t in last_seen},
    }
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return str(p)


# ── ① 제외 규칙 단일 출처 ──────────────────────────────────────────────────
def test_exclusion_rule_is_shared_with_backtest():
    """제외 판정을 자체 구현하지 않고 백테스트 모듈 것을 그대로 쓴다.

    두 곳에서 따로 정의하면 '백필은 했는데 백테스트가 안 쓰는' 종목이 생긴다.
    """
    src = open(bf.__file__, encoding="utf-8").read()
    assert "from api.quant.backtest.kr_fundamental import" in src
    assert "exclusion_reason" in src
    # 자체 정규식으로 스팩/우선주를 다시 정의하지 않았는지
    assert "스팩" not in src.split('"""')[2] if src.count('"""') > 2 else True


# ── ② 멱등 · 쿼터 보호 ─────────────────────────────────────────────────────
def test_targets_skip_tickers_that_already_have_series(tmp_path, monkeypatch):
    monkeypatch.setattr(bf, "DELIST_PATH",
                        _write_delisting(tmp_path, {"111110": "20220630", "222220": "20230930"}))
    monkeypatch.setattr("api.quant.backtest.kr_fundamental.load_names", lambda: {})
    monkeypatch.setattr("api.quant.backtest.kr_fundamental.load_fundamentals",
                        lambda: {"111110": [{"quarter_end": "2022-03-31"}]})
    got = bf._targets()
    assert [t for t, _, _ in got] == ["222220"]


def test_targets_skip_still_listed(tmp_path, monkeypatch):
    """as_of 와 last_seen 이 같으면 아직 상장 중 — 대상이 아니다."""
    monkeypatch.setattr(bf, "DELIST_PATH",
                        _write_delisting(tmp_path, {"111110": "20260731", "222220": "20230930"}))
    monkeypatch.setattr("api.quant.backtest.kr_fundamental.load_names", lambda: {})
    monkeypatch.setattr("api.quant.backtest.kr_fundamental.load_fundamentals", lambda: {})
    assert [t for t, _, _ in bf._targets()] == ["222220"]


def test_targets_exclude_preferred_and_spac(tmp_path, monkeypatch):
    monkeypatch.setattr(bf, "DELIST_PATH", _write_delisting(
        tmp_path, {"111115": "20220630", "222220": "20220630", "333330": "20220630"}))
    monkeypatch.setattr("api.quant.backtest.kr_fundamental.load_names",
                        lambda: {"333330": "케이비17호스팩"})
    monkeypatch.setattr("api.quant.backtest.kr_fundamental.load_fundamentals", lambda: {})
    assert [t for t, _, _ in bf._targets()] == ["222220"]   # 우선주·스팩 제외


def test_targets_year_span_covers_yoy(tmp_path, monkeypatch):
    """YoY 델타를 위해 최초 관측 **한 해 전**부터 긁는다."""
    monkeypatch.setattr(bf, "DELIST_PATH", _write_delisting(
        tmp_path, {"222220": "20230930"}, first_seen={"222220": "20210131"}))
    monkeypatch.setattr("api.quant.backtest.kr_fundamental.load_names", lambda: {})
    monkeypatch.setattr("api.quant.backtest.kr_fundamental.load_fundamentals", lambda: {})
    (_, y0, y1), = bf._targets()
    assert (y0, y1) == (2020, 2023)


def test_targets_floor_at_min_year(tmp_path, monkeypatch):
    monkeypatch.setattr(bf, "DELIST_PATH", _write_delisting(
        tmp_path, {"222220": "20200630"}, first_seen={"222220": "20200131"}))
    monkeypatch.setattr("api.quant.backtest.kr_fundamental.load_names", lambda: {})
    monkeypatch.setattr("api.quant.backtest.kr_fundamental.load_fundamentals", lambda: {})
    (_, y0, _), = bf._targets()
    assert y0 == bf.MIN_YEAR == 2019


# ── ③ 응답 0건 ≠ 실패 ──────────────────────────────────────────────────────
def test_zero_response_marks_key_done_not_retried():
    """상폐 후 미제출이면 응답 0건이 정상이다 — 실패로 세면 무한 재시도가 된다."""
    src = open(bf.__file__, encoding="utf-8").read()
    assert "응답 0건은 **실패가 아니다**" in src
    # done.add 가 got 유무와 무관하게 실행되는지 (조건 블록 밖)
    body = src.split("def collect(")[1]
    add_line = [ln for ln in body.splitlines() if "done.add(key)" in ln][0]
    assert len(add_line) - len(add_line.lstrip()) == 12   # for-루프 본문 들여쓰기


# ── ④ 스키마 단일 출처 ─────────────────────────────────────────────────────
def test_writes_through_shared_append_not_new_file():
    """기존 jsonl 에 같은 스키마로 append 한다 — 별 파일을 만들지 않는다."""
    src = open(bf.__file__, encoding="utf-8").read()
    assert "_append_quarterly_snapshots" in src
    assert "dart_quarterly_snapshots" in src
    # 자체 출력 경로를 새로 정의하지 않았는지
    assert "OUT_PATH" not in src and "_backfill.jsonl" not in src


def test_reprt_codes_cover_four_quarters():
    assert set(bf.REPRT_CODES) == {"11011", "11014", "11012", "11013"}
    assert len(bf.REPRT_CODES) == 4


def test_progress_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(bf, "PROGRESS_PATH", str(tmp_path / "prog.json"))
    bf._save_progress({"done_keys": ["2020:11011"], "targets": 5})
    assert bf._load_progress()["done_keys"] == ["2020:11011"]


def test_progress_missing_file_is_empty_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(bf, "PROGRESS_PATH", str(tmp_path / "none.json"))
    assert bf._load_progress() == {}


# ── ⑤ 중단 내성 (2026-08-08 실사고) ────────────────────────────────────────
def test_frozen_targets_survive_partial_fill(tmp_path, monkeypatch):
    """🚨 부분 수집 후 재실행이 대상을 다시 계산하면 안 된다.

    실사고: 15/32 구간에서 중단. 2019~2022 만 채워진 종목이 '펀더멘털 보유'로
    분류돼 2023~2025 를 영영 못 받는다 — 그 종목은 조용히 반쪽만 남는다.
    frozen 목록이 있으면 디스크 상태와 무관하게 그대로 쓴다.
    """
    monkeypatch.setattr(bf, "DELIST_PATH",
                        _write_delisting(tmp_path, {"222220": "20250630"}))
    # 이미 시계열이 생긴 상태로 흉내 — 재계산하면 대상에서 빠진다
    monkeypatch.setattr("api.quant.backtest.kr_fundamental.load_names", lambda: {})
    monkeypatch.setattr("api.quant.backtest.kr_fundamental.load_fundamentals",
                        lambda: {"222220": [{"quarter_end": "2019-12-31"}]})
    assert bf._targets() == []                                    # 재계산 = 유실
    assert bf._targets([["222220", 2019, 2025]]) == [("222220", 2019, 2025)]


def test_frozen_targets_ignore_malformed_rows():
    assert bf._targets([["222220", 2019, 2025], ["bad"], None]) == [("222220", 2019, 2025)]


def test_checkpoint_saves_after_every_key():
    """완료 시점에만 저장하면 중단 1회로 진도가 통째 날아간다."""
    src = open(bf.__file__, encoding="utf-8").read()
    body = src.split("def collect(")[1]
    # for-루프 본문 안에서 done.add 직후 체크포인트가 있어야 한다
    lines = body.splitlines()
    i = next(n for n, ln in enumerate(lines) if "done.add(key)" in ln)
    assert "_checkpoint()" in lines[i + 1]
    assert "frozen_targets" in src
