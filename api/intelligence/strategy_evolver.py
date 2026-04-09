"""
Verity Brain V2 — 전략 진화 엔진

Claude Sonnet에게 현재 constitution 가중치 + 최근 성과 데이터를 주고
가중치/임계값 변경을 제안받는다. 제안은 백테스트 검증 후
텔레그램 승인 → constitution 업데이트 → 다음 full 분석에 자동 반영.

적중률 80% + 제안 10회 이상 누적 시 자동 승인 모드 전환.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import anthropic

from api.config import (
    ANTHROPIC_API_KEY,
    DATA_DIR,
    STRATEGY_REGISTRY_PATH,
    STRATEGY_MAX_WEIGHT_DELTA,
    STRATEGY_MIN_SNAPSHOT_DAYS,
    now_kst,
)

_CONSTITUTION_PATH = os.path.join(DATA_DIR, "verity_constitution.json")

_SYSTEM_PROMPT = """너는 15년 차 퀀트 리서치 헤드다. VERITY 시스템의 투자 판단 가중치를 최적화하는 역할이다.

원칙:
- 과적합(overfitting) 경계: 최근 7일만 보고 판단하지 마라. 14일·30일 추세도 함께 봐라
- 한 번에 큰 변경 금지: 각 가중치는 ±0.05 이내로만 조정
- 가중치 합은 반드시 1.0 유지
- 변경 이유는 반드시 숫자로 뒷받침
- 바꿀 필요 없으면 솔직히 null 반환
- 반말 OK. 서론 금지. 핵심만.

퀀트 팩터(momentum/quality/volatility/mean_reversion)의 IC와 Decay 정보가 있으면:
- IC 양수 + ICIR > 0.5인 팩터는 가중치 유지/상향
- DECAYING/DEAD 팩터는 가중치 하향 또는 대체 제안
- EMERGING 팩터는 가중치 상향 검토
- multi_factor v3 가중치(9팩터)도 조정 대상에 포함"""


def _load_constitution() -> Dict[str, Any]:
    try:
        with open(_CONSTITUTION_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_constitution(const: Dict[str, Any]):
    with open(_CONSTITUTION_PATH, "w", encoding="utf-8") as f:
        json.dump(const, f, ensure_ascii=False, indent=2)


def _load_registry() -> Dict[str, Any]:
    try:
        with open(STRATEGY_REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "current_version": 1,
            "auto_approve": False,
            "auto_approve_threshold": {"min_proposals": 10, "hit_rate_pct": 80},
            "cumulative_stats": {
                "total_proposals": 0, "accepted": 0, "rejected": 0,
                "hit_count": 0, "hit_rate_pct": 0,
            },
            "versions": [],
            "pending_proposal": None,
        }


def _save_registry(reg: Dict[str, Any]):
    with open(STRATEGY_REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2, default=str)


# ── 성과 데이터 수집 ─────────────────────────────────────

def collect_performance_data(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """backtest_archive + postmortem + VAMS + 퀀트 팩터 IC/Decay를 모아 진화 입력 구성."""
    from api.intelligence.backtest_archive import evaluate_past_recommendations
    from api.workflows.archiver import load_snapshots_range

    bt_stats = evaluate_past_recommendations([7, 14, 30])

    pm = portfolio.get("postmortem", {})
    failures = pm.get("failures", [])
    failure_patterns: List[str] = []
    misleading_factors: Dict[str, int] = {}
    for f in failures:
        mf = f.get("misleading_factor", "")
        if mf:
            misleading_factors[mf] = misleading_factors.get(mf, 0) + 1
        lesson = f.get("lesson", "")
        if lesson:
            failure_patterns.append(lesson)

    vams = portfolio.get("vams", {})
    sim = vams.get("simulation_stats", {})

    snapshots = load_snapshots_range(30)

    # 퀀트 팩터 IC/Decay 분석
    quant_intel: Dict[str, Any] = {}
    try:
        from api.quant.alpha.alpha_scanner import scan_all_factors
        from api.quant.alpha.factor_decay import analyze_factor_decay, generate_decay_alerts

        ic_scan = scan_all_factors(forward_days=7)
        decay_report = analyze_factor_decay()
        decay_alerts = generate_decay_alerts(decay_report)

        quant_intel = {
            "significant_factors": ic_scan.get("significant_factors", []),
            "decaying_factors": ic_scan.get("decaying_factors", []),
            "factor_ranking": ic_scan.get("ranking", [])[:10],
            "decay_alerts": [
                {"factor": a["factor"], "level": a["level"], "action": a["action"]}
                for a in decay_alerts
            ],
        }
    except Exception as e:
        quant_intel = {"error": str(e)[:100]}

    return {
        "periods": bt_stats.get("periods", {}),
        "postmortem": {
            "failure_count": len(failures),
            "misleading_factors": misleading_factors,
            "lessons": failure_patterns[:5],
            "overall_lesson": pm.get("lesson", ""),
            "system_suggestion": pm.get("system_suggestion", ""),
        },
        "vams": {
            "win_rate": sim.get("win_rate", 0),
            "total_trades": sim.get("total_trades", 0),
            "max_drawdown_pct": sim.get("max_drawdown_pct", 0),
            "realized_pnl": sim.get("realized_pnl", 0),
        },
        "quant_factors": quant_intel,
        "snapshot_count": len(snapshots),
    }


# ── Claude 제안 요청 ─────────────────────────────────────

def _build_evolution_prompt(
    constitution: Dict[str, Any],
    perf: Dict[str, Any],
) -> str:
    fact_w = constitution.get("fact_score", {}).get("weights", {})
    sent_w = constitution.get("sentiment_score", {}).get("weights", {})
    grades = constitution.get("decision_tree", {}).get("grades", {})

    periods = perf.get("periods", {})
    p7 = periods.get("7d", {})
    p14 = periods.get("14d", {})
    p30 = periods.get("30d", {})
    pm = perf.get("postmortem", {})
    vams = perf.get("vams", {})

    qi = perf.get("quant_factors", {})
    qi_ranking = qi.get("factor_ranking", [])
    qi_decaying = qi.get("decaying_factors", [])
    qi_significant = qi.get("significant_factors", [])
    qi_alerts = qi.get("decay_alerts", [])

    quant_section = ""
    if qi_ranking:
        ranking_str = ", ".join(f"{r['factor']}(ICIR={r['icir']:.3f})" for r in qi_ranking[:8])
        quant_section = f"""
