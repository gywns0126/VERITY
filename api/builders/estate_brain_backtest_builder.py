"""
estate_brain_backtest_builder.py — V0 backward 검증 cron.

V0 검증 가능 (R-ONE 매매가격지수 2012~ 만 보유):
  ① 2022 Rate-Shock Rebound 사이클 — peak → trough drop 정합 (plan v0.2 -20%)
  ② 25구 × 5년 forward return 분포
  ③ 권역별 cumulative return — 핵심지(강남3구) 선행 검증

V0 검증 불가 (R-ONE 데이터 부재):
  ❌ 1997 IMF Shock-Recovery (R-ONE 데이터 2012~)
  ❌ 2008 GFC Debt-Deflation Drag (R-ONE 데이터 2012~)
  → plan v0.2 외부 출처 (KB·부동산원 보고서) 만 reference, 산식 직접 검증 X

V1 게이트 (사용자 secret 박힌 후):
  - 미분양 yoy → 6M 후 가격 변동 hit (R-ONE 미분양 데이터 fetch 가능)
  - PIR z + 전세가율 < 50 + Cap 역전 retrospective (KOSIS / 전세 statId 필요)

흐름 (estate_brain_builder 패턴 정합):
  1. 25구 R-ONE 매매가격지수 5년 (260 weeks) fetch
  2. 서울 평균 시계열 합성 (25구 단순 평균)
  3. cycle_analog 정합 — 2022 sub-window peak→trough drop
  4. 25구별 12M forward return (=52w) 분포
  5. atomic write → data/estate_brain_backtest.json
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from statistics import mean, median, stdev
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_REPO_ROOT, "data", "estate_brain_backtest.json")

SCHEMA_VERSION = "v0"
KST = timezone(timedelta(hours=9))

SEOUL_25_GU = [
    "종로구", "중구", "용산구", "성동구", "광진구", "동대문구",
    "중랑구", "성북구", "강북구", "도봉구", "노원구",
    "은평구", "서대문구", "마포구", "양천구", "강서구",
    "구로구", "금천구", "영등포구", "동작구", "관악구",
    "서초구", "강남구", "송파구", "강동구",
]
CORE_REGION = ("강남구", "서초구", "송파구", "마포구", "용산구", "성동구")  # 강남3구·마용성

# Plan v0.2 cycle_analog drop assumption (도쿄 사이클 검증 reference)
PLAN_DROPS_BY_PATTERN = {
    "Shock-Recovery": -18.2,        # 1997 IMF (R-ONE 부재 — 외부 reference)
    "Debt-Deflation Drag": -12.0,   # 2008 GFC (R-ONE 부재 — 외부 reference)
    "Rate-Shock Rebound": -20.0,    # 2022~ (R-ONE 으로 직접 검증)
}


def _load_vercel_api_modules() -> Dict[str, Any]:
    sources_dir = os.path.join(_REPO_ROOT, "vercel-api", "api", "landex", "_sources")
    pkg_name = "estate_backtest_runtime_sources"
    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [sources_dir]
    sys.modules[pkg_name] = pkg

    loaded: Dict[str, Any] = {}
    for mod_name in ("_lawd", "rone"):
        path = os.path.join(sources_dir, f"{mod_name}.py")
        if not os.path.exists(path):
            continue
        spec = importlib.util.spec_from_file_location(f"{pkg_name}.{mod_name}", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"{pkg_name}.{mod_name}"] = mod
        spec.loader.exec_module(mod)
        loaded[mod_name] = mod
    return loaded


def _compute_seoul_avg_series(
    indices_by_gu: Dict[str, Optional[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """25구 매매지수 시계열 → 서울 평균 시계열 (단순 산술 평균).

    각 시점 (week) 에서 25구 중 데이터 있는 구 평균. 권역 가중치는 V1.
    """
    week_to_values: Dict[str, List[float]] = {}
    for gu, payload in indices_by_gu.items():
        if not payload:
            continue
        for row in payload.get("series") or []:
            wk = row.get("week")
            val = row.get("index")
            if wk and val is not None:
                week_to_values.setdefault(wk, []).append(val)

    out = []
    for wk in sorted(week_to_values.keys()):
        vals = week_to_values[wk]
        if vals:
            out.append({"week": wk, "index": round(mean(vals), 3),
                        "n_gu": len(vals)})
    return out


def _compute_per_gu_returns(
    indices_by_gu: Dict[str, Optional[Dict[str, Any]]],
    horizon_weeks: int,
    bt_module: Any,
) -> Dict[str, Dict[str, Any]]:
    """25구 별 12M forward return 통계 (mean / median / std).

    각 구의 시계열 첫 시점 → +52w return 만 (단일값) — V0 단순화.
    V1 = 모든 시점 forward return 분포.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for gu, payload in indices_by_gu.items():
        if not payload:
            out[gu] = {"return_pct": None, "available": False}
            continue
        series = payload.get("series") or []
        rets = bt_module.compute_forward_return_pct(series, horizon_weeks=horizon_weeks)
        valid = [r for r in rets if r is not None]
        if not valid:
            out[gu] = {"return_pct": None, "available": False}
            continue
        out[gu] = {
            "first_t_return_pct": valid[0] if valid else None,
            "mean_return_pct": round(mean(valid), 2),
            "median_return_pct": round(median(valid), 2),
            "std_pp": round(stdev(valid), 2) if len(valid) >= 2 else None,
            "n_observations": len(valid),
            "available": True,
        }
    return out


