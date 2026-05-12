"""
subscription_collector.py — 한국부동산원 청약홈 분양정보 수집기 (ESTATE D / SubscriptionCalendar)

출처: data.go.kr 15098547 (한국부동산원_청약홈 분양정보 조회 서비스).
        OpenAPI base = odcloud (행안부 통합 API 플랫폼).
        endpoint    = api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail
                      (오피스텔/잔여세대는 v0 범위 외 — APT 만)
        인증        = env PUBLIC_DATA_API_KEY (policy_collector v2 와 동일 키).
                      data.go.kr 동일 계정에 15098547 활용신청 추가 필요 (user_action_queue 큐잉).

이 모듈은 "수집"만 한다. 이벤트 분해(5종: 모집공고/접수/발표/계약/입주) 는
api/builders/estate_subscription_calendar_builder.py 담당. 단일 책임 원칙.

응답 schema (출처: PublicDataReader WooilJeong/Reb.md 실측 + save-my-youth/api.py 사용 예):
    HOUSE_MANAGE_NO         주택관리번호 (primary key)
    PBLANC_NO               공고번호
    HOUSE_NM                주택명
    HSSPLY_ADRES            공급위치
    SUBSCRPT_AREA_CODE      청약지역코드
    SUBSCRPT_AREA_CODE_NM   청약지역명 (서울/경기/...)
    BSNS_MBY_NM             사업주체명
    CNSTRCT_ENTRPS_NM       건설업체명
    TOT_SUPLY_HSHLDCO       총공급세대수
    RCRIT_PBLANC_DE         모집공고일
    RCEPT_BGNDE             청약접수 시작일
    RCEPT_ENDDE             청약접수 종료일
    PRZWNER_PRESNATN_DE     당첨자발표일
    CNTRCT_CNCLS_BGNDE      계약체결 시작일
    CNTRCT_CNCLS_ENDDE      계약체결 종료일
    MVN_PREARNGE_YM         입주예정월
    PBLANC_URL              분양정보 URL (T29 — 외부 상세)
    HMPG_ADRES              홈페이지 주소
    SPECLT_RDN_EARTH_AT     투기과열지구 여부
    RENT_SECD / _NM         임대구분
    ... 그 외 1순위/2순위/해당지역/기타지역 접수일 다수 (v0 범위 외)

거짓말 트랩 컴플라이언스:
    T1  fabricate 금지   — 5xx/네트워크/파싱 실패 시 빈 list
    T9  silent 실패 X    — 모든 실패 logger.error + 빈 list
    T11 URL 가정 X       — base URL 은 reb.py + save-my-youth 실 코드 정합 (T29 동급)
    T15 timeout 명시     — 기본 15s
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail"
DEFAULT_PER_PAGE = 500              # odcloud 안정 (10000 도 가능하나 안전 buffer)
DEFAULT_TIMEOUT_SEC = 15
DEFAULT_LOOKBACK_DAYS = 30           # 과거 30일 + 향후 90일 = SubscriptionCalendar 표준 window
DEFAULT_LOOKFORWARD_DAYS = 90
MAX_PAGES = 20                       # 안전 한도 — 분양 0~20건/일 기준 1page 충분

KST = timezone(timedelta(hours=9))


def _service_key() -> str:
    """env 기반 인증키. 호출 시점 lookup (테스트 monkeypatch 친화)."""
    return os.environ.get("PUBLIC_DATA_API_KEY", "").strip()


def collect_subscriptions(
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    lookforward_days: int = DEFAULT_LOOKFORWARD_DAYS,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    now: Optional[datetime] = None,
    _http_get: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    청약홈 분양정보 (APT) 를 lookback~lookforward 윈도우로 수집.

    Args:
        lookback_days:    오늘 기준 N일 전 RCRIT_PBLANC_DE 부터 (이미 발표된 공고).
        lookforward_days: 향후 N일까지의 입주예정/접수예정 포함 — 실제 필터는 RCRIT_PBLANC_DE 기준만,
                          이후 일정(계약·입주) 은 row 안에 박혀있으므로 calendar builder 가 분해.
        timeout_sec:      HTTP timeout.
        now:              테스트 주입용.
        _http_get:        테스트 주입용 (requests.get 대체). 첫 호출당 response 반환.

    Returns:
        List[dict] — 각 row 가 분양 공고 1건 (전체 컬럼). 실패 시 [] (T1).
    """
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    now_kst = now_utc.astimezone(KST)

    # RCRIT_PBLANC_DE 형식 = YYYY-MM-DD (PublicDataReader 실측). cond filter 동일 format.
    start_str = (now_kst - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    key = _service_key()
    if not key:
        logger.error(
            "subscription_collector: PUBLIC_DATA_API_KEY missing. "
            "logged=True (feedback_data_collection_verification_mandatory)",
        )
        return []

    http_get = _http_get or requests.get

    all_rows: List[Dict[str, Any]] = []
    page = 1
    while page <= MAX_PAGES:
        params = {
            "serviceKey": key,
            "page": page,
            "perPage": DEFAULT_PER_PAGE,
            "returnType": "json",
            "cond[RCRIT_PBLANC_DE::GTE]": start_str,
        }

        try:
            res = http_get(API_BASE, params=params, timeout=timeout_sec)
        except requests.RequestException as e:
            logger.error("subscription_collector: HTTP error %s for %s (page=%d)", e, API_BASE, page)
            break

        if getattr(res, "status_code", 0) != 200:
            logger.error(
                "subscription_collector: non-200 %s from %s (page=%d)",
                getattr(res, "status_code", "?"), API_BASE, page,
            )
            break

        try:
            payload = res.json()
        except (ValueError, TypeError) as e:
            logger.error("subscription_collector: JSON parse failed (page=%d): %s", page, e)
            break

        if not isinstance(payload, dict):
            logger.error("subscription_collector: payload not dict (page=%d)", page)
            break

        rows = payload.get("data") or []
        if not isinstance(rows, list):
            logger.error("subscription_collector: data not list (page=%d)", page)
            break

        all_rows.extend(rows)

        match_count = int(payload.get("matchCount") or 0)
        if len(all_rows) >= match_count or not rows:
            break
        page += 1

    return all_rows
