"""내용 신선도 축 회귀 테스트 (PM 2026-08-07 "상시 신선도 체크").

증명하려는 것 = **2026-08-07 국민연금 사고를 이 축이 실제로 잡는가**.
그 사고에서 보드는 파일 시각만 보고 "fresh" 를 냈다:
    last_ts 2026-07-08 · age 29.7일 < SLA 35일 → fresh
    실제 내용은 2026년 5월분 (7/15 수집이 timeout 으로 죽어 6월분 유실)
파일은 계속 새로 써지므로 기존 축으로는 영원히 잡히지 않는다.

같이 지키는 것:
  · opt-in — 임계 미등록 스트림은 unknown, 기존 판정을 건드리지 않는다(오탐 억제).
  · 미래 일자는 stale 이 아니라 unknown (소스 오기/타임존 착오에 잘못된 경보 금지).
  · glob 스트림에서 NameError 가 나지 않는다(obj 미초기화 결함, 구현 중 발견).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.observability.content_freshness import (  # noqa: E402
    content_status,
    extract_content_ts,
    parse_content_date,
)

KST = timezone(timedelta(hours=9))
NPS_MAX = 86400  # 60일 — SLA 등록값


def test_reproduces_the_2026_08_07_incident():
    """5월 데이터를 8월에 들고 있으면 stale — 이 사고가 잡혀야 한다."""
    now = datetime(2026, 8, 7, 12, 0, tzinfo=KST)
    ts = extract_content_ts({"_meta": {"data_ym_latest": "202605"}}, "data_ym_latest")
    assert ts is not None
    st, age = content_status(ts, NPS_MAX, now)
    assert st == "stale", f"5월 데이터가 8월에 fresh 로 통과하면 사고가 재현된다 (age={age}분)"
    assert age / 1440 > 60


def test_normal_cycle_stays_fresh():
    """정상 주기(월 16일에 전월분 수집)는 통과해야 한다 — 아니면 매달 오탐이 뜬다."""
    now = datetime(2026, 7, 16, 5, 0, tzinfo=KST)
    ts = extract_content_ts({"_meta": {"data_ym_latest": "202606"}}, "data_ym_latest")
    assert content_status(ts, NPS_MAX, now)[0] == "fresh"


def test_worst_normal_lag_still_fresh():
    """소스가 한 달 밀린 최악의 정상 경우(다음 수집 직전)도 통과 — 임계 여유 확인."""
    now = datetime(2026, 8, 15, 5, 0, tzinfo=KST)      # 다음 수집 직전
    ts = extract_content_ts({"_meta": {"data_ym_latest": "202606"}}, "data_ym_latest")
    st, age = content_status(ts, NPS_MAX, now)
    assert st == "fresh", f"정상 최악 지연에서 오탐 (age={age / 1440:.0f}일)"


def test_month_end_is_the_reference_point():
    """YYYYMM 은 말일 기준 — 1일로 잡으면 월간 자료가 항상 한 달 더 낡아 보인다."""
    t = parse_content_date("202606")
    assert (t.year, t.month, t.day) == (2026, 6, 30)
    assert parse_content_date("202602").day == 28          # 평년
    assert parse_content_date("202402").day == 29          # 윤년


@pytest.mark.parametrize("v,ok", [
    ("2026-06-30", True), ("20260630", True), ("202606", True),
    ("", False), (None, False), ("나중에", False), ("209913", False), ("2026-13-01", False),
])
def test_parse_rejects_garbage(v, ok):
    assert (parse_content_date(v) is not None) is ok


def test_opt_in_only():
    """임계 미등록이면 unknown — 추측 임계를 100개 스트림에 걸면 경고가 무뎌진다."""
    ts = parse_content_date("202001")
    assert content_status(ts, None)[0] == "unknown"
    assert content_status(None, NPS_MAX)[0] == "unknown"


def test_future_date_is_unknown_not_stale():
    """미래 일자 = 소스 오기. stale 로 올리면 방향이 틀린 경보가 된다."""
    now = datetime(2026, 8, 7, tzinfo=KST)
    ts = parse_content_date("202712")
    assert content_status(ts, NPS_MAX, now)[0] == "unknown"


def test_extractor_ignores_nested_noise():
    """최상위·_meta 만 본다 — 깊이 파면 종목별 날짜를 주워 엉뚱한 판정을 낸다."""
    obj = {"stocks": {"005930": {"ym": "201901", "as_of": "2019-01-01"}}}
    assert extract_content_ts(obj) is None


def test_explicit_field_wins():
    obj = {"_meta": {"data_ym_latest": "202606", "as_of": "2020-01-01"}}
    assert extract_content_ts(obj, "data_ym_latest").month == 6


# ── 보드 통합 ────────────────────────────────────────────────────────
def test_board_marks_stale_reason_and_survives_glob_streams(monkeypatch):
    """보드가 내용 stale 을 최종 판정으로 올리고, glob 스트림에서 죽지 않는다."""
    import api.builders.freshness_board_builder as B

    now = datetime(2026, 8, 7, 12, 0, tzinfo=KST)
    manifest = {"streams": [
        {"id": "nps_employment", "file": "nps_employment.json", "schedule": "always",
         "criticality": "P2", "max_age_minutes": 50400,
         "max_content_age_minutes": NPS_MAX, "content_field": "data_ym_latest"},
        {"id": "globby", "file": "history/*.json", "schedule": "always",
         "criticality": "P2", "max_age_minutes": 50400,
         "max_content_age_minutes": NPS_MAX},
    ]}

    monkeypatch.setattr(B, "now_kst", lambda: now)
    monkeypatch.setattr(B, "_load_any", lambda p: manifest if str(p).endswith("freshness_sla.json")
                        else {"_meta": {"data_ym_latest": "202605"}})
    monkeypatch.setattr(B, "MANIFEST", "freshness_sla.json")
    monkeypatch.setattr(os.path, "exists", lambda p: True)
    # 파일 시각은 '방금' — 기존 축만으로는 fresh 가 나오는 상황을 재현한다
    monkeypatch.setattr(B, "_extract_ts", lambda o, f=None: now.isoformat())
    monkeypatch.setattr(B, "latest_ts_for_glob", lambda f, tf=None: now)

    board = B.build_board()
    by_id = {r["id"]: r for r in board["streams"]}

    nps = by_id["nps_employment"]
    assert nps["status"] == "stale"
    assert nps["stale_reason"] == "content", "파일은 새것인데 내용이 낡은 경우를 잡아야 한다"
    assert by_id["globby"]["status"] == "fresh"   # glob 경로에서 NameError 없이 통과
