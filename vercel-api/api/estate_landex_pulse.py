"""
GET /api/estate/landex-pulse — ESTATE 25구 LANDEX overview + drill-down (P2 wire — 2026-05-17)

contract_landex_pulse.md (P0 명세) 기반.

2026-05-17 P2 wire (estate_landex_snapshots Supabase read-through):
    - 옛 P1 mock (25구 모두 _seeded 의사 난수) 폐기 → landex_scores.py 의
      _fetch_snapshot_rows() 동일 패턴 reuse. 25구 v/d/s/c/r/landex/gei/gei_stage 실측.
    - detail (timeseries 52주/24개월, feature_contributions, strengths/weaknesses) =
      별도 source 부재 (landex_features/landex_narrative endpoint Phase 2 chain 필요)
      → detail mock 유지 + source 필드로 hybrid 명시 ("live_scores+mock_detail").
    - catalyst_score = mock 유지 (Phase 2 별도 score 정의 큐).
    - meta.primary (top_gainer/top_loser/avg_landex) = real scores 기반 산출.

Query parameters:
    scenario = "live" (default) | "mock"
        live  — Supabase estate_landex_snapshots fetch + detail mock fallback
        mock  — 옛 P1 mock 100% (Framer 개발 toggle 보존)
        옛 값 backward compat: "normal" → "live", "regime_shift" → "mock" (mock 만 regime 시뮬)

응답 schema (contract_landex_pulse.md §2):
    { schema_version, generated_at, scenario, source, trigger, meta, gus: [25] }

거짓말 트랩:
    T1  fabricate 금지   — live source 필드로 real vs mock 부분 명시
    T2  mock fallback    — Supabase fetch fail 시 source="mock", scenario 그대로
    T29 source URL 절대  — Supabase REST endpoint 절대 URL
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# 25구 — LandexMapDashboard SEOUL_25_GU 정합 (지리적 순서: 동남→서북)
SEOUL_25_GU = [
    "강동구", "송파구", "강남구", "서초구", "관악구",
    "동작구", "영등포구", "금천구", "구로구", "강서구",
    "양천구", "마포구", "서대문구", "은평구", "노원구",
    "도봉구", "강북구", "성북구", "중랑구", "동대문구",
    "광진구", "성동구", "용산구", "중구", "종로구",
]

# Supabase 1회 fetch — landex_scores 의 _fetch_snapshot_rows 와 동일 패턴
SUPABASE_TIMEOUT_SEC = 4  # vercel.json maxDuration=5 안전 마진
DEFAULT_PRESET = "balanced"
LANDEX_METHODOLOGY_VERSION = "v1.0"  # landex_scores._methodology.VERSION 정합


def _seeded(seed_str: str, idx: int) -> float:
    """결정적 의사 난수 (0~1) — detail mock 산출용 (timeseries / features / strengths)."""
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


# ─────────────────────────────────────────────────
# Live fetch (Supabase estate_landex_snapshots) — landex_scores 패턴 reuse
# ─────────────────────────────────────────────────

def _fetch_live_scores(month: str) -> list[dict] | None:
    """estate_landex_snapshots 25구 행 조회 (landex_scores._fetch_snapshot_rows 동일 패턴).

    Returns: 25 rows or None (테이블 비었거나 Supabase 미설정 또는 timeout).
    """
    url = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    anon = (os.environ.get("SUPABASE_ANON_KEY") or "").strip()
    if not url or not anon:
        return None
    params = {
        "select": "gu,v_score,d_score,s_score,c_score,r_score,landex,tier10,gei,gei_stage,raw_payload",
        "month": f"eq.{month}",
        "preset": f"eq.{DEFAULT_PRESET}",
        "methodology_version": f"eq.{LANDEX_METHODOLOGY_VERSION}",
    }
    headers = {"apikey": anon, "Authorization": f"Bearer {anon}"}
    try:
        r = requests.get(
            f"{url}/rest/v1/estate_landex_snapshots",
            headers=headers, params=params, timeout=SUPABASE_TIMEOUT_SEC,
        )
        r.raise_for_status()
        rows = r.json()
        return rows if rows else None
    except Exception as e:
        _logger.warning("estate_landex_pulse: live fetch 실패: %s", e)
        return None


def _gen_mock_detail(gu: str, idx: int, scenario_seed: str, now: datetime) -> dict:
    """detail mock (timeseries 52주/24개월, features, strengths/weaknesses) — 별도 endpoint chain 부재 동안."""
    seed = f"{gu}-{scenario_seed}-2026-05"
    weekly_price_index = []
    base_price = 100.0
    for w in range(52):
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
        "feature_contributions": features,
        "timeseries": {
            "weekly_price_index": weekly_price_index,
            "monthly_unsold": monthly_unsold,
        },
        "strengths": strengths,
        "weaknesses": weaknesses,
        "_detail_source": "mock",  # Phase 2 landex_features/landex_narrative chain 큐.
    }


def _build_gu_live(row: dict, idx: int, scenario_seed: str, now: datetime) -> dict:
    """Supabase row + detail mock 합성 → contract_landex_pulse.md schema 정합."""
    gu = row.get("gu") or SEOUL_25_GU[idx]
    landex = row.get("landex") or 50.0
    gei = row.get("gei") or 0.0
    v = row.get("v_score") or 0.0
    d = row.get("d_score") or 0.0
    s = row.get("s_score") or 0.0
    c = row.get("c_score") or 0.0
    r = row.get("r_score") or 0.0
    # catalyst_score = mock 유지 (Phase 2 catalyst 정의 큐). raw_payload 에 있으면 사용.
    catalyst = (row.get("raw_payload") or {}).get("catalyst_score")
    if catalyst is None:
        catalyst = round(_seeded(f"{gu}-{scenario_seed}", 8) * 100, 1)
    detail = _gen_mock_detail(gu, idx, scenario_seed, now)
    detail["radar"] = {"v": v, "d": d, "s": s, "c": c, "r": r}
    return {
        "gu_name": gu,
        "landex": round(landex, 1),
        "grade": _grade_from_landex(landex),
        "gei": round(gei, 1),
        "stage": _stage_from_gei(gei),
        "v_score": round(v, 1),
        "d_score": round(d, 1),
        "s_score": round(s, 1),
        "c_score": round(c, 1),
        "r_score": round(r, 1),
        "catalyst_score": catalyst,
        "detail": detail,
        "_source": "live",
    }


def _build_gu_mock(gu: str, scenario: str, idx: int, now: datetime) -> dict:
    """옛 P1 mock — 25구 모두 _seeded 의사 난수 (scenario=mock 또는 fetch fail 시 fallback)."""
    seed = f"{gu}-{scenario}-2026-05"
    base = 35 + _seeded(seed, 1) * 50
    if scenario == "mock_regime_shift":
        # 옛 regime_shift backward compat — 처음 3구 HOT, 4-5구 AVOID
        if idx < 3:
            base = min(95, base + 25)
        elif idx < 5:
            base = max(20, base - 20)
    landex = round(base, 1)
    gei = round(_seeded(seed, 2) * 100, 1)
    v = round(40 + _seeded(seed, 3) * 60, 1)
    d = round(40 + _seeded(seed, 4) * 60, 1)
    s = round(40 + _seeded(seed, 5) * 60, 1)
    c = round(40 + _seeded(seed, 6) * 60, 1)
    r = round(40 + _seeded(seed, 7) * 60, 1)
    catalyst = round(_seeded(seed, 8) * 100, 1)
    detail = _gen_mock_detail(gu, idx, scenario, now)
    detail["radar"] = {"v": v, "d": d, "s": s, "c": c, "r": r}
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
        "detail": detail,
        "_source": "mock",
    }


def _build_meta(gus: list[dict], scenario: str, source: str, now: datetime) -> dict:
    """meta.primary (top_gainer/top_loser/avg_landex) — real scores 기반 산출."""
    sorted_by_landex = sorted(gus, key=lambda g: g["landex"], reverse=True)
    top_gainer = sorted_by_landex[0]
    top_loser = sorted_by_landex[-1]
    avg_landex = round(sum(g["landex"] for g in gus) / len(gus), 1)
    gei_s4_count = sum(1 for g in gus if g["stage"] == 4)

    if avg_landex >= 60:
        regime = "bull"
    elif avg_landex <= 45:
        regime = "bear"
    else:
        regime = "neutral"

    # 등급 변화 카운트 = real source 부재 시 mock (Phase 2 시계열 비교 필요)
    if scenario == "mock_regime_shift":
        degraded_count, gained_count = 2, 3
    else:
        # live 또는 mock — 등급 변화 0~1 (cry wolf 방지)
        degraded_count, gained_count = 0, 1

    # change_pct = mock (시계열 비교 부재). Phase 2 wire 시 real 산출.
    top_gainer_change = round(_seeded(top_gainer["gu_name"], 99) * 8 + 2, 1)
    top_loser_change = round(-(_seeded(top_loser["gu_name"], 99) * 6 + 1), 1)

    return {
        "primary": {
            "current_regime": regime,
            "top_gainer": {
                "gu_name": top_gainer["gu_name"],
                "change_pct": top_gainer_change,
            },
            "top_loser": {
                "gu_name": top_loser["gu_name"],
                "change_pct": top_loser_change,
            },
            "last_shift_at": (now - timedelta(hours=int(_seeded(scenario, 0) * 48))).isoformat(timespec="seconds"),
        },
        "detail": {
            "degraded_count": degraded_count,
            "gained_count": gained_count,
            "gei_s4_count": gei_s4_count,
            "avg_landex": avg_landex,
            "data_freshness_min": int(_seeded(scenario, 1) * 30 + 5),
            "_source": source,
        },
    }


def _build_payload(scenario: str, now: datetime) -> dict:
    """진짜 wire 흐름:
        live → Supabase fetch + detail mock fallback
        mock → 옛 P1 mock 100%
    """
    # month = 전월 (snapshot cron 매월 1회 갱신)
    month = (now - timedelta(days=now.day)).strftime("%Y-%m")

    if scenario == "live":
        rows = _fetch_live_scores(month)
        if rows:
            # 25구 모두 fetch 됐는지 확인 — 누락 구는 mock fallback
            row_by_gu = {r.get("gu"): r for r in rows}
            gus = []
            n_live = 0
            for i, gu in enumerate(SEOUL_25_GU):
                if gu in row_by_gu:
                    gus.append(_build_gu_live(row_by_gu[gu], i, "live", now))
                    n_live += 1
                else:
                    gus.append(_build_gu_mock(gu, "mock", i, now))
            source = "live_scores+mock_detail" if n_live == 25 else f"live_scores_partial({n_live}/25)+mock_detail"
        else:
            # fetch fail → mock fallback (T2 정합 — source 명시)
            gus = [_build_gu_mock(gu, "mock", i, now) for i, gu in enumerate(SEOUL_25_GU)]
            source = "mock_fallback (Supabase unavailable)"
    else:
        # scenario=mock — 옛 P1 mock 100%
        gus = [_build_gu_mock(gu, scenario, i, now) for i, gu in enumerate(SEOUL_25_GU)]
        source = "mock"

    meta = _build_meta(gus, scenario, source, now)
    trigger_type = "regime_shift" if (meta["detail"]["degraded_count"] + meta["detail"]["gained_count"]) >= 3 else "normal"

    return {
        "schema_version": "1.1",  # P2 wire — scenario semantic 변경
        "generated_at": now.isoformat(timespec="seconds"),
        "scenario": scenario,
        "source": source,  # live_scores+mock_detail | mock | mock_fallback
        "trigger": {"type": trigger_type},
        "meta": meta,
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
        scenario = (params.get("scenario", ["live"])[0] or "live").strip().lower()
        # backward compat — 옛 enum "normal"|"regime_shift" 처리
        if scenario == "normal":
            scenario = "live"
        elif scenario == "regime_shift":
            scenario = "mock_regime_shift"  # mock 의 regime 시뮬 branch
        if scenario not in ("live", "mock", "mock_regime_shift"):
            scenario = "live"

        now = datetime.now(KST)
        payload = _build_payload(scenario, now)

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
