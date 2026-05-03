"""
GET /api/estate/landex-pulse — ESTATE 25구 LANDEX overview + drill-down (P1 Mock)

contract_landex_pulse.md (P0 명세) 기반. P1 단계 — mock 응답만.
P2 wire 시 estate_landex_snapshots 테이블 + features/narrative endpoint 통합 (별도 phase).

Query parameters:
    scenario = "normal" (default) | "regime_shift"
        normal       — 등급 변화 0~1개 (cry wolf 방지, REGIME_SHIFT_THRESHOLD=3 미만)
        regime_shift — 등급 변화 5개 이상

응답 schema (contract_landex_pulse.md §2):
    { schema_version, generated_at, trigger, meta: {primary, detail}, gus: [25] }

거짓말 트랩:
    T2 정합 — mock 응답 source 명시 (scenario 필드)
    T29 정합 — endpoint 자체 production domain only
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

KST = timezone(timedelta(hours=9))

# 25구 — LandexMapDashboard SEOUL_25_GU 정합 (지리적 순서: 동남→서북)
SEOUL_25_GU = [
    "강동구", "송파구", "강남구", "서초구", "관악구",
    "동작구", "영등포구", "금천구", "구로구", "강서구",
    "양천구", "마포구", "서대문구", "은평구", "노원구",
    "도봉구", "강북구", "성북구", "중랑구", "동대문구",
    "광진구", "성동구", "용산구", "중구", "종로구",
]


def _seeded(seed_str: str, idx: int) -> float:
    """결정적 의사 난수 (0~1) — 같은 (seed, idx) → 같은 값."""
    s = sum(ord(c) for c in seed_str) + idx * 137
    x = math.sin(s * 12.9898) * 43758.5453
    return abs(x - math.floor(x))


def _grade_from_landex(landex: float) -> str:
    """등급 임계 — LandexMapDashboard 정합."""
    if landex >= 80: return "HOT"
    if landex >= 65: return "WARM"
    if landex >= 50: return "NEUT"
    if landex >= 35: return "COOL"
    return "AVOID"


def _stage_from_gei(gei: float) -> int:
    """Stage 임계 — LandexMapDashboard 정합."""
    if gei >= 80: return 4
    if gei >= 60: return 3
    if gei >= 40: return 2
    if gei >= 20: return 1
    return 0


def _gen_gu(gu: str, scenario: str, idx: int, now: datetime) -> dict:
    """단일 구 mock — landex/gei/5축/catalyst + detail (radar/features/timeseries)."""
    seed = f"{gu}-{scenario}-2026-05"
    # landex 분포: normal 은 정규 분포 ~ 50±15, regime_shift 는 일부 구 임계 넘는 변동
    base = 35 + _seeded(seed, 1) * 50  # 35~85
    if scenario == "regime_shift":
        # 처음 5개 구는 등급 임계 넘는 큰 변동 (HOT/AVOID 극단)
        if idx < 3:
            base = min(95, base + 25)  # 상승 → HOT 권역
        elif idx < 5:
            base = max(20, base - 20)  # 하락 → AVOID 권역
    landex = round(base, 1)

    gei = round(_seeded(seed, 2) * 100, 1)
    v = round(40 + _seeded(seed, 3) * 60, 1)
    d = round(40 + _seeded(seed, 4) * 60, 1)
    s = round(40 + _seeded(seed, 5) * 60, 1)
    c = round(40 + _seeded(seed, 6) * 60, 1)
    r = round(40 + _seeded(seed, 7) * 60, 1)
    catalyst = round(_seeded(seed, 8) * 100, 1)

    # detail — drill-down expand 데이터
    weekly_price_index = []
    base_price = 100.0
    for w in range(52):
        # 주간 매매가격지수 시계열 — 결정적 walk
        delta = (_seeded(seed, 100 + w) - 0.5) * 1.5
        base_price *= (1 + delta / 100)
        date = (now - timedelta(weeks=51 - w)).strftime("%Y-%m-%d")
        weekly_price_index.append({"date": date, "value": round(base_price, 2)})

    monthly_unsold = []
    base_unsold = 200 + idx * 8
    for m in range(24):
        delta = (_seeded(seed, 200 + m) - 0.5) * 0.3
        base_unsold *= (1 + delta)
        date = (now - timedelta(days=30 * (23 - m))).strftime("%Y-%m")
        monthly_unsold.append({"date": date, "value": round(base_unsold, 0)})

    # feature contributions — 5축 + 추가 sub-features
    features = [
        {"feature": "transit_exp_index", "weight": round(_seeded(seed, 50) * 0.3, 3),
         "sign": "+" if _seeded(seed, 51) > 0.4 else "-"},
        {"feature": "price_to_avg_ratio", "weight": round(_seeded(seed, 52) * 0.25, 3),
         "sign": "+" if _seeded(seed, 53) > 0.5 else "-"},
        {"feature": "unsold_inventory", "weight": round(_seeded(seed, 54) * 0.2, 3),
         "sign": "-" if _seeded(seed, 55) > 0.5 else "+"},
        {"feature": "subway_card_volume", "weight": round(_seeded(seed, 56) * 0.15, 3),
         "sign": "+" if _seeded(seed, 57) > 0.5 else "-"},
        {"feature": "interest_rate_sensitivity", "weight": round(_seeded(seed, 58) * 0.1, 3),
         "sign": "-" if _seeded(seed, 59) > 0.5 else "+"},
    ]

    strengths_pool = [
        "교통 인프라 상위 — 환승역 접근성 양호",
        "수급 안정 — 미분양 누적 낮음",
        "재건축 진행 단지 분포",
        "직주근접 우위",
        "학군 프리미엄",
    ]
    weaknesses_pool = [
        "신규 공급 제한",
        "고금리 직접 노출",
        "정책 리스크 노출 (조정대상지역)",
        "가격 모멘텀 둔화",
        "임차 수요 약세",
    ]
    strengths = [strengths_pool[(idx + w) % len(strengths_pool)] for w in range(2)]
    weaknesses = [weaknesses_pool[(idx + w + 1) % len(weaknesses_pool)] for w in range(2)]

    return {
        "gu_name": gu,
        "landex": landex,
        "grade": _grade_from_landex(landex),
        "gei": gei,
        "stage": _stage_from_gei(gei),
        "v_score": v,
        "d_score": d,
        "s_score": s,
        "c_score": c,
        "r_score": r,
        "catalyst_score": catalyst,
        "detail": {
            "radar": {"v": v, "d": d, "s": s, "c": c, "r": r},
            "feature_contributions": features,
            "timeseries": {
                "weekly_price_index": weekly_price_index,
                "monthly_unsold": monthly_unsold,
            },
            "strengths": strengths,
            "weaknesses": weaknesses,
        },
    }


def _build_payload(scenario: str, now: datetime) -> dict:
    gus = [_gen_gu(gu, scenario, i, now) for i, gu in enumerate(SEOUL_25_GU)]

    # meta.detail — 등급 변화 카운트는 시나리오별 결정적
    if scenario == "regime_shift":
        degraded_count = 2
        gained_count = 3
    else:
        degraded_count = 0
        gained_count = 1

    gei_s4_count = sum(1 for g in gus if g["stage"] == 4)
    avg_landex = round(sum(g["landex"] for g in gus) / len(gus), 1)

    # top gainer / loser — landex 최대/최소
    sorted_by_landex = sorted(gus, key=lambda g: g["landex"], reverse=True)
    top_gainer = sorted_by_landex[0]
    top_loser = sorted_by_landex[-1]

    # current_regime — 평균 LANDEX 기반
    if avg_landex >= 60:
        regime = "bull"
    elif avg_landex <= 45:
        regime = "bear"
    else:
        regime = "neutral"

    return {
        "schema_version": "1.0",
        "generated_at": now.isoformat(timespec="seconds"),
        "scenario": scenario,
        "trigger": {
            "type": "regime_shift" if (degraded_count + gained_count) >= 3 else "normal",
        },
        "meta": {
            "primary": {
                "current_regime": regime,
                "top_gainer": {
                    "gu_name": top_gainer["gu_name"],
                    "change_pct": round(_seeded(top_gainer["gu_name"], 99) * 8 + 2, 1),
                },
                "top_loser": {
                    "gu_name": top_loser["gu_name"],
                    "change_pct": round(-(_seeded(top_loser["gu_name"], 99) * 6 + 1), 1),
                },
                "last_shift_at": (now - timedelta(hours=int(_seeded(scenario, 0) * 48))).isoformat(timespec="seconds"),
            },
            "detail": {
                "degraded_count": degraded_count,
                "gained_count": gained_count,
                "gei_s4_count": gei_s4_count,
                "avg_landex": avg_landex,
                "data_freshness_min": int(_seeded(scenario, 1) * 30 + 5),
            },
        },
        "gus": gus,
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
        scenario = (params.get("scenario", ["normal"])[0] or "normal").strip().lower()
        if scenario not in ("normal", "regime_shift"):
            scenario = "normal"

        now = datetime.now(KST)
        payload = _build_payload(scenario, now)

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
