"""
"오늘 리포트 발행 가능?" — 8개 조건 자동 판정.

판정 결과:
  ready          : 모든 조건 만족 → cron 자동 진행
  manual_review  : 일부 조건 미만족 (1~2개) → PDF 생성 + 워터마크 강조
  hold           : 핵심 조건 미만족 (3개+) → PDF 생성 차단 + 알림

8개 조건 (실측 임계 — 환경변수 가능):
  1. data_freshness_ok       : portfolio 신선도 < TRUST_FRESHNESS_MAX_MIN (기본 1440분 = 24h)
  2. core_sources_ok         : yfinance/fred/kis/dart 모두 정상
  3. drift_below_threshold   : drift overall_score < TRUST_DRIFT_THRESHOLD (기본 0.3)
                                + 첫날(no_baseline)은 자동 PASS
  4. ai_models_ok            : gemini/anthropic 모두 critical/warning 아님
  5. brain_distribution_normal: BUY+ 비율 어제 대비 ±20%p 이내 (verity_brain.grade 기준)
                                grade 미부여 = FAIL (측정 불가, brain 산출 점검 필요)
  6. pipeline_cron_ok        : 마지막 portfolio.updated_at 24h 이내
                                (mode 별 임계 분리 미구현 — quick/realtime 도 24h 적용)
  7. deadman_clear           : system_health.status != "critical" (warning 통과)
  8. pdf_generator_ok        : 폰트 + 출력 디렉토리 OK

저장: data/metadata/trust_log.jsonl
"""
from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

_PATH = os.path.join(DATA_DIR, "metadata", "trust_log.jsonl")
_REPORTS_DIR = os.path.join(DATA_DIR, "reports")
_FONT_PATH = os.path.join(os.path.dirname(DATA_DIR), "api", "reports", "fonts", "NanumGothic.ttf")

# 임계 — 일배치 cron 기준. 환경변수로 덮어쓰기 가능.
FRESHNESS_MAX_MIN = int(os.environ.get("TRUST_FRESHNESS_MAX_MIN", "1440"))
DRIFT_THRESHOLD = float(os.environ.get("TRUST_DRIFT_THRESHOLD", "0.3"))
BRAIN_DIST_DELTA_MAX = 0.20  # BUY+ 비율 변화 ±20%p


def _check_freshness(data_health: Dict[str, Any]) -> Dict[str, Any]:
    meta = data_health.get("_meta") if isinstance(data_health, dict) else None
    if not meta:
        return {"ok": False, "detail": "data_health 미산출"}
    fm = meta.get("portfolio_freshness_minutes")
    if fm is None:
        return {"ok": False, "detail": "freshness 미상"}
    return {"ok": fm < FRESHNESS_MAX_MIN,
            "detail": f"{fm}분 (임계 {FRESHNESS_MAX_MIN}분)"}


def _check_core_sources(data_health: Dict[str, Any]) -> Dict[str, Any]:
    meta = data_health.get("_meta") if isinstance(data_health, dict) else None
    ok = bool(meta and meta.get("core_sources_ok"))
    bad = []
    if isinstance(data_health, dict):
        for src in ("yfinance", "fred", "kis", "dart"):
            v = data_health.get(src)
            if isinstance(v, dict) and v.get("status") == "critical":
                bad.append(src)
    return {"ok": ok, "detail": f"core 소스 {'정상' if ok else '이상: ' + ','.join(bad)}"}


