#!/usr/bin/env python3
"""
arena_sim_prototype.py — ARENA 시뮬 엔진 프로토타입 (B4 MC 리스크 레이어 seed)

WHY: PM 결정 5/31 ([[project_arena_kickoff_2026_05_30]] SUPERSEDED) — ARENA 수동 게임
폐기, B4 백테스트 sprint에 Monte Carlo 리스크 분포 레이어로 흡수. 본 프로토타입 =
그 seed. GBM(가정 기반)과 block bootstrap(실 수익률 재생) 두 경로 생성기를 나란히
비교 — 부트스트랩이 실 fat tail/폭락을 보존해 꼬리 리스크가 GBM보다 두껍게 나옴을 실증.

순환 함정 가드 (RULE 7):
  · GBM      = 우리가 넣은 μ/σ 재생산 → "forward 시나리오" 라벨, 검증 X
  · bootstrap= 실 historical 일별 수익률 block 재추출 → 실 분포 근거, B4 MC 레이어 정공법

A축 §6 Lock 산식:
  · GBM 이산   : r_d = (μ−σ²/2)/P + σ/√P · Z
  · 레버리지   : 일일 L배 (1차 근사, position×leverage 일일 적용)
  · Kelly 연속 : f* = (μ−r_f)/σ²,  half = f*/2
  · 거래비용   : 진입+청산 1회 (ROUND_TRIP_COST, §5.8.3)

실행:
  python scripts/arena_sim_prototype.py                  # 실데이터 GBM vs bootstrap 비교
  python scripts/arena_sim_prototype.py --block 10       # bootstrap block 길이
  python scripts/arena_sim_prototype.py --mu 0.10 --sigma 0.20  # 수동 GBM only

측정값 = historical estimate (가설). site 노출 X.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import numpy as np

from scripts.arena_asset_stats import ROUND_TRIP_COST, fetch_close, compute_stats


def kelly(mu: float, sigma: float, rf: float = 0.0) -> float:
    """Kelly 연속 f* = (μ−r_f)/σ² (A축 §3.2). f>1 = 레버리지 권장."""
    return (mu - rf) / (sigma ** 2)


# ── 경로 생성기 (둘 다 underlying 일별 단순수익률 (paths, periods) 반환) ──────────
def gbm_paths(mu: float, sigma: float, periods: int, n: int, rng) -> np.ndarray:
    """GBM 이산 step — 가정 기반 (정규분포). forward 시나리오용, 검증 X."""
    drift = (mu - 0.5 * sigma ** 2) / periods
    vol = sigma / np.sqrt(periods)
    z = rng.standard_normal((n, periods))
    return np.exp(drift + vol * z) - 1.0


def bootstrap_paths(real_simple: np.ndarray, periods: int, n: int, block: int, rng) -> np.ndarray:
    """Block bootstrap — 실 일별 수익률 연속 덩어리 재추출 (fat tail/군집 보존, 비순환)."""
    m = len(real_simple)
    n_blocks = int(np.ceil(periods / block))
    starts = rng.integers(0, m, size=(n, n_blocks))                  # (n, n_blocks)
    offsets = np.arange(block)
    idx = (starts[:, :, None] + offsets[None, None, :]) % m          # wrap-around (n,nb,block)
    idx = idx.reshape(n, n_blocks * block)[:, :periods]
    return real_simple[idx]


def evaluate(under_simple: np.ndarray, position: float, leverage: float, cost: float) -> dict:
    """경로 → position×leverage 일일 적용 + 진입/청산 비용 → 최종 자본배수 분포 + MDD."""
    daily_port = position * (leverage * under_simple)
    growth = np.cumprod(np.maximum(1.0 + daily_port, 0.0), axis=1)    # 일일 wipeout floor
    final = growth[:, -1] * (1.0 - cost)
    run_max = np.maximum.accumulate(growth, axis=1)
    mdd = (growth / run_max - 1.0).min(axis=1)
    p = lambda a, q: float(np.percentile(a, q))                       # noqa: E731
    return {
        "median": p(final, 50), "p5": p(final, 5), "p95": p(final, 95),
        "p_loss": float((final < 1.0).mean()),
        "p_ruin_50": float((final < 0.5).mean()),
        "median_mdd": p(mdd, 50), "worst_mdd": float(mdd.min()),
    }


def run_turn(label: str, mu: float, sigma: float, periods: int, position: float,
             leverage: float, category: str, real_simple: np.ndarray | None,
             n_paths: int, block: int, seed: int = 7) -> None:
    cost = ROUND_TRIP_COST.get(category, 0.001)
    f_full = kelly(mu, sigma)
    eff = position * leverage
    verdict = ("보수적" if eff <= f_full / 2 else "Kelly 범위" if eff <= f_full else "과대(파산위험)")

    rng = np.random.default_rng(seed)
    g = evaluate(gbm_paths(mu, sigma, periods, n_paths, rng), position, leverage, cost)
    b = None
    if real_simple is not None and len(real_simple) >= block * 3:
        b = evaluate(bootstrap_paths(real_simple, periods, n_paths, block, rng),
                     position, leverage, cost)

    print(f"\n━━━ {label}  (μ={mu:+.1%} σ={sigma:.1%} P={periods})  position {position:.0%}×{leverage:.0f}x "
          f"= exp {eff:.2f} / Kelly {f_full:.2f} → {verdict} ━━━")
    print(f"  {'metric':<14}{'GBM(가정)':>14}{'Bootstrap(실)':>16}")
    rows = [
        ("중앙 자본배수", "median", "x", False),
        ("P5 (하위)",     "p5",     "x", False),
        ("P95 (상위)",    "p95",    "x", False),
        ("손실 확률",     "p_loss", "%", True),
        ("반토막↓ 확률",  "p_ruin_50", "%", True),
        ("MDD 중앙",      "median_mdd", "%mag", True),
        ("최악 MDD",      "worst_mdd",  "%mag", True),
    ]
    for name, key, unit, _ in rows:
        gv = g[key]
        bv = b[key] if b else None
        if unit == "x":
            gs, bs = f"{gv:.3f}x", (f"{bv:.3f}x" if b else "—")
        elif unit == "%":
            gs, bs = f"{gv:.1%}", (f"{bv:.1%}" if b else "—")
        else:  # %mag (음수 magnitude)
            gs, bs = f"{abs(gv):.1%}", (f"{abs(bv):.1%}" if b else "—")
        print(f"  {name:<14}{gs:>14}{bs:>16}")


def main() -> int:
    ap = argparse.ArgumentParser(description="ARENA 시뮬 엔진 프로토타입 (B4 MC seed)")
    ap.add_argument("--mu", type=float, default=None)
    ap.add_argument("--sigma", type=float, default=None)
    ap.add_argument("--periods", type=int, default=252)
    ap.add_argument("--position", type=float, default=0.25)
    ap.add_argument("--leverage", type=float, default=1.0)
    ap.add_argument("--n-paths", type=int, default=10000)
    ap.add_argument("--block", type=int, default=10, help="bootstrap block 길이 (일)")
    ap.add_argument("--years", type=float, default=5.0,
                    help="historical lookback (장기일수록 다 regime 포함, 가용 한도 내 자동 trim)")
    args = ap.parse_args()

    print("=== ARENA 시뮬 엔진 프로토타입 — GBM(가정) vs Block Bootstrap(실 수익률) ===")
    print("    (B4 MC 리스크 레이어 seed. 측정 = historical estimate 가설. site 노출 X)")

    if args.mu is not None and args.sigma is not None:
        run_turn("MANUAL", args.mu, args.sigma, args.periods, args.position,
                 args.leverage, "us_etf", None, args.n_paths, args.block)
        return 0

    demo = [
        ("SPY (미장 ETF)",   "SPY",       "us_etf", 252, 0.25, 1.0),
        ("KODEX 200 (KR)",   "069500.KS", "kr_etf", 252, 0.25, 1.0),
        ("BTC (코인)",       "BTC-USD",   "coin",   365, 0.10, 1.0),
        ("SPY + 3x 레버리지", "SPY",       "us_etf", 252, 0.25, 3.0),
    ]
    for label, ticker, cat, P, pos, lev in demo:
        try:
            close = fetch_close(ticker, args.years)
            stats, _ = compute_stats(close, P)
            real_simple = close.pct_change().dropna().to_numpy()
            print(f"\n[창] {label}: {stats['start']} ~ {stats['end']}  (N={stats['n_days']:,}일)")
            run_turn(label, stats["mu_gbm_annual"], stats["sigma_annual"], P, pos, lev,
                     cat, real_simple, args.n_paths, args.block)
        except Exception as e:  # noqa: BLE001
            print(f"\n[SKIP] {label}: {e}", file=sys.stderr)

    print("\n관찰 포인트: Bootstrap의 P5·반토막확률·최악MDD가 GBM보다 나쁠수록")
    print("            = 실 시장의 fat tail/폭락이 GBM 정규분포 가정에 가려졌다는 증거.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