═══ 퀀트 팩터 IC 분석 ═══
팩터 순위(ICIR): {ranking_str}
유의미 팩터: {', '.join(qi_significant) if qi_significant else '없음'}
붕괴 경고: {', '.join(qi_decaying) if qi_decaying else '없음'}
Decay 알림: {json.dumps(qi_alerts, ensure_ascii=False) if qi_alerts else '없음'}
"""

    return f"""[VERITY Brain 가중치 최적화 요청]

═══ 현행 Fact Score 가중치 (합=1.0) ═══
{json.dumps(fact_w, indent=2)}

═══ 현행 Sentiment Score 가중치 (합=1.0) ═══
{json.dumps(sent_w, indent=2)}

═══ 등급 임계값 ═══
{json.dumps(grades, indent=2)}

═══ 최근 성과 ═══
7일: 적중률 {p7.get('hit_rate', 'N/A')}% | 평균수익 {p7.get('avg_return', 'N/A')}% | Sharpe {p7.get('sharpe', 'N/A')} | {p7.get('total_recs', 0)}건
14일: 적중률 {p14.get('hit_rate', 'N/A')}% | 평균수익 {p14.get('avg_return', 'N/A')}% | Sharpe {p14.get('sharpe', 'N/A')} | {p14.get('total_recs', 0)}건
30일: 적중률 {p30.get('hit_rate', 'N/A')}% | 평균수익 {p30.get('avg_return', 'N/A')}% | Sharpe {p30.get('sharpe', 'N/A')} | {p30.get('total_recs', 0)}건

═══ AI 오심 복기 ═══
실패 {pm.get('failure_count', 0)}건
잘못된 시그널 팩터: {json.dumps(pm.get('misleading_factors', {}), ensure_ascii=False)}
교훈: {pm.get('overall_lesson', '없음')}
시스템 제안: {pm.get('system_suggestion', '없음')}

═══ VAMS 시뮬레이션 ═══
승률 {vams.get('win_rate', 0):.1f}% | 총 {vams.get('total_trades', 0)}회 | MDD {vams.get('max_drawdown_pct', 0):.1f}% | 실현손익 {vams.get('realized_pnl', 0):+,.0f}원
{quant_section}
═══ 규칙 ═══
- 각 가중치 변경폭: 최대 ±{STRATEGY_MAX_WEIGHT_DELTA}
- fact_score weights 합 = 1.0, sentiment_score weights 합 = 1.0 강제
- 등급 임계값(brain_score)도 조정 가능하나 합리적 범위 유지
- 퀀트 팩터 IC가 DECAYING이면 해당 팩터 가중치 하향 검토
- 바꿀 필요 없으면 "changes": null

