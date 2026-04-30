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

import os
import sys
import statistics
import time
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

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
    print(f"\n=== Verdict ===")
    if landex_md is None:
        print("⚠ LANDEX drift 산출 불가 — 데이터 부족")
    elif landex_md < 2.0 and tier_rate < 20.0:
        print(f"✅ 합성 가능")
        print(f"   LANDEX mean|Δ|={landex_md:.2f} < 2.0, tier 변동 {tier_rate:.1f}% < 20%")
        print(f"   V mean|Δ|={v_md:.2f} (후행 등록 noise 수준)")
        print(f"   → 백테스트 v0-mid 진입 권장")
    elif landex_md < 5.0 and tier_rate < 40.0:
        print(f"⚠️ 부분 가능")
        print(f"   LANDEX mean|Δ|={landex_md:.2f}, tier 변동 {tier_rate:.1f}%")
        print(f"   → V·R 한정 + ±2점 buffer 로 v0 진입 권장")
    else:
        print(f"❌ 합성 불가")
        print(f"   LANDEX mean|Δ|={landex_md:.2f}, tier 변동 {tier_rate:.1f}%")
        print(f"   → Vintage Retrieval 인프라 (raw 보존 마이그레이션) 우선")


if __name__ == "__main__":
    main()
