"""
estate_brain_backtest_50y_builder.py — 50년 backward 검증 cron (V0.3).

V0 backtest (R-ONE 13y, 2022 만 검증) 한계 돌파:
  - BIS FRED `QKRR628BIS` 1975~ 분기 (50년 backbone)
  - KOSIS-KB `101Y014` 1986~ 월 (40년, 권역 분리 가능)
  - 자동 cycle 감지 (drop > 10% & duration > 1y) → plan v0.3 5 패턴 매칭

검증 가능 (호출 3 결과):
  ① IMF 1997 (Shock-Recovery)         — BIS + KOSIS 둘 다 직접
  ② GFC 2008 (Debt-Deflation Drag)    — BIS + KOSIS 둘 다
  ③ Rate-Shock 2022~                  — BIS + KOSIS + R-ONE
  ④ Supply Glut 1990~95               — BIS + KOSIS (1986~)
  ⑤ Policy Shock 2003·2017            — BIS + KOSIS

Plan v0.3 Source 정합:
  - plan: docs/ESTATE_BRAIN_V0_PLAN.md §V0.3
  - constitution: data/estate_constitution.json cycle_analogs 5개

memory feedback_real_call_over_llm_consensus 정합 — 실 시계열로 plan LLM 가정 검증.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import math
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_REPO_ROOT, "data", "estate_brain_backtest_50y.json")

SCHEMA_VERSION = "v0.3"
KST = timezone(timedelta(hours=9))

# Plan v0.3 5 패턴 (constitution.json cycle_analogs 정합)
PLAN_V0_3_PATTERNS: List[Dict[str, Any]] = [
    {"name": "Shock-Recovery",      "year_label": "1997 IMF", "drop_pct": -12.4,
     "duration_months": 12, "shape": "V", "trigger_type": "external_crisis"},
    {"name": "Debt-Deflation Drag", "year_label": "2008 GFC", "drop_pct": -35.0,
     "duration_months": 72, "shape": "U", "trigger_type": "external_crisis"},
    {"name": "Rate-Shock Rebound",  "year_label": "2022~", "drop_pct": -17.2,
     "duration_months": 15, "shape": "V", "trigger_type": "rate_shock"},
    {"name": "Supply Glut",         "year_label": "1990~95", "drop_pct": -15.0,
     "duration_months": 65, "shape": "U", "trigger_type": "supply_overhang"},
    {"name": "Policy Shock",        "year_label": "2003+2017", "drop_pct": -5.0,
     "duration_months": 18, "shape": "W", "trigger_type": "regulatory_shock"},
]

KOSIS_REGION_CODES_V0 = ["00"]  # V0 = 전국만. V1 = 11(서울) / 41(경기) 등 추가


# ────────────────────────────────────────────────────────────
# 동적 import (project root 와 vercel-api 분리)

def _load_vercel_api_modules() -> Dict[str, Any]:
    sources_dir = os.path.join(_REPO_ROOT, "vercel-api", "api", "landex", "_sources")
    pkg_name = "estate_50y_runtime_sources"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [sources_dir]
    sys.modules[pkg_name] = pkg

    loaded: Dict[str, Any] = {}
    for mod_name in ("bis", "kosis"):
        path = os.path.join(sources_dir, f"{mod_name}.py")
        if not os.path.exists(path):
            continue
        spec = importlib.util.spec_from_file_location(f"{pkg_name}.{mod_name}", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"{pkg_name}.{mod_name}"] = mod
        spec.loader.exec_module(mod)
        loaded[mod_name] = mod
    return loaded


# ────────────────────────────────────────────────────────────
# Plan v0.3 정합 검증 — 자동 감지 cycle 중 plan 패턴 nearest 매칭

def _match_plan_to_detected(
    plan_pattern: Dict[str, Any],
    detected_cycles: List[Dict[str, Any]],
    drop_scale: float = 15.0,
    duration_scale: float = 30.0,
) -> Optional[Dict[str, Any]]:
    """plan 패턴 → 자동 감지 cycle list 중 nearest cycle 반환.

    distance = sqrt((drop_diff/scale_drop)² + (duration_diff/scale_duration)²).
    None = 감지 cycle 없음.
    """
    if not detected_cycles:
        return None
    best = None
    best_dist = float("inf")
    for c in detected_cycles:
        d_diff = abs(c["drop_pct"] - plan_pattern["drop_pct"]) / drop_scale
        t_diff = abs(c["duration_months"] - plan_pattern["duration_months"]) / duration_scale
        dist = math.sqrt(d_diff ** 2 + t_diff ** 2)
        if dist < best_dist:
            best_dist = dist
            best = c
    return {
        **best,
        "plan_match_distance": round(best_dist, 3),
    } if best else None


def _validate_plan_v0_3(
    detected_by_source: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """plan v0.3 5 패턴 각각의 자동 감지 매칭 (BIS / KOSIS 우선순위)."""
    out: Dict[str, Any] = {}
    for plan in PLAN_V0_3_PATTERNS:
        matched = None
        matched_source = None
        # BIS 우선 (50y 더 길어서 모든 패턴 cover) — 일치 안 하면 KOSIS
        for src in ("bis", "kosis_kb"):
            cycles = detected_by_source.get(src) or []
            m = _match_plan_to_detected(plan, cycles)
            if m and (matched is None or m["plan_match_distance"] < matched["plan_match_distance"]):
                matched = m
                matched_source = src

        within_drop = (
            abs(matched["drop_pct"] - plan["drop_pct"]) <= 10.0
            if matched else False
        )
        within_duration = (
            abs(matched["duration_months"] - plan["duration_months"]) <= 24
            if matched else False
        )

        out[plan["name"]] = {
            "plan": {
                "year_label": plan["year_label"],
                "expected_drop_pct": plan["drop_pct"],
                "expected_duration_months": plan["duration_months"],
                "expected_shape": plan["shape"],
                "trigger_type": plan["trigger_type"],
            },
            "matched": matched,
            "matched_source": matched_source,
            "within_tolerance_drop": within_drop,
            "within_tolerance_duration": within_duration,
            "within_tolerance_combined": within_drop and within_duration,
        }
    return out


# ────────────────────────────────────────────────────────────
# Source fetch + auto-detect + classify

def _fetch_and_detect(
    fetch_fn: Callable,
    period_per_year: int,
    bt_module: Any,
    drop_threshold_pct: float = -10.0,
    min_duration_periods: int = 4,
    label: str = "",
) -> Dict[str, Any]:
    try:
        payload = fetch_fn()
    except Exception as e:
        logger.warning("%s fetch 실패: %s", label, e)
        payload = None

    if not payload:
        return {"available": False, "n_points": 0, "cycles": []}

    series = payload.get("series") or []
    if not series:
        return {"available": True, "n_points": 0, "cycles": []}

    detected = bt_module.detect_cycles_auto(
        series, period_per_year=period_per_year,
        drop_threshold_pct=drop_threshold_pct,
        min_duration_periods=min_duration_periods,
    )
    classified = []
    for c in detected:
        cls = bt_module.classify_cycle_pattern(c)
        classified.append({**c, **cls})

    return {
        "available": True,
        "n_points": len(series),
        "first_label": series[0].get("date") or series[0].get("month") or series[0].get("quarter"),
        "last_label": series[-1].get("date") or series[-1].get("month") or series[-1].get("quarter"),
        "cycles": classified,
        "source": payload.get("source"),
        "as_of": payload.get("as_of"),
    }


def build(
    _modules: Optional[Dict[str, Any]] = None,
    _bt: Optional[Any] = None,
    _now: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = _now or datetime.now(KST)
    if _bt is None:
        from api.intelligence import estate_brain_backtest as _bt  # type: ignore
    modules = _modules if _modules is not None else _load_vercel_api_modules()
    bis = modules.get("bis")
    kosis = modules.get("kosis")

    # 1. BIS 50y 분기
    bis_block = _fetch_and_detect(
        lambda: bis.fetch_bis_korea_real_rppi() if bis else None,
        period_per_year=4,
        bt_module=_bt,
        min_duration_periods=4,  # 4 분기 = 1년
        label="BIS",
    )

    # 2. KOSIS-KB 40y 월 (V0 = 전국만)
    kosis_kb_blocks: Dict[str, Dict[str, Any]] = {}
    for region_code in KOSIS_REGION_CODES_V0:
        kosis_kb_blocks[region_code] = _fetch_and_detect(
            lambda rc=region_code: kosis.fetch_kb_house_price_index(region_code=rc) if kosis else None,
            period_per_year=12,
            bt_module=_bt,
            min_duration_periods=12,  # 12 개월 = 1년
            label=f"KOSIS_KB_{region_code}",
        )

    # 3. plan v0.3 5 패턴 정합
    detected_by_source = {
        "bis": bis_block.get("cycles", []),
        "kosis_kb": kosis_kb_blocks.get("00", {}).get("cycles", []),
    }
    plan_validation = _validate_plan_v0_3(detected_by_source)

    diagnostics = {
        "bis_available": bis_block.get("available", False),
        "bis_points": bis_block.get("n_points", 0),
        "bis_cycles_detected": len(bis_block.get("cycles", [])),
        "kosis_kb_available": kosis_kb_blocks.get("00", {}).get("available", False),
        "kosis_kb_points": kosis_kb_blocks.get("00", {}).get("n_points", 0),
        "kosis_kb_cycles_detected": len(kosis_kb_blocks.get("00", {}).get("cycles", [])),
        "plan_patterns_count": len(PLAN_V0_3_PATTERNS),
        "plan_within_tolerance_count": sum(
            1 for v in plan_validation.values()
            if v.get("within_tolerance_combined")
        ),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(timespec="seconds"),
        "scope": "v0_3_50y_5pattern",
        "covered_periods": ["1975~2025 (BIS)", "1986~ (KOSIS-KB)"],
        "bis_50y": bis_block,
        "kosis_kb_40y": kosis_kb_blocks,
        "plan_v0_3_validation": plan_validation,
        "diagnostics": diagnostics,
        "model_meta": {
            "version": "v0_3_hardcoded",
            "source": "cron_backtest_50y_builder",
            "plan_source": "Plan v0.3 (Perplexity 2026-05-09 호출 3 결과 흡수)",
            "v1_gates": [
                "권역 분리 (KOSIS L2 5권역 / L3 시도 region_code 검증 후)",
                "BIS 명목 RPPI 시리즈 ID 추가 (실질만 V0.3)",
                "Decoupling 패턴 (V2) — 수도권 vs 지방 cross-correlation",
                "regime-aware signal hit rate (PIR z + 전세가율 + Cap 역전)",
            ],
        },
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    payload = build()
    _write_json_atomic(OUTPUT_PATH, payload)
    diag = payload["diagnostics"]
    logger.info(
        "main: wrote %s (BIS pts=%d cycles=%d / KOSIS-KB pts=%d cycles=%d / plan match=%d/5)",
        OUTPUT_PATH, diag["bis_points"], diag["bis_cycles_detected"],
        diag["kosis_kb_points"], diag["kosis_kb_cycles_detected"],
        diag["plan_within_tolerance_count"],
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
