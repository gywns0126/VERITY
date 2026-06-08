#!/usr/bin/env python3
"""
berserker_shadow.py — ARENA 버서커 shadow 채점 루프 (Phase 2)

WHY: PM 결정 6/8 — 버서커(최대 공격)가 보수코어 대비 "실제로 더 버는가"를
검증 데이터로 판정. shadow only (실자본 0). 매일 같은 검증 신호 위에 두 포트폴리오를
기록 — 보수코어(분산) vs 버서커(집중·상향 사이징). 공격 다이얼 = validation_progress
([[project_arena_kickoff_2026_05_30]] 6/8 부활). 누적 trail 로 expectancy/SQN/Calmar 비교.

  w_berserker = (1 − a)·w_conservative + a·w_concentrated     # a = aggression(=validation_progress)
  → a=0 (검증 부족) 면 버서커 ≡ 보수코어. a→1 (PASS) 면 top-K 집중·brain_score 틸트.

가드:
  · shadow only — 실주문 0. 레버리지·숏 미적용 (LOCKED, berserker_status.py 카운트다운).
  · 신호 universe = 코어 BUY 판정과 동일 (recommendation ∈ BUY 집합). divergence 0.
  · 측정값 = 가설 (N=X). site 노출 시 "(가설/N=X)" 의무 (RULE 7).
  · 비교 메트릭 = 표본 부족 시 None (N 게이트). 곡선 맞추기 회피 ([[feedback_threshold_calibration_overfit_guard]]).

산출:
  · data/arena/berserker_shadow.jsonl   (일별 목표 포트폴리오 trail, append-only)
  · data/arena/berserker_shadow_score.json (누적 비교 — N 충분 시)

실행:
  python -m api.arena.berserker_shadow            # 오늘 snapshot append + 채점
  python -m api.arena.berserker_shadow --check    # IO 없이 순수 함수 검증만
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from api.config import now_kst, DATA_DIR

_BUY_SET = ("BUY", "STRONG_BUY", "매수", "강력 매수")
_CONS_MAX_NAMES = 10      # 보수코어 = 상위 N 동일가중
_CONS_MAX_WEIGHT = 0.20   # 종목당 상한 (집중 위험 제한)
_BERS_TOP_K = 4           # 버서커 풀집중 시 종목 수


def _is_core_buy(r: dict) -> bool:
    return r.get("recommendation") in _BUY_SET


def _brain_score(r: dict) -> float:
    vb = r.get("verity_brain") or {}
    return float(vb.get("brain_score") or r.get("raw_brain_score") or 0.0)


def conservative_weights(eligible: list) -> dict:
    """보수코어 = 상위 brain_score 동일가중 (상한 캡). 잔여 = 현금."""
    ranked = sorted(eligible, key=_brain_score, reverse=True)[:_CONS_MAX_NAMES]
    if not ranked:
        return {}
    w = min(_CONS_MAX_WEIGHT, 1.0 / len(ranked))
    return {r["ticker"]: round(w, 4) for r in ranked}


def concentrated_weights(eligible: list) -> dict:
    """버서커 풀집중 = top-K, brain_score 비례 틸트. 잔여 = 현금."""
    ranked = sorted(eligible, key=_brain_score, reverse=True)[:_BERS_TOP_K]
    if not ranked:
        return {}
    scores = [_brain_score(r) for r in ranked]
    total = sum(scores) or float(len(ranked))
    return {r["ticker"]: round(s / total, 4) for r, s in zip(ranked, scores)}


def berserker_weights(eligible: list, aggression: float) -> dict:
    """w_bers = (1−a)·w_cons + a·w_concentrated. a=0 → 보수코어와 동일."""
    a = max(0.0, min(1.0, aggression))
    cons = conservative_weights(eligible)
    conc = concentrated_weights(eligible)
    tickers = set(cons) | set(conc)
    out = {}
    for t in tickers:
        w = (1 - a) * cons.get(t, 0.0) + a * conc.get(t, 0.0)
        if w > 1e-6:
            out[t] = round(w, 4)
    return out


def build_snapshot(recommendations: list, aggression: float, as_of: str) -> dict:
    """오늘 보수 vs 버서커 목표 포트폴리오 1 snapshot."""
    eligible = [r for r in recommendations if _is_core_buy(r)]
    cons = conservative_weights(eligible)
    bers = berserker_weights(eligible, aggression)
    prices = {r["ticker"]: r.get("current_price") or r.get("price")
              for r in eligible if (r.get("current_price") or r.get("price"))}
    return {
        "as_of": as_of,
        "aggression": round(aggression, 4),
        "n_eligible": len(eligible),
        "conservative": cons,
        "berserker": bers,
        "cash_conservative": round(1.0 - sum(cons.values()), 4),
        "cash_berserker": round(1.0 - sum(bers.values()), 4),
        "prices": {t: round(float(p), 4) for t, p in prices.items()},
    }


def _port_return(prev_weights: dict, prev_prices: dict, cur_prices: dict) -> Optional[float]:
    """전일 목표 가중 × 실현 수익률. 가격 매칭 안 되면 그 종목 0 기여(현금)."""
    if not prev_weights:
        return 0.0  # 100% 현금 → 0 수익
    r = 0.0
    for t, w in prev_weights.items():
        p0, p1 = prev_prices.get(t), cur_prices.get(t)
        if p0 and p1 and p0 > 0:
            r += w * (p1 / p0 - 1.0)
    return round(r, 6)


def score_trail(snapshots: list) -> dict:
    """누적 trail → 보수 vs 버서커 일별 수익률 + 종합. N 부족 시 메트릭 None."""
    if len(snapshots) < 2:
        return {"n_periods": max(0, len(snapshots) - 1),
                "_note": "표본 부족 — 비교 시작 전 (snapshot ≥2 필요)"}

    rets_c, rets_b = [], []
    for prev, cur in zip(snapshots, snapshots[1:]):
        cp = cur.get("prices", {})
        rets_c.append(_port_return(prev.get("conservative", {}), prev.get("prices", {}), cp))
        rets_b.append(_port_return(prev.get("berserker", {}), prev.get("prices", {}), cp))

    def _cum(rs):
        eq = 1.0
        for x in rs:
            eq *= (1 + (x or 0.0))
        return round((eq - 1.0) * 100, 3)

    n = len(rets_c)
    return {
        "n_periods": n,
        "conservative_cum_return_pct": _cum(rets_c),
        "berserker_cum_return_pct": _cum(rets_b),
        "berserker_minus_conservative_pp": round(_cum(rets_b) - _cum(rets_c), 3),
        # expectancy/SQN/Calmar = N 게이트 (VAMS MIN_TRADES=20 정합). 그 전엔 informational only.
        "expectancy_metrics": (None if n < 20 else "TODO_phase2b_wire"),
        "_disclaimer": f"가설 — shadow 비교 (N={n} periods). 실자본 0. N<20 = 예비 결과.",
    }


def run() -> dict:
    from api.arena.berserker_status import compute_berserker_status

    recs_path = Path(DATA_DIR) / "recommendations.json"
    recommendations = json.loads(recs_path.read_text(encoding="utf-8"))
    status = compute_berserker_status()
    aggression = status["validation_progress"]
    as_of = now_kst().strftime("%Y-%m-%d")

    snap = build_snapshot(recommendations, aggression, as_of)

    out_dir = Path(DATA_DIR) / "arena"
    out_dir.mkdir(parents=True, exist_ok=True)
    trail_path = out_dir / "berserker_shadow.jsonl"

    # 같은 날 재실행 = 마지막 항목 교체 (중복 append 방지)
    existing = []
    if trail_path.exists():
        existing = [json.loads(l) for l in trail_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    existing = [s for s in existing if s.get("as_of") != as_of]
    existing.append(snap)
    existing.sort(key=lambda s: s.get("as_of", ""))
    trail_path.write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in existing) + "\n", encoding="utf-8")

    score = score_trail(existing)
    (out_dir / "berserker_shadow_score.json").write_text(
        json.dumps(score, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"snapshot": snap, "score": score, "trail_len": len(existing)}


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="ARENA 버서커 shadow 채점")
    ap.add_argument("--check", action="store_true", help="IO 없이 순수 함수 검증")
    args = ap.parse_args(argv)

    if args.check:
        recs = [
            {"ticker": "A", "recommendation": "BUY", "verity_brain": {"brain_score": 80}, "price": 100},
            {"ticker": "B", "recommendation": "STRONG_BUY", "verity_brain": {"brain_score": 60}, "price": 50},
            {"ticker": "C", "recommendation": "AVOID", "verity_brain": {"brain_score": 40}, "price": 10},
        ]
        s0 = build_snapshot(recs, aggression=0.0, as_of="2026-06-08")
        s1 = build_snapshot(recs, aggression=1.0, as_of="2026-06-09")
        # a=0 → 버서커 == 보수코어
        assert s0["berserker"] == s0["conservative"], "a=0 mismatch"
        # a=1 → 집중 (top-K, score 틸트). AVOID 제외 → A/B 만
        assert set(s1["berserker"]) == {"A", "B"}, s1["berserker"]
        assert s1["berserker"]["A"] > s1["berserker"]["B"], "score 틸트 실패"
        sc = score_trail([s0, s1])
        assert sc["n_periods"] == 1
        print(f"[check] OK — a=0 동일성·a=1 집중 틸트·score_trail 통과. "
              f"보수 {s0['conservative']}, 버서커(a=1) {s1['berserker']}")
        return 0

    out = run()
    snap, score = out["snapshot"], out["score"]
    print(f"[shadow] {snap['as_of']} aggression={snap['aggression']} "
          f"eligible={snap['n_eligible']} → 보수 현금 {snap['cash_conservative']} / "
          f"버서커 현금 {snap['cash_berserker']} (trail {out['trail_len']})")
    if "conservative_cum_return_pct" in score:
        print(f"  누적: 보수 {score['conservative_cum_return_pct']}% / "
              f"버서커 {score['berserker_cum_return_pct']}% "
              f"(Δ {score['berserker_minus_conservative_pp']}pp, N={score['n_periods']})")
    else:
        print(f"  {score.get('_note')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
