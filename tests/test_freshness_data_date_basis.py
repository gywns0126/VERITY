"""신선도 나이 기준 = 쓴 시각 vs 데이터 날짜 (2026-08-09).

배경: 판정이 시각을 읽는 순서가 `collected_at → generated_at → updated_at → as_of` 라
`generated_at`(쓴 시각)이 `as_of`(데이터 날짜)를 이긴다. T+N 소스에서는 이게 어긋난다 —
파일을 방금 썼으면 데이터가 며칠 묵었어도 "신선" 이다.

실측(2026-08-09): `securities_lending` 은 8/8 11:22 에 쓰였는데 내용은 8/6 데이터였다.
쓴 시각 기준 유효 age 0.0h vs 데이터 날짜 기준 24.0h — 35h 가림.

대상은 매니페스트에서 `ts_field: _meta.as_of` 를 지정한 스트림뿐(측정 결과 3개).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import scripts.freshness_shadow_monitor as fm

KST = timezone(timedelta(hours=9))
_DATA_DATE_STREAMS = {"kr_index_daily", "hot_stock", "securities_lending"}


# ── 날짜-only 파싱 ──

def test_compact_date_parsed_as_end_of_day():
    # as_of=20260806 = "8/6 장까지" → 8/6 이 끝난 시점(8/7 00:00)에 완성.
    # 자정으로 잡으면 하루가 통째로 더 늙어 보여 임계가 어긋난다.
    t = fm._parse_ts_kst("20260806")
    assert t == datetime(2026, 8, 7, 0, 0, tzinfo=KST)


def test_iso_date_keeps_midnight_semantics():
    # 🚨 ISO date 는 기존 동작 유지 — 아이템 `date` 필드가 fallback 으로 잡히는 스트림이
    #   나중에 생겼을 때 조용히 24h 젊어지는 것을 막는다.
    assert fm._parse_ts_kst("2026-08-06") == datetime(2026, 8, 6, 0, 0, tzinfo=KST)


def test_iso_datetime_unchanged():
    t = fm._parse_ts_kst("2026-08-07T15:37:59+09:00")
    assert t == datetime(2026, 8, 7, 15, 37, 59, tzinfo=KST)


def test_garbage_returns_none():
    assert fm._parse_ts_kst("20261332") is None      # 8자리지만 날짜 아님
    assert fm._parse_ts_kst("not-a-date") is None
    assert fm._parse_ts_kst("") is None


# ── 매니페스트 배선 ──

def _manifest():
    with open(fm.MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def test_data_date_streams_point_at_as_of():
    streams = {s["id"]: s for s in _manifest()["streams"]}
    for sid in _DATA_DATE_STREAMS:
        assert streams[sid].get("ts_field") == "_meta.as_of", sid
        assert "age_basis" in streams[sid], sid  # 왜 그런지 파일에 남긴다


def test_no_other_stream_uses_data_date_basis():
    # 범위를 넓힐 때는 의도적으로 — 임계(max_age)가 T+N 지연을 감당하는지 재검토 필요.
    others = [s["id"] for s in _manifest()["streams"]
              if s.get("ts_field") == "_meta.as_of" and s["id"] not in _DATA_DATE_STREAMS]
    assert others == []


def test_data_date_streams_read_the_real_files():
    # 배선이 실제로 값을 뽑는지 — 오타로 ts_field 가 빗나가면 NO_TS 로 조용히 떨어진다.
    for s in _manifest()["streams"]:
        if s["id"] not in _DATA_DATE_STREAMS:
            continue
        path = os.path.join(fm.DATA_DIR, s["file"])
        if not os.path.exists(path):  # 로컬 체크아웃에 없을 수 있음
            continue
        ts = fm._extract_ts(fm._load_any(path), s["ts_field"])
        assert ts and len(ts) == 8 and ts.isdigit(), (s["id"], ts)
        assert fm._parse_ts_kst(ts) is not None


def test_data_date_is_never_younger_than_write_time_basis():
    # 데이터 날짜 기준은 쓴 시각 기준보다 젊게 나올 수 없다(= 가림이 사라지는 방향).
    for s in _manifest()["streams"]:
        if s["id"] not in _DATA_DATE_STREAMS:
            continue
        path = os.path.join(fm.DATA_DIR, s["file"])
        if not os.path.exists(path):
            continue
        obj = fm._load_any(path)
        t_write = fm._parse_ts_kst(fm._extract_ts(obj, None) or "")
        t_data = fm._parse_ts_kst(fm._extract_ts(obj, s["ts_field"]) or "")
        if t_write and t_data:
            assert t_data <= t_write, s["id"]