def _check_drift(drift: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(drift, dict):
        return {"ok": True, "detail": "drift 평가 불가 (베이스 없음 — 첫날)"}
    err = drift.get("error")
    if err == "no_baseline":
        return {"ok": True, "detail": "drift 베이스 없음 (첫날)"}
    score = drift.get("overall_drift_score", 0.0)
    level = drift.get("level", "ok")
    return {"ok": score < DRIFT_THRESHOLD and level != "critical",
            "detail": f"PSI={score:.3f} level={level}"}


def _check_ai_models(portfolio: dict) -> Dict[str, Any]:
    sh = portfolio.get("system_health") or {}
    api_health = sh.get("api_health") or {}
    bad = []
    for m in ("gemini", "anthropic"):
        v = api_health.get(m)
        if isinstance(v, dict) and v.get("status") in ("critical", "warning"):
            bad.append(m)
    return {"ok": len(bad) == 0,
            "detail": "AI 정상" if not bad else f"이상: {','.join(bad)}"}


def _check_brain_distribution(portfolio: dict) -> Dict[str, Any]:
    """BUY+ 비율 어제 대비 ±20%p 이내인지 — explainability.jsonl 활용.

    grade 위치 = recommendations[i].verity_brain.grade (top-level grade 아님).
    이전 버그: r.get("grade") 만 봐서 항상 [] → silent PASS.
    """
    recs = portfolio.get("recommendations") or []
    if not recs:
        return {"ok": False, "detail": "recommendations 없음"}

    grades = [
        (r.get("verity_brain") or {}).get("grade")
        for r in recs
        if (r.get("verity_brain") or {}).get("grade")
    ]
    if not grades:
        return {"ok": False,
                "detail": f"grade 미부여 ({len(recs)}종목 모두) — 측정 불가, brain 산출 점검 필요"}

    today_buy_pct = sum(1 for g in grades if g in ("STRONG_BUY", "BUY")) / len(grades)

    # 어제 비교
    explain_path = os.path.join(DATA_DIR, "metadata", "explainability.jsonl")
    if not os.path.exists(explain_path):
        return {"ok": True, "detail": f"BUY+ {today_buy_pct:.1%} (베이스 없음)"}

    try:
        last = None
        today_str = now_kst().strftime("%Y-%m-%d")
        with open(explain_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if e.get("date") == today_str:
                        continue
                    last = e
                except json.JSONDecodeError:
                    continue
        if not last:
            return {"ok": True, "detail": f"BUY+ {today_buy_pct:.1%} (베이스 없음)"}

        prev_features = last.get("raw_features") or {}
        prev_buy = prev_features.get("grade_distribution_buy_pct")
        if prev_buy is None:
            return {"ok": True, "detail": f"BUY+ {today_buy_pct:.1%} (어제 데이터 없음)"}
        delta = today_buy_pct - prev_buy
        ok = abs(delta) < BRAIN_DIST_DELTA_MAX
        return {"ok": ok,
                "detail": f"BUY+ {today_buy_pct:.1%} (어제 {prev_buy:.1%}, Δ{delta*100:+.1f}%p)"}
    except OSError:
        return {"ok": True, "detail": f"BUY+ {today_buy_pct:.1%} (비교 실패)"}


def _check_pipeline_cron(portfolio: dict) -> Dict[str, Any]:
    """마지막 cron 성공 여부 — portfolio.updated_at 24시간 이내."""
    ts = portfolio.get("updated_at")
    if not ts:
        return {"ok": False, "detail": "updated_at 없음"}
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        age = (now_kst() - dt).total_seconds() / 3600
        return {"ok": age < 24,
                "detail": f"마지막 업데이트 {age:.1f}h 전"}
    except (ValueError, TypeError):
        return {"ok": False, "detail": "updated_at 파싱 실패"}


def _check_deadman(portfolio: dict) -> Dict[str, Any]:
    """system_health.status == 'critical' 여부."""
    sh = portfolio.get("system_health") or {}
    status = sh.get("status", "unknown")
    return {"ok": status != "critical",
            "detail": f"system_health={status}"}


def _check_pdf_generator() -> Dict[str, Any]:
    """폰트 파일 존재 + reports 디렉토리 쓰기 가능."""
    issues = []
    if not os.path.exists(_FONT_PATH):
        issues.append("NanumGothic.ttf 누락")
    try:
        os.makedirs(_REPORTS_DIR, exist_ok=True)
        if not os.access(_REPORTS_DIR, os.W_OK):
            issues.append("reports/ 쓰기 불가")
    except OSError as e:
        issues.append(f"reports/ 생성 실패: {e}")
    return {"ok": len(issues) == 0,
            "detail": "정상" if not issues else "; ".join(issues)}


def report_readiness(portfolio: Optional[dict],
                     data_health: Optional[Dict[str, Any]] = None,
                     drift: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    8개 조건 자동 판정.

    Args:
      portfolio: portfolio.json 로드 결과
      data_health: check_data_health() 결과 (없으면 빈 평가)
      drift: compute_drift() 결과 (없으면 베이스 없음 처리)

    Returns:
      {
        "verdict": "ready"|"hold"|"manual_review",
        "conditions": {...},
        "satisfied": int,
        "total": int,
        "blocking_reasons": [...],
        "recommendation": str,
        "_meta": {...}
      }
    """
    if not isinstance(portfolio, dict):
        return {
            "verdict": "hold",
            "conditions": {},
            "satisfied": 0,
            "total": 8,
            "blocking_reasons": ["portfolio 없음"],
            "recommendation": "발행 차단 — 포트폴리오 데이터 부재",
            "_meta": {"error": "no_portfolio"},
        }

    data_health = data_health or {}
    checks = {
        "data_freshness_ok": _check_freshness(data_health),
        "core_sources_ok": _check_core_sources(data_health),
        "drift_below_threshold": _check_drift(drift or {}),
        "ai_models_ok": _check_ai_models(portfolio),
        "brain_distribution_normal": _check_brain_distribution(portfolio),
        "pipeline_cron_ok": _check_pipeline_cron(portfolio),
        "deadman_clear": _check_deadman(portfolio),
        "pdf_generator_ok": _check_pdf_generator(),
    }

    conditions = {k: v["ok"] for k, v in checks.items()}
    satisfied = sum(1 for v in conditions.values() if v)
    total = len(conditions)
    blocking_reasons = [f"{k}: {checks[k]['detail']}"
                       for k, v in conditions.items() if not v]

    # verdict 결정
    failed = total - satisfied
    if failed == 0:
        verdict = "ready"
        recommendation = "발행 가능 — 자동 cron 진행"
    elif failed <= 2:
        verdict = "manual_review"
        recommendation = f"발행 가능하나 검수 필요 ({failed}건 미충족)"
    else:
        verdict = "hold"
        recommendation = f"발행 차단 — {failed}건 미충족, 수동 점검 필요"

    return {
        "verdict": verdict,
        "conditions": conditions,
        "details": {k: v["detail"] for k, v in checks.items()},
        "satisfied": satisfied,
        "total": total,
        "blocking_reasons": blocking_reasons,
        "recommendation": recommendation,
        "_meta": {
            "checked_at": now_kst().isoformat(),
        },
    }


def persist_trust(result: Dict[str, Any]) -> str:
    """jsonl 누적 — cron 실행마다."""
    try:
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        entry = {
            "timestamp": (result.get("_meta") or {}).get("checked_at") or now_kst().isoformat(),
            "verdict": result.get("verdict"),
            "satisfied": result.get("satisfied"),
            "total": result.get("total"),
            "blocking_reasons": result.get("blocking_reasons", []),
        }
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return _PATH
    except OSError as e:
        logger.warning("trust_score: persist failed: %s", e)
        return ""
