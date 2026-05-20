"""ESTATE sector_pulse 빌더 — Fix A (transient resilience) carry-forward 회귀 테스트.

2026-05-20 신설. R-ONE RemoteDisconnected transient fetch 실패 시 직전 good 값을
carry-forward + stale 마킹하는 _carry_forward_if_transient 로직 보호.
[[project_estate_commercial_v0_design]] / [[feedback_real_call_over_llm_consensus]].
"""
from datetime import datetime, timedelta

from api.builders.estate_sector_pulse_builder import (
    KST,
    STALE_MAX_DAYS,
    _carry_forward_if_transient,
    _select_grp_series,
)


def _officetel_yield_rows():
    """officetel 수익률 = CLS_NM(규모) × GRP_NM(권역) 2차원. 같은 period 다중 값."""
    return [
        {"ITM_ID": 10001, "CLS_NM": "전체", "GRP_NM": "전국", "WRTTIME_IDTFR_ID": "202401", "DTA_VAL": 5.27},
        {"ITM_ID": 10001, "CLS_NM": "전체", "GRP_NM": "서울", "WRTTIME_IDTFR_ID": "202401", "DTA_VAL": 4.78},
        {"ITM_ID": 10001, "CLS_NM": "전체", "GRP_NM": "지방", "WRTTIME_IDTFR_ID": "202401", "DTA_VAL": 5.69},
        {"ITM_ID": 10001, "CLS_NM": "40㎡이하", "GRP_NM": "전국", "WRTTIME_IDTFR_ID": "202401", "DTA_VAL": 5.66},
        {"ITM_ID": 10001, "CLS_NM": "전체", "GRP_NM": "전국", "WRTTIME_IDTFR_ID": "202402", "DTA_VAL": 5.31},
    ]


def test_select_grp_series_picks_cls_and_grp():
    """2차원 통계에서 CLS '전체' × GRP '전국' 조합만 정확히 선택, 시간순 정렬."""
    series = _select_grp_series(_officetel_yield_rows(), itm_id=10001, cls_nm="전체", grp_nm="전국")
    assert len(series) == 2  # 202401, 202402 (전체·전국)
    assert [r["WRTTIME_IDTFR_ID"] for r in series] == ["202401", "202402"]
    assert series[-1]["DTA_VAL"] == 5.31  # 최신 = 전국·전체 officetel 수익률


def test_select_grp_series_wrong_itm_filtered():
    """ITM_ID 불일치(옛 100001 버그) → 전 행 제거 = 빈 series (yield None 의 옛 증상)."""
    series = _select_grp_series(_officetel_yield_rows(), itm_id=100001, cls_nm="전체", grp_nm="전국")
    assert series == []


def test_select_grp_series_no_match_empty():
    """존재하지 않는 GRP → 빈 series."""
    series = _select_grp_series(_officetel_yield_rows(), itm_id=10001, cls_nm="전체", grp_nm="없는권역")
    assert series == []


def _good_sector():
    return {
        "key": "retail_mid_large",
        "name": "중대형 상가",
        "verdict": "NEUTRAL",
        "rationale": "YoY -0.24%",
        "latest_index": 99.44,
        "yield_pct": 0.99,
        "as_of": "2026년 1분기",
    }


def test_transient_failure_carries_forward_prev_good():
    """index fetch transient 실패 + 직전 good → 직전 값 유지, stale 마킹."""
    new = {"key": "retail_mid_large", "verdict": "UNAVAILABLE",
           "_error_index": "fetch failed or empty"}
    out = _carry_forward_if_transient(new, _good_sector())
    assert out["verdict"] == "NEUTRAL"
    assert out["latest_index"] == 99.44
    assert out["stale"] is True
    assert out["stale_since"]
    assert "⚠ stale" in out["rationale"]


def test_structural_defect_not_masked():
    """'no region series' = 구조적 결함 → carry 안 함 (실결함 UNAVAILABLE 노출 유지)."""
    new = {"key": "x", "verdict": "UNAVAILABLE", "_error_index": "no region series"}
    out = _carry_forward_if_transient(new, _good_sector())
    assert out["verdict"] == "UNAVAILABLE"
    assert out.get("stale") is None


def test_no_carry_when_prev_unavailable():
    """직전도 UNAVAILABLE = 살릴 good 값 없음 → carry 안 함."""
    new = {"key": "x", "verdict": "UNAVAILABLE", "_error_index": "fetch failed or empty"}
    out = _carry_forward_if_transient(new, {"key": "x", "verdict": "UNAVAILABLE"})
    assert out["verdict"] == "UNAVAILABLE"
    assert out.get("stale") is None


def test_no_carry_when_prev_missing():
    """직전 스냅샷에 해당 sector 부재(None) → carry 안 함."""
    new = {"key": "x", "verdict": "UNAVAILABLE", "_error_index": "fetch failed or empty"}
    out = _carry_forward_if_transient(new, None)
    assert out["verdict"] == "UNAVAILABLE"


def test_stale_over_limit_reverts_to_unavailable():
    """stale 누적이 STALE_MAX_DAYS 초과 → 오래된 값 숨기고 UNAVAILABLE 정직 노출."""
    old = _good_sector()
    old["stale_since"] = (datetime.now(KST) - timedelta(days=STALE_MAX_DAYS + 5)).isoformat(timespec="seconds")
    new = {"key": "x", "verdict": "UNAVAILABLE", "_error_index": "fetch failed or empty"}
    out = _carry_forward_if_transient(new, old)
    assert out["verdict"] == "UNAVAILABLE"
    assert out.get("stale") is None


def test_fresh_success_untouched():
    """fetch 성공(에러 없음) → 손 안 댐. 회복 시 stale 자동 해제."""
    fresh = {"key": "x", "verdict": "BULLISH", "_error_index": None, "latest_index": 103.6}
    out = _carry_forward_if_transient(fresh, _good_sector())
    assert out is fresh
    assert out.get("stale") is None


def test_stale_since_preserved_across_consecutive_carries():
    """연속 carry 시 최초 실패 시각(stale_since) 보존 — 누적 추적 정확."""
    since = (datetime.now(KST) - timedelta(days=3)).isoformat(timespec="seconds")
    prev = _good_sector()
    prev["stale_since"] = since
    prev["stale"] = True
    new = {"key": "x", "verdict": "UNAVAILABLE", "_error_index": "fetch failed or empty"}
    out = _carry_forward_if_transient(new, prev)
    assert out["stale_since"] == since
