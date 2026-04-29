"""LANDEX VWORLD 어댑터 단위 테스트.

검증 범위:
  - V_WORLD_API_KEY 미설정 시 geocode() None (fail-closed)
  - ROAD 성공 응답 파싱 (refined.structure.level1/level2 추출)
  - ROAD NOT_FOUND → PARCEL fallback
  - 둘 다 NOT_FOUND → None
  - HTTP 에러·네트워크 실패 → None
  - LRU 캐시 — 동일 주소 재호출 시 API 한 번만
  - is_seoul_gu / extract_location_gu 헬퍼

vercel-api 경로는 sys.path 에 없으므로 importlib 로 직접 로드.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _load_vworld(monkeypatch, env: dict | None = None):
    for k in ("V_WORLD_API_KEY",):
        monkeypatch.delenv(k, raising=False)
    if env:
        for k, v in env.items():
            monkeypatch.setenv(k, v)

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vw_path = os.path.join(repo_root, "vercel-api", "api", "landex", "_sources", "vworld.py")
    spec = importlib.util.spec_from_file_location("vworld_test_load", vw_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # 캐시 초기화 — 테스트 간 격리
    mod.clear_cache()
    return mod


def _ok_response(level1="서울특별시", level2="강남구", level3="역삼동",
                 x="127.036", y="37.5"):
    """VWORLD status=OK mock — refined.structure 위치에 데이터."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={
        "response": {
            "status": "OK",
            "refined": {
                "text": f"{level1} {level2} {level3} 도로명 (동)",
                "structure": {
                    "level0": "대한민국", "level1": level1, "level2": level2,
                    "level3": level3, "level4A": f"{level3}1동",
                    "level4AC": "1168064000", "level4L": "도로명", "level5": "152",
                },
            },
            "result": {"crs": "EPSG:4326", "point": {"x": x, "y": y}},
        }
    })
    return resp


def _not_found_response():
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={
        "response": {"status": "NOT_FOUND",
                      "input": {"type": "ROAD", "address": "X"}}
    })
    return resp


def _error_response(text="LIMIT_EXCEEDED"):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={
        "response": {"status": "ERROR", "error": {"text": text, "code": "999"}}
    })
    return resp


# ──────────────────────────────────────────────
# 키 게이트
# ──────────────────────────────────────────────

def test_no_api_key_returns_none(monkeypatch):
    vw = _load_vworld(monkeypatch)
    assert vw.geocode("서울 강남구 테헤란로 152") is None


def test_empty_address_returns_none(monkeypatch):
    vw = _load_vworld(monkeypatch, env={"V_WORLD_API_KEY": "test_key"})
    assert vw.geocode("") is None
    assert vw.geocode("   ") is None
    assert vw.geocode(None) is None  # type: ignore


# ──────────────────────────────────────────────
# 응답 파싱
# ──────────────────────────────────────────────

def test_road_success(monkeypatch):
    vw = _load_vworld(monkeypatch, env={"V_WORLD_API_KEY": "test_key"})
    with patch.object(vw.requests, "get",
                      return_value=_ok_response("서울특별시", "강남구", "역삼동")):
        out = vw.geocode("서울특별시 강남구 테헤란로 152")
    assert out is not None
    assert out["level1"] == "서울특별시"
    assert out["level2"] == "강남구"
    assert out["level3"] == "역삼동"
    assert out["level4A"] == "역삼동1동"
    assert out["matched_type"] == "ROAD"
    assert out["source"] == "vworld"
    assert "as_of" in out


def test_road_not_found_falls_back_to_parcel(monkeypatch):
    vw = _load_vworld(monkeypatch, env={"V_WORLD_API_KEY": "test_key"})
    responses = iter([_not_found_response(), _ok_response("서울특별시", "강남구", "역삼동")])
    with patch.object(vw.requests, "get", side_effect=lambda *a, **kw: next(responses)):
        out = vw.geocode("서울 강남구 역삼동 737")
    assert out is not None
    assert out["level2"] == "강남구"
    assert out["matched_type"] == "PARCEL"


def test_both_road_and_parcel_not_found(monkeypatch):
    vw = _load_vworld(monkeypatch, env={"V_WORLD_API_KEY": "test_key"})
    with patch.object(vw.requests, "get", return_value=_not_found_response()):
        out = vw.geocode("(주)현대 사옥")
    assert out is None


