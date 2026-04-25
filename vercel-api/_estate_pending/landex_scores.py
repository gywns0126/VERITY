"""
GET /api/landex/scores?gu=강남구&month=2026-04&preset=balanced
GET /api/landex/scores?month=2026-04                       (전체 25구)

응답:
{
  "version": "1.0",
  "month": "2026-04",
  "preset": "balanced",
  "data": [
    {
      "gu": "강남구",
      "v": 82, "d": 65, "s": 58, "c": 92, "r": 18,
      "landex": 73.4,
      "tier10": "A",  "tier5": "WARM",
      "gei": 68, "gei_stage": 3,
      "trend": { "landex": "up", "volume": "down" },
      "divergences": [...],
      "low_liquidity": false,
      "missing_factors": 0
    }, ...
  ]
}

v1: 결정적 mock (실제 API 키·데이터 파이프라인 연결 전).
실 데이터 연결 시 _generate_mock_scores() → fetch_real_scores() 교체.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
import logging
import math
import os
import re
from urllib.parse import parse_qs, urlparse

import requests

from api.landex._methodology import VERSION, WEIGHT_PRESETS
from api.landex._compute import compute_landex, score_to_tier10, tier10_to_tier5, detect_divergence

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


def _seeded_rand(seed_str: str, idx: int) -> float:
    """결정적 의사 난수 — 같은 (seed, idx) → 같은 값. 0~1 범위."""
    s = sum(ord(c) for c in seed_str) + idx * 137
    x = math.sin(s * 12.9898) * 43758.5453
    return abs(x - math.floor(x))


def _fetch_snapshot_rows(gus: list[str], month: str, preset: str) -> list[dict] | None:
    """estate_landex_snapshots 테이블에서 행 조회 (anon 키로 SELECT 가능 — RLS 공개 정책).

    Returns: 행 리스트 or None (테이블 비었거나 Supabase 미설정).
    """
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not anon:
        return None

    gu_filter = ",".join(f'"{g}"' for g in gus)
    params = {
        "select": "gu,v_score,d_score,s_score,c_score,r_score,landex,tier10,gei,gei_stage,raw_payload,methodology_version",
        "month": f"eq.{month}",
        "preset": f"eq.{preset}",
        "methodology_version": f"eq.{VERSION}",
        "gu": f"in.({gu_filter})",
    }
    headers = {"apikey": anon, "Authorization": f"Bearer {anon}"}
    try:
        r = requests.get(f"{url}/rest/v1/estate_landex_snapshots",
                         headers=headers, params=params, timeout=5)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return None
        return rows
    except Exception as e:
        _logger.warning("snapshot fetch 실패: %s", e)
        return None


def _snapshot_to_response(snap_row: dict) -> dict:
    """Supabase row → API 응답 형식 (mock 응답과 동일 스키마)."""
    landex = snap_row.get("landex")
    tier10_code = snap_row.get("tier10")
    tier10_obj = score_to_tier10(landex) if landex is not None else None

    # 다이버전스 — 실시간 산출 (snapshot 에는 trend 없음, v1.5 에서 trend 컬럼 추가 시 활용)
    divergences = []
    return {
        "gu": snap_row.get("gu"),
        "v": snap_row.get("v_score"),
        "d": snap_row.get("d_score"),
        "s": snap_row.get("s_score"),
        "c": snap_row.get("c_score"),
        "r": snap_row.get("r_score"),
        "landex": landex,
        "tier10": tier10_code,
        "tier5": tier10_to_tier5(tier10_code),
        "tier_status": tier10_obj["status"] if tier10_obj else None,
        "gei": snap_row.get("gei"),
        "gei_stage": snap_row.get("gei_stage"),
        "trend": {"landex": "flat", "volume": "flat"},  # v1.5 에서 시계열 비교로 산출
        "divergences": divergences,
        "low_liquidity": False,
        "missing_factors": (snap_row.get("raw_payload") or {}).get("missing_factors", 0),
        "source": "snapshot",
    }


def _generate_mock_scores(gus, month, preset):
    """결정적 mock — 실 데이터 연결 전. 같은 month → 같은 결과."""
    out = []
    for i, gu in enumerate(gus):
        seed = f"{gu}-{month}"
        # V/D/S/C 는 정상 범위, R 은 inverted 후 점수 (낮을수록 좋음 → 점수 높음)
        v_raw = 40 + _seeded_rand(seed, 1) * 60
        d_raw = 40 + _seeded_rand(seed, 2) * 60
        s_raw = 40 + _seeded_rand(seed, 3) * 60
        c_raw = 40 + _seeded_rand(seed, 4) * 60
        r_raw_risk = _seeded_rand(seed, 5) * 100  # 0=무위험, 100=고위험
        r_score = 100 - r_raw_risk  # inverted

        scores = {"V": round(v_raw, 1), "D": round(d_raw, 1), "S": round(s_raw, 1),
                  "C": round(c_raw, 1), "R": round(r_score, 1)}
        landex, missing = compute_landex(scores, preset=preset)

        gei = round(_seeded_rand(seed, 6) * 100, 1)
        gei_stage = 4 if gei >= 80 else 3 if gei >= 60 else 2 if gei >= 40 else 1 if gei >= 20 else 0

        # 추세 (mock — 인접 시점 비교 대신 결정적 룰)
        landex_trend = "up" if _seeded_rand(seed, 7) > 0.4 else "down" if _seeded_rand(seed, 7) < 0.2 else "flat"
        volume_trend = "up" if _seeded_rand(seed, 8) > 0.5 else "down" if _seeded_rand(seed, 8) < 0.25 else "flat"

        divergences = detect_divergence(landex_trend, gei_stage, volume_trend)
        tier10_obj = score_to_tier10(landex)
        tier10_code = tier10_obj["code"] if tier10_obj else None
        tier5 = tier10_to_tier5(tier10_code)

        out.append({
            "gu": gu,
            "v": scores["V"], "d": scores["D"], "s": scores["S"], "c": scores["C"], "r": scores["R"],
            "landex": landex,
            "tier10": tier10_code,
            "tier5": tier5,
            "tier_status": tier10_obj["status"] if tier10_obj else None,
            "gei": gei,
            "gei_stage": gei_stage,
            "trend": {"landex": landex_trend, "volume": volume_trend},
            "divergences": divergences,
            "low_liquidity": _seeded_rand(seed, 9) < 0.1,
            "missing_factors": missing,
        })
    return out


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        gu_param = params.get("gu", [""])[0].strip()
        month = params.get("month", ["2026-04"])[0].strip()
        preset = params.get("preset", ["balanced"])[0].strip().lower()

        if not _MONTH_RE.match(month):
            self._err(400, "invalid_month_format", "month=YYYY-MM 필수")
            return
        if preset not in WEIGHT_PRESETS:
            preset = "balanced"

        if gu_param:
            if not _GU_RE.match(gu_param) or gu_param not in SEOUL_25_GU:
                self._err(400, "invalid_gu", "서울 25구 한자 이름 필요")
                return
            gus = [gu_param]
        else:
            gus = SEOUL_25_GU

        # 1순위: Supabase snapshots 조회 (cron 워커가 미리 채워둠)
        source = "snapshot"
        snap_rows = _fetch_snapshot_rows(gus, month, preset)
        if snap_rows:
            data = [_snapshot_to_response(r) for r in snap_rows]
            # 누락된 구는 mock 으로 보완
            present = {d["gu"] for d in data}
            missing = [g for g in gus if g not in present]
            if missing:
                data.extend(_generate_mock_scores(missing, month, preset))
                source = "snapshot+mock"
        else:
            # 2순위: 결정적 mock (snapshot 없을 때 그래도 디자인·시연 가능)
            data = _generate_mock_scores(gus, month, preset)
            source = "mock"

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        # snapshot 은 매월 1회 갱신, mock 은 결정적 → 둘 다 길게 캐시
        self.send_header("Cache-Control", "public, max-age=600")
        self.end_headers()
        body = json.dumps({
            "version": VERSION,
            "month": month,
            "preset": preset,
            "source": source,  # snapshot | mock | snapshot+mock
            "data": data,
        }, ensure_ascii=False).encode("utf-8")
        self.wfile.write(body)

    def _err(self, status: int, code: str, message: str):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"error": code, "message": message}).encode("utf-8"))
