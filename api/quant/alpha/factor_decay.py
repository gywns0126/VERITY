"""
팩터 수명(Decay) 모니터

학술 근거:
  - McLean & Pontiff (2016): 학술 논문 발표 후 팩터 수익률이 58% 감소
  - Chordia, Subrahmanyam & Tong (2014): 시장 이상현상의 수명은 유한
  - 팩터 크라우딩: 너무 많은 투자자가 같은 팩터를 쓰면 수익 감소

기능:
  1. IC 히스토리에서 팩터별 추세선(선형 회귀) 계산
  2. 구조적 붕괴 vs 일시적 부진 분류
  3. 팩터 교체 제안 → Strategy Evolver에 전달
  4. 텔레그램 경고 메시지 생성
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import numpy as np

from api.config import DATA_DIR, now_kst


IC_CACHE_PATH = os.path.join(DATA_DIR, "factor_ic_history.json")


def _load_ic_history() -> List[Dict[str, Any]]:
    try:
        with open(IC_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _linear_trend(values: List[float]) -> Dict[str, float]:
    """선형 회귀로 추세 기울기와 R² 계산."""
    n = len(values)
    if n < 3:
        return {"slope": 0, "r_squared": 0, "intercept": 0}

    x = np.arange(n, dtype=float)
    y = np.array(values, dtype=float)

    x_mean = np.mean(x)
    y_mean = np.mean(y)

    ss_xy = np.sum((x - x_mean) * (y - y_mean))
    ss_xx = np.sum((x - x_mean) ** 2)

    if ss_xx == 0:
        return {"slope": 0, "r_squared": 0, "intercept": float(y_mean)}

    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean

    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y_mean) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    return {
        "slope": round(float(slope), 6),
        "r_squared": round(float(r_squared), 4),
        "intercept": round(float(intercept), 6),
    }


# 팩터 유형별 최소 IC 샘플 (2026-06-08 Perplexity NQ1 — 7일 일간 IC 윈도가 fundamental 에 부적합).
# price(모멘텀/반전/기술/심리): 일간 IC 의미 有 → 5 유지. fundamental(밸류/퀄리티/안전/컨센서스):
# 분기 보고서 reporting-lag 45~90일 불변 → 7일 IC = 동일 데이터 자기상관 노이즈. 신호가 실제
# 갱신(≥1 분기)되려면 더 긴 history 필요 → 21 floor(조기 DECAYING/DEAD 오분류 + 부당 downweight 차단).
# ⚠️ Perplexity 이상치: fundamental IC 통계 유의성엔 12~20분기 필요(Flint-Vermaak / Goodwin 1998).
#    본 21 은 premature 분류 방지 실용 floor — 저-N 노이즈 가중치 변동↓. 출처: alphaarchitect/spglobal/arxiv.
_FUNDAMENTAL_FACTORS = {"fundamental", "quality", "safety_score", "consensus"}
_MIN_SAMPLES_PRICE = 5
_MIN_SAMPLES_FUNDAMENTAL = 21


def _min_samples_for(factor: str) -> int:
    """팩터 유형별 최소 IC 샘플 — fundamental 은 7일 자기상관 노이즈 회피 위해 상향."""
    return _MIN_SAMPLES_FUNDAMENTAL if factor in _FUNDAMENTAL_FACTORS else _MIN_SAMPLES_PRICE


def analyze_factor_decay(
    min_history_days: int = 7,
    forward_days: int | None = None,
) -> Dict[str, Any]:
    """
    모든 팩터의 IC 추세를 분석하여 수명 상태를 판별.

    Args:
        min_history_days: 최소 필요 히스토리 일수
            2026-05-16: 14 → 7 완화 (audit BRAIN_SELF_GROWTH P0-2).
            **Perplexity NQ1 (2026-05-16) verdict**: 7일 완화는 통계적으로 취약.
            - ICIR=0.5 가정 시 t-stat≥2 위해 최소 T≥16 (실용 30-60일)
            - BARRA 12-36개월(252-756일) / Wells Fargo 12-24개월 기관 표준
            - 7일 = 가격 기반 팩터만 OK, 재무 팩터는 분기 공시 기준
            **임시 절충**: 7일 임계 유지 + confidence_penalty 추가
            (sample N 작을수록 IC weight multiplier 감소 적용)
            **후속 큐**: 팩터 유형별 (price-based vs fundamental) min_history 분리 — P2
        forward_days: None이면 모든 윈도우 통합, 지정하면 해당 윈도우만 분석

    분류:
      - HEALTHY: IC 양수 + 추세 안정/상승
      - WEAKENING: IC 양수이나 하락 추세
      - DECAYING: IC가 0 근처로 수렴 (구조적 붕괴)
      - DEAD: IC 음수로 전환
      - EMERGING: 최근 IC가 급등 (새로운 알파 등장)
      - INSUFFICIENT: 데이터 부족
    """
    raw_history = _load_ic_history()

    if forward_days is not None:
        history = [h for h in raw_history if h.get("forward_days", 7) == forward_days]
    else:
        # None = 기존 단기 윈도(7/14/30)만 병합. 신규 장기윈도(63/126, fundamental 분기)는
        # 명시 forward_days 로만 조회 — 기존 decay 소비자(strategy_evolver/backtest_archive)
        # backward-compat, 장기윈도 IC 가 기본 decay 분석을 오염시키지 않도록. 2026-06-09.
        history = [h for h in raw_history if h.get("forward_days", 7) <= 30]

    if len(history) < min_history_days:
        return {
            "status": "insufficient_data",
            "history_days": len(history),
            "min_required": min_history_days,
            "forward_days_filter": forward_days,
            "factors": {},
        }

    factor_names = set()
    for entry in history:
        factor_names.update(entry.get("factors", {}).keys())

    results: Dict[str, Dict[str, Any]] = {}

    for factor in factor_names:
        ic_values = []
        icir_values = []

        for entry in history:
            fd = entry.get("factors", {}).get(factor, {})
            ic = fd.get("ic_mean")
            icir = fd.get("icir")
            if ic is not None:
                ic_values.append(ic)
            if icir is not None:
                icir_values.append(icir)

        _min_samples = _min_samples_for(factor)
        if len(ic_values) < _min_samples:
            _is_fund = factor in _FUNDAMENTAL_FACTORS
            results[factor] = {
                "status": "INSUFFICIENT",
                "label": (f"데이터 부족 ({len(ic_values)}/{_min_samples}, "
                          f"{'fundamental 분기 신호' if _is_fund else 'price'})"),
                "ic_mean_all": 0,
                "ic_recent": 0,
                "trend": {},
                "min_samples": _min_samples,
                "factor_type": "fundamental" if _is_fund else "price",
            }
            continue

        ic_trend = _linear_trend(ic_values)
        ic_mean_all = float(np.mean(ic_values))
        ic_recent = float(np.mean(ic_values[-5:]))
        ic_earliest = float(np.mean(ic_values[:5]))
        # Perplexity Q2 (2026-05-17): ICIR 임계 게이트 활성
        icir_recent = float(np.mean(icir_values[-5:])) if len(icir_values) >= 5 else 0.0

        status, label = _classify_decay(
            ic_mean_all, ic_recent, ic_earliest, ic_trend, icir_recent=icir_recent
        )

        results[factor] = {
            "status": status,
            "label": label,
            "ic_mean_all": round(ic_mean_all, 5),
            "ic_recent": round(ic_recent, 5),
            "ic_earliest": round(ic_earliest, 5),
            "icir_recent": round(icir_recent, 4),
            "trend": ic_trend,
            "sample_count": len(ic_values),
        }

    healthy = [k for k, v in results.items() if v["status"] == "HEALTHY"]
    weakening = [k for k, v in results.items() if v["status"] == "WEAKENING"]
    decaying = [k for k, v in results.items() if v["status"] in ("DECAYING", "DEAD")]
    emerging = [k for k, v in results.items() if v["status"] == "EMERGING"]

    return {
        "status": "ok",
        "history_days": len(history),
        "forward_days_filter": forward_days,
        "factors": results,
        "healthy_factors": healthy,
        "weakening_factors": weakening,
        "decaying_factors": decaying,
        "emerging_factors": emerging,
        "analyzed_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }


def _classify_decay(
    ic_all: float,
    ic_recent: float,
    ic_early: float,
    trend: Dict[str, float],
    icir_recent: float = 0.0,
) -> tuple:
    """팩터 수명 상태 분류.

    Perplexity Q2 (2026-05-17) 학계 자문 적용:
    - ICIR < 0.2 → INSUFFICIENT_ICIR (weight floor 30% 강제)
    - ICIR ≥ 0.3 → 알파 신뢰 가능 게이트 (정상 운용)
    - ICIR ≥ 0.5 → 안정적 신호 (가중치 증가 정당화)
    - ICIR ≥ 1.0 → 매우 강 (과적합 점검)

    IC 자체 임계와 ICIR 안정성 임계 동시 적용.
    """
    slope = trend.get("slope", 0)
    r2 = trend.get("r_squared", 0)

    # DEAD: 최근 IC가 음수
    if ic_recent < -0.02:
        return "DEAD", f"IC 음수 전환 ({ic_recent:.4f}) — 팩터 무효"

    # INSUFFICIENT_ICIR: ICIR 측정 가능하고 < 0.2 (Perplexity Q2 권장)
    if icir_recent > 0 and icir_recent < 0.2:
        return (
            "INSUFFICIENT_ICIR",
            f"ICIR 불안정 ({icir_recent:.3f} < 0.2) — 노이즈 지배, weight floor 30%"
        )

    # EMERGING: 최근 IC가 급등
    if ic_recent > ic_early + 0.05 and ic_recent > 0.05:
        return "EMERGING", f"IC 급등 ({ic_early:.4f} → {ic_recent:.4f}) — 새 알파"

    # DECAYING: 추세적 하락 + 0 수렴
    if slope < -0.001 and r2 > 0.3 and ic_recent < 0.03:
        return "DECAYING", f"구조적 붕괴 (기울기 {slope:.5f}, IC→{ic_recent:.4f})"

    # WEAKENING: IC 양수이나 하락 추세
    if ic_all > 0.03 and ic_recent < ic_all * 0.6:
        return "WEAKENING", f"약화 중 (전체 {ic_all:.4f} → 최근 {ic_recent:.4f})"

    if slope < -0.0005 and ic_all > 0.02:
        return "WEAKENING", f"완만한 하락 (기울기 {slope:.5f})"

    # OVERFITTING_SUSPECT: ICIR ≥ 1.0 (Perplexity Q2 매우 드묾, 과적합 점검)
    if icir_recent >= 1.0:
        return (
            "OVERFITTING_SUSPECT",
            f"ICIR 매우 높음 ({icir_recent:.3f} ≥ 1.0) — 과적합 점검 필요"
        )

    # HEALTHY (Perplexity Q2: ICIR ≥ 0.3 게이트)
    if ic_recent > 0.03 and (icir_recent == 0 or icir_recent >= 0.3):
        suffix = f", ICIR {icir_recent:.3f}" if icir_recent > 0 else ""
        return "HEALTHY", f"유효 (IC {ic_recent:.4f}{suffix})"

    return "NEUTRAL", f"중립 (IC {ic_recent:.4f})"


def compute_ic_weight_adjustments() -> Dict[str, Any]:
    """IC/ICIR 히스토리 기반 팩터별 가중치 multiplier 산출.

    2026-05-25 FREEZE (PM 사전등록 [[project_ic_dead_freeze_2026_05_23]]):
    --------------------------------------------------------------------
    동적 IC 재계산 path 동결. 사유 = 유효-N ≈ 6 (factor_ic_history 112 스냅샷 / 39일,
    7d-forward overlap, autocorrelation 착시) 위에서 standalone IC로 자동 가중치
    변조 = N<50 이론고정([[feedback_threshold_calibration_overfit_guard]]) +
    옵션-2 방법론 동결([[project_win_condition_decision]]) 정면 위반.

    실측: PM 승인 4 factor (multi_factor/consensus/prediction/timing) 외에 자동 drift
    3 factor (mean_reversion/fundamental/quality) DEAD 진입. 특히 quality 30d ICIR
    0.888 HEALTHY 인데 7d-primary 가 0.0 으로 살해 = "7d 노이즈가 30d 우량 살해".

    동결 spec:
      - frozen static dict 반환 — PM 5/18 승인분 4 factor 만 multiplier 0.0 유지
      - status="frozen_2026_05_23"
      - 나머지 9 factor 는 dict 부재 → caller 자동 neutral (1.0)
      - analyze_factor_decay (측정·리포트) 는 호출 안 함 (적용 ⊥ 측정 분리, 후속 sprint)

    재개 trigger (RULE 7 1회 권한 보존):
      - 유효-N 마일스톤 (non-overlapping 또는 Newey-West 보정) 도달
      - 30d primary 전환 + marginal IC + PM 사전등록 재합의
      - 현 7d-standalone-snapshotN 방식 폐기
    """
    _FROZEN_DISABLE = {"multi_factor", "consensus", "prediction", "timing"}
    adjustments: Dict[str, Dict[str, Any]] = {}
    for factor in _FROZEN_DISABLE:
        adjustments[factor] = {
            "multiplier": 0.0,
            "raw_multiplier": 0.0,
            "confidence_factor": 1.0,
            "history_days": 0,
            "status": "DEAD",
            "ic_recent": 0.0,
            "frozen_reason": "PM_2026_05_18_disable",
        }
    return {
        "status": "frozen_2026_05_23",
        "primary_window": "frozen",
        "adjustments": adjustments,
        "log": [
            "FROZEN 2026-05-23 PM — multi_factor/consensus/prediction/timing disable 유지",
            "FROZEN 2026-05-23 PM — 9 factor 자동 drift 차단, neutral(1.0) 복원",
        ],
        "computed_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "frozen_at": "2026-05-23",
    }


def _compute_ic_weight_adjustments_unfrozen() -> Dict[str, Any]:
    """동적 IC 재계산 path — 2026-05-23 freeze 직전 코드 보존 (재개 trigger 도달 시 활용).

    호출 금지 (caller 없음). 본 함수 = 학술 trail + 후일 unfreeze sprint reference.
    """
    decay_7d = analyze_factor_decay(forward_days=7)
    decay_14d = analyze_factor_decay(forward_days=14)
    decay_30d = analyze_factor_decay(forward_days=30)

    primary = decay_7d if decay_7d.get("status") == "ok" else None
    if primary is None:
        primary = decay_14d if decay_14d.get("status") == "ok" else None
    if primary is None:
        primary = decay_30d if decay_30d.get("status") == "ok" else None
    if primary is None:
        return {"status": "insufficient_data", "adjustments": {}, "log": []}

    _STATUS_MULT = {
        "HEALTHY": 1.0,
        "EMERGING": 1.15,
        "NEUTRAL": 1.0,
        "WEAKENING": 0.85,
        "DECAYING": 0.6,
        # 2026-05-18 — Tier 2 C (PM 1회 권한 사용). Perplexity Q7 답 (Grinold-Kahn FLAM /
        # AQR / Barra IC-IR weighting 학술 정공법): IC negative 지속 factor = Disable (w=0).
        # 옛 0.3× demote = 임시 처리 (6개월 이내 초기 만 정당화). 운영 4 factor
        # (multi_factor IC -0.158 / prediction -0.094 / timing -0.167 / consensus -0.143)
        # 모두 IC < -0.05 지속 = Disable 학술 정공법.
        # Weight reset 정책: 3개월 연속 IC > +0.03 → 단계적 복원 (0.1× → 0.3× → 0.5× → 1.0×).
        "DEAD": 0.0,
        "INSUFFICIENT": 1.0,
        # Perplexity Q2 (2026-05-17): ICIR < 0.2 = weight floor 30% 강제
        "INSUFFICIENT_ICIR": 0.3,
        # ICIR ≥ 1.0 = 과적합 의심 = 가중치 보수적 (1.0 유지, 가중 증가 X)
        "OVERFITTING_SUSPECT": 1.0,
    }

    _EXCLUDE = {"brain_score", "safety_score"}

    aux_reports = {}
    for label, rpt in [("14d", decay_14d), ("30d", decay_30d)]:
        if rpt.get("status") == "ok":
            aux_reports[label] = rpt.get("factors", {})

    # ── 2026-05-16 Perplexity NQ1 보강: sample size confidence penalty ──
    # 7일 임계 완화 통계적 취약 (ICIR 0.5 가정 시 t-stat≥2 위해 T≥16 필요).
    # primary history 길이에 따라 multiplier 조정폭 축소:
    #   N ≥ 30: full multiplier (보수 정합)
    #   N 14-29: 0.7× shrinkage (중간)
    #   N 7-13: 0.4× shrinkage (취약 — 1.0 근처로 수렴)
    n_history = primary.get("history_days", len(primary.get("factors", {})))
    if n_history >= 30:
        confidence_factor = 1.0
    elif n_history >= 14:
        confidence_factor = 0.7
    else:  # 7-13
        confidence_factor = 0.4

    def _shrink_mult(raw_mult: float, conf: float) -> float:
        """raw multiplier 와 1.0 (no-op) 사이 conf 비율 보간."""
        return round(1.0 + (raw_mult - 1.0) * conf, 3)

    adjustments: Dict[str, Dict[str, Any]] = {}
    log: List[str] = []

    for factor, info in primary.get("factors", {}).items():
        if factor in _EXCLUDE:
            continue
        status = info.get("status", "NEUTRAL")
        raw_mult = _STATUS_MULT.get(status, 1.0)

        ic_recent = info.get("ic_recent", 0)
        if ic_recent > 0.10:
            raw_mult = min(raw_mult * 1.05, 1.20)
        elif ic_recent < -0.03:
            raw_mult = min(raw_mult, 0.50)

        # Perplexity NQ1: confidence penalty 적용
        mult = _shrink_mult(raw_mult, confidence_factor)

        cross_check = {}
        for label, aux_factors in aux_reports.items():
            aux = aux_factors.get(factor, {})
            if aux:
                cross_check[label] = {
                    "status": aux.get("status", "?"),
                    "ic_recent": round(float(aux.get("ic_recent", 0)), 5),
                }

        adjustments[factor] = {
            "multiplier": round(float(mult), 3),
            "raw_multiplier": round(float(raw_mult), 3),
            "confidence_factor": confidence_factor,
            "history_days": n_history,
            "status": status,
            "ic_recent": round(float(ic_recent), 5),
        }
        if cross_check:
            adjustments[factor]["cross_window"] = cross_check

        if mult != 1.0:
            log.append(f"{factor}: {status} (IC {ic_recent:.4f}, N={n_history}, conf={confidence_factor}) → x{mult:.2f} (raw x{raw_mult:.2f})")

    return {
        "status": "ok",
        "primary_window": primary.get("forward_days_filter", 7),
        "adjustments": adjustments,
        "log": log,
        "computed_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }


def generate_decay_alerts(
    decay_report: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    팩터 수명 분석 결과에서 텔레그램/Strategy Evolver용 경고 생성.
    """
    if decay_report is None:
        decay_report = analyze_factor_decay()

    if decay_report.get("status") != "ok":
        return []

    alerts: List[Dict[str, Any]] = []

    for factor, info in decay_report.get("factors", {}).items():
        status = info.get("status", "")

        if status == "DECAYING":
            alerts.append({
                "level": "critical",
                "factor": factor,
                "message": f"팩터 '{factor}' 구조적 붕괴 감지 — 가중치 축소 또는 교체 필요",
                "detail": info.get("label", ""),
                "action": "reduce_weight",
            })
        elif status == "DEAD":
            alerts.append({
                "level": "critical",
                "factor": factor,
                "message": f"팩터 '{factor}' IC 음수 — 즉시 비활성화 권장",
                "detail": info.get("label", ""),
                "action": "disable",
            })
        elif status == "WEAKENING":
            alerts.append({
                "level": "warning",
                "factor": factor,
                "message": f"팩터 '{factor}' 약화 추세 — 모니터링 강화",
                "detail": info.get("label", ""),
                "action": "monitor",
            })
        elif status == "EMERGING":
            alerts.append({
                "level": "info",
                "factor": factor,
                "message": f"팩터 '{factor}' 새 알파 감지 — 가중치 상향 검토",
                "detail": info.get("label", ""),
                "action": "increase_weight",
            })

    alerts.sort(key=lambda x: {"critical": 0, "warning": 1, "info": 2}.get(x["level"], 3))
    return alerts
