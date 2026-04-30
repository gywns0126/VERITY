#!/usr/bin/env python3
"""LANDEX D (Development) 시점 민감도 검증 — v1.1 산식 robustness 확인.

목적:
  D 산식 v1.0 (12주/±0.5%p cap) 은 시점 1주 시프트로 30점 변동 — 합성 부적합 판정.
  v1.1 (26주/±2.0%p cap) 을 다른 as_of 시점으로 fetch 해서 *시점-시점 변동성* 직접 측정.
  baseline 없이 D 점수 자체의 stability 확인.

사용:
  python3 scripts/landex_d_stability.py
"""
from __future__ import annotations

import os
import sys
import time
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# .env 로드
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)

# vapi wrapping (run_landex_snapshot 동일 패턴)
VERCEL_API = ROOT / "vercel-api"
import importlib.util, types

api_pkg = types.ModuleType("vapi"); api_pkg.__path__ = [str(VERCEL_API / "api")]
sys.modules["vapi"] = api_pkg
landex_pkg = types.ModuleType("vapi.landex"); landex_pkg.__path__ = [str(VERCEL_API / "api" / "landex")]
sys.modules["vapi.landex"] = landex_pkg
sources_pkg = types.ModuleType("vapi.landex._sources")
sources_pkg.__path__ = [str(VERCEL_API / "api" / "landex" / "_sources")]
sys.modules["vapi.landex._sources"] = sources_pkg


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SD = VERCEL_API / "api" / "landex" / "_sources"
_load("vapi.landex._sources._lawd", SD / "_lawd.py")
rone = _load("vapi.landex._sources.rone", SD / "rone.py")
from vapi.landex._sources._lawd import SEOUL_25_GU


# 시점 — 4월 동안 1주 단위로 5개 샘플 (1주 시프트 민감도)
POINTS = [
    "202603W4",  # 3월 4주
    "202604W1",  # 4월 1주
    "202604W2",  # 4월 2주
    "202604W3",  # 4월 3주
    "202604W4",  # 4월 4주
]


def main():
    print(f"\n=== LANDEX D 시점 민감도 검증 (v1.1, 26주 윈도우, ±2.0%p cap) ===")
    print(f"시점: {POINTS}")
    print(f"구: {len(SEOUL_25_GU)}개")
    print(f"총 호출: {len(POINTS) * len(SEOUL_25_GU)} (예상 ~90초)\n")

    matrix: dict = {}
    t0 = time.time()
    for gu in SEOUL_25_GU:
        matrix[gu] = {}
        for p in POINTS:
            payload = rone.fetch_weekly_index(gu, weeks=26, as_of_yyyymmww=p)
            d = rone.compute_development_momentum_score(payload) if payload else None
            matrix[gu][p] = d
            time.sleep(0.15)
    elapsed = time.time() - t0
    print(f"[fetch] 완료 {elapsed:.1f}초\n")

    # 표 출력
    header = f"  {'구':6s}  " + "  ".join(f"{p:>8s}" for p in POINTS) + f"   {'1w_max|Δ|':>10s}  {'4w|Δ|':>7s}"
    print(header)
    one_week_diffs = []
    four_week_diffs = []
    for gu in SEOUL_25_GU:
        ds = matrix[gu]
        # 1주 시프트
        local_one_week = []
        for i in range(len(POINTS) - 1):
            a, b = ds[POINTS[i]], ds[POINTS[i + 1]]
            if a is not None and b is not None:
                local_one_week.append(abs(b - a))
        # 4주 시프트
        first, last = ds[POINTS[0]], ds[POINTS[-1]]
        four_w = abs(last - first) if first is not None and last is not None else None
        max_one = max(local_one_week) if local_one_week else None
        one_week_diffs.extend(local_one_week)
        if four_w is not None:
            four_week_diffs.append(four_w)

        def _fmt(x):
            return f"{x:>8.1f}" if x is not None else "    N/A"
        scores_s = "  ".join(_fmt(ds[p]) for p in POINTS)
        max_s = f"{max_one:>10.1f}" if max_one is not None else "       N/A"
        four_s = f"{four_w:>7.1f}" if four_w is not None else "    N/A"
        print(f"  {gu:6s}  {scores_s}   {max_s}  {four_s}")

    print()
    print("=== 요약 통계 ===")
    if one_week_diffs:
        print(f"  1주 시프트 D drift:  mean={statistics.mean(one_week_diffs):.2f}, "
              f"median={statistics.median(one_week_diffs):.2f}, "
              f"max={max(one_week_diffs):.2f}, n={len(one_week_diffs)}")
    if four_week_diffs:
        print(f"  4주 시프트 D drift:  mean={statistics.mean(four_week_diffs):.2f}, "
              f"median={statistics.median(four_week_diffs):.2f}, "
              f"max={max(four_week_diffs):.2f}, n={len(four_week_diffs)}")

    print()
    print("=== Verdict ===")
    mean_1w = statistics.mean(one_week_diffs) if one_week_diffs else None
    if mean_1w is None:
        print("⚠ 데이터 부족 — verdict 산출 불가")
    elif mean_1w < 5.0:
        print(f"✅ D v1.1 안정적 — 1주 시프트 평균 {mean_1w:.2f} < 5점")
        print(f"   → 백테스트 합성 D 산식 신뢰 가능")
    elif mean_1w < 10.0:
        print(f"⚠️ D v1.1 중간 안정성 — 1주 시프트 평균 {mean_1w:.2f} (5~10점)")
        print(f"   → V·R·S·C + D buffer 로 진행 권장")
    else:
        print(f"❌ D v1.1 여전히 시점 민감 — 1주 시프트 평균 {mean_1w:.2f} ≥ 10점")
        print(f"   → 산식 추가 변경 (52주 window? 또는 다른 형태) 필요")


if __name__ == "__main__":
    main()
