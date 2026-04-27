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

        # grade 분포
        grades = [r.get("grade") for r in recs if r.get("grade")]
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


def _psi_single(yesterday: float, today: float, ref_scale: float = 1.0) -> float:
    """
    단일 스칼라 PSI 근사. 두 값을 정규화 (yesterday 기준 ±50% bin) 하여 PSI 산출.

    완전한 분포 PSI 는 아니지만, 메타데이터 누적 후 bin-PSI 로 대체 가능.
    현재는 변화율 기반 근사:
      ratio = today / yesterday
      PSI ≈ |ratio - 1| × log(ratio) (안정 근사)
    """
    if yesterday is None or today is None:
        return 0.0
    eps = 1e-6
    y = abs(yesterday) + eps
    t = abs(today) + eps
    ratio = t / y
    if ratio <= 0:
        return 0.0
    return round(abs(ratio - 1) * abs(math.log(ratio)), 4)


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
        psi = _psi_single(y, t)
        level = _psi_level(psi)
        drifts[k] = {"psi": psi, "level": level,
                     "yesterday": round(y, 4), "today": round(t, 4)}
        psi_values.append(psi)
        if level in ("warning", "critical"):
            drifted.append(k)

    overall = round(sum(psi_values) / len(psi_values), 4) if psi_values else 0.0
    overall_level = _psi_level(overall) if psi_values else "ok"
    # 1개라도 critical 이면 overall critical
    if any(d["level"] == "critical" for d in drifts.values()):
        overall_level = "critical"

    return {
        "feature_drifts": drifts,
        "overall_drift_score": overall,
        "drifted_features": drifted,
        "level": overall_level,
        "comparable_count": len(psi_values),
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