JSON만:
{{
  "changes": {{
    "fact_score_weights": {{"키": 새값, ...}} 또는 null,
    "sentiment_score_weights": {{"키": 새값, ...}} 또는 null,
    "grade_thresholds": {{"등급": 새_min_brain_score, ...}} 또는 null
  }} 또는 null,
  "reason": "왜 바꾸는지 핵심 한 줄",
  "expected_improvement": "어떤 지표가 얼마나 개선될지 예상"
}}"""


def propose_evolution(
    perf: Dict[str, Any],
    constitution: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Claude Sonnet에게 가중치 변경 제안을 받는다."""
    if not ANTHROPIC_API_KEY:
        return None

    prompt = _build_evolution_prompt(constitution, perf)

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]

        result = json.loads(text)
        result["_input_tokens"] = message.usage.input_tokens
        result["_output_tokens"] = message.usage.output_tokens
        return result

    except json.JSONDecodeError:
        print("  [V2] Claude 응답 JSON 파싱 실패")
        return None
    except anthropic.RateLimitError:
        print("  [V2] Claude 속도 제한")
        return None
    except Exception as e:
        print(f"  [V2] Claude 호출 실패: {str(e)[:80]}")
        return None


# ── 제안 검증 ────────────────────────────────────────────

def validate_proposal(
    proposal: Dict[str, Any],
    constitution: Dict[str, Any],
) -> tuple[bool, str]:
    """제안된 가중치가 규칙을 만족하는지 검증."""
    changes = proposal.get("changes")
    if changes is None:
        return True, "변경 없음"

    fact_changes = changes.get("fact_score_weights")
    if fact_changes:
        current = constitution.get("fact_score", {}).get("weights", {})
        merged = {**current, **fact_changes}
        total = sum(merged.values())
        if abs(total - 1.0) > 0.01:
            return False, f"fact_score 가중치 합 {total:.3f} != 1.0"
        for k, v in fact_changes.items():
            if k not in current:
                return False, f"존재하지 않는 fact 키: {k}"
            if abs(v - current[k]) > STRATEGY_MAX_WEIGHT_DELTA + 0.001:
                return False, f"{k} 변경폭 {abs(v - current[k]):.3f} > 최대 {STRATEGY_MAX_WEIGHT_DELTA}"

    sent_changes = changes.get("sentiment_score_weights")
    if sent_changes:
        current = constitution.get("sentiment_score", {}).get("weights", {})
        merged = {**current, **sent_changes}
        total = sum(merged.values())
        if abs(total - 1.0) > 0.01:
            return False, f"sentiment 가중치 합 {total:.3f} != 1.0"
        for k, v in sent_changes.items():
            if k not in current:
                return False, f"존재하지 않는 sentiment 키: {k}"
            if abs(v - current[k]) > STRATEGY_MAX_WEIGHT_DELTA + 0.001:
                return False, f"{k} 변경폭 {abs(v - current[k]):.3f} > 최대 {STRATEGY_MAX_WEIGHT_DELTA}"

    grade_changes = changes.get("grade_thresholds")
    if grade_changes:
        for grade, score in grade_changes.items():
            if not (0 <= score <= 100):
                return False, f"{grade} 임계값 {score}이 0~100 범위 밖"

    return True, "검증 통과"


# ── 스냅샷 기반 가상 백테스트 ─────────────────────────────

def simulate_proposal(
    proposal: Dict[str, Any],
    constitution: Dict[str, Any],
) -> Dict[str, Any]:
    """제안된 가중치로 과거 스냅샷을 재채점하여 가상 성과를 산출."""
    from api.predictors.backtester import backtest_brain_strategy

    changes = proposal.get("changes")
    if not changes:
        return {"sharpe": 0, "hit_rate": 0, "expected_value": 0, "note": "변경 없음"}

    override = {}
    if changes.get("fact_score_weights"):
        current_fact = dict(constitution.get("fact_score", {}).get("weights", {}))
        current_fact.update(changes["fact_score_weights"])
        override["fact_score_weights"] = current_fact
    if changes.get("sentiment_score_weights"):
        current_sent = dict(constitution.get("sentiment_score", {}).get("weights", {}))
        current_sent.update(changes["sentiment_score_weights"])
        override["sentiment_score_weights"] = current_sent
    if changes.get("grade_thresholds"):
        override["grade_thresholds"] = changes["grade_thresholds"]

    return backtest_brain_strategy(override)


# ── 제안 적용 ────────────────────────────────────────────

