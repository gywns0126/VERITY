"""통계청 KOSIS Open API 어댑터 — estate_brain L1 PIR 입력 (권역 중위소득).

API 포털: https://kosis.kr/openapi/
호출 베이스: https://kosis.kr/openapi/Param/statisticsParameterData.do
  (직접 명세 패턴 — orgId/tblId/itmId/objL1 명시. userStatsId 패턴 폐기)

V0 한계 (의도적 — V1 calibration 큐):
  - KOSIS 가계금융복지조사 등 가구소득 통계는 대부분 *전국 단일값*.
    서울 25구 단위는 통계청 마이크로데이터/부동산원 등 별도 source 필요.
  - V0 = 전국 가구 평균 경상소득 단일값 → 서울 25구 모두 동일값 사용.
  - V1 = 권역 가중치 (도심/동북/서북/서남/동남) Perplexity·실측 calibration 후 적용.

실측 검증 (2026-05-08, feedback_real_call_over_llm_consensus 정합):
  - 통계표: DT_1HDAAB04 (소득원천별 소득5분위별 가구소득, 가계금융복지조사)
  - 응답: DT=7427.31 만원 (2025, 가구 평균 경상소득), C1_NM=가구소득(경상소득)(전년도)

R-ONE 어댑터 (`./rone.py`) 패턴 정합:
  - KOSIS_API_KEY 환경변수 (Vercel + GH Actions secret 둘 다 지원)
  - KOSIS_INCOME_STAT_ID 환경변수 = 통계표 tblId (예: DT_1HDAAB04)
  - 키/tblId 부재 → None (fail-closed, estate_brain L1 layer skip)
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

KOSIS_BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

# 직접 명세 패턴 default (실측 2026-05-08, DT_1HDAAB04 = 가구 평균 경상소득)
DEFAULT_INCOME_ORG_ID = "101"   # 통계청
DEFAULT_INCOME_ITM_ID = "T00"   # 전체 항목
DEFAULT_INCOME_OBJ_L1 = "00"    # 전체 분류 (가구소득 경상소득 소계)

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
    """KOSIS 통계표 tblId — 사용자 실호출 검증 후 env 로 주입.

    실측 default 후보 (2026-05-08): DT_1HDAAB04
      = 가계금융복지조사 / 소득원천별 소득5분위별 가구소득 / 전국 가구 평균 경상소득
    """
    return os.environ.get("KOSIS_INCOME_STAT_ID", "").strip()


def _income_org_id() -> str:
    return os.environ.get("KOSIS_INCOME_ORG_ID", DEFAULT_INCOME_ORG_ID).strip()


def _income_itm_id() -> str:
    return os.environ.get("KOSIS_INCOME_ITM_ID", DEFAULT_INCOME_ITM_ID).strip()


def _income_obj_l1() -> str:
    return os.environ.get("KOSIS_INCOME_OBJ_L1", DEFAULT_INCOME_OBJ_L1).strip()


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
        _logger.warning("KOSIS_INCOME_STAT_ID 미설정 — 통계표 tblId 사용자 결정 큐")
        return None

    # 직접 명세 패턴 — orgId/tblId/itmId/objL1 명시 (실측 2026-05-08 검증)
    params = {
        "method": "getList",
        "apiKey": key,
        "format": "json",
        "jsonVD": "Y",
        "orgId": _income_org_id(),
        "tblId": stat_id,
        "itmId": _income_itm_id(),
        "objL1": _income_obj_l1(),
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
# REB 공동주택 실거래가격지수 (KOSIS DT_KAB_11672_S13) — 2006~ 월간 매매지수.
#
# 진화 노트 (2026-05-10):
#   기존 가정: KOSIS 가 KB국민은행 주택가격동향 (tblId=101Y014, 1986~) mirror — Perplexity
#     2026-05-09 LLM 가정. 실호출 결과 err=21 "통계표 부재" → KOSIS 에 KB 1986~ 월간
#     mirror 부재 확정 (memory feedback_real_call_over_llm_consensus 사례 추가).
#   정정: KOSIS 통합검색·통계포털 직접 검색 (사용자 화면 audit) → 실 가격지수 series 는
#     한국부동산원 (REB / KAB, orgId=408) 의 공동주택 실거래가격지수만 존재.
#       tblId=DT_KAB_11672_S13, 2006.01~, 월간, 9 권역 (전국·수도권·지방·서울·인천·
#       경기·광역시·지방광역시·지방도)
#   plan v0.3 정정: 시작 1986 → 2006 양보 (17년 short), 대신 권역 9개·월간·작동 보장.
#   BIS via FRED 1975~ 분기가 50y backbone 그대로, REB 가 권역 보강 layer.
#
# orgId=408 = 한국부동산원 (KAB). KB국민은행 아님 — 옛 주석 정정.

# KOSIS 9 권역 코드 매핑 (objL1).
# 매핑 규칙: 25구별 brain → 권역 broadcast 시 사용 (V1 calibration 후 가중치).
KOSIS_REB_REGION_CODES = {
    "전국":     "00",
    "수도권":   "10",
    "지방":     "20",
    "서울":     "11",
    "인천":     "28",
    "경기":     "41",
    "광역시":   "30",
    "지방광역시": "31",
    "지방도":   "32",
}


def _reb_apt_index_stat_id() -> str:
    """기본 stat_id = DT_KAB_11672_S13 (REB 공동주택 매매 실거래가격지수, 2006~ 월).

    검증: 사용자 OPENAPI URL (2026-05-10) — 9 권역 × 242 month = 2178 row.
    환경변수 KOSIS_REB_APT_INDEX_STAT_ID 로 override 가능 (옛 KOSIS_KB_INDEX_STAT_ID
    이름은 polymorph alias 로 backward compat).
    """
    return (
        os.environ.get("KOSIS_REB_APT_INDEX_STAT_ID")
        or os.environ.get("KOSIS_KB_INDEX_STAT_ID")  # legacy alias
        or "DT_KAB_11672_S13"
    ).strip()


# Legacy export — backward compat (테스트·외부 import). V1 정리 시 제거 검토.
_kb_index_stat_id = _reb_apt_index_stat_id


def fetch_reb_apt_price_index(
    region_nm: str = "전국",
    item_code: Optional[str] = None,
    start_period: str = "200601",
    end_period: Optional[str] = None,
    timeout: float = 30.0,
) -> Optional[dict]:
    """KOSIS API 의 한국부동산원 공동주택 매매 실거래가격지수 (DT_KAB_11672_S13).

    수록기간: 2006.01~ 월간. 9 권역 (전국/수도권/지방/서울/인천/경기/광역시/
    지방광역시/지방도). 단위 = 지수 (2017.11=100).

    구현 노트:
      KOSIS DT_KAB_11672_S13 는 objL1=숫자코드 (00, 11, ...) 가 아니라 *범용 ALL 값*
      만 인식 (사용자 OPENAPI URL 검증 2026-05-10 — objL1=ALL 만 정상, objL1=00
      은 err=21 "잘못된 요청변수"). → 항상 ALL 로 호출 후 응답에서 region_nm 으로
      클라이언트 측 필터.

    Args:
      region_nm: 권역 한글명 (KOSIS_REB_REGION_CODES 키). default "전국".
                 9 권역 외 값은 빈 응답.
      item_code: ITM_ID (T001=지수, T002=잠정 증감률). None = default T001 (지수).
      start_period: 시작 YYYYMM (default 200601 = REB 시계열 시작점).
      end_period: 끝 YYYYMM. None = 가장 최근.

    Returns:
      {
        "series": [{"month": "YYYYMM", "index": float, "region_nm": str}, ...]
                  (시간 오름차순)
        "region_nm": "전국", "as_of": "YYYYMM",
        "collected_at": "...", "source": "KOSIS_REB_APT",
        "stat_id": "DT_KAB_11672_S13",
        "n_points": int,
      }
      None → 키 미설정 / 네트워크 실패 / 응답 파싱 실패 / 빈 응답 / 권역 missing
    """
    key = _api_key()
    if not key:
        _logger.warning("KOSIS_API_KEY 미설정 — REB 시계열 fetch X")
        return None
    if region_nm not in KOSIS_REB_REGION_CODES:
        _logger.warning("Unknown REB region_nm: %s (must be one of %s)",
                        region_nm, list(KOSIS_REB_REGION_CODES.keys()))
        return None

    stat_id = _reb_apt_index_stat_id()
    params = {
        "method": "getList",
        "apiKey": key,
        "format": "json",
        "jsonVD": "Y",
        "orgId": "408",  # 한국부동산원 (KAB) — KB국민은행 아님 (옛 주석 정정)
        "tblId": stat_id,
        "prdSe": "M",  # 월
        "startPrdDe": start_period,
        "objL1": "ALL",  # 통계표 특성 — 숫자코드 인식 X, ALL 만 인식
    }
    # itmId default = T001 (지수). 미지정·다른 ITM 가 응답에 섞이면 month 별 multi-row
    # 발생 → series 의미 깨짐. 명시적 default 강제.
    params["itmId"] = item_code or "T001"
    # endPrdDe 미지정 시 KOSIS 가 startPrdDe 단일 월만 반환 → 시계열 깨짐.
    # 명시 안 주면 자동으로 *현재 시점* 까지 fetch (최근 월 = 오늘 KST 기준 YYYYMM).
    if end_period:
        params["endPrdDe"] = end_period
    else:
        params["endPrdDe"] = _kst_now().strftime("%Y%m")

    try:
        r = requests.get(KOSIS_BASE, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        _logger.warning("KOSIS REB apt index fetch 실패 (region=%s): %s", region_code, e)
        return None

    if isinstance(data, dict) and "err" in data:
        _logger.warning("KOSIS REB apt 에러: %s", data.get("err"))
        return None
    if isinstance(data, dict) and "RESULT" in data:
        code = data.get("RESULT", {}).get("CODE")
        if code != KOSIS_RESULT_OK:
            _logger.warning("KOSIS REB apt 에러 코드: %s", code)
            return None

    rows = data if isinstance(data, list) else []
    if not rows:
        _logger.warning("KOSIS REB apt 빈 응답 (region=%s)", region_code)
        return None

    series: list[dict] = []
    for row in rows:
        # objL1=ALL 호출이라 9 권역 응답 mixed → region_nm 으로 1개만 필터.
        row_region = (row.get("C1_NM") or "").strip()
        if row_region != region_nm:
            continue
        prd = (row.get("PRD_DE") or "").strip()
        val_str = row.get("DT")
        if not prd or val_str is None:
            continue
        try:
            val = float(str(val_str).replace(",", ""))
        except (ValueError, TypeError):
            continue
        series.append({"month": prd, "index": val, "region_nm": row_region})

    if not series:
        _logger.warning("KOSIS REB apt 응답에 region_nm=%s row 없음", region_nm)
        return None

    series.sort(key=lambda x: x["month"])
    return {
        "series": series,
        "region_nm": region_nm,
        "as_of": series[-1]["month"],
        "collected_at": _kst_now().isoformat(timespec="seconds"),
        "source": "KOSIS_REB_APT",
        "stat_id": stat_id,
        "n_points": len(series),
    }


# ── Backward compat alias — 기존 caller (estate_brain_backtest_50y_builder) 무영향. ──
# V1 정리 시 caller rename 후 alias 삭제 검토.
fetch_kb_house_price_index = fetch_reb_apt_price_index
