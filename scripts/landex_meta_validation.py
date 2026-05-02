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
SILENT_METRICS_LOG = ROOT / "data" / "metadata" / "landex_meta_validation.jsonl"
STABILITY_BUFFER_WEEKS = 3
RECENT_VERDICTS_KEEP = 10
KST = timezone(timedelta(hours=9))

# ─────────────────────────────────────────────────────────────────────
# D3 silent 측정 — 5/12 결정 사전 준비 (2026-05-02)
# 운영 임계 / verdict / cron return 값 변경 X. silent jsonl 기록만.
# 사양: docs/ESTATE_VALIDATION_METRICS.md
# RUNBOOK: docs/LANDEX_VALIDATION_RUNBOOK_5_12.md
# ─────────────────────────────────────────────────────────────────────
SILENT_HORIZON_WEEKS = 13                # T+13주 forward return
SILENT_THR_SPEARMAN_IC = 0.10
SILENT_THR_SPEARMAN_PVAL = 0.10
SILENT_THR_RMSE_RATIO = 0.5              # market_volatility × 0.5
SILENT_THR_DIRECTION_ACC = 0.60
SILENT_THR_QUINTILE_SPREAD_PCT = 1.0
SILENT_THR_P0_PASS_OF_4 = 3              # 4중 3 통과

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


# ─────────────────────────────────────────────────────────────────────
# D3 silent 메트릭 헬퍼 (운영 verdict 미터치, jsonl 기록만)
# ─────────────────────────────────────────────────────────────────────
def _spearman_rank_ic(scores: list, returns: list) -> tuple[Optional[float], Optional[float]]:
    """Spearman rank correlation (statistic, pvalue). scipy 의존성 회피용 자체 구현.

    동률 처리: average rank (scipy.stats.rankdata 와 동일).
    p-value: t 분포 근사 (n>=10).
    """
    valid = [(s, r) for s, r in zip(scores, returns) if s is not None and r is not None]
    n = len(valid)
    if n < 3:
        return None, None
    s_vals = [v[0] for v in valid]
    r_vals = [v[1] for v in valid]
    s_ranks = _rankdata(s_vals)
    r_ranks = _rankdata(r_vals)
    # Pearson on ranks = Spearman
    mean_s = sum(s_ranks) / n
    mean_r = sum(r_ranks) / n
    cov = sum((s_ranks[i] - mean_s) * (r_ranks[i] - mean_r) for i in range(n)) / n
    var_s = sum((x - mean_s) ** 2 for x in s_ranks) / n
    var_r = sum((x - mean_r) ** 2 for x in r_ranks) / n
    if var_s == 0 or var_r == 0:
        return 0.0, 1.0
    rho = cov / ((var_s * var_r) ** 0.5)
    rho = max(-1.0, min(1.0, rho))
    # p-value (t 근사) — n=25 에서 |rho|=0.40 → t≈2.07 → p≈0.05
    if n > 2 and abs(rho) < 1.0:
        t = rho * ((n - 2) / max(1e-12, 1 - rho ** 2)) ** 0.5
        p = _two_sided_pvalue_t(t, n - 2)
    else:
        p = 0.0 if abs(rho) >= 1.0 else 1.0
    return round(rho, 4), round(p, 4)


def _rankdata(values: list) -> list:
    """Average rank (scipy.stats.rankdata equivalent)."""
    n = len(values)
    sorted_pairs = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sorted_pairs[j + 1][1] == sorted_pairs[i][1]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-based
        for k in range(i, j + 1):
            ranks[sorted_pairs[k][0]] = avg_rank
        i = j + 1
    return ranks


def _two_sided_pvalue_t(t: float, df: int) -> float:
    """t 분포 양측 p-value 근사 (Abramowitz-Stegun). scipy 회피."""
    import math
    if df <= 0:
        return 1.0
    x = df / (df + t * t)
    a = df / 2
    b = 0.5
    # Incomplete beta 근사 (Stirling-like)
    # 본격 산출은 scipy.stats.t.sf 와 차이 가능 — silent 메트릭 용도라 근사 수용
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        ibeta = bt * _betacf(x, a, b) / a
    else:
        ibeta = 1.0 - bt * _betacf(1 - x, b, a) / b
    return min(1.0, max(0.0, ibeta))


def _betacf(x: float, a: float, b: float, max_iter: int = 100) -> float:
    """Continued fraction for incomplete beta (Numerical Recipes)."""
    eps = 3e-7
    qab = a + b; qap = a + 1; qam = a - 1
    c = 1.0
    d = 1 - qab * x / qap
    if abs(d) < 1e-30: d = 1e-30
    d = 1 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        if abs(d) < 1e-30: d = 1e-30
        c = 1 + aa / c
        if abs(c) < 1e-30: c = 1e-30
        d = 1 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        if abs(d) < 1e-30: d = 1e-30
        c = 1 + aa / c
        if abs(c) < 1e-30: c = 1e-30
        d = 1 / d
        delt = d * c
        h *= delt
        if abs(delt - 1.0) < eps: break
    return h