def _compute_core_vs_noncore_drop(
    indices_by_gu: Dict[str, Optional[Dict[str, Any]]],
    bt_module: Any,
) -> Dict[str, Any]:
    """핵심지(강남3구·마용성) vs 비핵심지 peak→trough drop 비교.

    plan v0.2 §3 공통 패턴 검증: 핵심지 *먼저 저점 → 먼저 회복*.
    """
    core_drops = []
    non_core_drops = []
    for gu, payload in indices_by_gu.items():
        if not payload:
            continue
        d = bt_module.compute_drop_from_peak_pct(payload.get("series") or [])
        if d is None:
            continue
        if gu in CORE_REGION:
            core_drops.append(d)
        else:
            non_core_drops.append(d)
    return {
        "core_mean_drop_pct": round(mean(core_drops), 2) if core_drops else None,
        "core_n": len(core_drops),
        "non_core_mean_drop_pct": round(mean(non_core_drops), 2) if non_core_drops else None,
        "non_core_n": len(non_core_drops),
        "core_outperform": (
            (mean(non_core_drops) < mean(core_drops))
            if (core_drops and non_core_drops) else None
        ),
        "_note": "drop 은 음수 — core_mean > non_core_mean 이면 핵심지가 덜 떨어졌다는 의미",
    }


def build(
    weeks: int = 260,  # 5년 = 2022 Rate-Shock 사이클 cover
    horizon_weeks: int = 52,
    _modules: Optional[Dict[str, Any]] = None,
    _bt: Optional[Any] = None,
    _now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """V0 backtest payload."""
    now = _now or datetime.now(KST)
    if _bt is None:
        from api.intelligence import estate_brain_backtest as _bt  # type: ignore
    modules = _modules if _modules is not None else _load_vercel_api_modules()
    rone = modules.get("rone")

    # 1. 25구 매매가격지수 fetch
    indices_by_gu: Dict[str, Optional[Dict[str, Any]]] = {}
    for gu in SEOUL_25_GU:
        try:
            indices_by_gu[gu] = rone.fetch_weekly_index(gu, weeks=weeks) if rone else None
        except Exception as e:
            logger.warning("rone fetch 실패 %s: %s", gu, e)
            indices_by_gu[gu] = None

    # 2. 서울 평균 시계열
    seoul_avg = _compute_seoul_avg_series(indices_by_gu)

    # 3. cycle_analog 2022 정합
    seoul_drop = _bt.compute_drop_from_peak_pct(seoul_avg)
    cycle_validation = _bt.validate_cycle_analog(
        actual_drops_by_period={"2022": seoul_drop} if seoul_drop is not None else {},
        plan_drops_by_pattern=PLAN_DROPS_BY_PATTERN,
        tolerance_pct=5.0,
    )

    # 4. 25구 forward return 통계
    per_gu_returns = _compute_per_gu_returns(indices_by_gu, horizon_weeks, _bt)

    # 5. 핵심지 vs 비핵심지
    core_vs_noncore = _compute_core_vs_noncore_drop(indices_by_gu, _bt)

    diagnostics = {
        "rone_available": any(p is not None for p in indices_by_gu.values()),
        "gu_with_data": sum(1 for p in indices_by_gu.values() if p is not None),
        "weeks_requested": weeks,
        "seoul_avg_points": len(seoul_avg),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(timespec="seconds"),
        "scope": "v0_partial",
        "covered_periods": ["2022~"],
        "uncovered_periods_external_only": ["1997", "2008"],
        "cycle_analog_validation": cycle_validation,
        "per_gu_forward_returns": per_gu_returns,
        "core_vs_noncore": core_vs_noncore,
        "seoul_avg_drop_from_peak_pct": seoul_drop,
        "diagnostics": diagnostics,
        "model_meta": {
            "version": "v0_hardcoded",
            "source": "cron_backtest_builder",
            "plan_drops_source": "Plan v0.2 §3 cycle_analog (Perplexity 2026-05-08 + 외부 보고서)",
            "v1_gates": [
                "미분양 yoy → 6M 가격 lag (R-ONE 미분양 추가 fetch)",
                "PIR z 신호 retrospective (KOSIS statId 박힌 후)",
                "전세가율 < 50 신호 (R-ONE 전세 statId 박힌 후)",
                "단지 단위 forward 검증 (운영 누적 6-12M)",
            ],
        },
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    payload = build()
    _write_json_atomic(OUTPUT_PATH, payload)
    diag = payload["diagnostics"]
    cv = payload["cycle_analog_validation"].get("Rate-Shock Rebound")
    logger.info(
        "main: wrote %s (gu=%d/25 drop=%s plan=%s within_tol=%s)",
        OUTPUT_PATH, diag["gu_with_data"],
        cv.get("actual_drop_pct") if cv else None,
        cv.get("plan_drop_pct") if cv else None,
        cv.get("within_tolerance") if cv else None,
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
