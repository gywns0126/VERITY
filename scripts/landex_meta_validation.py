#!/usr/bin/env python3
"""LANDEX 메타-검증 — Supabase baseline vs as_of 시점 재계산 합성 결과 drift 측정.

목적:
  estate_landex_snapshots 의 실측 점수 (baseline) 와 동일 시점 *합성 룰로 재계산한* 점수
  (synthetic) 의 drift 측정. 12년치 백테스트 합성의 가/부 결정 근거.

  - V (MOLIT): 후행 등록으로 raw 데이터 변동 가능 → 진짜 검증 가능
  - R (ECOS): as_of_yyyymm 으로 과거 시점 fetch — 결정적 (drift ≈ 0 기대)
  - D/S (R-ONE): as_of_yyyymmww/as_of_yyyymm cutoff — 결정적 (drift ≈ 0 기대)
  - C (서울 지하철): 시점 의존 fetch 불가 — drift 0 자동 (검증 의미 X)

사용:
  python3 scripts/landex_meta_validation.py 2026-04 [--preset balanced]

Verdict 임계 (3자 LLM 합의 기반):
  ✅ LANDEX mean|Δ| < 2.0 + tier 변동 < 20% → 백테스트 v0-mid 진입
  ⚠️  LANDEX mean|Δ| < 5.0 + tier 변동 < 40% → V·R 한정 + buffer
  ❌  그 외 → Vintage Retrieval 인프라 우선
"""
from __future__ import annotations

import json
import os
import sys
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
HEALTH_PATH = ROOT / "data" / "metadata" / "estate_system_health.json"
STABILITY_BUFFER_WEEKS = 3
RECENT_VERDICTS_KEEP = 10
KST = timezone(timedelta(hours=9))

# 1) .env 로드
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)

# 2) sys.path 로 vercel-api 모듈 wrapping (run_landex_snapshot.py 와 동일 패턴)
VERCEL_API = ROOT / "vercel-api"

import importlib.util
import types

api_pkg = types.ModuleType("vapi"); api_pkg.__path__ = [str(VERCEL_API / "api")]
sys.modules["vapi"] = api_pkg

landex_pkg = types.ModuleType("vapi.landex"); landex_pkg.__path__ = [str(VERCEL_API / "api" / "landex")]
sys.modules["vapi.landex"] = landex_pkg

sources_pkg = types.ModuleType("vapi.landex._sources")
sources_pkg.__path__ = [str(VERCEL_API / "api" / "landex" / "_sources")]
sys.modules["vapi.landex._sources"] = sources_pkg


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {name} from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SD = VERCEL_API / "api" / "landex" / "_sources"
LD = VERCEL_API / "api" / "landex"

_load("vapi.landex._sources._lawd",        SD / "_lawd.py")
_load("vapi.landex._sources.molit",        SD / "molit.py")
_load("vapi.landex._sources.ecos",         SD / "ecos.py")
_load("vapi.landex._sources.seoul_subway", SD / "seoul_subway.py")
_load("vapi.landex._sources.rone",         SD / "rone.py")
_load("vapi.landex._methodology",          LD / "_methodology.py")
_load("vapi.landex._compute",              LD / "_compute.py")

snapshot_src = (LD / "_snapshot.py").read_text()
snapshot_src = snapshot_src.replace("from . import _methodology as M", "from vapi.landex import _methodology as M")
snapshot_src = snapshot_src.replace("from ._compute import", "from vapi.landex._compute import")
snapshot_src = snapshot_src.replace("from ._sources._lawd import", "from vapi.landex._sources._lawd import")
snapshot_src = snapshot_src.replace("from ._sources import", "from vapi.landex._sources import")

snap_module = types.ModuleType("vapi.landex._snapshot")
snap_module.__file__ = str(LD / "_snapshot.py")
sys.modules["vapi.landex._snapshot"] = snap_module
exec(compile(snapshot_src, str(LD / "_snapshot.py"), "exec"), snap_module.__dict__)


# 3) 메타-검증 본체
import requests