def _rmse(scores: list, returns: list) -> tuple[Optional[float], Optional[float]]:
    """RMSE (z-score 정규화 후) + market_volatility (= actual std).

    Returns (rmse_normalized, market_volatility_pct).
    """
    valid = [(s, r) for s, r in zip(scores, returns) if s is not None and r is not None]
    n = len(valid)
    if n < 2:
        return None, None
    s_vals = [v[0] for v in valid]
    r_vals = [v[1] for v in valid]
    mean_s = sum(s_vals) / n
    mean_r = sum(r_vals) / n
    var_s = sum((x - mean_s) ** 2 for x in s_vals) / n
    var_r = sum((x - mean_r) ** 2 for x in r_vals) / n
    if var_s == 0 or var_r == 0:
        return None, round(var_r ** 0.5, 4)
    s_norm = [(x - mean_s) / (var_s ** 0.5) for x in s_vals]
    r_norm = [(x - mean_r) / (var_r ** 0.5) for x in r_vals]
    sq_err = sum((s_norm[i] - r_norm[i]) ** 2 for i in range(n)) / n
    rmse = sq_err ** 0.5
    return round(rmse, 4), round(var_r ** 0.5, 4)


def _direction_accuracy(scores: list, returns: list) -> Optional[float]:
    """방향성 적중 = sign(score - mean(score)) == sign(return - mean(return)) 비율."""
    valid = [(s, r) for s, r in zip(scores, returns) if s is not None and r is not None]
    n = len(valid)
    if n < 2:
        return None
    mean_s = sum(v[0] for v in valid) / n
    mean_r = sum(v[1] for v in valid) / n
    correct = sum(
        1 for s, r in valid
        if (s - mean_s) * (r - mean_r) > 0
    )
    # 0 차이 (정확히 mean) 는 무시 (반반)
    nonzero = sum(1 for s, r in valid if (s - mean_s) != 0 and (r - mean_r) != 0)
    return round(correct / nonzero, 4) if nonzero else None


def _quintile_spread(scores: list, returns: list, q_size: int = 5) -> Optional[float]:
    """Q5 (top 5 score) 평균 return - Q1 (bottom 5) 평균 return.

    n=25 → 분위당 5구. q_size 조정 가능.
    """
    valid = [(s, r) for s, r in zip(scores, returns) if s is not None and r is not None]
    n = len(valid)
    if n < q_size * 2:
        return None
    sorted_pairs = sorted(valid, key=lambda x: x[0])
    q1 = sorted_pairs[:q_size]
    q5 = sorted_pairs[-q_size:]
    q1_ret = sum(r for _, r in q1) / q_size
    q5_ret = sum(r for _, r in q5) / q_size
    return round(q5_ret - q1_ret, 4)


def _sharpe_long_only_q5(scores: list, returns: list, q_size: int = 5,
                          rf_pct: float = 0.0) -> Optional[float]:
    """Long-only Q5 Sharpe (annualized 의도하지 않음, raw)."""
    valid = [(s, r) for s, r in zip(scores, returns) if s is not None and r is not None]
    n = len(valid)
    if n < q_size:
        return None
    sorted_pairs = sorted(valid, key=lambda x: x[0])
    q5 = sorted_pairs[-q_size:]
    q5_rets = [r for _, r in q5]
    mean_r = sum(q5_rets) / q_size
    var_r = sum((r - mean_r) ** 2 for r in q5_rets) / q_size
    if var_r == 0:
        return None
    return round((mean_r - rf_pct) / (var_r ** 0.5), 4)


