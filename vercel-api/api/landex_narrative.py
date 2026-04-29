"""
GET /api/landex/narrative?gu=강남구&month=2026-04&preset=balanced

ScoreDetailPanel 의 강점/약점 문장 — 5요소 점수 + 25구 평균 대비 차이로
룰 기반 자동 생성. AI 호출 없음 (지연·비용 회피).

응답:
{
  "version": "1.0", "month": "2026-04", "preset": "balanced", "gu": "강남구",
  "strengths": ["입지 인프라 최상위 — 25구 평균 대비 +44점", ...],
  "weaknesses": ["가치 평가 약점 — 평균 대비 -22점 (이미 비싸 저평가 메리트 약함)", ...],
  "source": "snapshot" | "snapshot+mock" | "mock"
}
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import re
from urllib.parse import parse_qs, urlparse

import requests

from api.landex._methodology import VERSION, WEIGHT_PRESETS

_logger = logging.getLogger(__name__)

SEOUL_25_GU = [
    "강남구", "서초구", "송파구", "강동구", "마포구",
    "용산구", "성동구", "광진구", "중구", "종로구",
    "서대문구", "은평구", "강서구", "양천구", "영등포구",
    "구로구", "금천구", "관악구", "동작구", "성북구",
    "동대문구", "중랑구", "노원구", "도봉구", "강북구",
]

_GU_RE = re.compile(r"^[가-힣]{2,8}구$")
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

# 5요소 → 강점/약점 문구 템플릿
# (axis, label, strength_template, weakness_template, threshold)
NARRATIVE_RULES = [
    {
        "key": "v_score", "name": "V 가치",
        "strong": "가치 평가 양호 — 25구 평균 대비 +{diff:.0f}점 (저평가 메리트 큼)",
        "weak":   "가치 평가 약점 — 평균 대비 {diff:.0f}점 (이미 비싸 저평가 메리트 약함)",
    },
    {
        "key": "d_score", "name": "D 개발호재",
        "strong": "개발 모멘텀 강세 — 가격 가속도 +{diff:.0f}점 (호재 반영 진행 중)",
        "weak":   "개발 모멘텀 둔화 — 가속도 {diff:.0f}점 (감속·하락 추세)",
    },
    {
        "key": "s_score", "name": "S 수급",
        "strong": "수급 양호 — 미분양 적고 +{diff:.0f}점 우위",
        "weak":   "수급 부담 — 미분양 적체 신호 {diff:.0f}점",
    },
    {
        "key": "c_score", "name": "C 입지",
        "strong": "입지 인프라 최상위 — 평균 대비 +{diff:.0f}점 (지하철 접근성·승하차)",
        "weak":   "입지 인프라 약점 — 평균 대비 {diff:.0f}점 (역 수·승하차 적음)",
    },
    {
        "key": "r_score", "name": "R 리스크",
        "strong": "리스크 우호 (거시) — 기준금리 환경 안정",
        "weak":   "리스크 부담 (거시) — 금리 인상 압력",
    },
]


def _fetch_all_25(month: str, preset: str) -> list[dict] | None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not anon:
        return None
    params = {
        "select": "gu,v_score,d_score,s_score,c_score,r_score,landex,tier10",
        "month": f"eq.{month}",
        "preset": f"eq.{preset}",
        "methodology_version": f"eq.{VERSION}",
    }
    headers = {"apikey": anon, "Authorization": f"Bearer {anon}"}
    try:
        r = requests.get(f"{url}/rest/v1/estate_landex_snapshots",
                         headers=headers, params=params, timeout=5)
        r.raise_for_status()
        rows = r.json()
        return rows or None
    except Exception as e:
        _logger.warning("snapshot fetch 실패: %s", e)
        return None


def _build_narrative(target: dict, all_rows: list[dict]) -> tuple[list[str], list[str]]:
    """target row + 25구 row → 강점/약점 문구.

    각 축의 (점수 - 평균) 차이로 강·약 분류:
      diff >= +10  : strength
      diff <= -10  : weakness
      그 외 : skip (보통 수준)

    R 은 모든 구 동일 (거시 지표) — 평균 대비 차이가 0 이라 분기 불가능.
    대신 절대 점수로: ≥ 60 → strong, ≤ 40 → weak.
    """
    strengths: list[str] = []
    weaknesses: list[str] = []

    avgs: dict[str, float] = {}
    for rule in NARRATIVE_RULES:
        vals = [r.get(rule["key"]) for r in all_rows if r.get(rule["key"]) is not None]
        if vals:
            avgs[rule["key"]] = sum(vals) / len(vals)

    for rule in NARRATIVE_RULES:
        key = rule["key"]
        val = target.get(key)
        if val is None:
            continue

        if key == "r_score":
            # 거시 지표 — 절대값 기준
            if val >= 60:
                strengths.append(rule["strong"])
            elif val <= 40:
                weaknesses.append(rule["weak"])
            continue

        avg = avgs.get(key)
        if avg is None:
            continue
        diff = val - avg
        if diff >= 10:
            strengths.append(rule["strong"].format(diff=diff))
        elif diff <= -10:
            weaknesses.append(rule["weak"].format(diff=diff))
        # |diff| < 10 — 평범, 문구 생성 안 함

    # 강점·약점 모두 비어있으면 (모든 축이 평균에 근접) — 일반적 문구 1개
    if not strengths and not weaknesses:
        landex = target.get("landex")
        if landex is not None:
            if landex >= 60:
                strengths.append("LANDEX 종합 양호 — 5요소 균형 잡혀 안정적 입지")
            elif landex <= 40:
                weaknesses.append("LANDEX 종합 약세 — 다수 요소가 평균 이하로 분산")
            else:
                strengths.append("LANDEX 평균권 — 두드러진 강·약 없음 (수익률 시장 추종)")

    return strengths, weaknesses


def _mock_narrative(gu: str) -> tuple[list[str], list[str]]:
    """결정적 mock — 데이터 없을 때만."""
    seed = sum(ord(c) for c in gu)
    pool_strong = [
        "교통 인프라 양호 — 환승역 접근성 평균 이상",
        "수급 안정 — 미분양 누적 낮음",
        "재건축 진행 단지 분포",
        "직주근접 우위",
    ]
    pool_weak = [
        "신규 공급 절벽 가능성",
        "고금리 직접 노출",
        "정책 리스크 노출",
        "가격 모멘텀 둔화",
    ]
    return (
        [pool_strong[seed % len(pool_strong)]],
        [pool_weak[(seed * 7) % len(pool_weak)]],
    )


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        gu = params.get("gu", [""])[0].strip()
        month = params.get("month", ["2026-04"])[0].strip()
        preset = params.get("preset", ["balanced"])[0].strip().lower()

        if not _GU_RE.match(gu) or gu not in SEOUL_25_GU:
            self._err(400, "invalid_gu", "gu=서울 25구 중 하나 필요")
            return
        if not _MONTH_RE.match(month):
            self._err(400, "invalid_month", "month=YYYY-MM 형식")
            return
        if preset not in WEIGHT_PRESETS:
            preset = "balanced"

        rows = _fetch_all_25(month, preset)
        if rows:
            target = next((r for r in rows if r.get("gu") == gu), None)
            if target:
                strengths, weaknesses = _build_narrative(target, rows)
                source = "snapshot"
            else:
                strengths, weaknesses = _mock_narrative(gu)
                source = "snapshot+mock"
        else:
            strengths, weaknesses = _mock_narrative(gu)
            source = "mock"

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=600")
        self.end_headers()
        body = json.dumps({
            "version": VERSION,
            "month": month, "preset": preset, "gu": gu,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "source": source,
        }, ensure_ascii=False).encode("utf-8")
        self.wfile.write(body)

    def _err(self, status: int, code: str, message: str):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"error": code, "message": message}).encode("utf-8"))
