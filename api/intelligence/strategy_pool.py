"""
Strategy Pool — Sequential → Portfolio of strategies (2026-05-17, Perplexity Q4 v2).

기존 strategy_evolver: 단일 current 전략 vs 단일 proposal 비교 → 27 cycle reject 원인 1종.
Pool 방식: max N (default 3) 의 ensemble 유지. proposal 가 가장 약한 strategy 와 비교 →
더 낮은 진입 장벽 + regime 변화 강건성.

산식:
- Pool 크기 max N (config STRATEGY_POOL_MAX_SIZE, default 3)
- proposal Sharpe vs pool 의 worst Sharpe + margin (STRATEGY_SHARPE_MIN_MARGIN)
- 통과 시 worst strategy 교체 (pool size 유지)
- 가중치 = Sharpe 비례 (정규화) 또는 Equal Weight

NOTE: 본 모듈 = 인프라 prep. strategy_evolver 의 propose() 통합 = STRATEGY_POOL_ENABLED
config (default 0). 활성 시 sequential 대신 pool 방식 적용.

Memory: project_brain_learning_loop_repair, project_perplexity_q1_q6_batch_2026_05_17.
"""
from __future__ import annotations

import functools
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

KST = timezone(timedelta(hours=9))

REPO_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
REGISTRY_PATH = REPO_ROOT / "data" / "strategy_registry.json"
_CONSTITUTION_PATH = REPO_ROOT / "data" / "verity_constitution.json"
_GRADE_ORDER = ("STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID")  # high → low


@functools.lru_cache(maxsize=1)
def _grade_min_scores() -> tuple:
    """constitution decision_tree.grades 의 (grade, min_brain_score) — 등급 사다리 단일 출처.

    2026-06-07: 앙상블 verdict 하드코드(75/60/45/25) → constitution 단일 출처화.
    verity_brain._score_to_grade 와 동일 source(constitution decision_tree.grades) 참조 →
    CAUTION 25 등 임계가 한 곳에서만 정의(drift 차단). 실패 시 안전 fallback.
    """
    defaults = (75.0, 60.0, 45.0, 25.0, 0.0)
    try:
        c = json.loads(_CONSTITUTION_PATH.read_text())
        g = c.get("decision_tree", {}).get("grades", {})
        return tuple(
            (name, float(g.get(name, {}).get("min_brain_score", d)))
            for name, d in zip(_GRADE_ORDER, defaults)
        )
    except Exception:
        return tuple(zip(_GRADE_ORDER, defaults))


def _verdict_from_score(score: float) -> str:
    """점수 → verdict (constitution 등급 사다리, high→low 순)."""
    for name, mn in _grade_min_scores():
        if score >= mn:
            return name
    return "AVOID"