def fetch_baseline(month: str, preset: str = "balanced", methodology_version: Optional[str] = None) -> list[dict]:
    """Supabase 에서 baseline snapshot fetch.

    methodology_version 지정 시 그 version 만 fetch (default: synthetic 산식 version 일치).
    같은 gu 의 중복은 가장 최근 computed_at 만 keep.
    """
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_ANON_KEY 미설정")
    endpoint = f"{url}/rest/v1/estate_landex_snapshots"
    params = {
        "month": f"eq.{month}",
        "preset": f"eq.{preset}",
        "select": "*",
        "order": "computed_at.desc",
    }
    if methodology_version:
        params["methodology_version"] = f"eq.{methodology_version}"
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    r = requests.get(endpoint, headers=headers, params=params, timeout=15)
    r.raise_for_status()
    rows = r.json()
    by_gu: dict = {}
    for row in rows:  # 이미 computed_at desc 정렬 — 첫 등장이 최신
        gu = row["gu"]
        if gu not in by_gu:
            by_gu[gu] = row
    return list(by_gu.values())


def _diff(b: dict, s: dict, key: str) -> Optional[float]:
    bv = b.get(key)
    sv = s.get(key)
    if bv is None or sv is None:
        return None
    return float(sv) - float(bv)


def _abs_mean(diffs):
    valid = [abs(d) for d in diffs if d is not None]
    return statistics.mean(valid) if valid else None


def _max_abs(diffs):
    valid = [abs(d) for d in diffs if d is not None]
    return max(valid) if valid else None


