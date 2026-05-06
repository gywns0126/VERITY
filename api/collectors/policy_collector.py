"""
policy_collector.py — ESTATE HeroBriefing 정책 수집 레이어 (v2 — data.go.kr 정공법)

v1 (korea.kr/rss/dept_molit.xml) 폐기 사유: korea.kr 가 datacenter ASN 차단 (Vercel
iad1 + GH Actions Azure US + Railway EU West 모두 ConnectionResetError 측정 확정,
2026-05-06). estate/docs/contract_p3_4_policy_data_source.md 참조.

v2 출처: data.go.kr 1371000 (문화체육관광부 = 정책브리핑 운영주체) 정식 OpenAPI.
  - 정책브리핑_보도자료 API (data.go.kr 15095295) — 부처별 보도자료, dept_molit RSS 1:1 정합
  - 인증: env PUBLIC_DATA_API_KEY (vercel-api/.env 박힘 — 활용신청 2026-05-06 완료)
  - 제약: startDate/endDate 3일 이내 (THREE_DAYS_OVER_ERROR resultCode=98)
  - 응답 schema: <response><body><NewsItem>... — 부처필드 = MinisterCode

이 모듈은 "수집"만 한다. prefilter (rough_relevance_filter) 는 api/analyzers/policy_keywords.py.
카테고리/Stage/affected_regions 분류는 api/analyzers/policy_classifier.py. 단일 책임 원칙.

Output schema (downstream 무변경 — v1 정합):
    id           NewsItemId
    title        Title (CDATA strip)
    source_url   OriginalUrl
    source_name  MinisterCode (실제 응답 부처명)
    published_at ApproveDate parsed (KST → UTC ISO 8601)
    raw_text     DataContents HTML strip

거짓말 트랩 컴플라이언스 (v1 → v2 정합):
    T1  fabricate 금지   — 5xx/네트워크/파싱/resultCode != 0 시 빈 배열만 반환
    T9  silent 실패 X    — 모든 실패 logging.error + 빈 배열
    T11 URL 가정 X       — API_BASE 는 data.go.kr 공식 endpoint (WebFetch 검증 2026-05-06)
    T12 User-Agent 강제  — 불필요 (정식 API key 인증)
    T15 timeout=15s, retry=0 (cron 자체가 자연 retry)
"""
from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

API_BASE = "http://apis.data.go.kr/1371000/pressReleaseService/pressReleaseList"
DEFAULT_MINISTER_FILTER = "국토교통부"  # v1 dept_molit 정합. None 이면 전체 부처
DEFAULT_LOOKBACK_HOURS = 72  # API 제약 = 3일. 72h = exact upper bound.
DEFAULT_TIMEOUT_SEC = 15
DEFAULT_NUM_OF_ROWS = 100  # 페이지당 — 72h MOLIT 기준 충분 (실측 0~3건/h)

KST = timezone(timedelta(hours=9))


def _service_key() -> str:
    """env 기반 인증키. 호출 시점 lookup (테스트 monkeypatch 친화)."""
    return os.environ.get("PUBLIC_DATA_API_KEY", "").strip()


