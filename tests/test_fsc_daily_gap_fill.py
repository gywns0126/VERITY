"""금융위 일봉 갭 채움 검증 (2026-08-09).

배경: `run_daily` 가 `latest` 하루만 당겨서, 하루를 통째로 놓치면(3슬롯 전부 실패)
그날 캔들이 영구히 비었다. 다음 날 run 이 성공해도 안 채워진다 —
`--mode backfill` 을 수동으로 돌리기 전까지. 신선도 보드는 최신 as_of 만 보므로
이 구멍은 영원히 미탐지고, 52주 고저·거래일 수가 오염된다.

러너 IP 간헐 차단(실패율 23%)에 대한 대응을 "매번 성공" 에서 "가끔 성공해도 복구" 로 옮긴다.
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MOD_PATH = os.path.join(_REPO_ROOT, "api", "collectors", "fsc_daily_prices.py")

# 🚨 파일 직접 로드 — 패키지 import 는 collectors/__init__ 이 dotenv 를 당겨 pip 필요.
_spec = importlib.util.spec_from_file_location("fsc_daily_gap_t", _MOD_PATH)
fsc = importlib.util.module_from_spec(_spec)
sys.modules["fsc_daily_gap_t"] = fsc
_spec.loader.exec_module(fsc)

_IDX_PATH = os.path.join(_REPO_ROOT, "api", "collectors", "fsc_index_prices.py")
_ispec = importlib.util.spec_from_file_location("fsc_index_gap_t", _IDX_PATH)
fsc_idx = importlib.util.module_from_spec(_ispec)
sys.modules["fsc_index_gap_t"] = fsc_idx
_ispec.loader.exec_module(fsc_idx)


# ── _candidate_days: 후보 거래일 산정 ──

def test_single_day_when_caught_up_to_previous():
    assert fsc._candidate_days("20260806", "20260807") == ["20260807"]


def test_weekend_skipped_in_gap():
    # 8/1 토 · 8/2 일 제외. 금(7/31) 다음 수집이 목(8/6)이면 월~목 4일을 채운다.
    assert fsc._candidate_days("20260731", "20260806") == [
        "20260803", "20260804", "20260805", "20260806"
    ]


def test_empty_cursor_takes_latest_only():
    # 최초 수집 = 이력 확보가 아니라 오늘치. 이력은 --mode backfill 담당.
    assert fsc._candidate_days("", "20260807") == ["20260807"]


def test_cursor_ahead_or_equal_takes_latest_only():
    assert fsc._candidate_days("20260807", "20260807") == ["20260807"]
    assert fsc._candidate_days("20260810", "20260807") == ["20260807"]


def test_corrupt_cursor_degrades_to_latest():
    assert fsc._candidate_days("2026-08-06", "20260807") == ["20260807"]


def test_gap_capped_to_recent_days():
    days = fsc._candidate_days("20260601", "20260807", max_days=3)
    assert days == ["20260805", "20260806", "20260807"]  # 최근 3 거래일만


def test_default_cap_is_bounded():
    assert fsc._MAX_GAP_DAYS == 10
    assert len(fsc._candidate_days("20250101", "20260807")) == 10


# ── run_daily: 구멍이 실제로 메워지는가 ──

def _row(code: str, bas: str, close: int):
    return {"srtnCd": code, "itmsNm": f"종목{code}", "mrktCtg": "KOSPI", "basDt": bas,
            "clpr": close, "mkp": close, "hipr": close, "lopr": close, "trqu": 1000,
            "trPrc": close * 1000}


def _bulk(bas: str, n: int = 600):
    return [_row(f"{i:06d}", bas, 1000 + i) for i in range(n)]


@pytest.fixture
def wired(monkeypatch):
    """청크·발행을 메모리로 대체. 실제 채워진 캔들 날짜를 관찰한다."""
    chunks = [{"as_of": "20260731", "stocks": {}} for _ in range(fsc.N_CHUNKS)]
    fsc._append_rows(chunks, _bulk("20260731"))
    calls = {"days": [], "saved_as_of": None, "hot": None, "close": None}

    def fake_fetch(day):
        calls["days"].append(day)
        if day == "20260805":
            return []            # 휴장일(또는 원천 미보유) = 빈 응답
        return _bulk(day)

    monkeypatch.setattr(fsc, "_load_chunks", lambda: chunks)
    monkeypatch.setattr(fsc, "fetch_day", fake_fetch)
    monkeypatch.setattr(fsc, "_save_chunks", lambda c, a: calls.__setitem__("saved_as_of", a))
    monkeypatch.setattr(fsc, "emit_hot_stock", lambda r, a: calls.__setitem__("hot", a))
    monkeypatch.setattr(fsc, "emit_close_latest",
                        lambda c, a, r=None: calls.__setitem__("close", a))
    return chunks, calls


def test_missed_days_are_backfilled(monkeypatch, wired):
    # 7/31 까지 있고 8/6 이 최신 = 8/3·8/4·8/6 을 채운다(8/5 는 빈 응답, 주말 제외).
    chunks, calls = wired
    monkeypatch.setattr(fsc, "latest_available_date", lambda: "20260806")
    assert fsc.run_daily() is True
    assert calls["days"] == ["20260803", "20260804", "20260805", "20260806"]
    ent = chunks[fsc._chunk_idx("000001")]["stocks"]["000001"]
    assert [c[0] for c in ent["c"]] == [20260731, 20260803, 20260804, 20260806]
    assert calls["saved_as_of"] == "20260806"
    assert calls["hot"] == "20260806" and calls["close"] == "20260806"


def test_latest_failure_discards_partial(monkeypatch, wired):
    # 중간 날은 받았는데 latest 를 못 받으면 as_of 를 올리지 않고 실패로 신고한다.
    chunks, calls = wired
    monkeypatch.setattr(fsc, "latest_available_date", lambda: "20260805")  # 빈 응답 날짜
    assert fsc.run_daily() is False
    assert calls["saved_as_of"] is None


def test_abnormal_bulk_aborts_without_save(monkeypatch, wired):
    # 벌크가 이상 축소(<500) = API 이상 → 기존 데이터 보존, 저장 금지.
    chunks, calls = wired
    monkeypatch.setattr(fsc, "latest_available_date", lambda: "20260806")
    monkeypatch.setattr(fsc, "fetch_day", lambda day: _bulk(day, n=10))
    assert fsc.run_daily() is False
    assert calls["saved_as_of"] is None


def test_no_op_when_already_latest(monkeypatch, wired):
    # 이미 최신 = 호출 0 (쿼터 낭비 금지). 옛 no-op 경로 회귀 방어.
    chunks, calls = wired
    for ch in chunks:
        ch["as_of"] = "20260806"
    monkeypatch.setattr(fsc, "latest_available_date", lambda: "20260806")
    monkeypatch.setattr(fsc, "_close_latest_current", lambda a: True)
    assert fsc.run_daily() is True
    assert calls["days"] == [] and calls["saved_as_of"] is None


# ── 지수 수집기도 같은 구멍을 갖고 있었다 (kr_index_daily = P1 스트림) ──

def test_index_candidate_days_same_policy():
    assert fsc_idx._candidate_days("20260731", "20260806") == [
        "20260803", "20260804", "20260805", "20260806"
    ]
    assert fsc_idx._MAX_GAP_DAYS == fsc._MAX_GAP_DAYS


def _idx_rows(bas: str, n: int = 8):
    return [{"idxNm": f"지수{i}", "idxCsf": "KRX", "basDt": bas, "clpr": 2500 + i,
             "fltRt": 0.5} for i in range(n)]


def test_index_missed_days_are_backfilled(monkeypatch):
    store = {"_meta": {"as_of": "20260731"}, "indices": {}}
    fsc_idx._append_rows(store, _idx_rows("20260731"))
    seen, saved = [], {}

    def fake_fetch(day):
        seen.append(day)
        return [] if day == "20260805" else _idx_rows(day)

    monkeypatch.setattr(fsc_idx, "_load", lambda: store)
    monkeypatch.setattr(fsc_idx, "fetch_day", fake_fetch)
    monkeypatch.setattr(fsc_idx, "_save", lambda s, a: saved.update({"as_of": a}))
    monkeypatch.setattr(fsc_idx, "latest_available_date", lambda: "20260806")

    assert fsc_idx.run_daily() is True
    assert seen == ["20260803", "20260804", "20260805", "20260806"]
    pts = [p[0] for p in store["indices"]["지수0"]["c"]]
    assert pts == [20260731, 20260803, 20260804, 20260806]
    assert saved["as_of"] == "20260806"


def test_index_latest_failure_discards_partial(monkeypatch):
    store = {"_meta": {"as_of": "20260731"}, "indices": {}}
    saved = {}
    monkeypatch.setattr(fsc_idx, "_load", lambda: store)
    monkeypatch.setattr(fsc_idx, "fetch_day", lambda day: [] if day == "20260806" else _idx_rows(day))
    monkeypatch.setattr(fsc_idx, "_save", lambda s, a: saved.update({"as_of": a}))
    monkeypatch.setattr(fsc_idx, "latest_available_date", lambda: "20260806")
    assert fsc_idx.run_daily() is False
    assert saved == {}
