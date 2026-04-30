"""
입력 feature 분포의 일별 변화 측정 — PSI (Population Stability Index).

수식:
  PSI = Σ (today_pct - yesterday_pct) × ln(today_pct / yesterday_pct)
  bin 별 합산. 작은 값(0)일 때 epsilon 처리.

해석:
  PSI 0~0.1   : 안정 (ok)
  PSI 0.1~0.2 : drift 의심 (warning)
  PSI 0.2+    : drift 발생 (critical)

저장: data/metadata/feature_drift.jsonl

가드 (spec §6):
  - scipy 없이 순수 Python (의존성 추가 회피)
  - feature 단일값 비교 (단일값 PSI 는 bin=2 근사)
  - 어제 데이터 부재 시 None 반환 — drift 평가 보류
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import timedelta
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

_PATH = os.path.join(DATA_DIR, "metadata", "feature_drift.jsonl")

# PSI 임계 (spec §1.2)
PSI_OK = 0.1
PSI_WARN = 0.2

# 추출 대상 feature (spec §1.2)
FEATURE_KEYS = (
    # 매크로
    "vix_avg", "usd_krw", "us_10y", "sp500_change_pct", "mood_score",
    # 종목 평균
    "avg_per", "avg_pbr", "avg_roe", "avg_debt_ratio",
    # 시장
    "avg_brain_score", "grade_distribution_buy_pct", "vci_avg",
    # 수급
    "foreign_net_avg", "institution_net_avg",
    # 뉴스
    "news_sentiment_avg",
)


def extract_features(portfolio: Optional[dict]) -> Dict[str, float]:
    """
    portfolio.json 에서 PSI 비교 대상 스칼라 feature 추출.
    누락 시 None — drift 계산에서 제외.
    """
    if not isinstance(portfolio, dict):
        return {}

    out: Dict[str, float] = {}
    macro = portfolio.get("macro") or {}
    recs = portfolio.get("recommendations") or []
    market = portfolio.get("market_summary") or {}
    vams = portfolio.get("vams") or {}

    def _scalar(d: Any, *keys) -> Optional[float]:
        cur = d
        for k in keys:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(k)
        if isinstance(cur, (int, float)) and not (isinstance(cur, float) and math.isnan(cur)):
            return float(cur)
        return None

    # 매크로 — dst_key 가 *_change_pct 면 change_pct, *_score 면 score, 그외 value 우선
    for src_key, dst_key in [
        ("vix", "vix_avg"),
        ("usd_krw", "usd_krw"),
        ("us_10y", "us_10y"),
        ("sp500", "sp500_change_pct"),
        ("market_mood", "mood_score"),
    ]:
        if dst_key.endswith("_change_pct"):
            sub_keys = ("change_pct", "value")
        elif dst_key.endswith("_score") or dst_key == "mood_score":
            sub_keys = ("score", "value")
        else:
            sub_keys = ("value", "change_pct")
        v = None
        for sk in sub_keys:
            v = _scalar(macro, src_key, sk)
            if v is not None:
                break
        if v is not None:
            out[dst_key] = v

    # recommendations 평균
    if recs:
        for src, dst in [("per", "avg_per"), ("pbr", "avg_pbr"), ("roe", "avg_roe"),
                         ("debt_ratio", "avg_debt_ratio"), ("brain_score", "avg_brain_score")]:
            vals = [r.get(src) for r in recs if isinstance(r.get(src), (int, float))]
            if vals:
                out[dst] = round(sum(vals) / len(vals), 4)

        # grade 분포 — 위치는 verity_brain.grade (top-level grade 아님)
        grades = [
            (r.get("verity_brain") or {}).get("grade")
            for r in recs
            if (r.get("verity_brain") or {}).get("grade")
        ]
        if grades:
            buy_count = sum(1 for g in grades if g in ("STRONG_BUY", "BUY"))
            out["grade_distribution_buy_pct"] = round(buy_count / len(grades), 4)

        # 수급 평균 (flow)
        for src, dst in [("foreign_net", "foreign_net_avg"), ("institution_net", "institution_net_avg")]:
            vals = []
            for r in recs:
                flow = r.get("flow")
                if isinstance(flow, dict) and isinstance(flow.get(src), (int, float)):
                    vals.append(flow[src])
            if vals:
                out[dst] = round(sum(vals) / len(vals), 4)

        # 뉴스 감성 평균
        s_vals = []
        for r in recs:
            s = r.get("social_sentiment") or r.get("sentiment")
            if isinstance(s, dict) and isinstance(s.get("score"), (int, float)):
                s_vals.append(s["score"])
            elif isinstance(s, (int, float)):
                s_vals.append(s)
        if s_vals:
            out["news_sentiment_avg"] = round(sum(s_vals) / len(s_vals), 4)

    # VCI 평균 (vams 또는 verity_brain)
    vci_avg = _scalar(vams, "vci_avg") or _scalar(portfolio.get("verity_brain") or {}, "vci_avg")
    if vci_avg is not None:
        out["vci_avg"] = vci_avg

    return out


def _psi_single(yesterday: float, today: float, ref_scale: float = 1.0,
                feature_name: Optional[str] = None) -> float:
    """
    단일 스칼라 PSI 근사. 두 값을 정규화 (yesterday 기준 ±50% bin) 하여 PSI 산출.

    완전한 분포 PSI 는 아니지만, 메타데이터 누적 후 bin-PSI 로 대체 가능.

    B-2 수정 (2026-04-29):
      % 형식 feature (이름에 _change_pct / _pct 포함) 의 경우 부호 변경 (예: 0.12 → -0.49)
      을 단순 abs 비율로 처리하면 PSI 폭증 (4.34 등). 이건 알고리즘 약점.
      → % feature 는 absolute pp difference 로 normalize.
    """
    if yesterday is None or today is None:
        return 0.0

    # % 형식 feature: 부호 변경 시 abs 차이로 PSI 산출 (단위 = pp)
    if feature_name and (feature_name.endswith("_change_pct")
                         or feature_name.endswith("_pct")
                         or feature_name in ("mood_score", "vix_avg")):
        diff = abs(today - yesterday)
        # 일일 변동 0.5pp = PSI 0.05 (warning), 1.5pp = PSI 0.15 (critical) 정도로 scale
        return round(min(diff * 0.1, 1.0), 4)

    # 부호 변경 또는 어제 값이 0 근방이면 ratio 가 폭주 → 자연스러운 상한으로 처리.
    # 부호가 다르면 명백한 drift, PSI 0.5 (critical) 으로 안전 클램프.
    if (yesterday > 0 and today < 0) or (yesterday < 0 and today > 0):
        return 0.5
    eps = 1e-6
    y = abs(yesterday) + eps
    t = abs(today) + eps
    # 어제 결측(=0) → 오늘 복구는 drift 가 아니라 데이터 가용성 회복. PSI 0 으로 스킵.
    # 반대 경우(어제 있음 → 오늘 0)는 데이터 손실이라 critical (0.5) 처리.
    if abs(yesterday) < 1e-3:
        return 0.0
    if abs(today) < 1e-3 and abs(yesterday) >= 1e-3:
        return 0.5
    ratio = t / y
    if ratio <= 0:
        return 0.0
    psi = abs(ratio - 1) * abs(math.log(ratio))
    # 수치적 노이즈 방지 — PSI > 1.0 은 이미 critical 이라 추가 정보 없음. 1.0 으로 캡.
    return round(min(psi, 1.0), 4)


def _psi_level(psi: float) -> str:
    if psi < PSI_OK:
        return "ok"
    if psi < PSI_WARN:
        return "warning"
    return "critical"


def _load_yesterday() -> Optional[Dict[str, float]]:
    """jsonl 에서 어제 또는 가장 최근 누적된 feature 로드."""
    if not os.path.exists(_PATH):
        return None
    try:
        last_entry = None
        today_str = now_kst().strftime("%Y-%m-%d")
        with open(_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if e.get("date") == today_str:
                        continue  # 오늘 자체는 건너뜀
                    last_entry = e
                except json.JSONDecodeError:
                    continue
        if not last_entry:
            return None
        return last_entry.get("raw_features") or None
    except OSError as e:
        logger.warning("feature_drift: yesterday load failed: %s", e)
        return None


def compute_drift(yesterday: Optional[Dict[str, float]] = None,
                  today: Optional[Dict[str, float]] = None,
                  features: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    PSI 기반 drift 계산.

    Args:
      yesterday: 어제 feature dict. None 이면 jsonl 최신본 로드.
      today: 오늘 feature dict. 필수.
      features: 평가 대상 키 (None → FEATURE_KEYS 전체).

    Returns:
      {
        "feature_drifts": {feature: {psi, level, yesterday, today}, ...},
        "overall_drift_score": 0.18,
        "drifted_features": [...],
        "level": "warning",
        "comparable_count": 12,
      }
    """
    if today is None:
        return {"feature_drifts": {}, "overall_drift_score": 0.0,
                "drifted_features": [], "level": "ok", "comparable_count": 0,
                "error": "no_today_features"}

    if yesterday is None:
        yesterday = _load_yesterday()

    if yesterday is None:
        return {"feature_drifts": {}, "overall_drift_score": 0.0,
                "drifted_features": [], "level": "ok", "comparable_count": 0,
                "error": "no_baseline"}

    keys = features or list(FEATURE_KEYS)
    drifts: Dict[str, Dict[str, Any]] = {}
    psi_values: List[float] = []
    drifted: List[str] = []

    for k in keys:
        y = yesterday.get(k)
        t = today.get(k)
        if y is None or t is None:
            continue
        psi = _psi_single(y, t, feature_name=k)
        level = _psi_level(psi)
        drifts[k] = {"psi": psi, "level": level,
                     "yesterday": round(y, 4), "today": round(t, 4)}
        psi_values.append(psi)
        if level in ("warning", "critical"):
            drifted.append(k)

    overall = round(sum(psi_values) / len(psi_values), 4) if psi_values else 0.0
    overall_level = _psi_level(overall) if psi_values else "ok"

    # cry-wolf 완화 (2026-04-30): 단일 feature critical 1개로 overall critical 승격하면
    # mood_score 등 변동 큰 매크로가 trust verdict 를 manual_review 로 항상 묶어버려
    # 자가진단 신호 의미가 약화됨 (실제 측정: 11회 중 8회 critical, overall=0.09 인데도).
    # 새 룰: critical 비율 ≥ 50% OR overall ≥ PSI_WARN(0.2) 일 때만 overall critical.
    # 단발 critical 은 drifted_features 로 노출되되 overall_level 은 _psi_level(overall) 따름.
    crit_count = sum(1 for d in drifts.values() if d["level"] == "critical")
    if drifts:
        crit_ratio = crit_count / len(drifts)
        if crit_ratio >= 0.5 or overall >= PSI_WARN:
            overall_level = "critical"
        elif crit_count >= 1 and overall_level == "ok":
            # 단발 critical — 최소 warning 으로 격상 (silent 통과 방지)
            overall_level = "warning"

    return {
        "feature_drifts": drifts,
        "overall_drift_score": overall,
        "drifted_features": drifted,
        "level": overall_level,
        "comparable_count": len(psi_values),
        "critical_count": crit_count,
    }


def persist_drift(result: Dict[str, Any], today_features: Dict[str, float]) -> str:
    """jsonl 누적 — 다음 날 비교 베이스로 사용."""
    try:
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        entry = {
            "date": now_kst().strftime("%Y-%m-%d"),
            "timestamp": now_kst().isoformat(),
            "overall_drift_score": result.get("overall_drift_score", 0.0),
            "level": result.get("level", "ok"),
            "drifted_features": result.get("drifted_features", []),
            "comparable_count": result.get("comparable_count", 0),
            "raw_features": today_features,  # 다음 날 비교용
        }
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return _PATH
    except OSError as e:
        logger.warning("feature_drift: persist failed: %s", e)
        return ""