def _compute_silent_metrics(
    pairs: list[tuple[float, Optional[float]]],
    operational_verdict: Optional[str] = None,
    horizon_weeks: int = SILENT_HORIZON_WEEKS,
) -> dict:
    """5 메트릭 산출 + 임계 통과 평가 (참고용, 운영 X).

    Args:
        pairs: [(score, forward_return_pct_t13), ...] — 25 구.
            forward_return None 이면 4 메트릭 산출 불가, p0_passed_count=0
        operational_verdict: 기존 IC 단독 verdict (호환 기록)
        horizon_weeks: T+N주 horizon 라벨

    Returns: silent jsonl 한 row (timestamp + metrics + thresholds_evaluated +
             current_operational_verdict).
    """
    scores = [p[0] for p in pairs]
    returns = [p[1] for p in pairs]
    n_districts = sum(1 for r in returns if r is not None)

    rho, pval = _spearman_rank_ic(scores, returns)
    rmse_v, vol = _rmse(scores, returns)
    dir_acc = _direction_accuracy(scores, returns)
    qspread = _quintile_spread(scores, returns)
    sharpe = _sharpe_long_only_q5(scores, returns)

    # 임계 통과 (silent — 운영 X)
    spearman_pass = (rho is not None and pval is not None
                     and rho >= SILENT_THR_SPEARMAN_IC and pval < SILENT_THR_SPEARMAN_PVAL)
    rmse_pass = (
        rmse_v is not None and vol is not None and vol > 0
        and rmse_v <= vol * SILENT_THR_RMSE_RATIO
    )
    direction_pass = (dir_acc is not None and dir_acc >= SILENT_THR_DIRECTION_ACC)
    quintile_pass = (qspread is not None and qspread >= SILENT_THR_QUINTILE_SPREAD_PCT)
    p0_passed = sum([spearman_pass, rmse_pass, direction_pass, quintile_pass])

    return {
        "timestamp": datetime.now(KST).isoformat(timespec="seconds"),
        "horizon_weeks": horizon_weeks,
        "n_districts": n_districts,
        "metrics": {
            "spearman_rank_ic": rho,
            "spearman_pvalue": pval,
            "rmse": rmse_v,
            "market_volatility": vol,
            "direction_accuracy": dir_acc,
            "quintile_spread_pct": qspread,
            "sharpe_long_only_q5": sharpe,
        },
        "thresholds_evaluated": {
            "spearman_pass": spearman_pass,
            "rmse_pass": rmse_pass,
            "direction_pass": direction_pass,
            "quintile_pass": quintile_pass,
            "p0_passed_count": p0_passed,
            "would_pass_with_3_of_4": p0_passed >= SILENT_THR_P0_PASS_OF_4,
        },
        "current_operational_verdict": operational_verdict,
    }


def _append_silent_metrics_jsonl(record: dict, path: Path = SILENT_METRICS_LOG) -> None:
    """jsonl append. 실패해도 운영 verdict 영향 X (silent 보장)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        # silent — 운영 영향 X. stderr 로만 알림
        print(f"⚠ silent metrics jsonl 기록 실패: {e}", file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        # D3 — mock dry-run 옵션
        if "--dry-run-silent" in sys.argv:
            return _dry_run_silent_metrics()
        print("Usage: python3 scripts/landex_meta_validation.py YYYY-MM [--preset balanced]", file=sys.stderr)
        print("   or: python3 scripts/landex_meta_validation.py --dry-run-silent  (D3 mock 검증)", file=sys.stderr)
        sys.exit(1)
    if "--dry-run-silent" in sys.argv:
        return _dry_run_silent_metrics()
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

    # ── D3 silent 측정 (운영 verdict 미터치) ──
    # forward_returns 는 현재 cron 에서 fetch 안 함 (R-ONE T+13주 별도 트랙).
    # 5/5 cron 후 forward_returns 통합 시 main 에 dict 전달만 추가하면 됨.
    # 현재는 score-only pair (forward=None) → spearman/rmse/direction/quintile = None.
    silent_pairs = [(r.get("s_landex"), None) for r in rows_print if r.get("s_landex") is not None]
    silent_record = _compute_silent_metrics(silent_pairs, operational_verdict=verdict)
    _append_silent_metrics_jsonl(silent_record)
    print(f"\n  → silent metrics jsonl 기록 (n={silent_record['n_districts']}, "
          f"p0_passed={silent_record['thresholds_evaluated']['p0_passed_count']}/4)")


def _dry_run_silent_metrics() -> int:
    """D3 mock dry-run — 25 구 fake (score, return) 페어로 silent 메트릭 + jsonl append 검증.

    운영 영향 X. tmp 디렉토리에 jsonl 쓰고 결과 출력 후 종료.
    """
    import tempfile, random
    rng = random.Random(42)
    # mock: 25 구. score 와 return 양의 상관 (rho ≈ 0.5) + noise
    pairs = []
    for i in range(25):
        score = 50 + rng.gauss(0, 10)            # 50 평균, std 10
        ret = 0.5 * (score - 50) / 10 + rng.gauss(0, 0.5)  # rho ≈ 0.7
        pairs.append((score, ret))

    record = _compute_silent_metrics(pairs, operational_verdict="ready")

    # tmp jsonl
    tmp_path = Path(tempfile.mkdtemp(prefix="landex_dryrun_")) / "landex_meta_validation.jsonl"
    _append_silent_metrics_jsonl(record, path=tmp_path)

    print("=== D3 silent metrics dry-run (mock 25 구) ===")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    print(f"\n[saved] {tmp_path}")
    print(f"\n[smoke] 운영 jsonl 경로 (실제 cron 시): {SILENT_METRICS_LOG}")
    return 0


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
