"""LANDEX R-ONE 어댑터 단위 테스트.

검증 범위:
  - REB_API_KEY 미설정 시 fetch_weekly_index() 가 None 반환 (fail-closed)
  - 정상 응답 파싱 → series 정렬 + as_of/collected_at 포함
  - 빈 응답·에러 응답 → None
  - compute_value_momentum_penalty: ±5% 변화율 → ∓15점 매핑 + clipping
  - compute_development_momentum_score: 가속도 → 0~100 매핑 + clipping
  - SEOUL_25_GU 외 입력 → None (gu 매핑 안전장치)

vercel-api/api/landex/_sources/rone.py 는 sys.path 에 없으므로 importlib 로 직접 로드.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _load_rone(monkeypatch, env: dict | None = None):
    """rone.py 를 격리 로드. 의존하는 ._lawd 도 같은 방식으로 로드해서 sys.modules 주입."""
    for k in ("REB_API_KEY", "REB_STAT_WEEKLY_APT_INDEX"):
        monkeypatch.delenv(k, raising=False)
    if env:
        for k, v in env.items():
            monkeypatch.setenv(k, v)

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sources_dir = os.path.join(repo_root, "vercel-api", "api", "landex", "_sources")

    # 1) ._lawd 먼저 로드 (rone.py 가 from ._lawd import ... 함)
    pkg_name = "vercel_landex_sources_test"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [sources_dir]
    monkeypatch.setitem(sys.modules, pkg_name, pkg)

    lawd_spec = importlib.util.spec_from_file_location(
        f"{pkg_name}._lawd", os.path.join(sources_dir, "_lawd.py"),
    )
    lawd_mod = importlib.util.module_from_spec(lawd_spec)
    monkeypatch.setitem(sys.modules, f"{pkg_name}._lawd", lawd_mod)
    lawd_spec.loader.exec_module(lawd_mod)

    rone_spec = importlib.util.spec_from_file_location(
        f"{pkg_name}.rone", os.path.join(sources_dir, "rone.py"),
    )
    rone_mod = importlib.util.module_from_spec(rone_spec)
    monkeypatch.setitem(sys.modules, f"{pkg_name}.rone", rone_mod)
    rone_spec.loader.exec_module(rone_mod)

    return rone_mod


# ──────────────────────────────────────────────
# fetch_weekly_index — 키 게이트 + 응답 파싱
# ──────────────────────────────────────────────

def test_no_api_key_returns_none(monkeypatch):
    rone = _load_rone(monkeypatch)
    assert rone.fetch_weekly_index("강남구", weeks=12) is None


def test_unknown_gu_returns_none(monkeypatch):
    rone = _load_rone(monkeypatch, env={
        "REB_API_KEY": "test_key",
        "REB_STAT_WEEKLY_APT_INDEX": "R_2024_test",
    })
    assert rone.fetch_weekly_index("강남시", weeks=12) is None  # 시 ≠ 구
    assert rone.fetch_weekly_index("Gangnam", weeks=12) is None


def _mock_ok_response(rows: list[dict], total: int | None = None):
    """R-ONE 표준 응답 mock. total=None 이면 head.list_total_count 생략 (호환성)."""
    head = []
    if total is not None:
        head.append({"list_total_count": total})
    head.append({"RESULT": {"CODE": "INFO-000", "MESSAGE": "정상"}})
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={
        "SttsApiTblData": [
            {"head": head},
            {"row": rows},
        ]
    })
    return resp


def _row(week: str, val: float, *, item_id: int = 10001, desc: str | None = None):
    """R-ONE row mock — ITM_ID, WRTTIME_DESC 포함 실제 응답 구조."""
    return {
        "WRTTIME_IDTFR_ID": week,
        "DTA_VAL": val,
        "ITM_ID": item_id,
        "WRTTIME_DESC": desc or "",
        "CLS_ID": 50068,
        "CLS_NM": "강남구",
        "CLS_FULLNM": "서울>강남지역>동남권>강남구",
    }


def test_parses_series_and_sorts_by_week(monkeypatch):
    rone = _load_rone(monkeypatch, env={
        "REB_API_KEY": "test_key",
        "REB_STAT_WEEKLY_APT_INDEX": "T244183132827305",
    })

    # 의도적으로 역순 — 주간 식별자 "YYYYWW" 형식 (실측)
    rows = [
        _row("202615", 101.5, desc="2026-04-06"),
        _row("202613", 100.0, desc="2026-03-23"),
        _row("202614", 100.7, desc="2026-03-30"),
        _row("202616", 102.3, desc="2026-04-13"),
    ]
    with patch.object(rone.requests, "get", return_value=_mock_ok_response(rows, total=4)):
        out = rone.fetch_weekly_index("강남구", weeks=12)

    assert out is not None
    assert out["gu"] == "강남구"
    assert out["cls_id"] == 50068
    assert out["source"] == "rone_weekly"
    assert out["as_of"] == "2026-04-13"   # WRTTIME_DESC 우선
    assert out["as_of_week"] == "202616"
    assert out["stat_id"] == "T244183132827305"
    assert "collected_at" in out and out["collected_at"]
    series = out["series"]
    assert [s["week"] for s in series] == ["202613", "202614", "202615", "202616"]
    assert series[0]["index"] == 100.0
    assert series[-1]["index"] == 102.3
    assert series[0]["date"] == "2026-03-23"


def test_truncates_to_recent_n_weeks(monkeypatch):
    rone = _load_rone(monkeypatch, env={
        "REB_API_KEY": "test_key",
        "REB_STAT_WEEKLY_APT_INDEX": "T244183132827305",
    })

    rows = []
    for i, w in enumerate(range(1, 18)):  # 17주
        rows.append(_row(f"2026{w:02d}", 100 + i * 0.1, desc=f"2026-week-{w:02d}"))
    with patch.object(rone.requests, "get", return_value=_mock_ok_response(rows, total=17)):
        out = rone.fetch_weekly_index("강남구", weeks=4)

    assert len(out["series"]) == 4
    assert out["series"][-1]["week"] == "202617"
    # 사전식 정렬 = 시간순 (YYYYWW zero-pad)
    assert [s["week"] for s in out["series"]] == ["202614", "202615", "202616", "202617"]


def test_filters_non_index_items(monkeypatch):
    """ITM_ID != 10001 (지수가 아닌 변동률 등) 행은 제외."""
    rone = _load_rone(monkeypatch, env={
        "REB_API_KEY": "test_key",
        "REB_STAT_WEEKLY_APT_INDEX": "T244183132827305",
    })
    rows = [
        _row("202613", 100.0, desc="2026-03-23"),
        _row("202614", 0.5, item_id=10002, desc="2026-03-30"),  # 변동률
        _row("202615", 101.0, desc="2026-04-06"),
    ]
    with patch.object(rone.requests, "get", return_value=_mock_ok_response(rows, total=3)):
        out = rone.fetch_weekly_index("강남구", weeks=12)
    assert len(out["series"]) == 2
    assert out["series"][0]["week"] == "202613"
    assert out["series"][1]["week"] == "202615"


def test_stat_id_unset_returns_none(monkeypatch):
    """REB_API_KEY 있어도 STAT_ID 미설정이면 호출 스킵."""
    rone = _load_rone(monkeypatch, env={
        "REB_API_KEY": "test_key",
        "REB_STAT_WEEKLY_APT_INDEX": "",  # 명시적 unset (DEFAULT 도 비어있어야)
    })
    # DEFAULT_STAT_WEEKLY 가 박혀있으므로 module-level 변수도 임시 무효화
    monkeypatch.setattr(rone, "DEFAULT_STAT_WEEKLY", "")
    assert rone.fetch_weekly_index("강남구", weeks=12) is None


def test_error_response_returns_none(monkeypatch):
    rone = _load_rone(monkeypatch, env={
        "REB_API_KEY": "test_key",
        "REB_STAT_WEEKLY_APT_INDEX": "T244183132827305",
    })

    err_resp = MagicMock()
    err_resp.raise_for_status = MagicMock()
    err_resp.json = MagicMock(return_value={"RESULT": {"CODE": "ERROR-401", "MESSAGE": "잘못된 인증키"}})
    with patch.object(rone.requests, "get", return_value=err_resp):
        out = rone.fetch_weekly_index("강남구", weeks=12)
    assert out is None


def test_empty_rows_returns_none(monkeypatch):
    rone = _load_rone(monkeypatch, env={
        "REB_API_KEY": "test_key",
        "REB_STAT_WEEKLY_APT_INDEX": "T244183132827305",
    })
    with patch.object(rone.requests, "get", return_value=_mock_ok_response([], total=0)):
        assert rone.fetch_weekly_index("강남구", weeks=12) is None


def test_network_error_returns_none(monkeypatch):
    rone = _load_rone(monkeypatch, env={
        "REB_API_KEY": "test_key",
        "REB_STAT_WEEKLY_APT_INDEX": "T244183132827305",
    })

    def _raise(*a, **kw):
        raise ConnectionError("simulated")

    with patch.object(rone.requests, "get", side_effect=_raise):
        assert rone.fetch_weekly_index("강남구", weeks=12) is None


def test_malformed_value_skipped(monkeypatch):
    rone = _load_rone(monkeypatch, env={
        "REB_API_KEY": "test_key",
        "REB_STAT_WEEKLY_APT_INDEX": "T244183132827305",
    })
    rows = [
        _row("202613", 100.0, desc="2026-03-23"),
        {"WRTTIME_IDTFR_ID": "202614", "DTA_VAL": "N/A", "ITM_ID": 10001},   # 무효값
        {"WRTTIME_IDTFR_ID": "202615", "DTA_VAL": "", "ITM_ID": 10001},      # 빈값
        _row("202616", 102.5, desc="2026-04-13"),
    ]
    with patch.object(rone.requests, "get", return_value=_mock_ok_response(rows, total=4)):
        out = rone.fetch_weekly_index("강남구", weeks=12)
    assert out is not None
    assert len(out["series"]) == 2  # 100.0, 102.5만 살아남음


# ──────────────────────────────────────────────
# compute_value_momentum_penalty
# ──────────────────────────────────────────────

def _payload(values: list[float]) -> dict:
    return {
        "gu": "강남구",
        "series": [{"week": f"2026010{i+1}", "index": v} for i, v in enumerate(values)],
        "as_of": "2026-01-01", "collected_at": "now",
        "source": "rone_weekly", "stat_id": "test",
    }


def test_value_penalty_none_for_short_series(monkeypatch):
    rone = _load_rone(monkeypatch)
    assert rone.compute_value_momentum_penalty(_payload([100, 101, 102])) is None
    assert rone.compute_value_momentum_penalty(None) is None
    assert rone.compute_value_momentum_penalty({"series": []}) is None


def test_value_penalty_zero_for_flat(monkeypatch):
    rone = _load_rone(monkeypatch)
    p = _payload([100.0] * 12)
    assert rone.compute_value_momentum_penalty(p) == 0.0


def test_value_penalty_negative_for_rising_prices(monkeypatch):
    rone = _load_rone(monkeypatch)
    # 100 → 105 (+5%) → -15
    p = _payload([100.0] + [101.0] * 10 + [105.0])
    assert rone.compute_value_momentum_penalty(p) == -15.0


def test_value_penalty_positive_for_falling_prices(monkeypatch):
    rone = _load_rone(monkeypatch)
    # 100 → 95 (-5%) → +15
    p = _payload([100.0] + [98.0] * 10 + [95.0])
    assert rone.compute_value_momentum_penalty(p) == 15.0


def test_value_penalty_clipped_at_extremes(monkeypatch):
    rone = _load_rone(monkeypatch)
    # +20% 도 -15에서 cap
    p = _payload([100.0] + [110.0] * 10 + [120.0])
    assert rone.compute_value_momentum_penalty(p) == -15.0
    # -20% 도 +15에서 cap
    p = _payload([100.0] + [90.0] * 10 + [80.0])
    assert rone.compute_value_momentum_penalty(p) == 15.0


# ──────────────────────────────────────────────
# compute_development_momentum_score
# ──────────────────────────────────────────────

def test_dev_score_none_for_short_series(monkeypatch):
    rone = _load_rone(monkeypatch)
    assert rone.compute_development_momentum_score(_payload([100] * 7)) is None
    assert rone.compute_development_momentum_score(None) is None


def test_dev_score_50_for_constant_acceleration(monkeypatch):
    """일정 속도로 오르면 가속도 = 0 → 50점."""
    rone = _load_rone(monkeypatch)
    # 8주간 동일 변화율 (등차) → 가속도 0
    series = [100 + i * 0.1 for i in range(8)]
    p = _payload(series)
    score = rone.compute_development_momentum_score(p)
    assert score is not None
    assert 48 <= score <= 52  # 부동소수점 여유


def test_dev_score_high_for_acceleration(monkeypatch):
    """앞 4주 평탄, 뒤 4주 급등 → 가속도 + → 50초과."""
    rone = _load_rone(monkeypatch)
    series = [100, 100, 100, 100, 100.5, 101.0, 101.5, 102.0]  # 뒤 4주 +2%
    p = _payload(series)
    score = rone.compute_development_momentum_score(p)
    assert score is not None
    assert score > 50  # 가속 → 50초과


def test_dev_score_low_for_deceleration(monkeypatch):
    """앞 4주 급등, 뒤 4주 평탄 → 가속도 - → 50미만."""
    rone = _load_rone(monkeypatch)
    series = [100, 100.5, 101.0, 101.5, 102.0, 102.0, 102.0, 102.0]
    p = _payload(series)
    score = rone.compute_development_momentum_score(p)
    assert score is not None
    assert score < 50


def test_dev_score_clipped_to_0_100(monkeypatch):
    rone = _load_rone(monkeypatch)
    # 극단적 가속
    series = [100, 100, 100, 100, 100, 100, 100, 110]
    p = _payload(series)
    score = rone.compute_development_momentum_score(p)
    assert 0 <= score <= 100


# ──────────────────────────────────────────────
# fetch_monthly_unsold + compute_supply_score
# ──────────────────────────────────────────────

def _row_unsold(month: str, val: int, *, item_id: int = 10001, desc: str | None = None,
                cls_id: int = 50020, cls_nm: str = "강남구"):
    return {
        "WRTTIME_IDTFR_ID": month,
        "DTA_VAL": val,
        "ITM_ID": item_id,
        "WRTTIME_DESC": desc or "",
        "CLS_ID": cls_id, "CLS_NM": cls_nm,
        "CLS_FULLNM": f"서울>{cls_nm}",
    }


def test_unsold_no_api_key(monkeypatch):
    rone = _load_rone(monkeypatch)
    assert rone.fetch_monthly_unsold("강남구", months=12) is None


def test_unsold_unknown_gu(monkeypatch):
    rone = _load_rone(monkeypatch, env={
        "REB_API_KEY": "test_key",
        "REB_STAT_MONTHLY_UNSOLD": "T237_test",
    })
    assert rone.fetch_monthly_unsold("강남시", months=12) is None


def test_unsold_uses_separate_cls_mapping(monkeypatch):
    """미분양은 매매지수와 다른 CLS_ID 매핑 사용 (강남구 = 50020 vs 50068)."""
    rone = _load_rone(monkeypatch)
    assert rone.GU_TO_RONE_UNSOLD_CLS["강남구"] == 50020
    assert rone.GU_TO_RONE_CLS["강남구"] == 50068
    assert rone.GU_TO_RONE_UNSOLD_CLS["강남구"] != rone.GU_TO_RONE_CLS["강남구"]


def test_unsold_parses_series(monkeypatch):
    rone = _load_rone(monkeypatch, env={
        "REB_API_KEY": "test_key",
        "REB_STAT_MONTHLY_UNSOLD": "T237_test",
    })
    rows = [
        _row_unsold("202602", 271, desc="2026년 02월"),
        _row_unsold("202512", 47, desc="2025년 12월"),
        _row_unsold("202601", 47, desc="2026년 01월"),
    ]
    with patch.object(rone.requests, "get", return_value=_mock_ok_response(rows, total=3)):
        out = rone.fetch_monthly_unsold("강남구", months=12)
    assert out is not None
    assert out["cls_id"] == 50020
    assert out["source"] == "rone_unsold"
    assert out["as_of"] == "2026년 02월"
    assert out["as_of_month"] == "202602"
    assert [s["month"] for s in out["series"]] == ["202512", "202601", "202602"]
    assert [s["unsold"] for s in out["series"]] == [47, 47, 271]


def _supply_payload(values: list[int]) -> dict:
    return {
        "gu": "강남구", "cls_id": 50020,
        "series": [{"month": f"2026{i+1:02d}", "unsold": v} for i, v in enumerate(values)],
        "as_of": "2026-month", "as_of_month": "202612",
        "collected_at": "now", "source": "rone_unsold", "stat_id": "test",
    }


def test_supply_score_max_for_zero(monkeypatch):
    rone = _load_rone(monkeypatch)
    p = _supply_payload([0] * 12)
    assert rone.compute_supply_score(p) == 70.0


def test_supply_score_drops_for_high_unsold(monkeypatch):
    rone = _load_rone(monkeypatch)
    p = _supply_payload([1000] * 12)  # 1000호 = level 40, trend 0 → 40
    score = rone.compute_supply_score(p)
    assert 35 <= score <= 45


def test_supply_score_penalizes_increasing_trend(monkeypatch):
    rone = _load_rone(monkeypatch)
    # 50→500 (+900%) → trend penalty -30, level (500=37) → 7
    p = _supply_payload([50, 50, 50, 50, 50, 50, 200, 300, 400, 500, 500, 500])
    score = rone.compute_supply_score(p)
    assert score < 30


def test_supply_score_rewards_decreasing_trend(monkeypatch):
    rone = _load_rone(monkeypatch)
    # 1000→100 (-90%) → trend +30, level (100≈50) → 80
    p = _supply_payload([1000, 1000, 1000, 1000, 1000, 1000, 500, 300, 200, 150, 100, 100])
    score = rone.compute_supply_score(p)
    assert score > 60


def test_supply_score_short_series_returns_none(monkeypatch):
    rone = _load_rone(monkeypatch)
    p = _supply_payload([10, 20, 30, 40, 50])  # < 6
    assert rone.compute_supply_score(p) is None
    assert rone.compute_supply_score(None) is None


def test_supply_score_clipped_to_0_100(monkeypatch):
    rone = _load_rone(monkeypatch)
    # 극단 케이스
    p = _supply_payload([0, 0, 0, 0, 0, 0, 10000, 10000, 10000, 10000, 10000, 10000])
    score = rone.compute_supply_score(p)
    assert 0 <= score <= 100
