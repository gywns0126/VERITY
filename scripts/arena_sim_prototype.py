#!/usr/bin/env python3
"""
arena_sim_prototype.py — ARENA 시뮬 엔진 프로토타입 (A축 잠근 산식 end-to-end 실증)

WHY: ArenaTradeTurn.tsx (5/30 mockup) 의 하드코딩 Kelly/시뮬 = mock. A축 §6 Lock
산식(GBM 이산 / Monte Carlo / Kelly / 레버리지 일일복리)을 그대로 구현해 "한 턴 →
1년 플레이스루" 자본 분포를 실제 산출. 산식 튜닝 X (구현만) — 곡선 맞추기 위반 아님.
C축(6/2) KS test 의 선행 sanity. 본인 only.

A축 §6 Lock 정합:
  · GBM 이산 step  : r_d = (μ−σ²/2)/P + σ/√P · Z      (P=연율화 인자)
  · 레버리지 ETF   : 일일 L배 복리 (underlying GBM 파생, ETF σ 직접 X — §5.8.2)
  · Kelly 연속     : f* = (μ−r_f)/σ²,  half = f*/2     (effective exposure = position% × leverage 와 비교)
  · 거래비용       : 진입+청산 1회 (ROUND_TRIP_COST, §5.8.3)

실행:
  python scripts/arena_sim_prototype.py                 # 실데이터 (SPY/KODEX200/BTC)
  python scripts/arena_sim_prototype.py --mu 0.10 --sigma 0.20 --periods 252  # 수동 params

산식 = A축 Lock. 측정값 = historical estimate (가설). site 노출 X.
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


def simulate(mu: float, sigma: float, periods: int, position: float, leverage: float,
             cost: float, n_paths: int = 10000, seed: int = 7) -> dict:
    """1년(=periods step) GBM Monte Carlo. 일일 L배 복리 + position 비중 + 진입/청산 비용.

    반환: 최종 자본배수 분포 통계 + 평균 경로 MDD.
    """
    rng = np.random.default_rng(seed)
    P = periods
    dt_drift = (mu - 0.5 * sigma ** 2) / P
    dt_vol = sigma / np.sqrt(P)

    # underlying 일일 로그수익률 → 단순수익률
    z = rng.standard_normal((n_paths, P))
    under_simple = np.exp(dt_drift + dt_vol * z) - 1.0          # (paths, P)

    # 레버리지 ETF = 일일 L배 (일일 리밸런싱, §5.8.2). position 비중 = 나머지 현금(rf=0)
    daily_port = position * (leverage * under_simple)            # 포트 일일 수익률
    growth = np.cumprod(1.0 + daily_port, axis=1)                # 자본 경로 (paths, P)
    final = growth[:, -1] * (1.0 - cost)                         # 진입+청산 왕복 비용 1회

    # 경로별 MDD (running max 대비)
    run_max = np.maximum.accumulate(growth, axis=1)
    dd = growth / run_max - 1.0
    mdd_per_path = dd.min(axis=1)

    pct = lambda a, q: float(np.percentile(a, q))               # noqa: E731
    return {
        "n_paths": n_paths,
        "mean": float(final.mean()),
        "median": pct(final, 50),
        "p5": pct(final, 5),
        "p25": pct(final, 25),
        "p75": pct(final, 75),
        "p95": pct(final, 95),
        "p_loss": float((final < 1.0).mean()),
        "p_ruin_50": float((final < 0.5).mean()),     # 자본 반토막 이하 확률
        "median_mdd": pct(mdd_per_path, 50),          # 음수 magnitude
        "worst_mdd": float(mdd_per_path.min()),
    }


def run_turn(label: str, mu: float, sigma: float, periods: int,
             position: float, leverage: float, category: str = "us_etf") -> None:
    cost = ROUND_TRIP_COST.get(category, 0.001)
    f_full = kelly(mu, sigma)
    f_half = f_full / 2.0
    eff = position * leverage                                    # 본인 결정 effective exposure

    if eff <= f_half:
        verdict, mark = "보수적 (half-Kelly 이하)", "·"
    elif eff <= f_full:
        verdict, mark = "Kelly 범위 내", "✓"
    else:
        verdict, mark = "과대 (full-Kelly 초과 — 파산 위험)", "!"

    r = simulate(mu, sigma, periods, position, leverage, cost)

    print(f"\n━━━ {label}  (μ={mu:+.1%}/yr  σ={sigma:.1%}  P={periods}) ━━━")
    print(f"  내 결정     : position {position:.0%} × leverage {leverage:.0f}x = exposure {eff:.2f}")
    print(f"  Kelly       : full {f_full:.2f} / half {f_half:.2f}  →  {mark} {verdict}")
    print(f"  거래비용    : 왕복 {cost:.2%}")
    print(f"  ── 1년 플레이스루 ({r['n_paths']:,} paths, GBM MC) ──")
    print(f"  최종 자본배수: 중앙 {r['median']:.2f}x  (P5 {r['p5']:.2f} / P25 {r['p25']:.2f} "
          f"/ P75 {r['p75']:.2f} / P95 {r['p95']:.2f})")
    print(f"  평균        : {r['mean']:.2f}x")
    print(f"  손실 확률   : {r['p_loss']:.1%}   |   반토막↓ 확률: {r['p_ruin_50']:.1%}")
    print(f"  MDD (중앙)  : {abs(r['median_mdd']):.1%}   |   최악 경로 MDD: {abs(r['worst_mdd']):.1%}")


def main() -> int:
    ap = argparse.ArgumentParser(description="ARENA 시뮬 엔진 프로토타입")
    ap.add_argument("--mu", type=float, default=None, help="수동 μ (연). 생략 시 실데이터")
    ap.add_argument("--sigma", type=float, default=None, help="수동 σ (연)")
    ap.add_argument("--periods", type=int, default=252)
    ap.add_argument("--position", type=float, default=0.25, help="포지션 비중 (0~1)")
    ap.add_argument("--leverage", type=float, default=1.0)
    args = ap.parse_args()

    print("=== ARENA 시뮬 엔진 프로토타입 — A축 §6 Lock 산식 실증 ===")
    print("    (산식 구현 only, 튜닝 X. 측정값 = historical estimate 가설. site 노출 X)")

    if args.mu is not None and args.sigma is not None:
        run_turn("MANUAL", args.mu, args.sigma, args.periods, args.position, args.leverage)
        return 0

    # 실데이터 3종 (KR / 미장 / 코인) — B축 함수 재사용
    demo = [
        ("SPY (미장 ETF)",  "SPY",      "us_etf", 252, 0.25, 1.0),
        ("KODEX 200 (KR)",  "069500.KS","kr_etf", 252, 0.25, 1.0),
        ("BTC (코인)",      "BTC-USD",  "coin",   365, 0.10, 1.0),
        ("SPY + 3x 레버리지","SPY",     "us_etf", 252, 0.25, 3.0),   # 동일 자산, 레버리지만 ↑
    ]
    for label, ticker, cat, P, pos, lev in demo:
        try:
            close = fetch_close(ticker, 5.0)
            stats, _ = compute_stats(close, P)
            run_turn(label, stats["mu_gbm_annual"], stats["sigma_annual"], P, pos, lev, cat)
        except Exception as e:  # noqa: BLE001
            print(f"\n[SKIP] {label}: {e}", file=sys.stderr)
    print("\n비교: 동일 SPY 자산에 레버리지 1x vs 3x → exposure·손실확률·MDD 변화 관찰")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
