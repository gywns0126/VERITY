"""
test_estate_subscription_calendar_builder.py — calendar builder 검증.

핵심:
    1) row 1건 → 5종 event 분해 (recruit/application/announcement/contract/move_in)
    2) 빈 필드 → 해당 event skip (T1 정합)
    3) 날짜 normalization (YYYY-MM-DD / YYYYMMDD 둘 다)
    4) MVN_PREARNGE_YM (YYYYMM) → YYYY-MM-01 변환
    5) by_month / by_region aggregation
    6) upcoming_high_impact (향후 30d + recruit + ≥1000세대)
    7) collect 실패 시 events=[] (T1)
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from api.builders import estate_subscription_calendar_builder as builder


NOW = datetime(2026, 5, 12, 1, 0, 0, tzinfo=timezone.utc)


def _row(**kw) -> dict:
    base = {
        "HOUSE_MANAGE_NO": "MGR-001",
        "PBLANC_NO": "PB-2026-100",
        "HOUSE_NM": "테스트아파트",
        "HSSPLY_ADRES": "서울시 강남구 테스트동",
        "SUBSCRPT_AREA_CODE_NM": "서울",
        "BSNS_MBY_NM": "한국토지주택공사",
        "TOT_SUPLY_HSHLDCO": "500",
        "RCRIT_PBLANC_DE": "2026-05-15",
        "RCEPT_BGNDE": "2026-05-20",
        "RCEPT_ENDDE": "2026-05-22",
        "PRZWNER_PRESNATN_DE": "2026-05-29",
        "CNTRCT_CNCLS_BGNDE": "2026-06-10",
        "CNTRCT_CNCLS_ENDDE": "2026-06-14",
        "MVN_PREARNGE_YM": "202609",
        "PBLANC_URL": "https://example.gov.kr/p/100",
        "SPECLT_RDN_EARTH_AT": "N",
    }
    base.update(kw)
    return base


def test_explode_five_events(tmp_path):
    rows = [_row()]

    def collect(**kwargs):
        return rows

    payload = builder.build(now=NOW, lookback_days=30, lookforward_days=180, _collect=collect)

    types = sorted(e["event_type"] for e in payload["events"])
    assert types == sorted(["recruit", "application", "announcement", "contract", "move_in"])
    assert payload["total_subscriptions"] == 1


def test_skip_event_when_date_missing(tmp_path):
    row = _row(PRZWNER_PRESNATN_DE="", MVN_PREARNGE_YM="")

    def collect(**kwargs):
        return [row]

    payload = builder.build(now=NOW, lookback_days=30, lookforward_days=180, _collect=collect)
    types = {e["event_type"] for e in payload["events"]}
    assert "announcement" not in types
    assert "move_in" not in types
    assert "recruit" in types


def test_date_normalization_yyyymmdd_form():
    row = _row(RCRIT_PBLANC_DE="20260515",
               RCEPT_BGNDE="", RCEPT_ENDDE="",
               PRZWNER_PRESNATN_DE="", MVN_PREARNGE_YM="",
               CNTRCT_CNCLS_BGNDE="", CNTRCT_CNCLS_ENDDE="")

    def collect(**kwargs):
        return [row]

    payload = builder.build(now=NOW, lookback_days=30, lookforward_days=180, _collect=collect)
    recruit = [e for e in payload["events"] if e["event_type"] == "recruit"][0]
    assert recruit["date_start"] == "2026-05-15"


def test_move_in_month_to_first_day():
    row = _row(RCRIT_PBLANC_DE="", RCEPT_BGNDE="", RCEPT_ENDDE="",
               PRZWNER_PRESNATN_DE="", CNTRCT_CNCLS_BGNDE="", CNTRCT_CNCLS_ENDDE="",
               MVN_PREARNGE_YM="202611")

    def collect(**kwargs):
        return [row]

    payload = builder.build(now=NOW, lookback_days=30, lookforward_days=365, _collect=collect)
    move_in = [e for e in payload["events"] if e["event_type"] == "move_in"][0]
    assert move_in["date_start"] == "2026-11-01"


def test_by_month_aggregation():
    rows = [
        _row(HOUSE_MANAGE_NO="A", RCRIT_PBLANC_DE="2026-05-15",
             RCEPT_BGNDE="", RCEPT_ENDDE="", PRZWNER_PRESNATN_DE="",
             CNTRCT_CNCLS_BGNDE="", CNTRCT_CNCLS_ENDDE="", MVN_PREARNGE_YM=""),
        _row(HOUSE_MANAGE_NO="B", RCRIT_PBLANC_DE="2026-05-20",
             RCEPT_BGNDE="", RCEPT_ENDDE="", PRZWNER_PRESNATN_DE="",
             CNTRCT_CNCLS_BGNDE="", CNTRCT_CNCLS_ENDDE="", MVN_PREARNGE_YM=""),
        _row(HOUSE_MANAGE_NO="C", RCRIT_PBLANC_DE="2026-06-01",
             RCEPT_BGNDE="", RCEPT_ENDDE="", PRZWNER_PRESNATN_DE="",
             CNTRCT_CNCLS_BGNDE="", CNTRCT_CNCLS_ENDDE="", MVN_PREARNGE_YM="",
             SUBSCRPT_AREA_CODE_NM="부산"),
    ]

    def collect(**kwargs):
        return rows

    payload = builder.build(now=NOW, lookback_days=30, lookforward_days=90, _collect=collect)
    assert payload["by_month"]["2026-05"]["count"] == 2
    assert payload["by_month"]["2026-06"]["count"] == 1
    assert payload["by_region"]["서울"] == 2
    assert payload["by_region"]["부산"] == 1


def test_upcoming_high_impact():
    # 향후 20일 + 2000세대 recruit → high impact 진입
    target_date = (NOW + timedelta(days=20)).date().isoformat()
    rows = [
        _row(HOUSE_MANAGE_NO="BIG", RCRIT_PBLANC_DE=target_date,
             TOT_SUPLY_HSHLDCO="2000",
             RCEPT_BGNDE="", RCEPT_ENDDE="", PRZWNER_PRESNATN_DE="",
             CNTRCT_CNCLS_BGNDE="", CNTRCT_CNCLS_ENDDE="", MVN_PREARNGE_YM=""),
        # 향후 20일 + 200세대 = 임계 미달
        _row(HOUSE_MANAGE_NO="SMALL", RCRIT_PBLANC_DE=target_date,
             TOT_SUPLY_HSHLDCO="200",
             RCEPT_BGNDE="", RCEPT_ENDDE="", PRZWNER_PRESNATN_DE="",
             CNTRCT_CNCLS_BGNDE="", CNTRCT_CNCLS_ENDDE="", MVN_PREARNGE_YM=""),
    ]

    def collect(**kwargs):
        return rows

    payload = builder.build(now=NOW, lookback_days=10, lookforward_days=60, _collect=collect)
    ids = {e["house_manage_no"] for e in payload["upcoming_high_impact"]}
    assert "BIG" in ids
    assert "SMALL" not in ids


def test_collect_failure_returns_empty_payload():
    def collect(**kwargs):
        raise RuntimeError("network boom")

    payload = builder.build(now=NOW, _collect=collect)
    assert payload["events"] == []
    assert payload["total_subscriptions"] == 0
    assert payload["upcoming_high_impact"] == []


def test_speclt_rdn_earth_flag():
    row = _row(SPECLT_RDN_EARTH_AT="Y",
               RCEPT_BGNDE="", RCEPT_ENDDE="", PRZWNER_PRESNATN_DE="",
               CNTRCT_CNCLS_BGNDE="", CNTRCT_CNCLS_ENDDE="", MVN_PREARNGE_YM="")

    def collect(**kwargs):
        return [row]

    payload = builder.build(now=NOW, lookback_days=30, lookforward_days=90, _collect=collect)
    assert payload["events"][0]["speclt_rdn_earth"] is True


def test_window_filter_drops_far_future():
    far = (NOW + timedelta(days=500)).date().isoformat()
    near = (NOW + timedelta(days=10)).date().isoformat()
    rows = [
        _row(HOUSE_MANAGE_NO="NEAR", RCRIT_PBLANC_DE=near,
             RCEPT_BGNDE="", RCEPT_ENDDE="", PRZWNER_PRESNATN_DE="",
             CNTRCT_CNCLS_BGNDE="", CNTRCT_CNCLS_ENDDE="", MVN_PREARNGE_YM=""),
        _row(HOUSE_MANAGE_NO="FAR", RCRIT_PBLANC_DE=far,
             RCEPT_BGNDE="", RCEPT_ENDDE="", PRZWNER_PRESNATN_DE="",
             CNTRCT_CNCLS_BGNDE="", CNTRCT_CNCLS_ENDDE="", MVN_PREARNGE_YM=""),
    ]

    def collect(**kwargs):
        return rows

    payload = builder.build(now=NOW, lookback_days=30, lookforward_days=90, _collect=collect)
    ids = {e["house_manage_no"] for e in payload["events"]}
    assert "NEAR" in ids
    assert "FAR" not in ids
