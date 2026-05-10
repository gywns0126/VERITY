"""
estate_brain_builder.py — ESTATE Brain V0.2 snapshots 빌더 (cron worker).

contract: estate_brain V0.2 schema (api/intelligence/estate_brain.py compute_estate_brain)
        Plan: docs/ESTATE_BRAIN_V0_PLAN.md

흐름 (estate_change_feed_builder + estate_hero_briefing_builder 패턴 정합):
    ① ECOS macro fetch (treasury_10y_pct, rate_change_pp_6m)
    ② KOSIS 서울 중위소득 fetch (annual_income_won)
    ③ 25구 lead_time signals fetch (R-ONE 전세지수 + 전세가율 + 미분양)
    ④ 25구 aggregate brain (lead_time + cycle_analog 위주, 4 layer 없음)
    ⑤ V0 watchlist 5단지 brain (가격 mock + redev 진짜)
    ⑥ atomic write → data/estate_brain_snapshots.json

V0 한계 (의도적 — V1 게이트):
    - 단지 가격 = mock (RTMS clustering 누적 후 V1)
    - KOSIS / R-ONE 전세 statId 환경변수 미설정 시 layer skip
    - 25구 권역 가중치 V1 calibration 큐
    - watchlist hardcoded 5단지 → V1 동적 등록

vercel-api 어댑터 import:
    project root + vercel-api 분리 정합 — importlib 동적 로드 (테스트 패턴 정합).

거짓말 트랩 (T-시리즈 정합):
    T1·T9   fabricate·silent X — 실패 시 layer None + diagnostics 명시
    T2      mock 단지 가격 = "v0_mock" source 명시
    T18     ECOS / R-ONE 호출 실패 = log + diagnostics
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_REPO_ROOT, "data", "estate_brain_snapshots.json")
HISTORY_JSONL_PATH = os.path.join(_REPO_ROOT, "data", "estate_brain_history.jsonl")
HISTORY_SCHEMA_VERSION = "v0.1"

SCHEMA_VERSION = "v0.2"
KST = timezone(timedelta(hours=9))

SEOUL_25_GU = [
    "종로구", "중구", "용산구", "성동구", "광진구", "동대문구",
    "중랑구", "성북구", "강북구", "도봉구", "노원구",
    "은평구", "서대문구", "마포구", "양천구", "강서구",
    "구로구", "금천구", "영등포구", "동작구", "관악구",
    "서초구", "강남구", "송파구", "강동구",
]

# V0 watchlist — V1 동적 등록 (사용자 관심지역 → 단지 매칭).
# 가격 base = 통계청·KB 공시 mid-2024 평균 (V1 RTMS 실시간 swap 큐).
V0_WATCHLIST: List[Dict[str, Any]] = [
    {
        "complex_id": "강남구_대치동_은마_1979",
        "gu": "강남구", "dong": "대치동", "apt": "은마", "build_year": 1979,
        "price_won_mock": 26e8, "jeonse_won_mock": 6.5e8,
        "kb_price_mock": 27e8, "recent_actual_mock": 25.5e8,
        "redev": {"stage": "management_plan", "type": "redevelopment",
                  "months_in": 4, "valuation_pending": True, "subscription_announced": False},
    },
    {
        "complex_id": "강남구_압구정동_한양1_1977",
        "gu": "강남구", "dong": "압구정동", "apt": "한양1", "build_year": 1977,
        "price_won_mock": 38e8, "jeonse_won_mock": 8e8,
        "kb_price_mock": 39e8, "recent_actual_mock": 37.5e8,
        "redev": {"stage": "union_setup", "type": "reconstruction",
                  "months_in": 12, "valuation_pending": False, "subscription_announced": False},
    },
    {
        "complex_id": "송파구_잠실동_잠실엘스_2008",
        "gu": "송파구", "dong": "잠실동", "apt": "잠실엘스", "build_year": 2008,
        "price_won_mock": 24e8, "jeonse_won_mock": 13e8,
        "kb_price_mock": 24e8, "recent_actual_mock": 23.5e8,
        "redev": None,
    },
    {
        "complex_id": "마포구_아현동_마포래미안푸르지오_2014",
        "gu": "마포구", "dong": "아현동", "apt": "마포래미안푸르지오", "build_year": 2014,
        "price_won_mock": 18e8, "jeonse_won_mock": 10e8,
        "kb_price_mock": 18e8, "recent_actual_mock": 17.5e8,
        "redev": None,
    },
    {
        "complex_id": "노원구_상계동_상계주공5_1987",
        "gu": "노원구", "dong": "상계동", "apt": "상계주공5", "build_year": 1987,
        "price_won_mock": 9e8, "jeonse_won_mock": 4.5e8,
        "kb_price_mock": 9e8, "recent_actual_mock": 8.5e8,
        "redev": {"stage": "district_designation", "type": "reconstruction",
                  "months_in": 6, "valuation_pending": False, "subscription_announced": False},
    },
]

# PIR baseline (Plan v0.2 §Layer 별 정상 밴드 — 서울 아파트 15-25)
PIR_MA_10YR = 18.0
PIR_SIGMA_10YR = 2.0


# ────────────────────────────────────────────────────────────
# 동적 import — vercel-api 어댑터 (project root 와 분리)

def _fetch_user_watch_complexes(timeout: float = 8.0) -> List[Dict[str, Any]]:
    """모든 사용자 등록 단지 union (service_role 으로 RLS 우회).

    환경변수:
      SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
    부재 시 [] (V0_WATCHLIST hardcoded 만 사용).
    """
    import os as _os
    base = _os.environ.get("SUPABASE_URL", "").rstrip("/")
    service_key = _os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not service_key:
        return []
    try:
        import requests as _req
        r = _req.get(
            f"{base}/rest/v1/estate_user_watch_complexes",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
            },
            params={
                "select": "gu,dong,apt,apt_normalized,build_year,project_type,"
                          "redev_stage,months_in_stage,valuation_pending,"
                          "subscription_announced",
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            logger.warning("user_watch_complexes fetch HTTP %s", r.status_code)
            return []
        return r.json() or []
    except Exception as e:
        logger.warning("user_watch_complexes fetch 실패: %s", e)
        return []


def _dedupe_watchlist(
    hardcoded: List[Dict[str, Any]],
    user_complexes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """V0_WATCHLIST + 사용자 등록 union — (gu, dong, apt_normalized, build_year) 키로 중복 제거.

    hardcoded 우선 (mock 가격 박혀있어서). 사용자 등록은 동일 키 미존재 시 추가.
    사용자 단지에는 가격 mock 없음 → RTMS 매칭 의존, 매칭 실패 시 valuation None.
    """
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for item in hardcoded:
        # apt_normalized 산출 (hardcoded 는 "apt" 만)
        apt_norm = item.get("apt", "").strip().replace(" ", "")
        key = (item["gu"], item["dong"], apt_norm, item.get("build_year", 0))
        seen.add(key)
        out.append(item)
    for u in user_complexes:
        key = (u.get("gu"), u.get("dong"), u.get("apt_normalized"),
               u.get("build_year") or 0)
        if key in seen:
            continue
        seen.add(key)
        # 사용자 등록 → V0_WATCHLIST schema 정합 (가격 mock 없음 → None)
        complex_id = f"{u['gu']}_{u['dong']}_{u.get('apt_normalized') or u.get('apt')}_{u.get('build_year') or 0}"
        redev = None
        if u.get("redev_stage"):
            redev = {
                "stage": u["redev_stage"],
                "type": u.get("project_type") or "redevelopment",
                "months_in": u.get("months_in_stage") or 0,
                "valuation_pending": u.get("valuation_pending", False),
                "subscription_announced": u.get("subscription_announced", False),
            }
        out.append({
            "complex_id": complex_id,
            "gu": u["gu"], "dong": u["dong"],
            "apt": u.get("apt") or u.get("apt_normalized", ""),
            "build_year": u.get("build_year") or 0,
            # 가격 mock 없음 — RTMS 매칭 의존
            "price_won_mock": None,
            "jeonse_won_mock": None,
            "kb_price_mock": None,
            "recent_actual_mock": None,
            "redev": redev,
            "_source": "user_watchlist",
        })
    return out


def _load_vercel_api_modules() -> Dict[str, Any]:
    """vercel-api/api/landex/_sources/* + landex/_clustering.py 동적 로드.

    project root 에서 `from api.landex...` 가 안 되는 (vercel-api root 와 충돌) 환경 우회.
    테스트 패턴 정합 (`tests/test_landex_rone_jeonse.py` 등).
    """
    sources_dir = os.path.join(_REPO_ROOT, "vercel-api", "api", "landex", "_sources")
    landex_dir = os.path.join(_REPO_ROOT, "vercel-api", "api", "landex")
    pkg_name = "estate_brain_runtime_sources"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [sources_dir]
    sys.modules[pkg_name] = pkg

    loaded: Dict[str, Any] = {}
    # _sources 어댑터 — molit (RTMS 실거래) 추가
    for mod_name in ("_lawd", "kosis", "rone", "molit"):
        path = os.path.join(sources_dir, f"{mod_name}.py")
        if not os.path.exists(path):
            continue
        spec = importlib.util.spec_from_file_location(f"{pkg_name}.{mod_name}", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"{pkg_name}.{mod_name}"] = mod
        spec.loader.exec_module(mod)
        loaded[mod_name] = mod

    # landex 직속 — _clustering (RTMS 단지명 normalize)
    cl_path = os.path.join(landex_dir, "_clustering.py")
    if os.path.exists(cl_path):
        cl_pkg = "estate_brain_runtime_clustering"
        spec = importlib.util.spec_from_file_location(cl_pkg, cl_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[cl_pkg] = mod
        spec.loader.exec_module(mod)
        loaded["clustering"] = mod
    return loaded


# ────────────────────────────────────────────────────────────
# Macro fetch (ECOS + KOSIS)

def _fetch_macro(
    _ecos: Optional[Any] = None,
    _kosis: Optional[Any] = None,
) -> Dict[str, Any]:
    """ECOS 금리·국고채 + KOSIS 중위소득. 키 부재 / 실패 시 None 안전."""
    if _ecos is None:
        from api.collectors import ecos_macro as _ecos  # type: ignore

    macro_block = None
    try:
        macro_block = _ecos.get_ecos_macro_block()
    except Exception as e:
        logger.warning("ecos macro_block 실패: %s", e)
    treasury = _ecos.latest_treasury_10y_pct(macro_block) if macro_block else None

    rate_change = None
    try:
        rate_series = _ecos.fetch_korea_policy_rate_series(months=12)
        if rate_series:
            rate_change = _ecos.compute_rate_change_pp(rate_series, months_back=6)
    except Exception as e:
        logger.warning("ecos rate_change 실패: %s", e)

    annual_income = None
    income_meta = None
    if _kosis is not None:
        try:
            now_year = datetime.now(KST).year
            income = _kosis.fetch_seoul_median_income(now_year)
            if income:
                annual_income = income.get("value_won")
                income_meta = {"year": income.get("year"), "stat_id": income.get("stat_id"),
                               "as_of": income.get("as_of")}
        except Exception as e:
            logger.warning("kosis income 실패: %s", e)

    return {
        "treasury_10y_pct": treasury,
        "rate_change_pp_6m": rate_change,
        "annual_median_income_won": annual_income,
        "income_meta": income_meta,
        "ecos_macro_available": bool(macro_block and macro_block.get("available")),
    }


# ────────────────────────────────────────────────────────────
# 25구 lead_time signals

def _fetch_gu_lead_time(
    gu: str,
    rone: Optional[Any],
) -> Dict[str, Optional[float]]:
    """단일 구의 lead_time 입력 4종 fetch (jeonse_3m / jeonse_ratio / unsold_yoy / construction은 V1)."""
    out: Dict[str, Optional[float]] = {
        "jeonse_3m_change_pct": None,
        "jeonse_ratio_pct": None,
        "unsold_units_yoy_pct": None,
        "construction_starts_yoy_pct": None,  # V1 — KICT/국토부 별도 source
    }
    if rone is None:
        return out

    try:
        jeonse_idx = rone.fetch_weekly_jeonse_index(gu, weeks=14)
        out["jeonse_3m_change_pct"] = rone.compute_jeonse_3m_change_pct(jeonse_idx)
    except Exception as e:
        logger.debug("jeonse_index 실패 %s: %s", gu, e)

    try:
        # R-ONE 사양: 매매가격대비 전세가격 비율 = 월간(MM)만 존재. 24개월 lookback.
        ratio_payload = rone.fetch_monthly_jeonse_ratio(gu, months=24)
        out["jeonse_ratio_pct"] = rone.latest_jeonse_ratio_pct(ratio_payload)
    except Exception as e:
        logger.debug("jeonse_ratio 실패 %s: %s", gu, e)

    try:
        unsold = rone.fetch_monthly_unsold(gu, months=14)
        out["unsold_units_yoy_pct"] = rone.compute_unsold_yoy_pct(unsold)
    except Exception as e:
        logger.debug("unsold 실패 %s: %s", gu, e)

    return out


# ────────────────────────────────────────────────────────────
# Brain 산출 — gu aggregate + watchlist 단지

def _compute_gu_aggregate(
    gu: str,
    macro: Dict[str, Any],
    lead_time: Dict[str, Optional[float]],
    _compute_brain: Callable,
) -> Dict[str, Any]:
    """구 단위 aggregate brain — 4 layer 없음, lead_time + cycle_analog 위주."""
    return _compute_brain(
        complex_id=f"{gu}_aggregate",
        as_of=datetime.now(KST).isoformat(timespec="seconds"),
        # L1-L4 가격 정보 X (구 단위 단일 단지 X)
        treasury_10y_pct=macro.get("treasury_10y_pct"),
        target_cycle={"drop_pct": -20, "duration_months": 60, "shape": "W"},
        jeonse_3m_change_pct=lead_time.get("jeonse_3m_change_pct"),
        jeonse_ratio_pct=lead_time.get("jeonse_ratio_pct"),
        construction_starts_yoy_pct=lead_time.get("construction_starts_yoy_pct"),
        unsold_units_yoy_pct=lead_time.get("unsold_units_yoy_pct"),
        rate_change_pp=macro.get("rate_change_pp_6m"),
    )


def _fetch_watchlist_real_price(
    item: Dict[str, Any],
    modules: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """RTMS clustering 매칭 → 실 price_won 산출. None = 매칭 실패 → 호출자 mock fallback.

    매칭 키: (gu, dong, normalized_apt, build_year ±1). V0 단순 — 평형별 차별화는 V1.
    representative price = price_pyeong.mean × area_m2.median (단지 대표 평균가).
    """
    molit = modules.get("molit")
    clustering = modules.get("clustering")
    if not molit or not clustering:
        return None

    try:
        trades = molit.fetch_recent_trades(item["gu"], months=6)
    except Exception as e:
        logger.debug("molit fetch 실패 %s: %s", item["complex_id"], e)
        return None
    if not trades:
        return None

    try:
        clusters = clustering.cluster_trades(trades, gu=item["gu"])
    except Exception as e:
        logger.debug("clustering 실패 %s: %s", item["complex_id"], e)
        return None

    target_apt = clustering.normalize_apt_name(item["apt"])
    target = None
    for c in clusters:
        if c.get("dong") != item["dong"]:
            continue
        if c.get("apt_normalized") != target_apt:
            continue
        if abs((c.get("build_year") or 0) - item["build_year"]) > 1:
            continue
        target = c
        break

    if not target:
        return None

    pyeong_mean = (target.get("price_pyeong") or {}).get("mean")
    area_median = (target.get("area_m2") or {}).get("median")
    if not pyeong_mean or not area_median:
        return None

    price_won = int(pyeong_mean * (area_median / 3.305785))
    return {
        "price_won": price_won,
        "trade_count": target.get("trade_count"),
        "area_m2_median": area_median,
        "latest_deal_date": target.get("latest_deal_date"),
        "price_source": "rtms_actual",
    }


def _compute_complex(
    item: Dict[str, Any],
    macro: Dict[str, Any],
    lead_time: Dict[str, Optional[float]],
    _compute_brain: Callable,
    modules: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """단지 단위 brain — RTMS 실측 swap 시도 + redev 진짜 + lead_time 권역값.

    RTMS 매칭 성공 → real price (price_source=rtms_actual)
    RTMS 매칭 실패 → mock 가격 (price_source=v0_mock)
    """
    redev = item.get("redev") or {}
    annual_income = macro.get("annual_median_income_won") or 0

    # RTMS 실측 swap
    real = _fetch_watchlist_real_price(item, modules or {})
    if real:
        price_won = real["price_won"]
        price_source = "rtms_actual"
        rtms_meta = {
            "trade_count": real.get("trade_count"),
            "area_m2_median": real.get("area_m2_median"),
            "latest_deal_date": real.get("latest_deal_date"),
        }
    else:
        price_won = item.get("price_won_mock")
        price_source = "v0_mock"
        rtms_meta = None

    brain = _compute_brain(
        complex_id=item["complex_id"],
        as_of=datetime.now(KST).isoformat(timespec="seconds"),
        # 실측 swap 또는 mock fallback
        price_won=price_won,
        annual_income_won=annual_income or None,
        pir_ma_10yr=PIR_MA_10YR,
        pir_sigma_10yr=PIR_SIGMA_10YR,
        jeonse_won=item.get("jeonse_won_mock"),
        treasury_10y_pct=macro.get("treasury_10y_pct"),
        recent_actual_avg_won=item.get("recent_actual_mock"),
        kb_price_won=item.get("kb_price_mock"),
        # cycle / lead_time
        target_cycle={"drop_pct": -20, "duration_months": 60, "shape": "W"},
        jeonse_3m_change_pct=lead_time.get("jeonse_3m_change_pct"),
        jeonse_ratio_pct=lead_time.get("jeonse_ratio_pct"),
        construction_starts_yoy_pct=lead_time.get("construction_starts_yoy_pct"),
        unsold_units_yoy_pct=lead_time.get("unsold_units_yoy_pct"),
        rate_change_pp=macro.get("rate_change_pp_6m"),
        # redev (진짜)
        redevelopment_stage=redev.get("stage"),
        project_type=redev.get("type"),
        months_in_stage=redev.get("months_in", 0),
        valuation_announcement_pending=redev.get("valuation_pending", False),
        general_subscription_announced=redev.get("subscription_announced", False),
    )
    # 가격 source 명시 (T2 — rtms_actual / v0_mock 분기)
    brain["model_meta"]["price_source"] = price_source
    if rtms_meta:
        brain["model_meta"]["rtms_meta"] = rtms_meta
    return brain


# ────────────────────────────────────────────────────────────
# Top-level orchestrator

def build(
    _modules: Optional[Dict[str, Any]] = None,
    _ecos: Optional[Any] = None,
    _compute_brain: Optional[Callable] = None,
    _now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """ESTATE Brain snapshots payload 산출.

    실패 시에도 항상 dict (T1 — diagnostics 에 어떤 source 가 죽었는지 명시).
    """
    now = _now or datetime.now(KST)

    if _compute_brain is None:
        from api.intelligence.estate_brain import compute_estate_brain as _compute_brain  # type: ignore

    modules = _modules if _modules is not None else _load_vercel_api_modules()
    rone = modules.get("rone")
    kosis = modules.get("kosis")

    macro = _fetch_macro(_ecos=_ecos, _kosis=kosis)

    gu_aggregates: Dict[str, Any] = {}
    gu_lead_times: Dict[str, Dict[str, Optional[float]]] = {}
    for gu in SEOUL_25_GU:
        lead_time = _fetch_gu_lead_time(gu, rone)
        gu_lead_times[gu] = lead_time
        try:
            gu_aggregates[gu] = _compute_gu_aggregate(gu, macro, lead_time, _compute_brain)
        except Exception as e:
            logger.error("gu_aggregate %s 실패: %s", gu, e)

    # 사용자 등록 단지 union
    user_complexes_raw = _fetch_user_watch_complexes()
    full_watchlist = _dedupe_watchlist(V0_WATCHLIST, user_complexes_raw)

    complexes: Dict[str, Any] = {}
    rtms_swap_count = 0
    for item in full_watchlist:
        gu = item["gu"]
        lead_time = gu_lead_times.get(gu, {})
        try:
            brain = _compute_complex(item, macro, lead_time, _compute_brain, modules=modules)
            complexes[item["complex_id"]] = brain
            if brain.get("model_meta", {}).get("price_source") == "rtms_actual":
                rtms_swap_count += 1
        except Exception as e:
            logger.error("complex %s 실패: %s", item["complex_id"], e)

    diagnostics = {
        "ecos_available": macro.get("ecos_macro_available", False),
        "kosis_available": macro.get("annual_median_income_won") is not None,
        "rone_jeonse_available": any(
            lt.get("jeonse_3m_change_pct") is not None for lt in gu_lead_times.values()
        ),
        "rone_unsold_available": any(
            lt.get("unsold_units_yoy_pct") is not None for lt in gu_lead_times.values()
        ),
        "rtms_swap_count": rtms_swap_count,  # 매칭된 단지 수 (RTMS 실측)
        "watchlist_size": len(full_watchlist),
        "watchlist_v0_hardcoded_count": len(V0_WATCHLIST),
        "watchlist_user_count": len(user_complexes_raw),
        "watchlist_unique_count": len(full_watchlist),
        "supabase_available": bool(user_complexes_raw or
                                    bool(__import__("os").environ.get("SUPABASE_SERVICE_ROLE_KEY"))),
    }

    # 서울 종합 horizon (estate_horizon V0) — 25 gu lead_time 평균 기반.
    # cycle_analog target 은 V0 hardcoded (현재 사이클 KB 12M change 동적 추정은 V1 큐잉).
    horizon: Dict[str, Any] = {}
    try:
        from api.intelligence.estate_brain import (
            compute_lead_time_signals as _lt_fn,
            classify_cycle_analog as _ca_fn,
        )
        from api.intelligence.estate_horizon import compute_estate_horizon as _hz_fn

        def _avg(key: str) -> Optional[float]:
            vals = [
                lt.get(key) for lt in gu_lead_times.values()
                if lt.get(key) is not None
            ]
            return sum(vals) / len(vals) if vals else None

        seoul_lead = _lt_fn(
            jeonse_3m_change_pct=_avg("jeonse_3m_change_pct"),
            jeonse_ratio_pct=_avg("jeonse_ratio_pct"),
            construction_starts_yoy_pct=_avg("construction_starts_yoy_pct"),
            unsold_units_yoy_pct=_avg("unsold_units_yoy_pct"),
            rate_change_pp=macro.get("rate_change_pp_6m"),
        )
        seoul_analog = _ca_fn(
            target={"drop_pct": -20, "duration_months": 60, "shape": "W"},
        )
        horizon = _hz_fn(
            lead_signals=seoul_lead,
            cycle_analog=seoul_analog,
            as_of=now.isoformat(timespec="seconds"),
        )
    except Exception as e:
        logger.error("seoul horizon 산출 실패: %s", e)
        horizon = {
            "version": "v0",
            "verdict": None,
            "error": str(e),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(timespec="seconds"),
        "macro": {
            "treasury_10y_pct": macro.get("treasury_10y_pct"),
            "rate_change_pp_6m": macro.get("rate_change_pp_6m"),
            "annual_median_income_won": macro.get("annual_median_income_won"),
            "income_meta": macro.get("income_meta"),
        },
        "horizon": horizon,
        "gu_aggregates": gu_aggregates,
        "complexes": complexes,
        "diagnostics": diagnostics,
        "model_meta": {
            "version": "v0_hardcoded",
            "source": "cron_builder",
            "plan": "docs/ESTATE_BRAIN_V0_PLAN.md",
        },
    }


def _emit_alerts(payload: Dict[str, Any]) -> int:
    """brain payload → estate_alerts insert (Supabase service_role).

    SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY 부재 시 skip (alert 0건).
    dedupe_key uniq partial index → ON CONFLICT DO NOTHING (Postgres 중복 무시).
    """
    import os as _os
    base = _os.environ.get("SUPABASE_URL", "").rstrip("/")
    service_key = _os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not service_key:
        logger.info("alert emit skip — SUPABASE service_role 미설정")
        return 0

    try:
        from api.intelligence.estate_brain_alert_generator import generate_alerts
    except Exception as e:
        logger.warning("alert generator import 실패: %s", e)
        return 0

    alerts = generate_alerts(payload)
    if not alerts:
        return 0

    try:
        import requests as _req
        # Prefer: resolution=ignore-duplicates → dedupe_key 충돌 시 skip
        r = _req.post(
            f"{base}/rest/v1/estate_alerts",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
                "Prefer": "resolution=ignore-duplicates,return=minimal",
            },
            json=alerts, timeout=10,
        )
        if r.status_code >= 300:
            logger.warning("alert insert HTTP %s — %s", r.status_code, r.text[:200])
            return 0
        logger.info("alert emit OK — %d row attempted (dedupe 적용)", len(alerts))
        return len(alerts)
    except Exception as e:
        logger.warning("alert insert 실패: %s", e)
        return 0


def _compact_history_row(payload: Dict[str, Any]) -> Dict[str, Any]:
    """estate_brain_history.jsonl 1 row 산출 — payload 전체 복제 X.

    시계열 분석용 핵심 필드만 압축 (~3KB/row, 365일 = ~1MB/year).
    """
    gu_aggregates = payload.get("gu_aggregates") or {}
    complexes = payload.get("complexes") or []

    gu_scores: Dict[str, Any] = {}
    gu_signals: Dict[str, int] = {}
    gu_phase: Dict[str, str] = {}
    for gu, agg in gu_aggregates.items():
        if not isinstance(agg, dict):
            continue
        val = agg.get("valuation") or {}
        ca = agg.get("cycle_analog") or {}
        gu_scores[gu] = val.get("weighted_score")
        gu_signals[gu] = val.get("extreme_signals_count")
        gu_phase[gu] = ca.get("current_phase")

    complex_scores = [
        (c.get("valuation") or {}).get("weighted_score")
        for c in complexes if isinstance(c, dict)
    ]
    complex_scores = [s for s in complex_scores if isinstance(s, (int, float))]
    complex_summary = {
        "n": len(complex_scores),
        "mean": round(sum(complex_scores) / len(complex_scores), 2) if complex_scores else None,
        "min": round(min(complex_scores), 2) if complex_scores else None,
        "max": round(max(complex_scores), 2) if complex_scores else None,
    }

    macro = payload.get("macro") or {}
    macro_compact = {
        k: macro.get(k)
        for k in ("mortgage_rate_pct", "jeonse_to_sale_ratio_pct",
                  "unsold_houses_yoy_pct", "treasury_10y_pct")
        if k in macro
    }

    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "generated_at": payload.get("generated_at"),
        "gu_scores": gu_scores,
        "gu_signals": gu_signals,
        "gu_phase": gu_phase,
        "complex_summary": complex_summary,
        "macro": macro_compact,
        "diagnostics": payload.get("diagnostics") or {},
    }


def _append_history_jsonl(payload: Dict[str, Any], path: str = HISTORY_JSONL_PATH) -> bool:
    """history.jsonl append. 실패해도 운영 영향 X (silent).

    feedback_data_collection_verification_mandatory 정합:
      - try/finally + logged=True 명시 stderr
      - 실패 case 도 stderr 에 명시 표기 → silent skip 방지

    Returns: True 성공 / False 실패
    """
    logged = False
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        row = _compact_history_row(payload)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        logged = True
        return True
    except Exception as e:
        logger.error("estate_brain_history.jsonl append 실패: %s", e)
        return False
    finally:
        # silent skip 방지 (feedback_data_collection_verification_mandatory)
        import sys as _sys
        print(f"[estate_brain history] logged={logged} path={path}", file=_sys.stderr)


def main() -> int:
    """cron entry — build → write → append history → emit alerts."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    payload = build()
    _write_json_atomic(OUTPUT_PATH, payload)
    history_logged = _append_history_jsonl(payload)
    alert_attempted = _emit_alerts(payload)
    diag = payload["diagnostics"]
    logger.info(
        "main: wrote %s (gu=%d complexes=%d ecos=%s kosis=%s rone_jeonse=%s rone_unsold=%s "
        "history_logged=%s alerts=%d)",
        OUTPUT_PATH, len(payload["gu_aggregates"]), len(payload["complexes"]),
        diag["ecos_available"], diag["kosis_available"],
        diag["rone_jeonse_available"], diag["rone_unsold_available"],
        history_logged, alert_attempted,
    )
    return 0


def _write_json_atomic(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


if __name__ == "__main__":
    raise SystemExit(main())