def collect_policies(
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    minister_filter: Optional[str] = DEFAULT_MINISTER_FILTER,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    now: Optional[datetime] = None,
    _xml_text: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    data.go.kr 정책브리핑 보도자료 API 에서 lookback 윈도우 내 항목을 표준 dict 배열로 반환한다.

    Args:
        lookback_hours: 현재 시각 기준 N시간 이내 ApproveDate 만 포함. API 제약상 ≤72.
        minister_filter: MinisterCode 일치 항목만 필터. None 이면 전체 부처.
                         기본값 "국토교통부" 는 v1 dept_molit 정합.
        timeout_sec: HTTP timeout (T15).
        now: 테스트 주입용. None 이면 datetime.now(timezone.utc).
        _xml_text: 테스트 주입용. 주어지면 HTTP 호출 skip 후 그대로 파싱.

    Returns:
        List[dict]. 실패/빈 응답 시 [] 반환 (T1 — fabricate 금지).
    """
    # API 제약 가드 — 72h 초과 호출은 명시 에러 (T9)
    if lookback_hours > 72 and _xml_text is None:
        logger.error(
            "policy_collector: lookback_hours=%d > 72 violates API 3-day limit. "
            "Capping at 72h.", lookback_hours,
        )
        lookback_hours = 72

    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = now_utc - timedelta(hours=lookback_hours)

    # ① fetch
    if _xml_text is not None:
        xml_text = _xml_text
    else:
        key = _service_key()
        if not key:
            logger.error(
                "policy_collector: PUBLIC_DATA_API_KEY missing. "
                "logged=True (silent skip 금지 — feedback_data_collection_verification_mandatory)",
            )
            return []

        # API 는 KST date 기준 (정책브리핑 운영기관). startDate/endDate KST 로 환산.
        now_kst = now_utc.astimezone(KST)
        start_kst = (now_utc - timedelta(hours=lookback_hours)).astimezone(KST)
        params = {
            "serviceKey": key,
            "startDate": start_kst.strftime("%Y%m%d"),
            "endDate": now_kst.strftime("%Y%m%d"),
            "numOfRows": DEFAULT_NUM_OF_ROWS,
            "pageNo": 1,
        }
        try:
            res = requests.get(API_BASE, params=params, timeout=timeout_sec)
        except requests.RequestException as e:
            logger.error("policy_collector: HTTP error %s for %s", e, API_BASE)
            return []

        if res.status_code != 200:
            logger.error(
                "policy_collector: non-200 %d from %s",
                res.status_code, API_BASE,
            )
            return []
        xml_text = res.text

    # ② parse + result code 검증
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.error("policy_collector: XML parse error: %s", e)
        return []

    header = root.find("header")
    if header is not None:
        result_code = (header.findtext("resultCode") or "").strip()
        result_msg = (header.findtext("resultMsg") or "").strip()
        if result_code and result_code != "0":
            logger.error(
                "policy_collector: API resultCode=%s msg=%s",
                result_code, result_msg,
            )
            return []

    body = root.find("body")
    if body is None:
        logger.error("policy_collector: missing <body> in response")
        return []

    items = body.findall("NewsItem")
    if not items:
        logger.info("policy_collector: 0 NewsItem in response")
        return []

    # ③ filter by minister + lookback + normalize
    out: List[Dict[str, Any]] = []
    for item in items:
        try:
            policy, pub_dt = _parse_item(item)
        except Exception as e:
            logger.error("policy_collector: item parse failed: %s", e)
            continue

        if minister_filter is not None and policy["source_name"] != minister_filter:
            continue
        if pub_dt is None:
            continue
        if pub_dt < cutoff:
            continue
        out.append(policy)

    return out


def _parse_item(item: ET.Element) -> Tuple[Dict[str, Any], Optional[datetime]]:
    """단일 <NewsItem> 을 표준 dict + datetime 으로 분해. 내부 helper."""
    item_id = (item.findtext("NewsItemId") or "").strip()
    title = (item.findtext("Title") or "").strip()
    source_url = (item.findtext("OriginalUrl") or "").strip()
    minister = (item.findtext("MinisterCode") or "").strip()

    contents_raw = item.findtext("DataContents") or ""
    raw_text = BeautifulSoup(contents_raw, "html.parser").get_text(
        separator=" ", strip=True
    )

    # ApproveDate 포맷: "MM/DD/YYYY HH:MM:SS" KST (정책브리핑 운영기관 기준)
    pub_dt: Optional[datetime] = None
    approve_date_str = (item.findtext("ApproveDate") or "").strip()
    if approve_date_str:
        try:
            naive = datetime.strptime(approve_date_str, "%m/%d/%Y %H:%M:%S")
            pub_dt = naive.replace(tzinfo=KST).astimezone(timezone.utc)
        except (TypeError, ValueError) as e:
            logger.error(
                "policy_collector: ApproveDate parse failed (%r): %s",
                approve_date_str, e,
            )

    # 폴백 ID — NewsItemId 가 비어있으면 source_url 해시
    if not item_id:
        import hashlib
        seed = source_url or (title + approve_date_str)
        item_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()

    return {
        "id": item_id,
        "title": title,
        "source_url": source_url,
        "source_name": minister,  # MinisterCode 가 곧 부처명 (예: "국토교통부")
        "published_at": pub_dt.isoformat() if pub_dt else None,
        "raw_text": raw_text,
    }, pub_dt