def test_error_response_returns_none(monkeypatch):
    vw = _load_vworld(monkeypatch, env={"V_WORLD_API_KEY": "test_key"})
    with patch.object(vw.requests, "get", return_value=_error_response("LIMIT_EXCEEDED")):
        assert vw.geocode("서울 강남구 테헤란로 152") is None


def test_network_error_returns_none(monkeypatch):
    vw = _load_vworld(monkeypatch, env={"V_WORLD_API_KEY": "test_key"})
    with patch.object(vw.requests, "get", side_effect=ConnectionError("simulated")):
        assert vw.geocode("서울 강남구 테헤란로 152") is None


def test_missing_level1_returns_none(monkeypatch):
    """OK 응답이라도 level1 비어있으면 None (응답 깨진 케이스)."""
    vw = _load_vworld(monkeypatch, env={"V_WORLD_API_KEY": "test_key"})
    bad = MagicMock()
    bad.raise_for_status = MagicMock()
    bad.json = MagicMock(return_value={
        "response": {"status": "OK", "refined": {"structure": {}}, "result": {}}
    })
    with patch.object(vw.requests, "get", return_value=bad):
        assert vw.geocode("이상한 주소") is None


# ──────────────────────────────────────────────
# 캐시
# ──────────────────────────────────────────────

def test_lru_cache_avoids_duplicate_calls(monkeypatch):
    """동일 주소 두 번 호출 시 API 는 1번만 호출."""
    vw = _load_vworld(monkeypatch, env={"V_WORLD_API_KEY": "test_key"})
    mock_get = MagicMock(return_value=_ok_response())
    with patch.object(vw.requests, "get", mock_get):
        out1 = vw.geocode("서울 강남구 테헤란로 152")
        out2 = vw.geocode("서울 강남구 테헤란로 152")
    assert out1 is not None and out2 is not None
    assert out1["level2"] == out2["level2"]
    # 캐시 안 적중하면 mock_get 이 2번 불림 — 1번이어야 함
    assert mock_get.call_count == 1


def test_clear_cache_resets_lru(monkeypatch):
    vw = _load_vworld(monkeypatch, env={"V_WORLD_API_KEY": "test_key"})
    mock_get = MagicMock(return_value=_ok_response())
    with patch.object(vw.requests, "get", mock_get):
        vw.geocode("서울 강남구 테헤란로 152")
        vw.clear_cache()
        vw.geocode("서울 강남구 테헤란로 152")
    assert mock_get.call_count == 2


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────

def test_extract_location_gu(monkeypatch):
    vw = _load_vworld(monkeypatch, env={"V_WORLD_API_KEY": "test_key"})
    with patch.object(vw.requests, "get",
                      return_value=_ok_response(level2="강남구")):
        gu = vw.extract_location_gu("서울 강남구 테헤란로 152")
    assert gu == "강남구"


def test_extract_location_gu_fallback(monkeypatch):
    vw = _load_vworld(monkeypatch, env={"V_WORLD_API_KEY": "test_key"})
    with patch.object(vw.requests, "get", return_value=_not_found_response()):
        assert vw.extract_location_gu("이상한 주소") is None


def test_is_seoul_gu(monkeypatch):
    vw = _load_vworld(monkeypatch)
    assert vw.is_seoul_gu("강남구") is True
    assert vw.is_seoul_gu("서초구") is True
    assert vw.is_seoul_gu("성남시 분당구") is False  # 서울 아님
    assert vw.is_seoul_gu("해운대구") is False        # 부산
    assert vw.is_seoul_gu(None) is False
    assert vw.is_seoul_gu("") is False


def test_seoul_gu_set_completeness(monkeypatch):
    """서울 25구 모두 SEOUL_GU_NAMES 에 있어야 함."""
    vw = _load_vworld(monkeypatch)
    expected = {
        "강남구", "강동구", "강북구", "강서구", "관악구", "광진구",
        "구로구", "금천구", "노원구", "도봉구", "동대문구", "동작구",
        "마포구", "서대문구", "서초구", "성동구", "성북구", "송파구",
        "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구",
    }
    assert vw.SEOUL_GU_NAMES == expected