def _signed_mean(diffs):
    valid = [d for d in diffs if d is not None]
    return statistics.mean(valid) if valid else None


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/landex_meta_validation.py YYYY-MM [--preset balanced]", file=sys.stderr)
        sys.exit(1)
    month = sys.argv[1]
    preset = "balanced"
    if "--preset" in sys.argv:
        idx = sys.argv.index("--preset")
        if idx + 1 < len(sys.argv):
            preset = sys.argv[idx + 1]
    as_of_yyyymm = month.replace("-", "")

    print(f"\n=== LANDEX 메타-검증 ===")
    print(f"month={month} preset={preset} as_of_yyyymm={as_of_yyyymm}")
    print(f"REB_API_KEY: {bool(os.environ.get('REB_API_KEY'))}, "
          f"ECOS_API_KEY: {bool(os.environ.get('ECOS_API_KEY'))}, "
          f"SUPABASE_URL: {bool(os.environ.get('SUPABASE_URL'))}\n")

    methodology_module = sys.modules.get("vapi.landex._methodology")
    methodology_version = getattr(methodology_module, "VERSION", None)
    print(f"[1/3] Supabase baseline fetch (version={methodology_version})...")
    baseline = fetch_baseline(month, preset, methodology_version=methodology_version)
    print(f"  → {len(baseline)} 행")
    if not baseline:
        print("ERR: baseline 비어있음 — scripts/run_landex_snapshot.py 먼저 실행", file=sys.stderr)
        sys.exit(1)

    print(f"\n[2/3] Synthetic 재계산 (as_of_yyyymm={as_of_yyyymm})...")
    t0 = time.time()
    synthetic = snap_module.compute_snapshot(month, preset=preset, as_of_yyyymm=as_of_yyyymm)
    elapsed = time.time() - t0
    print(f"  → {len(synthetic)} 행, {elapsed:.1f}초\n")

    print("[3/3] 25구 비교...\n")
    by_gu_b = {b["gu"]: b for b in baseline}
    fields = ["v_score", "d_score", "s_score", "c_score", "r_score", "landex"]
    diffs_per_field = {f: [] for f in fields}
    tier_change = 0
    rows_print = []

    for s in synthetic:
        gu = s["gu"]
        b = by_gu_b.get(gu)
        if b is None:
            continue
        per_field = {f: _diff(b, s, f) for f in fields}
        for f in fields:
            diffs_per_field[f].append(per_field[f])
        b_t, s_t = b.get("tier10"), s.get("tier10")
        changed = (b_t != s_t)
        if changed:
            tier_change += 1
        rows_print.append({
            "gu": gu,
            "b_landex": b.get("landex"),
            "s_landex": s.get("landex"),
            "diff": per_field["landex"],
            "b_tier": b_t, "s_tier": s_t, "changed": changed,
            "v_diff": per_field["v_score"],
            "d_diff": per_field["d_score"],
            "s_diff": per_field["s_score"],
            "c_diff": per_field["c_score"],
            "r_diff": per_field["r_score"],
        })

    # 표 출력
    rows_print.sort(key=lambda r: abs(r["diff"] or 0), reverse=True)
    print(f"  {'구':6s} {'B_LDX':>7s} {'S_LDX':>7s} {'Δ':>7s}  {'B/S_T':>7s}  "
          f"{'V_Δ':>6s} {'D_Δ':>6s} {'S_Δ':>6s} {'C_Δ':>6s} {'R_Δ':>6s}")
    for r in rows_print:
        diff = r["diff"]
        diff_s = f"{diff:+.2f}" if diff is not None else "  N/A"
        tier_s = f"{r['b_tier'] or '-'}/{r['s_tier'] or '-'}{'*' if r['changed'] else ''}"
        def _fmt(x):
            return f"{x:+6.1f}" if x is not None else "   N/A"
        print(f"  {r['gu']:6s} "
              f"{(r['b_landex'] or 0):>7.2f} {(r['s_landex'] or 0):>7.2f} "
              f"{diff_s:>7s}  {tier_s:>7s}  "
              f"{_fmt(r['v_diff'])} {_fmt(r['d_diff'])} {_fmt(r['s_diff'])} "
              f"{_fmt(r['c_diff'])} {_fmt(r['r_diff'])}")

    print()
    print("=== 요약 통계 ===")
    for f in fields:
        ab = _abs_mean(diffs_per_field[f])
        mx = _max_abs(diffs_per_field[f])
        sg = _signed_mean(diffs_per_field[f])
        n = sum(1 for d in diffs_per_field[f] if d is not None)
        ab_s = f"{ab:.2f}" if ab is not None else "N/A"
        mx_s = f"{mx:.2f}" if mx is not None else "N/A"
        sg_s = f"{sg:+.2f}" if sg is not None else "N/A"
        print(f"  {f:10s}  mean|Δ|={ab_s:>6s}  max|Δ|={mx_s:>6s}  signed mean={sg_s:>7s}  (n={n}/25)")

    tier_rate = tier_change / len(rows_print) * 100 if rows_print else 0
    print(f"\n  tier 변동: {tier_change}/{len(rows_print)} 구 ({tier_rate:.1f}%)")

    # Verdict
    landex_md = _abs_mean(diffs_per_field["landex"])
    v_md = _abs_mean(diffs_per_field["v_score"])
    verdict = _compute_verdict(landex_md, tier_rate)
    print(f"\n=== Verdict ===")
    if verdict == "unknown":
        print("⚠ LANDEX drift 산출 불가 — 데이터 부족")
    elif verdict == "ready":
        print(f"✅ 합성 가능 (verdict=ready)")
        print(f"   LANDEX mean|Δ|={landex_md:.2f} < 2.0, tier 변동 {tier_rate:.1f}% < 20%")
        print(f"   V mean|Δ|={v_md:.2f} (후행 등록 noise 수준)")
        print(f"   → 백테스트 v0-mid 진입 권장")
    elif verdict == "manual_review":
        print(f"⚠️ 부분 가능 (verdict=manual_review)")
        print(f"   LANDEX mean|Δ|={landex_md:.2f}, tier 변동 {tier_rate:.1f}%")
        print(f"   → V·R 한정 + ±2점 buffer 로 v0 진입 권장 + 의심 팩터 0.5x soft penalty (5/5 후 도입)")
    else:  # invalidated
        print(f"❌ 합성 불가 (verdict=invalidated)")
        print(f"   LANDEX mean|Δ|={landex_md:.2f}, tier 변동 {tier_rate:.1f}%")
        print(f"   → 산식 변경 동결 + 롤백 검토 + Vintage Retrieval 인프라 우선")

    # estate_system_health.json 갱신 (3주 stability buffer 적용)
    metrics = {
        "landex_mean_drift": _round(landex_md, 2),
        "tier_change_rate": round(tier_rate, 1),
        "tier_change_count": tier_change,
        "per_field_mean_drift": {
            f: _round(_abs_mean(diffs_per_field[f]), 2) for f in fields if f != "landex"
        },
    }
    _update_system_health(verdict, metrics, len(rows_print))


def _compute_verdict(landex_md: Optional[float], tier_rate: float) -> str:
    """v0 임계 — landex_meta_validation 산식. 5/5 실측 후 재조정 검토 (feedback_real_call_over_llm_consensus)."""
    if landex_md is None:
        return "unknown"
    if landex_md < 2.0 and tier_rate < 20.0:
        return "ready"
    if landex_md < 5.0 and tier_rate < 40.0:
        return "manual_review"
    return "invalidated"


