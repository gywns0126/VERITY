"""multibagger_watch — 텐버거 후보 WATCH (로깅 전용, 결정 0).

2026-06-09 신설. PM 결정 B (US 확장 대신 KR 소형주 + 멀티배거). 동결 funnel(품질-가치)이
구조적으로 밀어내는 *초기 텐버거형 KR 소형주*를 별 렌즈로 관측·누적.

원칙:
  - 로깅 전용. 결정/실자본 영향 0. active 결정 운영 = 2026-09 gate (project_multi_bagger_watch 결정 22).
    watch 는 *관측*이라 gate 위배 아님 (decision_logging_separation 정합).
  - 재사용: lynch_classifier.classify_lynch_kr (6분류) + multi_bagger_signals.evaluate_multi_bagger_signals
    (5 신호: revenue_acceleration / operating_leverage / category_leader / industry_s_curve / hold_pnl).
    새 신호 로직 0.
  - "시간이 해자" — 언제 텐버거 후보였나는 backfill 불가. forward-only append.
  - funnel freeze 와 무관 (별 트랙, 결정 직교).

watch list = KR 소형주(floor 위 ~ 대형 아래) 중 Fast Grower OR 신호 1+ triggered (focused).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst
from api.intelligence.lynch_classifier import classify_lynch_kr
from api.analyzers.multi_bagger_signals import evaluate_multi_bagger_signals

_PATH = os.path.join(DATA_DIR, "metadata", "multibagger_watch.jsonl")

# 소형주 watch 범위 상한 (텐버거 zone: hard_floor 위 ~ 대형 아래). 관측 범위지 결정 임계 아님 — env 조정 가능.
SMALLCAP_MAX_KRW = int(os.environ.get("MULTIBAGGER_SMALLCAP_MAX_KRW", str(1_000_000_000_000)))  # 1조원


def _is_kr_smallcap(s: Dict[str, Any]) -> bool:
    if (s.get("currency") or "").upper() == "USD":
        return False
    mc = s.get("market_cap")
    try:
        mc = float(mc)
    except (TypeError, ValueError):
        return False
    return 0 < mc < SMALLCAP_MAX_KRW


def build_watch(stocks: List[Dict[str, Any]], as_of: Optional[str] = None) -> List[Dict[str, Any]]:
    """KR 소형주 중 Fast Grower OR 신호 triggered 후보만 watch 레코드 생성 (로깅 전용).

    peers = KR 소형주 모집단 (category_leader/industry_s_curve 섹터 peer 비교용).
    """
    as_of = as_of or now_kst().strftime("%Y-%m-%d")
    smallcaps = [s for s in (stocks or []) if _is_kr_smallcap(s)]
    peers = {"recommendations": smallcaps}  # multi_bagger_signals 섹터 peer context

    out: List[Dict[str, Any]] = []
    for s in smallcaps:
        lynch = classify_lynch_kr(s)
        sigs = evaluate_multi_bagger_signals(s, peers)
        is_fast = lynch.get("class") == "FAST_GROWER"
        alert_count = int(sigs.get("alert_count", 0) or 0)
        if not (is_fast or alert_count > 0):
            continue  # focused watch list — 무신호 소형주 제외
        out.append({
            "watch_date": as_of,
            "ticker": str(s.get("ticker")),
            "name": s.get("name"),
            "market_cap": s.get("market_cap"),
            "sector": s.get("sector"),
            "lynch_class": lynch.get("class"),
            "lynch_data_quality": lynch.get("data_quality"),
            "alert_count": alert_count,
            "signals": {
                k: {"triggered": bool(v.get("triggered")), "score": v.get("score")}
                for k, v in sigs.items() if isinstance(v, dict)
            },
            "spec_version": "watch.v0",
            "note": "로깅 전용 — 결정 0 (active gate 2026-09)",
        })
    return out


def log_watch(records: List[Dict[str, Any]], path: Optional[str] = None) -> int:
    """watch 레코드 append (forward-only). 실패해도 caller 진행 (부수효과)."""
    if not records:
        return 0
    target = path or _PATH
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(records)


def run_watch(stocks: List[Dict[str, Any]], path: Optional[str] = None) -> int:
    """build + log 일괄 (wide_scan 등 caller 진입점). 반환 = 로깅된 후보 수."""
    return log_watch(build_watch(stocks), path=path)
