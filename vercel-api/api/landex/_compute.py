"""LANDEX 계산 라이브러리 — 정규화·이상치·등급·Hysteresis·Confidence.

순수 함수 위주, 외부 의존성 없음 (numpy 미사용, stdlib만).
백엔드 라우트(/api/landex/scores)와 단위 테스트가 직접 import.
"""
from typing import Dict, List, Optional, Tuple
from statistics import median

from . import _methodology as M


# ──────────────────────────────────────────────────────────────
# ◆ 이상치 필터링 (3-Layer)
# ──────────────────────────────────────────────────────────────

def filter_outliers_rule_based(trades: List[dict]) -> Tuple[List[dict], int]:
    """1차: 룰 기반 (직거래·증여·상속·등기 누락) 제외.

    Returns: (filtered_trades, removed_count)
    """
    excluded = set(M.OUTLIER_FILTERS["rule_based"]["exclude_trade_types"])
    require_reg = M.OUTLIER_FILTERS["rule_based"]["require_registration"]
    out = []
    for t in trades:
        if t.get("trade_type") in excluded:
            continue
        if require_reg and not t.get("registered_at"):
            continue
        out.append(t)
    return out, len(trades) - len(out)


def filter_outliers_statistical(trades: List[dict], price_field: str = "price_pyeong") -> Tuple[List[dict], int]:
    """2차: 통계 기반 (단지·면적 평균 대비 ±30% 또는 IQR×1.5 중 더 보수적).

    trades 는 단일 단지·면적 풀 (호출자가 그룹핑 책임).
    """
    if len(trades) < 3:
        return trades, 0  # 표본 부족 — 통계 필터 미적용

    prices = sorted(t[price_field] for t in trades if t.get(price_field) is not None)
    if not prices:
        return trades, 0

    # IQR
    q1 = prices[len(prices) // 4]
    q3 = prices[(len(prices) * 3) // 4]
    iqr = q3 - q1
    iqr_lo = q1 - iqr * M.OUTLIER_FILTERS["statistical"]["iqr_multiplier"]
    iqr_hi = q3 + iqr * M.OUTLIER_FILTERS["statistical"]["iqr_multiplier"]

    # ±30% Hard cut (median 기준)
    med = median(prices)
    hard_pct = M.OUTLIER_FILTERS["statistical"]["hard_cut_pct"]
    hard_lo = med * (1 - hard_pct)
    hard_hi = med * (1 + hard_pct)

    # 더 보수적인 쪽 (좁은 범위)
    lo = max(iqr_lo, hard_lo)
    hi = min(iqr_hi, hard_hi)

    out = [t for t in trades if t.get(price_field) is not None and lo <= t[price_field] <= hi]
    return out, len(trades) - len(out)


def aggregate_price(trades: List[dict], price_field: str = "price_pyeong") -> Tuple[Optional[float], bool]:
    """3차: 분포 기반 집계 — median 기본, low_liquidity 플래그.

    Returns: (aggregated_price, low_liquidity_flag)
    """
    prices = [t[price_field] for t in trades if t.get(price_field) is not None]
    if not prices:
        return None, True
    threshold = M.OUTLIER_FILTERS["distribution"]["min_trades_for_median"]
    return median(prices), len(prices) < threshold


# ──────────────────────────────────────────────────────────────
# ◆ Min-Max 정규화 (5% Clipping)
# ──────────────────────────────────────────────────────────────

def normalize_minmax(values: List[float], inverted: bool = False) -> List[float]:
    """전체 풀에서 상하위 5% 클리핑 후 0-100 점수로 변환.

    inverted=True이면 100 - score (낮을수록 좋은 지표).
    None 값은 None 그대로 반환 (호출자가 결측치 처리).
    """
    valid = [v for v in values if v is not None]
    if not valid:
        return [None] * len(values)
    valid_sorted = sorted(valid)
    n = len(valid_sorted)
    clip_pct = M.NORMALIZATION["outlier_clip_pct"]
    lo_idx = int(n * clip_pct)
    hi_idx = int(n * (1 - clip_pct)) - 1
    lo = valid_sorted[lo_idx] if lo_idx < n else valid_sorted[0]
    hi = valid_sorted[max(hi_idx, 0)]
    rng = hi - lo
    if rng <= 0:
        return [50.0 if v is not None else None for v in values]

    out = []
    for v in values:
        if v is None:
            out.append(None)
            continue
        clamped = max(lo, min(hi, v))
        score = (clamped - lo) / rng * 100
        if inverted:
            score = 100 - score
        out.append(round(score, 2))
    return out


# ──────────────────────────────────────────────────────────────
# ◆ V/D/S/C/R → LANDEX 가중합
# ──────────────────────────────────────────────────────────────

def compute_landex(scores: Dict[str, Optional[float]], preset: str = "balanced") -> Tuple[Optional[float], int]:
    """V/D/S/C/R 각 0-100 점수 → 가중합 LANDEX (0-100) + 결측치 개수.

    preset: 'balanced' / 'growth' / 'value'
    """
    weights = M.WEIGHT_PRESETS.get(preset, M.WEIGHT_PRESETS["balanced"])
    total = 0.0
    weight_used = 0.0
    missing = 0
    for k, w in weights.items():
        v = scores.get(k)
        if v is None:
            missing += 1
            continue
        # R은 inverted: 점수 자체가 이미 정규화된 경우 그대로 사용
        # (호출자가 normalize_minmax(inverted=True)로 처리 가정)
        total += v * w
        weight_used += w
    if weight_used == 0:
        return None, missing
    # 결측 가중치 보정 — 사용된 가중치로 재정규화
    landex = total / weight_used
    return round(landex, 2), missing


# ──────────────────────────────────────────────────────────────
# ◆ 등급 변환 (10단계 + Hysteresis + 5단계 UI)
# ──────────────────────────────────────────────────────────────

def score_to_tier10(score: Optional[float], prev_tier: Optional[str] = None) -> Optional[dict]:
    """0-100 점수 → 10단계 등급. Hysteresis 버퍼 적용.

    prev_tier 가 있으면 경계에서 ±buffer_pct 만큼 이전 등급 유지 (깜빡임 방지).

    버킷 정의가 정수 max(예: 69)라 소수점 점수(69.12)가 매칭 실패하던 버그 수정 —
    TIER_10 가 높은 등급부터 정렬되어 있으므로 score >= min 인 첫 tier 반환.
    """
    if score is None:
        return None
    buffer = M.HYSTERESIS["buffer_pct"]

    # Hysteresis: prev_tier 의 경계에 buffer 만큼 여유
    if prev_tier:
        for t in M.TIER_10:
            if t["code"] == prev_tier:
                if t["min"] - buffer <= score <= t["max"] + buffer + 0.99:
                    return dict(t)
                break

    # 기본: TIER_10 은 S+ → F 순으로 정렬 → score >= min 인 첫 tier
    for t in M.TIER_10:
        if score >= t["min"]:
            return dict(t)
    return None


def tier10_to_tier5(tier10_code: Optional[str]) -> Optional[str]:
    if tier10_code is None:
        return None
    return M.TIER_10_TO_5.get(tier10_code)


# ──────────────────────────────────────────────────────────────
# ◆ Divergence 감지 (LANDEX vs GEI Stage)
# ──────────────────────────────────────────────────────────────

def detect_divergence(landex_trend: str, gei_stage: int, volume_trend: str) -> List[dict]:
    """LANDEX-GEI-거래량 다이버전스 감지.

    landex_trend: 'up' | 'down' | 'flat'
    gei_stage: 0~4
    volume_trend: 'up' | 'down' | 'flat'

    Returns: 감지된 경고 리스트 (각 dict: {kind, severity, message})
    """
    warnings = []
    # LANDEX 상승 + GEI 과열 (Stage 4) → 강한 경고
    if landex_trend == "up" and gei_stage >= 4:
        warnings.append({
            "kind": "landex_up_gei_overheat",
            "severity": "high",
            "message": "LANDEX 상승하나 GEI Stage 4 — 과열 후 조정 위험",
        })
    # LANDEX 상승 + 거래량 급감 → 가격 왜곡 의심
    if landex_trend == "up" and volume_trend == "down":
        warnings.append({
            "kind": "landex_up_volume_down",
            "severity": "mid",
            "message": "LANDEX 상승하나 거래량 급감 — 호가 위주 가격 변동 가능성",
        })
    # GEI 과열 + 거래량 급감 → 진정 신호
    if gei_stage >= 3 and volume_trend == "down":
        warnings.append({
            "kind": "gei_high_volume_down",
            "severity": "low",
            "message": "GEI 높음 + 거래량 감소 — 과열 진정 가능성",
        })
    return warnings


# ──────────────────────────────────────────────────────────────
# ◆ Confidence Score (DigestPublishPanel)
# ──────────────────────────────────────────────────────────────

def compute_confidence(checks: List[dict], divergence_warnings: int = 0) -> Tuple[float, bool]:
    """체크리스트 통과 비율 + 다이버전스 감점 → Confidence 점수 (0-100).

    Returns: (confidence_score, ready_to_publish)
    """
    if not checks:
        return 0.0, False
    passed = sum(1 for c in checks if c.get("passed"))
    base = passed / len(checks) * 100
    penalty = divergence_warnings * M.CONFIDENCE["divergence_penalty"]
    score = max(0.0, base - penalty)
    return round(score, 2), score >= M.CONFIDENCE["publish_threshold"]
