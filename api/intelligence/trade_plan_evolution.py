"""
trade_plan v0 자체 진화 신호 — Brain 이 자기 룰을 점검하는 메커니즘.

trade_plan_meta (분해 통계) 를 읽어 룰 변경 후보 알림을 산출.
**자동 룰 변경 X**. 사용자 검토 후 수동 적용 (memory: feedback_continuous_evolution
4가드 — commit/시간대/모니터링/롤백).

산출 신호 카테고리:
  - underperforming_horizon  : 특정 horizon hit rate < 45% 지속
  - drift_warning            : first_30d → latest 윈도 hit rate -10%p 이상 하락
  - low_ic                   : IC < 0 (multi_score 와 사후 수익 음의 상관 — 반전 신호)
  - feature_anomaly          : 4분위 분해에서 mean return 단조성 깨짐 (피처 무용 신호)
  - rule_change_candidates   : 위 신호 종합한 룰 변경 후보 텍스트

부족 데이터 시 status="insufficient_data" — 임의 신호 X.
sample size 임계: 분해 신호는 30 row, drift 는 윈도별 5 row 이상.

Brain 진화 prompt (strategy_evolver) 입력으로 사용 → Claude 가 룰 변경 결정 시 참조.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 임계
HIT_RATE_FAIL_PCT = 45.0
DRIFT_DROP_PCT = 10.0
MIN_BUCKET_N = 5
MIN_TOTAL_FOR_SIGNALS = 30


def _signal(level: str, topic: str, message: str, **details) -> Dict[str, Any]:
    return {"level": level, "topic": topic, "message": message, "details": details}


def _check_horizon_hit_rate(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    horizons = meta.get("horizon_summary") or {}
    for key, h in horizons.items():
        n = h.get("n", 0)
        hr = h.get("hit_rate_pct")
        if n < MIN_TOTAL_FOR_SIGNALS or hr is None:
            continue
        if hr < HIT_RATE_FAIL_PCT:
            out.append(_signal(
                "warning",
                f"hit_rate_{key}",
                f"{key} hit rate {hr}% (< {HIT_RATE_FAIL_PCT}%) — 룰 재검토 권고",
                horizon=key, n=n, hit_rate_pct=hr,
            ))
    return out


def _check_drift(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """timeseries_baseline 의 first_30d → latest 윈도 hit rate 하락 감지."""
    ts = meta.get("timeseries_baseline") or {}
    windows = ts.get("windows") or {}
    if not windows:
        return []

    first = windows.get("first_30d") or {}
    later_candidates = []
    for label in ("60d_plus", "30_60d"):
        w = windows.get(label) or {}
        if w.get("hit_rate_pct") is not None and w.get("n", 0) >= MIN_BUCKET_N:
            later_candidates.append((label, w))
            break

    if first.get("hit_rate_pct") is None or first.get("n", 0) < MIN_BUCKET_N:
        return []
    if not later_candidates:
        return []
    later_label, later = later_candidates[0]
    drop = float(first["hit_rate_pct"]) - float(later["hit_rate_pct"])
    if drop >= DRIFT_DROP_PCT:
        return [_signal(
            "critical",
            "drift_first_to_latest",
            f"첫 30일 hit rate {first['hit_rate_pct']}% → {later_label} {later['hit_rate_pct']}% (-{round(drop, 1)}%p) — drift 감지",
            first_30d=first, later=later, later_label=later_label, drop_pp=round(drop, 1),
        )]
    return []


def _check_ic(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    horizons = meta.get("horizon_summary") or {}
    for key, h in horizons.items():
        ic = h.get("ic")
        n = h.get("n", 0)
        if ic is None or n < MIN_TOTAL_FOR_SIGNALS:
            continue
        if ic < 0:
            out.append(_signal(
                "critical",
                f"low_ic_{key}",
                f"{key} IC {ic} < 0 — multi_score 가 사후 수익과 음의 상관 (반전 신호)",
                horizon=key, ic=ic, n=n,
            ))
        elif ic < 0.05:
            out.append(_signal(
                "warning",
                f"weak_ic_{key}",
                f"{key} IC {ic} < 0.05 — multi_score 의 예측력 약함",
                horizon=key, ic=ic, n=n,
            ))
    return out


def _check_feature_anomaly(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """4분위 분해에서 단조성 (Q1 < Q2 < Q3 < Q4 가 깨지면 피처 무용/노이즈)."""
    decomp = meta.get("feature_decomposition") or {}
    if not isinstance(decomp, dict) or decomp.get("status") == "insufficient_data":
        return []
    out: List[Dict[str, Any]] = []
    for fname, fdata in decomp.items():
        if not isinstance(fdata, dict) or fdata.get("status") == "insufficient_data":
            continue
        quartiles = fdata.get("quartile_mean_return_pct") or []
        means = [q.get("mean_return_pct") for q in quartiles if q.get("mean_return_pct") is not None]
        if len(means) < 4:
            continue
        # 단조 증가도 단조 감소도 아니면 noise
        increasing = all(means[i] <= means[i + 1] for i in range(3))
        decreasing = all(means[i] >= means[i + 1] for i in range(3))
        if not (increasing or decreasing):
            spread = round(max(means) - min(means), 2)
            out.append(_signal(
                "info",
                f"feature_noise_{fname}",
                f"{fname} 4분위 단조성 깨짐 (Q1~Q4 mean: {[round(m,1) for m in means]}, spread {spread}%) — 룰 입력 가치 약함",
                feature=fname, quartile_means=[round(m, 2) for m in means], spread=spread,
            ))
    return out


def _build_change_candidates(signals: List[Dict[str, Any]]) -> List[str]:
    """신호 종합해서 룰 변경 후보 텍스트 (Claude prompt 또는 사용자 검토용)."""
    cands: List[str] = []
    for s in signals:
        topic = s.get("topic", "")
        d = s.get("details", {})
        if topic.startswith("hit_rate_h"):
            h = d.get("horizon", "")
            cands.append(
                f"[{h}] hit rate {d.get('hit_rate_pct')}% — entry rule 강화 후보: "
                "RSI 임계 50→40 / BB 하단 ±0.5σ 협소화 / verdict + flow_score 조합 게이트"
            )
        elif topic.startswith("low_ic_") or topic.startswith("weak_ic_"):
            cands.append(
                f"[{d.get('horizon','')}] multi_score 예측력 약함 — verdict 가중치 재산출 필요. "
                "IC 양수 피처 (feature_decomposition 참조) 로 entry gate 교체 검토"
            )
        elif topic == "drift_first_to_latest":
            cands.append(
                f"drift 감지 (-{d.get('drop_pp')}%p) — 시장 regime 전환 가능성. "
                "Graham/CANSLIM regime switching 룰 활성 여부 점검"
            )
        elif topic.startswith("feature_noise_"):
            cands.append(
                f"{d.get('feature','')} 단조성 깨짐 — 결정 룰 입력에서 제외 검토 "
                "(현재 v0 룰엔 미포함, 향후 v1 입력 후보에서 제거)"
            )
    return cands


def analyze_trade_plan_signals(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """trade_plan_meta → 진화 신호 + 룰 변경 후보."""
    if not meta or meta.get("status") in (None, "empty"):
        return {
            "status": "no_data",
            "signals": [],
            "change_candidates": [],
            "note": "운영 시작 전 — trade_plan_meta 빈 상태",
        }

    sample_total = (meta.get("sample_size") or {}).get("total", 0)
    if sample_total < MIN_TOTAL_FOR_SIGNALS:
        return {
            "status": "insufficient_data",
            "signals": [],
            "change_candidates": [],
            "sample_size": sample_total,
            "min_required": MIN_TOTAL_FOR_SIGNALS,
            "note": f"분해 통계 임계 미달 ({sample_total}/{MIN_TOTAL_FOR_SIGNALS}) — 신호 산출 보류",
        }

    signals: List[Dict[str, Any]] = []
    signals.extend(_check_horizon_hit_rate(meta))
    signals.extend(_check_ic(meta))
    signals.extend(_check_drift(meta))
    signals.extend(_check_feature_anomaly(meta))

    change_candidates = _build_change_candidates(signals)
    n_critical = sum(1 for s in signals if s["level"] == "critical")
    n_warning = sum(1 for s in signals if s["level"] == "warning")

    if n_critical:
        status = "rule_review_needed"
    elif n_warning:
        status = "monitoring"
    else:
        status = "healthy"

    return {
        "status": status,
        "signals": signals,
        "change_candidates": change_candidates,
        "summary": {
            "critical": n_critical,
            "warning": n_warning,
            "info": sum(1 for s in signals if s["level"] == "info"),
            "sample_size": sample_total,
        },
        "policy_note": (
            "자동 룰 변경 없음. 사용자 검토 + 수동 적용 (4가드: commit/시간대/모니터링/롤백). "
            "rule_review_needed 시 trade_plan_v0 _build_trade_plan 룰 변경 후보 검토."
        ),
    }


def attach_to_portfolio(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """portfolio["trade_plan_evolution_signals"] 부착."""
    meta = portfolio.get("trade_plan_meta")
    signals = analyze_trade_plan_signals(meta)
    portfolio["trade_plan_evolution_signals"] = signals
    return signals