def _round(x: Optional[float], n: int) -> Optional[float]:
    return None if x is None else round(x, n)


def _apply_stability_buffer(prev: dict, latest: str) -> tuple[str, int]:
    """3주 stability buffer — 단발 false alarm 흡수.

    규칙:
      - latest=ready          → counter=0, active=ready (즉시 해제)
      - latest=unknown        → 상태 유지 (측정 실패)
      - latest=비-ready       → 같은 verdict 연속 시 counter+1, 다르면 counter=1 (리셋)
                                counter >= STABILITY_BUFFER_WEEKS 시만 active 승격
                                미만이면 prev_active 유지

    Returns: (new_active_verdict, new_counter)
    """
    prev_active = prev.get("active_verdict", "ready")
    prev_counter = int(prev.get("stability_counter", 0) or 0)
    prev_latest = prev.get("latest_verdict", "unknown")

    if latest == "ready":
        return "ready", 0
    if latest == "unknown":
        return prev_active, prev_counter
    # 비-ready (manual_review or invalidated)
    new_counter = (prev_counter + 1) if prev_latest == latest else 1
    if new_counter >= STABILITY_BUFFER_WEEKS:
        return latest, new_counter
    return prev_active, new_counter


def _update_system_health(verdict: str, metrics: dict, sample_n: int) -> None:
    """estate_system_health.json 의 meta_validation 섹션 갱신. sources 섹션은 건드리지 않음.
    Telegram 미연동 — ESTATE 는 주/월 단위 의사결정 도구라 즉시성 가치 낮음. user 는 매주 화
    cron 결과를 *직접* 점검(action_log). 외부 시장 충격 알림은 별도 인프라 (estate_alerts 등)."""
    try:
        if HEALTH_PATH.exists():
            data = json.loads(HEALTH_PATH.read_text(encoding="utf-8"))
        else:
            data = {"_schema_version": "1.0", "sources": {}, "meta_validation": {}}

        prev_meta = data.get("meta_validation") or {}
        new_active, new_counter = _apply_stability_buffer(prev_meta, verdict)

        now_kst = datetime.now(KST).isoformat(timespec="seconds")
        recent = list(prev_meta.get("recent_verdicts") or [])
        recent.append({
            "run_at": now_kst,
            "verdict": verdict,
            "tier_change_rate": metrics["tier_change_rate"],
            "tier_change_count": metrics["tier_change_count"],
            "landex_mean_drift": metrics["landex_mean_drift"],
            "sample_n": sample_n,
        })
        recent = recent[-RECENT_VERDICTS_KEEP:]

        data["meta_validation"] = {
            "last_run_at": now_kst,
            "latest_verdict": verdict,
            "active_verdict": new_active,
            "stability_counter": new_counter,
            "metrics": metrics,
            "recent_verdicts": recent,
        }
        data["generated_at"] = now_kst
        data["overall_status"] = _overall_status(data)

        HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
        HEALTH_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"\n  → estate_system_health.json 갱신 (verdict={verdict}, "
              f"active={new_active}, stability_counter={new_counter})")
    except Exception as e:
        # health.json 갱신 실패가 검증 자체를 죽이지 않게
        print(f"\n⚠ estate_system_health.json 갱신 실패: {e}", file=sys.stderr)


def _overall_status(data: dict) -> str:
    """sources status 의 worst + meta_validation.active_verdict 결합.

    우선순위: critical > warning > ok > unknown
    invalidated 는 critical 등급, manual_review 는 warning, ready 는 ok.
    """
    src_worst = "ok"
    for src in (data.get("sources") or {}).values():
        if not isinstance(src, dict):
            continue
        s = src.get("status", "unknown")
        src_worst = _worst_status(src_worst, s)

    active = (data.get("meta_validation") or {}).get("active_verdict", "ready")
    verdict_status = {
        "ready": "ok", "manual_review": "warning", "invalidated": "critical",
        "unknown": "unknown",
    }.get(active, "unknown")

    return _worst_status(src_worst, verdict_status)


def _worst_status(a: str, b: str) -> str:
    order = {"unknown": 0, "ok": 1, "warning": 2, "critical": 3}
    return a if order.get(a, 0) >= order.get(b, 0) else b


if __name__ == "__main__":
    main()