def apply_proposal(proposal: Dict[str, Any], backtest_result: Dict[str, Any]):
    """제안을 constitution에 반영하고 registry에 버전 기록."""
    constitution = _load_constitution()
    registry = _load_registry()
    changes = proposal.get("changes", {})

    if changes.get("fact_score_weights"):
        constitution.setdefault("fact_score", {}).setdefault("weights", {})
        constitution["fact_score"]["weights"].update(changes["fact_score_weights"])

    if changes.get("sentiment_score_weights"):
        constitution.setdefault("sentiment_score", {}).setdefault("weights", {})
        constitution["sentiment_score"]["weights"].update(changes["sentiment_score_weights"])

    if changes.get("grade_thresholds"):
        grades = constitution.setdefault("decision_tree", {}).setdefault("grades", {})
        for grade, score in changes["grade_thresholds"].items():
            if grade in grades:
                grades[grade]["min_brain_score"] = score

    _save_constitution(constitution)

    new_version = registry.get("current_version", 1) + 1
    registry["current_version"] = new_version
    registry["versions"].append({
        "version": new_version,
        "applied_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "proposed_by": "claude-sonnet-4",
        "change_summary": proposal.get("reason", ""),
        "reason": proposal.get("expected_improvement", ""),
        "backtest_before": None,
        "backtest_after": backtest_result,
        "actual_performance": None,
    })

    stats = registry.setdefault("cumulative_stats", {})
    stats["accepted"] = stats.get("accepted", 0) + 1

    _check_auto_approve_transition(registry)
    _save_registry(registry)

    return new_version


def reject_proposal(reason: str = ""):
    """대기 중인 제안을 거절 처리."""
    registry = _load_registry()
    pending = registry.get("pending_proposal")
    if not pending:
        return False

    registry["pending_proposal"] = None
    stats = registry.setdefault("cumulative_stats", {})
    stats["rejected"] = stats.get("rejected", 0) + 1
    _save_registry(registry)
    return True


def rollback_strategy() -> Optional[int]:
    """직전 버전의 constitution으로 롤백."""
    registry = _load_registry()
    versions = registry.get("versions", [])
    if len(versions) < 2:
        return None

    constitution = _load_constitution()
    prev = versions[-2]
    current_ver = registry["current_version"]

    registry["current_version"] = current_ver + 1
    registry["versions"].append({
        "version": current_ver + 1,
        "applied_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "proposed_by": "rollback",
        "change_summary": f"v{current_ver} 롤백 → v{prev['version']} 기반 복원",
        "reason": "사령관 롤백 명령",
        "backtest_before": None,
        "backtest_after": None,
        "actual_performance": None,
    })
    _save_registry(registry)

    return current_ver + 1


def _check_auto_approve_transition(registry: Dict[str, Any]):
    """자동 승인 전환 조건 확인."""
    threshold = registry.get("auto_approve_threshold", {})
    stats = registry.get("cumulative_stats", {})

    min_proposals = threshold.get("min_proposals", 10)
    min_hit_rate = threshold.get("hit_rate_pct", 80)
    total = stats.get("total_proposals", 0)
    hit_rate = stats.get("hit_rate_pct", 0)

    if total >= min_proposals and hit_rate >= min_hit_rate and not registry.get("auto_approve"):
        registry["auto_approve"] = True


# ── 제안 발송 (텔레그램) ──────────────────────────────────

def send_strategy_proposal(proposal: Dict[str, Any], backtest_result: Dict[str, Any]) -> bool:
    """전략 제안을 텔레그램으로 발송."""
    from api.notifications.telegram import send_message

    changes = proposal.get("changes", {})
    reason = proposal.get("reason", "사유 없음")

    parts = ["<b>🧠 Brain V2 전략 제안</b>\n"]

    if changes.get("fact_score_weights"):
        parts.append("<b>Fact 가중치 변경:</b>")
        for k, v in changes["fact_score_weights"].items():
            parts.append(f"  {k}: → {v:.2f}")

    if changes.get("sentiment_score_weights"):
        parts.append("<b>Sentiment 가중치 변경:</b>")
        for k, v in changes["sentiment_score_weights"].items():
            parts.append(f"  {k}: → {v:.2f}")

    if changes.get("grade_thresholds"):
        parts.append("<b>등급 임계값 변경:</b>")
        for k, v in changes["grade_thresholds"].items():
            parts.append(f"  {k}: → {v}")

    parts.append(f"\n<b>사유:</b> {reason}")

    bt = backtest_result
    parts.append(f"\n<b>백테스트 결과:</b>")
    parts.append(f"  Sharpe: {bt.get('sharpe', 0):.2f}")
    parts.append(f"  적중률: {bt.get('hit_rate', 0):.1f}%")
    parts.append(f"  기대값(E): {bt.get('expected_value', 0):.2f}%")

    parts.append(f"\n승인: /approve_strategy")
    parts.append(f"거절: /reject_strategy")

    return send_message("\n".join(parts))


