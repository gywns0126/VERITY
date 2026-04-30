"""한국부동산원 R-ONE Open API 어댑터 — LANDEX V/D/S 신호.

API 포털: https://www.reb.or.kr/r-one/portal/openapi/openApiIntroPage.do
호출 베이스: https://www.reb.or.kr/r-one/openapi/{ENDPOINT}.do

용도 (기존 어댑터와의 분담):
  - V (Value)  : MOLIT 실거래는 "현재 절대 평당가". R-ONE 주간지수는 "장기 가격 모멘텀".
                 누적 12주 변화율로 "이미 많이 오른 곳" → V 가산점 깎음 (mean-reversion).
                 ±15점 폭은 V 기여분(LANDEX 30%)의 ±50% — 1티어(10점) 이동 가능 수준.
  - D (Development) : 단기(8주) 분할 가속도. 가격이 *가속하며* 오르는 구는 호재 반영 중일 가능성 ↑.
  - S (Supply) : 월간 미분양 호수 + 추세. 미분양↓ + 감소 추세 → S 점수 ↑.
                  KOSIS Param 의 분류 시스템 까다로움 우회 — R-ONE 으로 단일화.

R-ONE 사양 (실측 검증 2026-04-29 — 3자 LLM 합의가 일부 틀려 *실측 우선*):
  - 엔드포인트: SttsApiTblData.do (catalog 는 SttsApiTbl.do)
  - 응답 필드: STATBL_ID / CLS_ID / CLS_NM / CLS_FULLNM / ITM_ID / ITM_NM /
              WRTTIME_IDTFR_ID / WRTTIME_DESC / DTA_VAL / UI_NM
  - DTACYCLE_CD 주간 코드 = "WK"  (LLM 추측 "WW" 는 오답. 실측 8개 주간 통계 모두 WK)
  - WRTTIME_IDTFR_ID 주간 형식 = "YYYYWW" (예 "202617" = 2026년 17주)
  - WRTTIME_DESC = 사람이 읽는 ISO 날짜 ("2026-04-20") — 표시용 권장
  - STATBL_ID 주간 매매가격지수 = "T244183132827305" (T+13자리, R_2024_* 형식 아님)
  - CLS_ID 는 R-ONE 자체 코드 — LAWD_CD 와 *완전히* 다름. 서울 25구 매핑 GU_TO_RONE_CLS 참조.
  - ITM_ID=10001 = 지수, 다른 ITM 은 변동률 등. 우리는 지수만 사용.

Stat IDs / 지역코드:
  실측 매핑은 코드 상단 GU_TO_RONE_CLS / DEFAULT_STAT_WEEKLY 상수에 박아둠.
  바뀌면 reb.or.kr 가입 후 SttsApiTbl.do (catalog) 재호출로 검증.

응답 포맷: Type=json 명시 (기본 xml). RESULT.CODE 가 INFO-000 이외면 에러.

인증: KEY 파라미터 (URL-decoded 그대로). 일일 트래픽 한도 미공시 — 캐시 적극 활용.
재배포 라이선스: data.go.kr 페이지 기준 "이용허락범위 제한 없음" (2026-04 확인).

feedback_macro_timestamp_policy 준수: 모든 응답에 collected_at + as_of 동시 노출.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from ._lawd import SEOUL_25_GU

_logger = logging.getLogger(__name__)

RONE_BASE = "https://www.reb.or.kr/r-one/openapi"

# ── 통계 ID 설정 (env override 지원) ──
# 실측으로 확정한 STATBL_ID. 다른 통계 쓰려면 env 로 override.
DEFAULT_STAT_WEEKLY = "T244183132827305"  # (주) 매매가격지수, 2012~현재 165k+ rows
DEFAULT_STAT_MONTHLY_UNSOLD = "T237973129847263"  # (월) 미분양주택현황, 2000~현재 55k+ rows

# 우리가 사용할 ITM_ID — 10001 = 지수/미분양현황 (변동률 등은 다른 ITM_ID).
# 두 통계 모두 ITM_ID=10001 이 메인 시계열. 다른 ITM_ID 는 컴포넌트 분해(예: 규모별).
ITEM_ID_INDEX = 10001

# R-ONE 표준 응답 필드 (실측 2026-04-29)
FIELD_REGION = "CLS_NM"            # 분류명(지역명) 예: "서울", "강남구"
FIELD_REGION_CODE = "CLS_ID"       # R-ONE 분류 코드 (정수)
FIELD_REGION_FULLNM = "CLS_FULLNM" # 분류 전체경로 예: "서울>강남지역>동남권>강남구"
FIELD_ITEM = "ITM_ID"              # 항목 코드 (지수=10001)
FIELD_PERIOD = "WRTTIME_IDTFR_ID"  # 주간 "YYYYWW" (예 "202617")
FIELD_PERIOD_DESC = "WRTTIME_DESC" # 사람이 읽는 ISO 날짜 (예 "2026-04-20")
FIELD_VALUE = "DTA_VAL"            # 지수값 (이미 float 로 옴, 안전을 위해 변환 처리)

# 서울 25구 → R-ONE CLS_ID 매핑 (실측 2026-04-29).
# *통계마다 CLS_ID 가 다름!* — STATBL_ID 별로 별도 매핑 필요.
# LAWD_CD(11680 등) 와 완전히 다른 R-ONE 자체 코드 체계.

# 매매가격지수(T244183132827305) 용 — 50043~50070 범위
GU_TO_RONE_CLS: dict[str, int] = {
    "종로구": 50043, "중구": 50044, "용산구": 50045, "성동구": 50047,
    "광진구": 50048, "동대문구": 50049, "중랑구": 50050, "성북구": 50051,
    "강북구": 50052, "도봉구": 50053, "노원구": 50054, "은평구": 50056,
    "서대문구": 50057, "마포구": 50058, "양천구": 50060, "강서구": 50061,
    "구로구": 50062, "금천구": 50063, "영등포구": 50064, "동작구": 50065,
    "관악구": 50066, "서초구": 50067, "강남구": 50068, "송파구": 50069,
    "강동구": 50070,
}

# 미분양주택현황(T237973129847263) 용 — 50019~50043 범위 (다름!)
GU_TO_RONE_UNSOLD_CLS: dict[str, int] = {
    "종로구": 50019, "강남구": 50020, "중구": 50021, "강동구": 50022,
    "용산구": 50023, "성동구": 50024, "강북구": 50025, "광진구": 50026,
    "강서구": 50027, "관악구": 50028, "동대문구": 50029, "중랑구": 50030,
    "구로구": 50031, "성북구": 50032, "금천구": 50033, "도봉구": 50034,
    "노원구": 50035, "은평구": 50036, "서대문구": 50037, "동작구": 50038,
    "마포구": 50039, "양천구": 50040, "서초구": 50041, "영등포구": 50042,
    "송파구": 50043,
}


def _api_key() -> str:
    return os.environ.get("REB_API_KEY", "").strip()


def _stat_weekly_id() -> str:
    return os.environ.get("REB_STAT_WEEKLY_APT_INDEX", DEFAULT_STAT_WEEKLY).strip()


def _stat_monthly_unsold_id() -> str:
    return os.environ.get("REB_STAT_MONTHLY_UNSOLD", DEFAULT_STAT_MONTHLY_UNSOLD).strip()


def _kst_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=9)))


def _parse_response(data: dict) -> tuple[Optional[int], list[dict]]:
    """R-ONE 응답에서 (list_total_count, row_list) 추출. 에러면 (None, [])."""
    if isinstance(data, dict) and "RESULT" in data:
        code = (data["RESULT"] or {}).get("CODE")
        if code and code != "INFO-000":
            _logger.warning("R-ONE error: %s", data["RESULT"])
            return None, []

    payload = data.get("SttsApiTblData") if isinstance(data, dict) else None
    rows: list[dict] = []
    total: Optional[int] = None
    chunks = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        head = chunk.get("head")
        if isinstance(head, list):
            for h in head:
                if isinstance(h, dict) and "list_total_count" in h:
                    try:
                        total = int(h["list_total_count"])
                    except (TypeError, ValueError):
                        pass
        if isinstance(chunk.get("row"), list):
            rows.extend(chunk["row"])
    return total, rows


def _fetch_stats_table(
    stat_id: str,
    cls_id: Optional[int] = None,
    dtacycle: str = "WK",
    page_size: int = 1000,
    max_pages: int = 5,
    timeout: float = 10.0,
) -> Optional[list[dict]]:
    """R-ONE SttsApiTblData 호출. 페이징 자동 처리하여 row 반환.

    dtacycle: "WK"(주간) | "MM"(월간) | "YY"(연간) — 통계마다 다름.

    응답이 *오래된 데이터부터* 내려와서 단일 페이지로는 최신 데이터 못 받음.
    1페이지로 list_total_count 확인 후 마지막 max_pages 페이지만 추가 호출.
    cron 워커 환경 가정 (Vercel API 라우트 부적합).

    실패 케이스(키/STAT_ID/네트워크/에러응답) 는 None.
    """
    key = _api_key()
    if not key:
        _logger.warning("REB_API_KEY 미설정 — R-ONE 호출 스킵")
        return None
    if not stat_id:
        _logger.warning("STATBL_ID 미설정 — R-ONE 호출 스킵")
        return None

    url = f"{RONE_BASE}/SttsApiTblData.do"
    base_params = {
        "KEY": key,
        "Type": "json",
        "pSize": str(page_size),
        "STATBL_ID": stat_id,
        "DTACYCLE_CD": dtacycle,
    }
    if cls_id is not None:
        base_params["CLS_ID"] = str(cls_id)

    def _get(page_index: int) -> Optional[tuple[Optional[int], list[dict]]]:
        try:
            r = requests.get(url, params={**base_params, "pIndex": str(page_index)}, timeout=timeout)
            r.raise_for_status()
            return _parse_response(r.json())
        except Exception as e:
            _logger.warning("R-ONE page %d 실패 stat=%s cls=%s: %s",
                            page_index, stat_id, cls_id, e)
            return None

    first = _get(1)
    if first is None:
        return None
    total, first_rows = first
    if total is None:
        return first_rows or None
    if total == 0:
        _logger.warning("R-ONE empty rows stat=%s cls=%s", stat_id, cls_id)
        return None

    last_page = (total + page_size - 1) // page_size  # ceil
    start_page = max(1, last_page - max_pages + 1)

    if last_page == 1:
        return first_rows

    rows: list[dict] = list(first_rows) if start_page == 1 else []
    page_iter_start = 2 if start_page == 1 else start_page
    for p in range(page_iter_start, last_page + 1):
        page_data = _get(p)
        if page_data is None:
            break
        rows.extend(page_data[1])
    return rows or None


def fetch_weekly_index(
    gu: str,
    weeks: int = 12,
    timeout: float = 10.0,
    as_of_yyyymmww: Optional[str] = None,
) -> Optional[dict]:
    """단일 구의 최근 N주 주간 아파트 매매가격지수 시계열.

    R-ONE 주간 식별자는 "YYYYMM W#" (예: "202604W1") 형식 — 정렬은 사전식으로 동작
    (월 → 주차 순서). 시점 필터를 클라이언트에서 만들기 어려워 최근 page_size 행을
    내려받아 정렬 후 N주 슬라이스.

    as_of_yyyymmww: 시점 기준 식별자 (예 "202604W4"). None 이면 *현재* 기준 최근 N주.
                    값이 있으면 해당 시점 *이전*만 keep 후 마지막 N주 슬라이스.
                    백테스트·메타-검증용.

    CLS_ID 는 R-ONE 자체 분류코드 — 우선 LAWD_CD(5자리)를 시도하되 매핑이 다르면
    실 호출 결과 보고 _gu_to_cls_id 별도 보정.

    Returns:
      {
        "gu": "강남구",
        "series": [{"week": "202602W1", "index": 102.34}, ...],  # 사전식 오름차순
        "as_of": "202604W4",                # 가장 최근 주 식별자 원본
        "collected_at": "2026-04-29T21:30:00+09:00",
        "source": "rone_weekly",
        "stat_id": "R_2024_xxx",
      }
      None → 키/STAT_ID 미설정 / 네트워크 실패 / 빈 응답 / gu 매핑 실패
    """
    cls_id = GU_TO_RONE_CLS.get(gu.strip())
    if cls_id is None:
        _logger.warning("Unknown gu for R-ONE: %s", gu)
        return None

    now = _kst_now()
    stat_id = _stat_weekly_id()
    # CLS_ID 필터로 단일 구만 받으면 weeks×수년치까지 한 페이지로 내려옴.
    # 응답엔 ITM_ID 다종(지수/변동률 등) 섞일 수 있어 ITM_ID_INDEX 만 통과.
    # as_of 모드는 12년치 전체 필요 (단일 구 ~624 rows) → 페이지 사이즈/페이지 수 키움.
    page_size_use = 1000 if as_of_yyyymmww else max(200, weeks * 6)
    max_pages_use = 2 if as_of_yyyymmww else 5
    rows = _fetch_stats_table(
        stat_id=stat_id,
        cls_id=cls_id,
        page_size=page_size_use,
        max_pages=max_pages_use,
        timeout=timeout,
    )
    if not rows:
        return None

    series: list[dict] = []
    last_desc: Optional[str] = None
    for row in rows:
        # ITM_ID 필터 — 지수만 (변동률·평균값 등은 다른 ITM_ID)
        itm = row.get(FIELD_ITEM)
        if itm is not None and int(itm) != ITEM_ID_INDEX:
            continue
        period = str(row.get(FIELD_PERIOD) or "").strip()
        raw_val = row.get(FIELD_VALUE)
        if not period or raw_val in (None, ""):
            continue
        try:
            val = float(str(raw_val).replace(",", ""))
        except (ValueError, TypeError):
            continue
        desc = (row.get(FIELD_PERIOD_DESC) or "").strip()
        series.append({"week": period, "index": val, "date": desc or None})
        last_desc = desc or last_desc

    if not series:
        return None

    # "YYYYWW" 사전식 정렬 = 시간 정렬 (해를 기준 5자리 zero-pad 가정 OK)
    series.sort(key=lambda x: x["week"])
    # as_of 모드: 시점 이전 데이터만 keep (백테스트 합성용 — look-ahead bias 차단)
    if as_of_yyyymmww:
        series = [s for s in series if s["week"] <= as_of_yyyymmww]
    series = series[-weeks:]  # 최근 N주 (또는 as_of 시점 거꾸로 N주)

    last = series[-1]
    return {
        "gu": gu,
        "cls_id": cls_id,
        "series": series,
        "as_of": last.get("date") or last["week"],  # 사람이 읽는 ISO 우선
        "as_of_week": last["week"],
        "collected_at": now.isoformat(timespec="seconds"),
        "source": "rone_weekly",
        "stat_id": stat_id,
    }


def fetch_weekly_index_seoul_25(
    weeks: int = 12,
    timeout: float = 10.0,
    sleep_between: float = 0.15,
    as_of_yyyymmww: Optional[str] = None,
) -> dict[str, Optional[dict]]:
    """서울 25구 일괄 조회. cron 워커용 — Vercel API 라우트에서는 호출 금지(10s 초과).

    as_of_yyyymmww: 시점 기준 (백테스트·메타-검증용). None 이면 현재 기준.
    """
    import time
    out: dict[str, Optional[dict]] = {}
    for gu in SEOUL_25_GU:
        out[gu] = fetch_weekly_index(gu, weeks=weeks, timeout=timeout, as_of_yyyymmww=as_of_yyyymmww)
        time.sleep(sleep_between)  # rate-limit 보호
    return out


# ──────────────────────────────────────────────────────────────
# ◆ 점수 산출 보조 함수 (V/D 입력)
# ──────────────────────────────────────────────────────────────

def compute_value_momentum_penalty(payload: Optional[dict]) -> Optional[float]:
    """누적 가격 상승률 → V 가산/감산점 (-15 ~ +15).

    로직:
      - 12주 누적 변화율 기준 (시계열이 더 길게 들어와도 최근 12주만 사용)
      - +5%↑ : -15 (이미 많이 오름 = 저평가 메리트 ↓)
      -   0% : 0   (평균 수준)
      - -5%↓ : +15 (조정 받음 = 저평가 메리트 ↑)

    호출자(_snapshot)가 MOLIT 기반 V 점수에 더해서 사용. None 이면 패널티 미적용.
    """
    if not payload:
        return None
    series = payload.get("series") or []
    if len(series) < 4:
        return None
    # D 가속도와 윈도우 분리 — V 는 항상 최근 12주만 사용 (의미 일관성)
    recent = series[-12:]
    first = recent[0]["index"]
    last = recent[-1]["index"]
    if first <= 0:
        return None
    change_pct = (last - first) / first * 100  # %
    # ±5% 구간 선형 매핑 → ∓15점
    capped = max(-5.0, min(5.0, change_pct))
    return round(-capped * 3.0, 2)  # +5% → -15, -5% → +15


def compute_d_volatility_flag(payload: Optional[dict], threshold_std: float = 0.3) -> bool:
    """26주 시계열 *변동률 std* → high volatility 플래그 (v1.2).

    std > 0.3%p 면 시점 시프트로 가속도 변동 큼 (정책충격·outlier 시점 영향).
    백테스트 합성 시 이 구의 D 점수는 confidence 낮음 — raw_payload['d_high_volatility'] = True.

    proxy 로직: 시계열 자체 노이즈가 큰 구는 *시점 시프트로 D 점수 변동* 도 클 가능성.
    정확한 매칭은 *과거 N 시점 fetch* 후 std 계산이지만 비용 5배 — 시계열 변동률 std 가 단일 호출 proxy.
    """
    if not payload:
        return False
    series = payload.get("series") or []
    if len(series) < 26:
        return False
    series = series[-26:]
    import statistics
    changes: list[float] = []
    for i in range(len(series) - 1):
        a = series[i]["index"]
        b = series[i + 1]["index"]
        if a > 0:
            changes.append((b - a) / a * 100)
    if len(changes) < 2:
        return False
    std_dev = statistics.stdev(changes)
    return std_dev > threshold_std


def compute_development_momentum_score(payload: Optional[dict]) -> Optional[float]:
    """장기 가속도 → D 점수 (0~100).

    로직 (v1.1 — 2026-04-30 산식 변경):
      - **26주 윈도우** 사용 (기존 12주 → 시점 1주 시프트 시 30점 변동 issue 해결)
      - 최근 13주 변화율 vs 직전 13주 변화율 비교 (acceleration)
      - 가속(최근 변화율 > 직전 변화율) → 호재 반영 중 → D 점수 ↑
      - 감속/하락 → D 점수 ↓
      - 가속도 +2.0%p ↑ → 100, 0%p → 50, -2.0%p ↓ → 0 (선형, 기존 ±0.5%p → ±2.0%p)
      - 4배 robust: 0.05%p 차이가 1.25점 (기존 5점)

    데이터 부족 시 (26주 미만) None — 호출자가 mock fallback.
    """
    if not payload:
        return None
    series = payload.get("series") or []
    if len(series) < 26:
        return None

    def _pct_change(a: float, b: float) -> Optional[float]:
        if a <= 0:
            return None
        return (b - a) / a * 100

    # 최근 26주만 사용 (더 들어와도 cutoff)
    series = series[-26:]
    half = len(series) // 2  # 13
    prior_chg = _pct_change(series[0]["index"], series[half - 1]["index"])
    recent_chg = _pct_change(series[half]["index"], series[-1]["index"])
    if recent_chg is None or prior_chg is None:
        return None

    accel = recent_chg - prior_chg  # %p
    capped = max(-2.0, min(2.0, accel))
    score = 50 + (capped / 2.0) * 50
    return round(score, 1)


# ──────────────────────────────────────────────────────────────
# ◆ S (Supply) — 월간 미분양 (T237973129847263)
# ──────────────────────────────────────────────────────────────

def fetch_monthly_unsold(
    gu: str,
    months: int = 12,
    timeout: float = 10.0,
    as_of_yyyymm: Optional[str] = None,
) -> Optional[dict]:
    """단일 구의 최근 N개월 미분양 호수 시계열.

    WRTTIME_IDTFR_ID 월간 형식 = "YYYYMM" (예 "202602"). 사전식 정렬 = 시간순.
    CLS_ID 매핑은 GU_TO_RONE_UNSOLD_CLS — 매매지수와 다른 코드체계 (실측 확인).

    as_of_yyyymm: 시점 기준 (예 "202604"). None 이면 *현재* 기준 최근 N개월.
                  값이 있으면 해당 월 *이전*만 keep 후 마지막 N개월.
                  백테스트·메타-검증용 (look-ahead bias 차단).

    Returns:
      {
        "gu": "강남구",
        "cls_id": 50020,
        "series": [{"month": "202602", "unsold": 0, "date": "2026년 02월"}, ...],
        "as_of": "2026년 02월", "as_of_month": "202602",
        "collected_at": "...",
        "source": "rone_unsold", "stat_id": "T237973129847263",
      }
      None → 키/STAT_ID 미설정 / 네트워크 실패 / gu 매핑 실패
    """
    cls_id = GU_TO_RONE_UNSOLD_CLS.get(gu.strip())
    if cls_id is None:
        _logger.warning("Unknown gu for R-ONE unsold: %s", gu)
        return None

    now = _kst_now()
    stat_id = _stat_monthly_unsold_id()
    page_size_use = 1000 if as_of_yyyymm else max(200, months * 6)
    max_pages_use = 2 if as_of_yyyymm else 5
    rows = _fetch_stats_table(
        stat_id=stat_id,
        cls_id=cls_id,
        dtacycle="MM",
        page_size=page_size_use,
        max_pages=max_pages_use,
        timeout=timeout,
    )
    if not rows:
        return None

    series: list[dict] = []
    for row in rows:
        itm = row.get(FIELD_ITEM)
        if itm is not None and int(itm) != ITEM_ID_INDEX:
            continue
        period = str(row.get(FIELD_PERIOD) or "").strip()
        raw_val = row.get(FIELD_VALUE)
        if not period or raw_val in (None, ""):
            continue
        try:
            val = int(float(str(raw_val).replace(",", "")))
        except (ValueError, TypeError):
            continue
        desc = (row.get(FIELD_PERIOD_DESC) or "").strip()
        series.append({"month": period, "unsold": val, "date": desc or None})

    if not series:
        return None

    series.sort(key=lambda x: x["month"])  # YYYYMM 사전식 = 시간순
    # as_of 모드: 시점 이전 데이터만 keep (look-ahead bias 차단)
    if as_of_yyyymm:
        series = [s for s in series if s["month"] <= as_of_yyyymm]
    series = series[-months:]

    last = series[-1]
    return {
        "gu": gu,
        "cls_id": cls_id,
        "series": series,
        "as_of": last.get("date") or last["month"],
        "as_of_month": last["month"],
        "collected_at": now.isoformat(timespec="seconds"),
        "source": "rone_unsold",
        "stat_id": stat_id,
    }


def fetch_monthly_unsold_seoul_25(
    months: int = 12,
    timeout: float = 10.0,
    sleep_between: float = 0.15,
    as_of_yyyymm: Optional[str] = None,
) -> dict[str, Optional[dict]]:
    """서울 25구 미분양 일괄 조회. cron 워커용.

    as_of_yyyymm: 시점 기준 (백테스트·메타-검증용). None 이면 현재 기준.
    """
    import time
    out: dict[str, Optional[dict]] = {}
    for gu in SEOUL_25_GU:
        out[gu] = fetch_monthly_unsold(gu, months=months, timeout=timeout, as_of_yyyymm=as_of_yyyymm)
        time.sleep(sleep_between)
    return out


def compute_supply_score(payload: Optional[dict]) -> Optional[float]:
    """월간 미분양 시계열 → S 점수 (0~100, 높을수록 양호).

    로직:
      ① 절대 수준 점수 (0~70):
         - 0호      → 70 (최상)
         - 100호    → 50
         - 500호    → 30
         - 1000호↑  → 10 (cap)
         - 로그 스케일: 70 - 10*log10(max(1, last)) 같은 곡선
      ② 추세 보정 (-30 ~ +30):
         - 최근 6M 평균 vs 직전 6M 평균
         - 감소(-50%↓) → +30 (소진 중)
         - 증가(+50%↑) → -30 (적체 중)
         - 선형 매핑

    합산 후 0~100 클립. 시계열 ≥ 6개월 필요.

    인구·세대수 정규화는 v1.5 — v1 은 절대량 + 추세.
    """
    if not payload:
        return None
    series = payload.get("series") or []
    if len(series) < 6:
        return None

    last_unsold = series[-1].get("unsold")
    if last_unsold is None or last_unsold < 0:
        return None

    # ① 절대 수준 (0~70)
    import math
    if last_unsold <= 0:
        level_score = 70.0
    else:
        # log10(1)=0 → 70, log10(10)=1 → 60, log10(100)=2 → 50, log10(1000)=3 → 40
        level_score = max(10.0, 70.0 - 10.0 * math.log10(last_unsold))

    # ② 추세 (앞 절반 vs 뒤 절반 평균)
    half = len(series) // 2
    prior_avg = sum(s["unsold"] for s in series[:half]) / max(1, half)
    recent_avg = sum(s["unsold"] for s in series[half:]) / max(1, len(series) - half)

    if prior_avg <= 0:
        # 0 → 0 그대로면 중립, 0 → 양수면 적체 발생
        trend_adj = -30.0 if recent_avg > 0 else 0.0
    else:
        change_pct = (recent_avg - prior_avg) / prior_avg * 100  # %
        # ±50% 선형 매핑 → ∓30
        capped = max(-50.0, min(50.0, change_pct))
        trend_adj = -capped * 0.6  # +50% → -30, -50% → +30

    score = max(0.0, min(100.0, level_score + trend_adj))
    return round(score, 1)
