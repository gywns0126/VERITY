"""
GET /api/landex/features?gu=강남구&month=2026-04&preset=balanced

ScoreDetailPanel 의 FeatureContribBar 용 — 5요소 기여도.
기여도 = 해당 구의 (요소점수 - 25구평균) — 양수면 강점, 음수면 약점.
R 은 inverted 후 점수라 그대로 사용 (높을수록 안전).

응답:
{
  "version": "1.0",
  "month": "2026-04",
  "preset": "balanced",
  "gu": "강남구",
  "features": [
    { "label": "V 가치", "value": -22.0 },
    { "label": "D 개발호재", "value": +28.0 },
    { "label": "S 수급", "value": +14.0 },
    { "label": "C 입지", "value": +44.0 },
    { "label": "R 리스크", "value": +0.0 }   // 모든 구 동일 → 0
  ],
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


def _fetch_all_25(month: str, preset: str) -> list[dict] | None:
    """estate_landex_snapshots 에서 25구 행을 한 번에 받음 (anon 키)."""
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


def _avg(rows: list[dict], key: str) -> float | None:
    vals = [r.get(key) for r in rows if r.get(key) is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _compute_features(target_row: dict, all_rows: list[dict]) -> list[dict]:
    """단일 구의 5요소 기여도 = 점수 - 25구평균."""
    out: list[dict] = []
    label_map = [
        ("v_score", "V 가치"),
        ("d_score", "D 개발호재"),
        ("s_score", "S 수급"),
        ("c_score", "C 입지"),
        ("r_score", "R 리스크"),
    ]
    for key, label in label_map:
        avg = _avg(all_rows, key)
        val = target_row.get(key)
        if avg is None or val is None:
            out.append({"label": label, "value": 0.0})
        else:
            out.append({"label": label, "value": round(val - avg, 1)})
    return out


def _mock_features(gu: str) -> list[dict]:
    """결정적 mock — 같은 구 → 같은 결과."""
    seed = sum(ord(c) for c in gu)
    base = [(seed * 17) % 50, (seed * 23) % 50, (seed * 31) % 50, (seed * 37) % 50, (seed * 41) % 30]
    signs = [+1, +1, +1, +1, -1] if seed % 2 == 0 else [-1, +1, -1, +1, +1]
    labels = ["V 가치", "D 개발호재", "S 수급", "C 입지", "R 리스크"]
    return [{"label": l, "value": float(s * v)} for l, s, v in zip(labels, signs, base)]


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
                features = _compute_features(target, rows)
                source = "snapshot"
            else:
                features = _mock_features(gu)
                source = "snapshot+mock"
        else:
            features = _mock_features(gu)
            source = "mock"

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=600")
        self.end_headers()
        body = json.dumps({
            "version": VERSION,
            "month": month, "preset": preset, "gu": gu,
            "features": features,
            "source": source,
        }, ensure_ascii=False).encode("utf-8")
        self.wfile.write(body)

    def _err(self, status: int, code: str, message: str):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"error": code, "message": message}).encode("utf-8"))