# ── 메인 진화 루프 ────────────────────────────────────────

def run_evolution_cycle(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """full 분석 후 실행되는 전략 진화 사이클."""
    from api.workflows.archiver import list_available_dates

    result = {
        "status": "skipped",
        "reason": "",
        "generated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }

    dates = list_available_dates()
    if len(dates) < STRATEGY_MIN_SNAPSHOT_DAYS:
        result["reason"] = f"스냅샷 {len(dates)}일 < 최소 {STRATEGY_MIN_SNAPSHOT_DAYS}일"
        return result

    if not ANTHROPIC_API_KEY:
        result["reason"] = "ANTHROPIC_API_KEY 미설정"
        return result

    registry = _load_registry()
    if registry.get("pending_proposal"):
        result["status"] = "pending"
        result["reason"] = "이전 제안 승인/거절 대기 중"
        return result

    constitution = _load_constitution()
    if not constitution:
        result["reason"] = "verity_constitution.json 로드 실패"
        return result

    print("  [V2] 성과 데이터 수집...")
    perf = collect_performance_data(portfolio)

    print("  [V2] Claude 전략 제안 요청...")
    proposal = propose_evolution(perf, constitution)
    if not proposal:
        result["reason"] = "Claude 제안 실패"
        return result

    changes = proposal.get("changes")
    if changes is None:
        result["status"] = "no_change"
        result["reason"] = proposal.get("reason", "변경 불필요")
        return result

    valid, msg = validate_proposal(proposal, constitution)
    if not valid:
        result["status"] = "invalid"
        result["reason"] = f"검증 실패: {msg}"
        return result

    registry["cumulative_stats"]["total_proposals"] = registry["cumulative_stats"].get("total_proposals", 0) + 1
    _save_registry(registry)

    print("  [V2] 백테스트 검증...")
    bt_result = simulate_proposal(proposal, constitution)

    current_bt = backtest_brain_strategy_current()
    bt_result["current_sharpe"] = current_bt.get("sharpe", 0)

    if bt_result.get("sharpe", 0) <= current_bt.get("sharpe", 0):
        result["status"] = "rejected_by_backtest"
        result["reason"] = f"Sharpe 미개선: 현행 {current_bt.get('sharpe', 0):.2f} >= 제안 {bt_result.get('sharpe', 0):.2f}"
        print(f"  [V2] {result['reason']}")
        return result

    if registry.get("auto_approve"):
        print("  [V2] 자동 승인 모드 → 즉시 적용")
        new_ver = apply_proposal(proposal, bt_result)
        result["status"] = "auto_applied"
        result["new_version"] = new_ver
        result["proposal"] = proposal
        result["backtest"] = bt_result

        try:
            from api.notifications.telegram import send_message
            send_message(
                f"🧠 Brain V2 자동 적용 완료 (v{new_ver})\n"
                f"사유: {proposal.get('reason', '?')}\n"
                f"Sharpe: {current_bt.get('sharpe', 0):.2f} → {bt_result.get('sharpe', 0):.2f}"
            )
        except Exception:
            pass

        return result

    registry["pending_proposal"] = {
        "proposal": proposal,
        "backtest_result": bt_result,
        "proposed_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }
    _save_registry(registry)

    print("  [V2] 텔레그램 승인 요청 발송...")
    send_strategy_proposal(proposal, bt_result)

    result["status"] = "pending_approval"
    result["proposal"] = proposal
    result["backtest"] = bt_result
    return result


def backtest_brain_strategy_current() -> Dict[str, Any]:
    """현행 constitution으로 백테스트 (비교 기준용)."""
    from api.predictors.backtester import backtest_brain_strategy
    return backtest_brain_strategy(override=None)


def get_strategy_status() -> Dict[str, Any]:
    """현재 전략 상태 요약 (텔레그램 봇용)."""
    registry = _load_registry()
    constitution = _load_constitution()

    return {
        "current_version": registry.get("current_version", 1),
        "auto_approve": registry.get("auto_approve", False),
        "stats": registry.get("cumulative_stats", {}),
        "pending": registry.get("pending_proposal") is not None,
        "fact_weights": constitution.get("fact_score", {}).get("weights", {}),
        "sentiment_weights": constitution.get("sentiment_score", {}).get("weights", {}),
    }
