"""Framer 첫 화면(TodayActionsCard) 을 위한 portfolio summary attach.

TodayActionsCard 가 새로 읽는 4개 필드 + alias 1개:
  - portfolio_summary.{today_pct, cumulative_pct, is_paper}
  - system_health.overall_status   (기존 status alias — 컴포넌트 호환)
  - decision_queue                 (alerts WARNING+ active 추출)
  - validation.{cumulative_days, target_days, ic_ir, hit_rate}
  - evolution.{label, count}

원칙:
  - 외부 호출 없음, portfolio 데이터만 사용
  - 모든 필드 누락 시 graceful (None / "" / [])
  - 기존 portfolio 필드 절대 덮어쓰지 않음 (system_health 도 alias 만 추가)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 검증 누적일수 목표 — VAMS 검증 정신 (메모리 project_validation_plan)
DEFAULT_VALIDATION_TARGET_DAYS = 90


def _safe_get(d: Any, *path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def compute_portfolio_summary(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """포트폴리오 P&L 요약 — VAMS 가상 운영 기준."""
    vams = portfolio.get("vams") or {}
    cum = vams.get("total_return_pct")
    holdings = vams.get("holdings") or []

    # today_pct = 보유 종목들의 1일 변동률 가중 평균. 일별 변동 필드가 없으면 None.
    today_pct: Optional[float] = None
    try:
        weighted_sum = 0.0
        weight_total = 0.0
        for h in holdings:
            change = h.get("today_change_pct")
            if not isinstance(change, (int, float)):
                continue
            cost = h.get("total_cost") or 0
            if not isinstance(cost, (int, float)) or cost <= 0:
                continue
            weighted_sum += float(change) * float(cost)
            weight_total += float(cost)
        if weight_total > 0:
            today_pct = round(weighted_sum / weight_total, 2)
    except Exception as e:
        logger.debug("portfolio_summary today_pct calc failed: %s", e)

    return {
        "today_pct": today_pct,
        "cumulative_pct": round(float(cum), 2) if isinstance(cum, (int, float)) else None,
        "is_paper": True,  # VAMS 는 가상 — 실계좌 전환 시 collector 가 덮어쓰면 됨
        "holdings_count": len(holdings),
    }


def compute_decision_queue(portfolio: Dict[str, Any]) -> List[Dict[str, Any]]:
    """결정 큐 — 운영자가 오늘 액션해야 할 항목.

    포함:
      - alerts 중 level WARNING/CRITICAL (resolved 아님)
      - trade_plan_meta verdict 가 manual_review/invalidated
      - master_rule drift (있으면)
    """
    queue: List[Dict[str, Any]] = []

    # alerts WARNING+
    for a in portfolio.get("alerts") or []:
        if not isinstance(a, dict):
            continue
        level = (a.get("level") or "").upper()
        if level not in ("WARNING", "CRITICAL", "ERROR"):
            continue
        if a.get("resolved") is True:
            continue
        queue.append({
            "source": "alert",
            "level": level,
            "category": a.get("category"),
            "message": a.get("message"),
            "action": a.get("action"),
        })

    # trade_plan_meta verdict
    tpm = portfolio.get("trade_plan_meta") or {}
    verdict = (tpm.get("active_verdict") or tpm.get("status") or "").lower()
    if verdict in ("manual_review", "invalidated"):
        queue.append({
            "source": "trade_plan_meta",
            "level": "WARNING" if verdict == "manual_review" else "CRITICAL",
            "category": "trade_plan",
            "message": f"trade_plan v0 verdict = {verdict}",
            "action": "메타-검증 결과 확인",
        })

    # master rule drift (있으면)
    drift = portfolio.get("master_rule_drift") or {}
    if isinstance(drift, dict) and drift.get("flagged"):
        queue.append({
            "source": "master_rule_drift",
            "level": "WARNING",
            "category": "rule_drift",
            "message": drift.get("summary") or "9권 마스터 룰 drift 감지",
            "action": "원전 vs 코드 비교",
        })

    return queue


def compute_validation(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """누적 검증일수 + 신뢰도 글로벌 통계.

    cumulative_days 는 factor_ic 의 가장 큰 윈도우 사용 (30/14/7).
    실측 누적 일수가 더 길어지면 별도 카운터로 확장 가능.
    """
    fic = portfolio.get("factor_ic") or {}
    windows = fic.get("windows_available") or []
    cumulative_days: Optional[int] = None
    if windows:
        try:
            cumulative_days = max(int(w) for w in windows if str(w).isdigit())
        except Exception:
            cumulative_days = None

    # IC IR 평균 (절대값) — factor_ic.ranking 에서
    ic_ir_avg: Optional[float] = None
    ranking = fic.get("ranking") or []
    if isinstance(ranking, list) and ranking:
        try:
            vals = [abs(float(r.get("icir"))) for r in ranking
                    if isinstance(r, dict) and isinstance(r.get("icir"), (int, float))]
            if vals:
                ic_ir_avg = round(sum(vals) / len(vals), 3)
        except Exception:
            ic_ir_avg = None

    # hit_rate 글로벌 (BUY/WATCH 가중평균)
    ba_grades = (portfolio.get("brain_accuracy") or {}).get("grades") or {}
    total_count = 0
    weighted_hit = 0.0
    for g, info in ba_grades.items():
        if not isinstance(info, dict):
            continue
        cnt = info.get("count")
        hr = info.get("hit_rate")  # 0~100
        if isinstance(cnt, (int, float)) and isinstance(hr, (int, float)) and cnt > 0:
            total_count += int(cnt)
            weighted_hit += float(cnt) * float(hr)
    hit_rate_global: Optional[float] = (
        round(weighted_hit / total_count / 100.0, 3) if total_count > 0 else None
    )

    return {
        "cumulative_days": cumulative_days,
        "target_days": DEFAULT_VALIDATION_TARGET_DAYS,
        "ic_ir": ic_ir_avg,
        "hit_rate": hit_rate_global,
        "sample_total": total_count or None,
    }


def compute_evolution(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """어제 대비 진화 신호 — trade_plan_evolution_signals.change_candidates 우선."""
    tpe = portfolio.get("trade_plan_evolution_signals") or {}
    candidates = tpe.get("change_candidates") or []
    count = len(candidates) if isinstance(candidates, list) else 0

    # brain_quality status 변화 (있으면 추가 신호)
    bq = portfolio.get("brain_quality") or {}
    bq_status = bq.get("status")

    if count > 0:
        label = f"{count}개 변경 후보"
    elif bq_status:
        label = f"품질 {bq_status}"
    else:
        label = "변경 없음"

    return {
        "label": label,
        "count": count,
        "brain_quality_status": bq_status,
        "brain_weights_diff": [],  # weights 시계열 누적 후 채울 자리
    }


def _hit_rate_for_grade(portfolio: Dict[str, Any], grade: Optional[str]) -> Optional[float]:
    """grade 별 적중률 (0~1). brain_accuracy.grades[grade].hit_rate (%) 변환."""
    if not grade:
        return None
    ba_grades = (portfolio.get("brain_accuracy") or {}).get("grades") or {}
    info = ba_grades.get(grade) or ba_grades.get(str(grade).upper())
    if not isinstance(info, dict):
        return None
    hr = info.get("hit_rate")
    if isinstance(hr, (int, float)):
        return round(float(hr) / 100.0, 3)
    return None


def _enrich_action_confidence(
    portfolio: Dict[str, Any],
    validation: Dict[str, Any],
) -> None:
    """daily_actions.{buy,sell,watch} 각각에 confidence_days/ic_ir/hit_rate 부착.

    validation 결과 재사용 — confidence_days/ic_ir 는 글로벌 동일,
    hit_rate 는 종목 grade 에 따라 다름.
    """
    da = portfolio.get("daily_actions")
    if not isinstance(da, dict):
        return

    cum_days = validation.get("cumulative_days")
    ic_ir = validation.get("ic_ir")

    for kind in ("buy", "sell", "watch"):
        action = da.get(kind)
        if not isinstance(action, dict):
            continue
        # SELL 은 보유 종목 — grade 정보 없을 수 있음. None 이면 글로벌 hit_rate.
        grade = action.get("grade")
        per_grade_hit = _hit_rate_for_grade(portfolio, grade)
        action["confidence_days"] = cum_days
        action["ic_ir"] = ic_ir
        action["hit_rate"] = (
            per_grade_hit if per_grade_hit is not None else validation.get("hit_rate")
        )


def attach_to_portfolio(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """portfolio 에 4 새 필드 + system_health.overall_status alias attach.

    main.py 의 daily_actions attach 직후 호출.
    """
    if not isinstance(portfolio, dict):
        return portfolio

    try:
        # system_health.overall_status alias (기존 status 가 더 표준)
        sh = portfolio.get("system_health")
        if isinstance(sh, dict) and "overall_status" not in sh:
            sh["overall_status"] = sh.get("status")

        portfolio["portfolio_summary"] = compute_portfolio_summary(portfolio)
        portfolio["decision_queue"] = compute_decision_queue(portfolio)
        validation = compute_validation(portfolio)
        portfolio["validation"] = validation
        portfolio["evolution"] = compute_evolution(portfolio)

        # daily_actions 에 신뢰도 필드 enrich (TodayActionsCard 카드 하단 라벨)
        _enrich_action_confidence(portfolio, validation)
    except Exception as e:  # noqa: BLE001 — 가드 정책
        logger.warning("dashboard_summary attach failed: %s", e, exc_info=True)

    return portfolio
