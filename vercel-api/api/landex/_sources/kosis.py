"""통계청 KOSIS Open API 어댑터 — estate_brain L1 PIR 입력 (권역 중위소득).

API 포털: https://kosis.kr/openapi/
호출 베이스: https://kosis.kr/openapi/statisticsData.do (또는 Param/statisticsParameterData.do)

V0 한계 (의도적 — V1 calibration 큐):
  - KOSIS 가계금융복지조사 등 가구소득 통계는 대부분 *시·도 단위* (광역).
    서울 25구 단위는 통계청 마이크로데이터/부동산원 등 별도 source 필요.
  - V0 = 서울 시·도 중위소득 단일값 → 25구 모두 동일값 사용 (PIR 권역 차별화 없음).
  - V1 = 권역 가중치 (도심/동북/서북/서남/동남) Perplexity·실측 calibration 후 적용.

R-ONE 어댑터 (`./rone.py`) 패턴 정합:
  - KOSIS_API_KEY 환경변수 (Vercel + GH Actions secret 둘 다 지원)
  - KOSIS_INCOME_STAT_ID 환경변수 (사용자 검증 후 박는 통계표 ID)
  - 키/statId 부재 → None (fail-closed, estate_brain L1 layer skip)
  - feedback_macro_timestamp_policy: collected_at + as_of 동시 노출

서울 5대 권역 분류 (서울시 도시기본계획 2030):
  도심권/동북권/서북권/서남권/동남권 — V0 enum 만 박음, 가중치 없음.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

_logger = logging.getLogger(__name__)

KOSIS_BASE = "https://kosis.kr/openapi/statisticsData.do"

# 서울 5대 권역 매핑 (Source: 서울시 도시기본계획 2030)
# V0 = 매핑 enum 만. V1 = 권역별 가중치 calibration 큐.
SEOUL_REGION_MAP: dict[str, str] = {
    # 도심권 (Center)
    "종로구": "center", "중구": "center", "용산구": "center",
    # 동북권 (Northeast)
    "성동구": "northeast", "광진구": "northeast", "동대문구": "northeast",
    "중랑구": "northeast", "성북구": "northeast", "강북구": "northeast",
    "도봉구": "northeast", "노원구": "northeast",
    # 서북권 (Northwest)
    "은평구": "northwest", "서대문구": "northwest", "마포구": "northwest",
    # 서남권 (Southwest)
    "양천구": "southwest", "강서구": "southwest", "구로구": "southwest",
    "금천구": "southwest", "영등포구": "southwest", "동작구": "southwest",
    "관악구": "southwest",
    # 동남권 (Southeast)
    "서초구": "southeast", "강남구": "southeast",
    "송파구": "southeast", "강동구": "southeast",
}

KOSIS_RESULT_OK = "INFO-000"


def _api_key() -> str:
    return (
        os.environ.get("KOSIS_API_KEY")
        or os.environ.get("KOSIS_OPEN_API_KEY")
        or ""
    ).strip()


def _income_stat_id() -> str:
    """KOSIS userStatsId 또는 (orgId, tblId) 조합 — 사용자 검증 후 env 로 주입.

    예시 source 후보 (V0 진입 시 사용자 결정):
      - 가계금융복지조사 가구소득 5분위 (통계청)
      - 도시근로자 가구당 월평균 소득 (통계청 가계동향조사)
    """
    return os.environ.get("KOSIS_INCOME_STAT_ID", "").strip()


def _kst_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=9)))


def get_seoul_region(gu: str) -> Optional[str]:
    """25구 → 서울 5대 권역 코드 (center/northeast/northwest/southwest/southeast).

    V1 권역 가중치 계산 시 사용.
    """
    return SEOUL_REGION_MAP.get((gu or "").strip())


def fetch_seoul_median_income(
    year: int,
    timeout: float = 10.0,
) -> Optional[dict]:
    """서울 시·도 단위 가구 중위 연소득 fetch.

    Returns:
      {"value_won": 65000000, "year": 2024, "as_of": "...", "collected_at": "..."}
      None → 키/statId 미설정/네트워크 실패/응답 파싱 실패

    호출자 (estate_brain compute_estate_brain) 는 25구 모두 같은 단일값 사용 (V0 한계).
    """
    key = _api_key()
    if not key:
        _logger.warning("KOSIS_API_KEY 미설정 — None 반환")
        return None

    stat_id = _income_stat_id()
    if not stat_id:
        _logger.warning("KOSIS_INCOME_STAT_ID 미설정 — 통계표 ID 사용자 결정 큐")
        return None

    # V0 default 호출 — userStatsId 패턴 (사용자가 KOSIS 에서 즐겨찾기 ID 생성)
    # V1 에서 (orgId/tblId/objL1/itmId) 직접 명세 패턴 추가 검토.
    params = {
        "method": "getList",
        "apiKey": key,
        "format": "json",
        "jsonVD": "Y",
        "userStatsId": stat_id,
        "prdSe": "Y",  # 연 단위
        "newEstPrdCnt": "1",  # 가장 최근 1개
    }

    try:
        r = requests.get(KOSIS_BASE, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        _logger.warning("KOSIS fetch 실패 (year=%s): %s", year, e)
        return None

    # KOSIS 에러 응답: {"err": "..."} 또는 {"RESULT": {"CODE": "..."}}
    if isinstance(data, dict) and "err" in data:
        _logger.warning("KOSIS 에러: %s", data.get("err"))
        return None
    if isinstance(data, dict) and "RESULT" in data:
        code = data.get("RESULT", {}).get("CODE")
        if code != KOSIS_RESULT_OK:
            _logger.warning("KOSIS 에러 코드: %s", code)
            return None

    # 정상 응답: list of dict, 각 row 에 PRD_DE / DT / C1_NM / ITM_NM / UNIT_NM
    rows = data if isinstance(data, list) else []
    if not rows:
        _logger.warning("KOSIS 빈 응답 (year=%s, stat=%s)", year, stat_id)
        return None

    # 가장 최근 row 추출
    latest = rows[-1] if rows else None
    if not latest:
        return None

    raw_value = latest.get("DT")
    if raw_value is None:
        return None
    try:
        # 단위는 통계표마다 다름 (만원/원). 사용자가 statId 박을 때 단위 검증 의무.
        # V0 default = 만원 (가계금융복지조사 표준). V1 = unit_nm 기반 자동 변환.
        value_man = float(str(raw_value).replace(",", ""))
        value_won = int(value_man * 10_000)
    except (ValueError, TypeError):
        _logger.warning("KOSIS DT 변환 실패: %s", raw_value)
        return None

    prd_de = str(latest.get("PRD_DE", "")).strip()
    now_iso = _kst_now().isoformat()

    return {
        "value_won": value_won,
        "year": int(prd_de) if prd_de.isdigit() else year,
        "unit_nm": latest.get("UNIT_NM", "만원"),
        "as_of": prd_de,
        "collected_at": now_iso,
        "source": "KOSIS",
        "stat_id": stat_id,
    }


# ────────────────────────────────────────────────────────────
# KB 주택가격동향 (KOSIS 101Y014 mirror) — 1986~ 월간 매매가격지수
# 사용자 Perplexity 호출 2 결과 (2026-05-09):
#   "KOSIS 가 KB국민은행 주택가격동향조사를 국가승인통계(제042001호)로 등록·배포 →
#    1986년 1월부터 월간 매매·전세 가격지수를 무료로 자동 수집"

def _kb_index_stat_id() -> str:
    """기본 stat_id = 101Y014 (KB 주택가격동향). 환경변수 override 가능."""
    return os.environ.get("KOSIS_KB_INDEX_STAT_ID", "101Y014").strip()


def fetch_kb_house_price_index(
    region_code: str = "00",
    item_code: Optional[str] = None,
    start_period: str = "198601",
    end_period: Optional[str] = None,
    timeout: float = 30.0,
) -> Optional[dict]:
    """KOSIS API 의 KB 주택가격동향 (101Y014) — 1986~ 월간 매매가격지수.

    Args:
      region_code: KOSIS objL1 지역코드 (default "00" = 전국). KB L2/L3 매핑은
                   사용자 검증 큐 (V1 calibration).
      item_code: ITM_ID (매매·전세 등 항목). None = default (전국 매매지수).
      start_period: 시작 YYYYMM (default 198601 = KB 시계열 시작점)
      end_period: 끝 YYYYMM. None = 가장 최근.

    Returns:
      {
        "series": [{"month": "YYYYMM", "index": float, "region_nm": str}, ...]
                  (시간 오름차순)
        "region_code": "00", "as_of": "YYYYMM",
        "collected_at": "...", "source": "KOSIS_KB",
        "stat_id": "101Y014",
        "n_points": int,
      }
      None → 키 미설정 / 네트워크 실패 / 응답 파싱 실패
    """
    key = _api_key()
    if not key:
        _logger.warning("KOSIS_API_KEY 미설정 — KB 시계열 fetch X")
        return None

    stat_id = _kb_index_stat_id()
    params = {
        "method": "getList",
        "apiKey": key,
        "format": "json",
        "jsonVD": "Y",
        "orgId": "408",  # KB국민은행 (KOSIS 기관 코드)
        "tblId": stat_id,
        "prdSe": "M",  # 월
        "startPrdDe": start_period,
        "objL1": region_code,
    }
    if end_period:
        params["endPrdDe"] = end_period
    if item_code:
        params["itmId"] = item_code

    try:
        r = requests.get(KOSIS_BASE, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        _logger.warning("KOSIS KB index fetch 실패 (region=%s): %s", region_code, e)
        return None

    if isinstance(data, dict) and "err" in data:
        _logger.warning("KOSIS KB 에러: %s", data.get("err"))
        return None
    if isinstance(data, dict) and "RESULT" in data:
        code = data.get("RESULT", {}).get("CODE")
        if code != KOSIS_RESULT_OK:
            _logger.warning("KOSIS KB 에러 코드: %s", code)
            return None

    rows = data if isinstance(data, list) else []
    if not rows:
        _logger.warning("KOSIS KB 빈 응답 (region=%s)", region_code)
        return None

    series: list[dict] = []
    region_nm = ""
    for row in rows:
        prd = (row.get("PRD_DE") or "").strip()
        val_str = row.get("DT")
        if not prd or val_str is None:
            continue
        try:
            val = float(str(val_str).replace(",", ""))
        except (ValueError, TypeError):
            continue
        if not region_nm:
            region_nm = (row.get("C1_NM") or "").strip()
        series.append({"month": prd, "index": val, "region_nm": region_nm or row.get("C1_NM", "")})

    if not series:
        return None

    series.sort(key=lambda x: x["month"])
    return {
        "series": series,
        "region_code": region_code,
        "region_nm": region_nm,
        "as_of": series[-1]["month"],
        "collected_at": _kst_now().isoformat(timespec="seconds"),
        "source": "KOSIS_KB",
        "stat_id": stat_id,
        "n_points": len(series),
    }
