"""
GET /api/estate/change-feed — Page 1 ChangeFeed broadcast feed (P1 Mock)

estate/docs/contract_change_feed.md (v0.2 — 2 카테고리 축소). anonymous endpoint.

P1 단계 — mock 응답만. P2 wire 시:
    - regulation = policy_collector.collect_policies(minister_filter='국토교통부')
    - catalyst   = policy_collector + policy_keywords + policy_classifier 의 catalyst 분류

Query parameters:
    scenario   = "live" (default) | "empty" | "error"  ← P1 Mock toggle
    categories = comma-sep "regulation,catalyst" (v0.2 = 2 카테고리만)
    hours      = lookback (default 72)

응답 schema = contract_change_feed.md §2 Response schema.

거짓말 트랩:
    T1  fabricate 금지   — items 빈 배열 fallback
    T9  silent 실패 X    — error scenario 명시
    T18 카운트 정합      — category_counts 합 = total
    T29 source URL 절대  — production domain only (mock 도 정합)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

KST = timezone(timedelta(hours=9))

VALID_CATEGORIES = ("regulation", "catalyst")  # v0.2 — gei/anomaly 폐기


def _mock_live_items(now: datetime) -> list[dict]:
    """live 시나리오 — 7건 (regulation 5 + catalyst 2). 시간 역순."""
    return [
        {
            "id": "alert_mock_001",
            "category": "regulation",
            "severity": "high",
            "region_label": "서울 강남구",
            "title": "재건축 안전진단 기준 완화 검토",
            "summary": "국토교통부, D등급 단지도 재건축 가능하도록 안전진단 기준 개정안 마련 중",
            "occurred_at": (now - timedelta(hours=2)).isoformat(timespec="seconds"),
            "source_name": "국토교통부",
            "source_url": "https://www.korea.kr/briefing/pressReleaseView.do?newsId=156759801",
            "drill_down_url": None,
        },
        {
            "id": "alert_mock_002",
            "category": "catalyst",
            "severity": "mid",
            "region_label": "서울 강동구",
            "title": "지하철 9호선 4단계 연장 착공 확정",
            "summary": "둔촌동~보훈병원 5.4km 구간, 2026년 하반기 착공 — 강동구 7개 역 영향권",
            "occurred_at": (now - timedelta(hours=5)).isoformat(timespec="seconds"),
            "source_name": "국토교통부",
            "source_url": "https://www.korea.kr/briefing/pressReleaseView.do?newsId=156759802",
            "drill_down_url": None,
        },
        {
            "id": "alert_mock_003",
            "category": "regulation",
            "severity": "mid",
            "region_label": "전국",
            "title": "DSR 규제 산정 방식 정비",
            "summary": "주담대 한도 산정 시 신용대출 합산 룰 명확화. 7월 시행",
            "occurred_at": (now - timedelta(hours=11)).isoformat(timespec="seconds"),
            "source_name": "금융위원회",
            "source_url": "https://www.korea.kr/briefing/pressReleaseView.do?newsId=156759803",
            "drill_down_url": None,
        },
        {
            "id": "alert_mock_004",
            "category": "regulation",
            "severity": "low",
            "region_label": "서울 송파구",
            "title": "투기과열지구 해제 검토",
            "summary": "송파구 일부 동(가락·문정) 투기과열지구 해제 의견 수렴 중",
            "occurred_at": (now - timedelta(hours=18)).isoformat(timespec="seconds"),
            "source_name": "국토교통부",
            "source_url": "https://www.korea.kr/briefing/pressReleaseView.do?newsId=156759804",
            "drill_down_url": None,
        },
        {
            "id": "alert_mock_005",
            "category": "catalyst",
            "severity": "high",
            "region_label": "경기 성남시",
            "title": "성남 분당 1기 신도시 재정비 마스터플랜 발표",
            "summary": "분당 326개 단지 대상 용적률 상향(평균 273%)·기반시설 확충 로드맵 공개",
            "occurred_at": (now - timedelta(hours=26)).isoformat(timespec="seconds"),
            "source_name": "국토교통부",
            "source_url": "https://www.korea.kr/briefing/pressReleaseView.do?newsId=156759805",
            "drill_down_url": None,
        },
        {
            "id": "alert_mock_006",
            "category": "regulation",
            "severity": "low",
            "region_label": "전국",
            "title": "양도세 비과세 보유기간 산정 기준 명확화",
            "summary": "2주택 → 1주택 전환 시 비과세 적용 기산일 행정해석 변경",
            "occurred_at": (now - timedelta(hours=40)).isoformat(timespec="seconds"),
            "source_name": "기획재정부",
            "source_url": "https://www.korea.kr/briefing/pressReleaseView.do?newsId=156759806",
            "drill_down_url": None,
        },
        {
            "id": "alert_mock_007",
            "category": "regulation",
            "severity": "low",
            "region_label": "전국",
            "title": "공공임대주택 청약자격 통합기준 시행",
            "summary": "행복주택·국민임대 등 통합 자격 기준 도입. 6월 1일 시행",
            "occurred_at": (now - timedelta(hours=60)).isoformat(timespec="seconds"),
            "source_name": "국토교통부",
            "source_url": "https://www.korea.kr/briefing/pressReleaseView.do?newsId=156759807",
            "drill_down_url": None,
        },
    ]


def _build_payload(scenario: str, categories_filter: list[str], hours: int, now: datetime) -> dict:
    """payload 빌드 — scenario 분기. T1·T9·T18·T29 정합."""
    base = {
        "schema_version": "1.0",
        "fetched_at": now.isoformat(timespec="seconds"),
        "namespace": "estate",
        "scenario": scenario,
        "lookback_hours": hours,
    }

    if scenario == "error":
        return {
            **base,
            "error": "변동 피드 일시 불가 (mock error scenario)",
            "items": [],
            "category_counts": {},
            "total": 0,
        }

    if scenario == "empty":
        return {
            **base,
            "items": [],
            "category_counts": {c: 0 for c in VALID_CATEGORIES},
            "total": 0,
        }

    # live (default)
    items = _mock_live_items(now)

    # category filter
    if categories_filter:
        items = [it for it in items if it["category"] in categories_filter]

    # lookback filter (occurred_at 기반)
    cutoff = now - timedelta(hours=hours)
    items = [it for it in items if datetime.fromisoformat(it["occurred_at"]) >= cutoff]

    # category_counts (T18 — 합 = total)
    counts = {c: 0 for c in VALID_CATEGORIES}
    for it in items:
        cat = it["category"]
        if cat in counts:
            counts[cat] += 1

    return {
        **base,
        "items": items,
        "category_counts": counts,
        "total": len(items),
    }


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)

        scenario = (params.get("scenario", ["live"])[0] or "live").strip().lower()
        if scenario not in ("live", "empty", "error"):
            scenario = "live"

        cats_raw = (params.get("categories", [""])[0] or "").strip()
        categories_filter = [
            c.strip() for c in cats_raw.split(",")
            if c.strip() in VALID_CATEGORIES
        ] if cats_raw else []

        try:
            hours = int(params.get("hours", ["72"])[0])
            hours = max(1, min(hours, 168))  # 1h ~ 7d 가드
        except (ValueError, TypeError):
            hours = 72

        now = datetime.now(KST)
        payload = _build_payload(scenario, categories_filter, hours, now)

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=60")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
