"""
policy_collector.py — ESTATE HeroBriefing 정책 수집 레이어 (P2 Step 1.2)

정책브리핑(korea.kr) 부처별 RSS 통합 feed 를 호출해서 표준 dict 배열로 정규화한다.
이 모듈은 "수집"만 한다. 부동산 관련도 prefilter (rough_relevance_filter) 는
api/analyzers/policy_keywords.py 의 책임. 카테고리/Stage/affected_regions 분류는
api/analyzers/policy_classifier.py 의 책임. 단일 책임 원칙.

Primary feed:
    https://www.korea.kr/rss/dept_<dept>.xml
    - dept_molit.xml = 국토교통부 (HeroBriefing 기본)
    - dept_moef / dept_fsc 등은 feed_url + source_name 만 바꿔 동일 함수 재사용

거짓말 트랩 컴플라이언스:
    T1  fabricate 금지   — 5xx/네트워크/파싱 실패 시 전부 빈 배열만 반환
    T9  silent 실패 X    — 모든 실패 logging.error + 빈 배열
    T11 URL 가정 X       — feed_url default 는 korea.kr 안내 페이지에 노출된 실제 URL
    T12 User-Agent 강제  — 정부 사이트 default UA 차단 우회
    T15 timeout=10s, retry=0 (cron 자체가 자연 retry — 작업 정의서 명시)
"""
from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENT = "VERITY-ESTATE/1.0 (+https://github.com/gywns0126/VERITY)"
DEFAULT_FEED_URL = "https://www.korea.kr/rss/dept_molit.xml"
DEFAULT_SOURCE_NAME = "국토교통부"
DEFAULT_TIMEOUT_SEC = 10
# 결정 2 (P2 사용자 보강 2026-05-02): default 24 → 72.
# 사유: 24h 정책 평균 0~1건 (Step 1.2 실증). 빌더 폴백 사다리 (24h → 72h → LANDEX) 1차 윈도우.
DEFAULT_LOOKBACK_HOURS = 72

# Dublin Core 네임스페이스 (dc:date 폴백 파싱용)
DC_NS = "http://purl.org/dc/elements/1.1/"


def collect_policies(
    feed_url: str = DEFAULT_FEED_URL,
    source_name: str = DEFAULT_SOURCE_NAME,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    user_agent: str = USER_AGENT,
    now: Optional[datetime] = None,
    _xml_text: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    부처별 RSS feed 에서 lookback 윈도우 내 정책 dict 배열을 반환한다.

    Args:
        feed_url:      RSS XML URL (korea.kr 부처별 feed 또는 동일 스키마)
        source_name:   응답 dict 의 source_name 필드 (예: "국토교통부")
        lookback_hours: 현재 시각 기준 N시간 이내 published 만 포함 (기본 24h)
        timeout_sec:   HTTP timeout (T15 — 기본 10s)
        user_agent:    T12 — 정부 사이트 차단 우회용 UA
        now:           테스트 주입용. None 이면 datetime.now(timezone.utc)
        _xml_text:     테스트 주입용. 주어지면 HTTP 호출 skip 후 그대로 파싱

    Returns:
        List[dict]. 각 dict 필드:
            id           guid 텍스트, 없으면 link 의 SHA1 해시
            title        CDATA 추출 후 strip
            source_url   link 의 절대 URL
            source_name  인자 그대로 (예: "국토교통부")
            published_at ISO 8601 (timezone-aware UTC)
            raw_text     description 의 HTML 제거된 평문

        실패/빈 응답 시 [] 반환 (T1 — 가짜 정책 fabricate 금지).
    """
    # ① fetch
    if _xml_text is not None:
        xml_text = _xml_text
    else:
        try:
            res = requests.get(
                feed_url,
                headers={"User-Agent": user_agent},
                timeout=timeout_sec,
            )
        except requests.RequestException as e:
            logger.error("policy_collector: HTTP error %s for %s", e, feed_url)
            return []

        if res.status_code >= 500:
            logger.error(
                "policy_collector: server error %d from %s",
                res.status_code, feed_url,
            )
            return []
        if res.status_code != 200:
            logger.error(
                "policy_collector: non-200 %d from %s",
                res.status_code, feed_url,
            )
            return []
        xml_text = res.text

    # ② parse
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.error("policy_collector: XML parse error: %s", e)
        return []

    channel = root.find("channel")
    if channel is None:
        logger.error("policy_collector: missing <channel> in feed")
        return []

    items = channel.findall("item")
    if not items:
        logger.info("policy_collector: 0 items in feed (empty channel)")
        return []

    # ③ filter by lookback + normalize
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(hours=lookback_hours)

    out: List[Dict[str, Any]] = []
    for item in items:
        try:
            policy, pub_dt = _parse_item(item, source_name)
        except Exception as e:
            # 단일 item 파싱 실패는 전체 fail 시키지 않음. 명시적 로그 (T9).
            logger.error("policy_collector: item parse failed: %s", e)
            continue

        if pub_dt is None:
            # published_at 미상은 lookback 비교 불가 → 제외
            continue
        if pub_dt < cutoff:
            continue
        out.append(policy)

    return out


def _parse_item(item: ET.Element, source_name: str):
    """단일 <item> 을 표준 dict + datetime 으로 분해. 내부 helper."""
    title = (item.findtext("title") or "").strip()
    link = (item.findtext("link") or "").strip()

    description_raw = item.findtext("description") or ""
    raw_text = BeautifulSoup(description_raw, "html.parser").get_text(
        separator=" ", strip=True
    )

    pub_dt: Optional[datetime] = None
    pub_date_str = (item.findtext("pubDate") or "").strip()
    if pub_date_str:
        try:
            pub_dt = parsedate_to_datetime(pub_date_str)
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            else:
                pub_dt = pub_dt.astimezone(timezone.utc)
        except (TypeError, ValueError) as e:
            logger.error("policy_collector: pubDate parse failed (%r): %s", pub_date_str, e)

    # 폴백: dc:date (ISO 8601)
    if pub_dt is None:
        dc_date = item.findtext(f"{{{DC_NS}}}date")
        if dc_date:
            try:
                pub_dt = datetime.fromisoformat(dc_date.replace("Z", "+00:00"))
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                else:
                    pub_dt = pub_dt.astimezone(timezone.utc)
            except (TypeError, ValueError) as e:
                logger.error("policy_collector: dc:date parse failed (%r): %s", dc_date, e)

    guid = (item.findtext("guid") or "").strip()
    if guid:
        item_id = guid
    elif link:
        item_id = hashlib.sha1(link.encode("utf-8")).hexdigest()
    else:
        seed = title + (pub_date_str or "")
        item_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()

    return {
        "id": item_id,
        "title": title,
        "source_url": link,
        "source_name": source_name,
        "published_at": pub_dt.isoformat() if pub_dt else None,
        "raw_text": raw_text,
    }, pub_dt