def load_pool(registry: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """data/strategy_registry.json 의 strategy_pool field 로드.

    schema:
        [
          {"version": int, "applied_at": iso, "sharpe": float, "weight": float, "snapshot": {...}},
          ...
        ]
    """
    if registry is None:
        if not REGISTRY_PATH.exists():
            return []
        try:
            registry = json.loads(REGISTRY_PATH.read_text())
        except Exception:
            return []
    return registry.get("strategy_pool") or []


def save_pool(pool: List[Dict[str, Any]], registry: Dict[str, Any]) -> None:
    """registry 에 pool 저장. caller 가 _save_registry 호출."""
    registry["strategy_pool"] = pool


def is_significantly_better(
    sr_proposal: float,
    sr_target: float,
    min_margin: float = 0.10,
    T: int = 90,
    returns: Optional[List[float]] = None,
    use_psr: bool = False,
    psr_confidence: float = 0.90,
) -> Tuple[bool, str]:
    """proposal SR 가 target SR 보다 유의하게 큰지 판정.

    Returns: (pass_bool, reason).

    use_psr=True 시 PSR 통계 검정 추가. False 면 절대 margin 만.
    """
    gap = sr_proposal - sr_target
    if gap < min_margin:
        return False, f"margin 미달 ({gap:+.3f} < {min_margin:.2f})"

    if use_psr:
        try:
            from api.quant.alpha.psr import compute_psr
            psr_result = compute_psr(
                sr_observed=sr_proposal,
                sr_benchmark=sr_target,
                T=T,
                returns=returns,
            )
            if psr_result["psr"] < psr_confidence:
                return False, f"PSR {psr_result['psr']:.3f} < {psr_confidence:.2f}"
        except Exception as e:
            print(f"[strategy_pool] PSR check 실패 (margin gate 만): {e}", file=sys.stderr)

    return True, f"통과 (gap {gap:+.3f}, margin {min_margin:.2f} OK)"


def add_to_pool(
    pool: List[Dict[str, Any]],
    new_strategy: Dict[str, Any],
    *,
    max_size: int = 3,
    min_margin: float = 0.10,
    T: int = 90,
    returns: Optional[List[float]] = None,
    use_psr: bool = False,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Pool 에 new_strategy 추가 (가장 약한 strategy 와 비교).

    Returns: (new_pool, decision_dict).

    decision_dict:
        {accepted: bool, reason: str, replaced_version: Optional[int], pool_size: int}
    """
    new_sr = new_strategy.get("sharpe", 0)

    # Pool 비었으면 무조건 accept
    if not pool:
        new_pool = [new_strategy]
        return new_pool, {
            "accepted": True,
            "reason": "pool empty — 무조건 accept",
            "replaced_version": None,
            "pool_size": 1,
        }

    # Pool 안 가득 차면 무조건 추가
    if len(pool) < max_size:
        new_pool = pool + [new_strategy]
        return _rebalance_weights(new_pool), {
            "accepted": True,
            "reason": f"pool 미충 ({len(pool)} < {max_size}) — 무조건 추가",
            "replaced_version": None,
            "pool_size": len(new_pool),
        }

    # Pool 가득 — 가장 약한 strategy 와 비교
    worst = min(pool, key=lambda s: s.get("sharpe", 0))
    worst_sr = worst.get("sharpe", 0)
    pass_bool, reason = is_significantly_better(
        new_sr, worst_sr, min_margin=min_margin, T=T, returns=returns, use_psr=use_psr,
    )

    if not pass_bool:
        return pool, {
            "accepted": False,
            "reason": f"worst SR {worst_sr:.3f} 대비 {reason}",
            "replaced_version": None,
            "pool_size": len(pool),
        }

    # 교체
    new_pool = [s for s in pool if s.get("version") != worst.get("version")]
    new_pool.append(new_strategy)
    return _rebalance_weights(new_pool), {
        "accepted": True,
        "reason": f"worst (v{worst.get('version')}, SR {worst_sr:.3f}) 교체 — {reason}",
        "replaced_version": worst.get("version"),
        "pool_size": len(new_pool),
    }


def _rebalance_weights(
    pool: List[Dict[str, Any]],
    method: str = "sharpe_proportional",
) -> List[Dict[str, Any]]:
    """Pool 의 strategies 가중치 재산출.

    method:
      - "sharpe_proportional": Sharpe 비례 (음수 = 0)
      - "equal_weight": 1/N
    """
    n = len(pool)
    if n == 0:
        return pool

    if method == "equal_weight":
        for s in pool:
            s["weight"] = round(1.0 / n, 4)
        return pool

    # sharpe_proportional (음수 → 0)
    sharpes = [max(s.get("sharpe", 0), 0) for s in pool]
    total = sum(sharpes)
    if total == 0:
        # 전 strategy SR 0 또는 음수 = equal weight fallback
        for s in pool:
            s["weight"] = round(1.0 / n, 4)
        return pool

    for s, sr in zip(pool, sharpes):
        s["weight"] = round(sr / total, 4)
    return pool


def compute_ensemble_signal(
    pool: List[Dict[str, Any]],
    stock_signals: Dict[str, Any],
) -> Dict[str, Any]:
    """Pool 의 strategies 가중치 평균 → ensemble verdict 산출.

    stock_signals: {strategy_version: {brain_score: float, verdict: str}}

    Returns: {ensemble_score: float, ensemble_verdict: str, contributions: dict}
    """
    if not pool or not stock_signals:
        return {"ensemble_score": None, "ensemble_verdict": None, "contributions": {}}

    contributions = {}
    weighted_sum = 0.0
    weight_total = 0.0
    for s in pool:
        v = s.get("version")
        w = s.get("weight", 0)
        sig = stock_signals.get(v) or stock_signals.get(str(v)) or {}
        score = sig.get("brain_score", 0)
        contributions[v] = {"weight": w, "score": score, "verdict": sig.get("verdict")}
        weighted_sum += score * w
        weight_total += w

    ensemble_score = round(weighted_sum / max(weight_total, 1e-9), 2)
    # verdict mapping — constitution decision_tree.grades 단일 출처 (2026-06-07, 하드코드 제거)
    verdict = _verdict_from_score(ensemble_score)

    return {
        "ensemble_score": ensemble_score,
        "ensemble_verdict": verdict,
        "contributions": contributions,
    }


if __name__ == "__main__":
    # Sanity test
    sample_pool = []

    s1 = {"version": 1, "sharpe": 0.8, "applied_at": "2026-04-01"}
    s2 = {"version": 2, "sharpe": 1.2, "applied_at": "2026-05-01"}
    s3 = {"version": 3, "sharpe": 0.6, "applied_at": "2026-05-10"}

    pool1, dec1 = add_to_pool(sample_pool, s1)
    print(f"Add s1 (SR 0.8): {dec1}")

    pool2, dec2 = add_to_pool(pool1, s2)
    print(f"Add s2 (SR 1.2): {dec2}")

    pool3, dec3 = add_to_pool(pool2, s3)
    print(f"Add s3 (SR 0.6): {dec3}")

    # Pool 가득 — 새 proposal 시도
    s4 = {"version": 4, "sharpe": 0.9, "applied_at": "2026-05-15"}
    pool4, dec4 = add_to_pool(pool3, s4, min_margin=0.10)
    print(f"Add s4 (SR 0.9, margin 0.10): {dec4}")
    print(f"Pool: {[(s['version'], s['sharpe'], s.get('weight')) for s in pool4]}")

    s5 = {"version": 5, "sharpe": 0.65, "applied_at": "2026-05-16"}
    pool5, dec5 = add_to_pool(pool4, s5, min_margin=0.10)
    print(f"Add s5 (SR 0.65, margin 0.10): {dec5}")
    # s5 vs worst (s3 SR 0.6) gap = 0.05 < margin 0.10 → reject 예상
