"""
Verity Brain V2 — 전략 진화 엔진

Claude Sonnet에게 현재 constitution 가중치 + 최근 성과 데이터를 주고
가중치/임계값 변경을 제안받는다. 제안은 백테스트 검증 후
텔레그램 승인 → constitution 업데이트 → 다음 full 분석에 자동 반영.

자동 승인 전환 조건 (V2):
  누적 적중률 80%+ AND 강세 75%+ AND 약세 70%+ AND 롤링 윈도우 적중률 65%+
서킷 브레이커:
  자동 승인 중 롤링 적중률 < 55% 또는 Sharpe 하락 추세 → 즉시 해제
"""
from __future__ import annotations

import json
import os
import shutil
from typing import Any, Dict, List, Optional

import anthropic

from api.mocks import mockable
from api.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL_DEFAULT,
    CLAUDE_MODEL_HEAVY,
    CLAUDE_OPUS_ENABLE,
    DATA_DIR,
    STRATEGY_REGISTRY_PATH,
    STRATEGY_MAX_WEIGHT_DELTA,
    STRATEGY_MAX_CUMULATIVE_DRIFT,
    STRATEGY_MIN_SNAPSHOT_DAYS,
    STRATEGY_MIN_SNAPSHOT_DAYS_FORCED,
    STRATEGY_MIN_OOS_DAYS,
    now_kst,
)

_CONSTITUTION_PATH = os.path.join(DATA_DIR, "verity_constitution.json")
_CONSTITUTION_BACKUP_DIR = os.path.join(DATA_DIR, "constitution_backups")

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
    """원자적 쓰기 + .bak 유지 + 타임스탬프 아카이브(롤백 소스)."""
    os.makedirs(os.path.dirname(_CONSTITUTION_PATH) or ".", exist_ok=True)
    tmp = _CONSTITUTION_PATH + ".tmp"
    bak = _CONSTITUTION_PATH + ".bak"
    if os.path.exists(_CONSTITUTION_PATH):
        try:
            shutil.copy2(_CONSTITUTION_PATH, bak)
        except Exception:
            pass
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(const, f, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(tmp, _CONSTITUTION_PATH)
    except Exception:
        if os.path.exists(bak):
            try:
                shutil.copy2(bak, _CONSTITUTION_PATH)
            except Exception:
                pass
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
        raise
    try:
        os.makedirs(_CONSTITUTION_BACKUP_DIR, exist_ok=True)
        stamp = now_kst().strftime("%Y%m%dT%H%M%S")
        shutil.copy2(
            _CONSTITUTION_PATH,
            os.path.join(_CONSTITUTION_BACKUP_DIR, f"constitution_{stamp}.json"),
        )
    except Exception:
        pass


_CIRCUIT_BREAKER_DEFAULTS: Dict[str, Any] = {
    "rolling_window": 8,
    "min_rolling_hit_rate_pct": 55,
    "max_rolling_mdd_pct": 15,
    "min_rolling_sharpe_improvement": -0.10,
    "cooldown_proposals": 5,
    "triggered_at": None,
    "reason": "",
    "proposals_since_trigger": 0,
}


def _load_registry() -> Dict[str, Any]:
    try:
        with open(STRATEGY_REGISTRY_PATH, "r", encoding="utf-8") as f:
            reg = json.load(f)
        reg.setdefault("circuit_breaker", dict(_CIRCUIT_BREAKER_DEFAULTS))
        for k, v in _CIRCUIT_BREAKER_DEFAULTS.items():
            reg["circuit_breaker"].setdefault(k, v)
        return reg
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "current_version": 1,
            "auto_approve": False,
            "auto_approve_threshold": {
                "min_proposals": 10,
                "hit_rate_pct": 80,
                "bull_hit_rate_pct": 75,
                "bear_hit_rate_pct": 70,
            },
            "circuit_breaker": dict(_CIRCUIT_BREAKER_DEFAULTS),
            "cumulative_stats": {
                "total_proposals": 0, "accepted": 0, "rejected": 0,
                "hit_count": 0, "hit_rate_pct": 0,
                "bull_proposals": 0, "bull_hits": 0, "bull_hit_rate_pct": 0,
                "bear_proposals": 0, "bear_hits": 0, "bear_hit_rate_pct": 0,
            },
            "versions": [],
            "pending_proposal": None,
        }


def _save_registry(reg: Dict[str, Any]):
    """원자적 쓰기 + .bak 유지."""
    os.makedirs(os.path.dirname(STRATEGY_REGISTRY_PATH) or ".", exist_ok=True)
    tmp = STRATEGY_REGISTRY_PATH + ".tmp"
    bak = STRATEGY_REGISTRY_PATH + ".bak"
    if os.path.exists(STRATEGY_REGISTRY_PATH):
        try:
            shutil.copy2(STRATEGY_REGISTRY_PATH, bak)
        except Exception:
            pass
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        os.replace(tmp, STRATEGY_REGISTRY_PATH)
    except Exception:
        if os.path.exists(bak):
            try:
                shutil.copy2(bak, STRATEGY_REGISTRY_PATH)
            except Exception:
                pass
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
        raise


# ── 성과 데이터 수집 ─────────────────────────────────────

def collect_performance_data(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """backtest_archive + postmortem + VAMS + 퀀트 팩터 IC/Decay를 모아 진화 입력 구성."""
    from api.intelligence.backtest_archive import evaluate_past_recommendations
    from api.workflows.archiver import load_snapshots_range

    bt_stats = evaluate_past_recommendations([7, 14, 30])

    pm = portfolio.get("postmortem", {})
    # Brain Audit §3-D: postmortem multi-window 지원 — 표본 크기 기준 윈도우 우선 선택.
    #   30d ≥ 20건 → high confidence 사용
    #   14d ≥ 10건 → medium
    #   else 7d (low) — 단기 노이즈 가중치 영향 최소화
    pm_windows = pm.get("windows") or {}
    if pm_windows:
        if pm_windows.get("30d", {}).get("analyzed_count", 0) >= 20:
            pm_source = pm_windows["30d"]
        elif pm_windows.get("14d", {}).get("analyzed_count", 0) >= 10:
            pm_source = pm_windows["14d"]
        else:
            pm_source = pm_windows.get("7d") or pm
    else:
        # 구 단일-window 포맷 하위 호환
        pm_source = pm

    failures = pm_source.get("failures", [])
    # confidence 폴백 (구 포맷이 confidence 필드 없는 경우)
    _n = len(failures)
    pm_confidence = pm_source.get(
        "confidence",
        "high" if _n >= 20 else "medium" if _n >= 10 else "low",
    )
    pm_period = pm_source.get("period", pm.get("period", "?"))

    failure_patterns: List[str] = []
    misleading_factors: Dict[str, int] = dict(pm_source.get("misleading_factors", {}))
    if not misleading_factors:
        # source 에 집계 없으면 failures 에서 직접 추출 (구 포맷 폴백)
        for f in failures:
            mf = f.get("misleading_factor", "")
            if mf:
                misleading_factors[mf] = misleading_factors.get(mf, 0) + 1
    for f in failures:
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

    # trade_plan v0 자체 검증 결과 — Brain 진화 prompt 의 자기 점검 입력
    tp_meta = portfolio.get("trade_plan_meta") or {}
    tp_evo = portfolio.get("trade_plan_evolution_signals") or {}
    trade_plan_block = {
        "status": tp_meta.get("status"),
        "sample_size": tp_meta.get("sample_size", {}).get("total", 0),
        "horizons": {
            k: {"n": v.get("n", 0), "hit_rate_pct": v.get("hit_rate_pct"),
                "median_return_pct": v.get("median_return_pct"), "ic": v.get("ic")}
            for k, v in (tp_meta.get("horizon_summary") or {}).items()
        },
        "evolution_status": tp_evo.get("status"),
        "evolution_summary": tp_evo.get("summary"),
        "rule_change_candidates": tp_evo.get("change_candidates", [])[:5],
    }

    # brain_weights cross-validation OOS (Sprint 11 결함 2 후속)
    bw_cv = portfolio.get("brain_weights_cv") or {}
    brain_weights_cv_block = {
        "status": bw_cv.get("status"),
        "lookback_days": bw_cv.get("lookback_days"),
        "candidates": [
            {"w_fact": c["w_fact"], "hit_rate_pct": c.get("hit_rate_pct"),
             "avg_return_net_pct": c.get("avg_return_net_pct"), "n": c.get("n_buy_picks", 0)}
            for c in (bw_cv.get("candidates") or [])
        ],
        "best_by_return": bw_cv.get("best_by_return"),
        "best_by_hit_rate": bw_cv.get("best_by_hit_rate"),
    }

    return {
        "periods": bt_stats.get("periods", {}),
        "postmortem": {
            "failure_count": len(failures),
            "misleading_factors": misleading_factors,
            "lessons": failure_patterns[:5],
            "overall_lesson": pm_source.get("lesson", pm.get("lesson", "")),
            "system_suggestion": pm_source.get("system_suggestion", pm.get("system_suggestion", "")),
            # Brain Audit §3-D: 표본 크기 기반 신뢰도 — Claude 가중치 조정 보수성 결정에 사용
            "confidence": pm_confidence,
            "window_period": pm_period,
            "primary_window": pm.get("primary_window"),
        },
        "vams": {
            "win_rate": sim.get("win_rate", 0),
            "total_trades": sim.get("total_trades", 0),
            "max_drawdown_pct": sim.get("max_drawdown_pct", 0),
            "realized_pnl": sim.get("realized_pnl", 0),
        },
        "quant_factors": quant_intel,
        "trade_plan_v0": trade_plan_block,
        "brain_weights_cv": brain_weights_cv_block,
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
    qi_error = qi.get("error")
    if qi_ranking:
        ranking_str = ", ".join(f"{r['factor']}(ICIR={r['icir']:.3f})" for r in qi_ranking[:8])
        quant_section = f"""
═══ 퀀트 팩터 IC 분석 ═══
팩터 순위(ICIR): {ranking_str}
유의미 팩터: {', '.join(qi_significant) if qi_significant else '없음'}
붕괴 경고: {', '.join(qi_decaying) if qi_decaying else '없음'}
Decay 알림: {json.dumps(qi_alerts, ensure_ascii=False) if qi_alerts else '없음'}
"""
    elif qi_error:
        quant_section = f"""
═══ 퀀트 팩터 IC 분석 ═══
IC 스캔 실패: {qi_error}
(스냅샷 부족 또는 데이터 오류 — 퀀트 가중치 조정 시 보수적으로 판단할 것)
"""

    trigger_section = ""
    tc = perf.get("trigger_context")
    if tc:
        tl = {
            "daily": "일일", "weekly": "주간", "quarterly": "분기",
            "semi": "반기", "annual": "연간",
        }.get(tc.get("period", ""), tc.get("period", ""))
        trigger_section = f"""
═══ 트리거 컨텍스트 ═══
주기: {tl} ({tc.get('period_end', '?')})
스냅샷: {tc.get('days_available', '?')}일
적중률: {tc.get('hit_rate_pct', '?')}%
브레인 정확도: {json.dumps(tc.get('brain_accuracy', {}), ensure_ascii=False)[:200]}
→ 장기 주기일수록 보수적으로 판단하고, 단기 과적합을 경계할 것
"""

    research_section = ""
    try:
        from api.intelligence.quarterly_research import build_research_context_for_evolution
        research_ctx = build_research_context_for_evolution()
        if research_ctx:
            research_section = f"\n{research_ctx}\n"
    except Exception:
        pass

    # brain_weights cross-validation OOS — fact/sentiment 가중치 후보별 backtest
    bw_cv_section = ""
    bw_cv = perf.get("brain_weights_cv") or {}
    if bw_cv.get("status") == "active":
        cands = bw_cv.get("candidates") or []
        cand_lines = "\n".join(
            f"  w_fact={c['w_fact']:.2f}: hit={c.get('hit_rate_pct','-')}% / "
            f"avg_ret={c.get('avg_return_net_pct','-')}% / n={c.get('n', 0)}"
            for c in cands
        )
        best_r = bw_cv.get("best_by_return") or {}
        best_h = bw_cv.get("best_by_hit_rate") or {}
        bw_cv_section = f"""
═══ brain_weights CV OOS (lookback {bw_cv.get('lookback_days', '?')}d, T+1 보정) ═══
{cand_lines}
best_return: w_fact={best_r.get('w_fact', '?')} ({best_r.get('avg_return', '?')}%)
best_hit_rate: w_fact={best_h.get('w_fact', '?')} ({best_h.get('hit_rate', '?')}%)
※ 단일 윈도우 — multi-window 평균은 다음 단계. 자동 적용 X.
"""

    # trade_plan v0 자체 검증 결과 — Brain 의 자기 점검 입력
    trade_plan_section = ""
    tp = perf.get("trade_plan_v0") or {}
    if tp.get("status") and tp.get("status") not in ("empty", "no_data"):
        horizons_str = ", ".join(
            f"{k}: hit {v.get('hit_rate_pct', '-')}% / IC {v.get('ic', '-')} / n={v.get('n', 0)}"
            for k, v in (tp.get("horizons") or {}).items()
        )
        evo_status = tp.get("evolution_status", "?")
        evo_summary = tp.get("evolution_summary") or {}
        change_cands = tp.get("rule_change_candidates") or []
        cand_str = "\n".join(f"  - {c}" for c in change_cands[:5]) if change_cands else "  (없음)"
        trade_plan_section = f"""
═══ trade_plan v0 자체 검증 ═══
샘플: {tp.get('sample_size', 0)}건 · 상태: {tp.get('status')}
호라이즌별 (Hit Rate / IC): {horizons_str or '데이터 부족'}
진화 신호: {evo_status} (critical {evo_summary.get('critical', 0)} / warning {evo_summary.get('warning', 0)})
룰 변경 후보:
{cand_str}
※ trade_plan_v0 결정 룰은 단순(BB/MA20/RSI). 자동 변경 X — 가중치 조정 시 위 신호를 참조해 판단.
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
실패 {pm.get('failure_count', 0)}건 ({pm.get('window_period', '?')}, 신뢰도 {pm.get('confidence', 'low')})
잘못된 시그널 팩터: {json.dumps(pm.get('misleading_factors', {}), ensure_ascii=False)}
교훈: {pm.get('overall_lesson', '없음')}
시스템 제안: {pm.get('system_suggestion', '없음')}
※ 신뢰도 low(<10건)면 가중치 변경 보수적으로 판단할 것

═══ VAMS 시뮬레이션 ═══
승률 {vams.get('win_rate', 0):.1f}% | 총 {vams.get('total_trades', 0)}회 | MDD {vams.get('max_drawdown_pct', 0):.1f}% | 실현손익 {vams.get('realized_pnl', 0):+,.0f}원
{quant_section}{trigger_section}{research_section}{bw_cv_section}{trade_plan_section}
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


@mockable("claude.strategy_evolution")
def propose_evolution(
    perf: Dict[str, Any],
    constitution: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Claude Sonnet에게 가중치 변경 제안을 받는다."""
    if not ANTHROPIC_API_KEY:
        return None

    prompt = _build_evolution_prompt(constitution, perf)

    model = CLAUDE_MODEL_HEAVY if CLAUDE_OPUS_ENABLE else CLAUDE_MODEL_DEFAULT
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        print(f"  [V2] 전략 진화 모델: {model}")
        message = client.messages.create(
            model=model,
            max_tokens=800,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            text = text.rsplit("```", 1)[0]

        result = json.loads(text)
        result["_model"] = model
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
    """제안된 가중치가 규칙을 만족하는지 검증.

    검사 항목:
      1) 합계 1.0 (±0.01 허용)
      2) 존재하지 않는 키 거부
      3) 단건 변경폭 ±STRATEGY_MAX_WEIGHT_DELTA 이내
      4) 누적 드리프트 ±STRATEGY_MAX_CUMULATIVE_DRIFT 이내
         (versions[0].pre_change_snapshot 을 baseline 으로 비교 — 같은 방향 N회 누적 표류 방어)
    """
    changes = proposal.get("changes")
    if changes is None:
        return True, "변경 없음"

    # 누적 드리프트 baseline: 가장 오래된 pre_change_snapshot (data/strategy_registry.json.versions[0])
    registry = _load_registry()
    versions = registry.get("versions", []) or []
    baseline_snapshot: Dict[str, Any] = {}
    for v in versions:
        snap = v.get("pre_change_snapshot") or {}
        if snap:
            baseline_snapshot = snap
            break  # 시간순 append 구조이므로 versions[0] 근처의 가장 오래된 스냅샷

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
            # Brain Audit §2-E: 값 범위 검증 — 음수/이상치 weight 차단
            if not (0 <= v <= 0.5):
                return False, f"fact.{k}={v} out of [0, 0.5]"
            if abs(v - current[k]) > STRATEGY_MAX_WEIGHT_DELTA + 0.001:
                return False, f"{k} 변경폭 {abs(v - current[k]):.3f} > 최대 {STRATEGY_MAX_WEIGHT_DELTA}"
        # 누적 드리프트 체크 (baseline 대비)
        initial_fact_w = baseline_snapshot.get("fact_score_weights", {}) or {}
        for k, new_v in fact_changes.items():
            if k in initial_fact_w:
                drift = abs(new_v - initial_fact_w[k])
                if drift > STRATEGY_MAX_CUMULATIVE_DRIFT + 0.001:
                    return False, (
                        f"fact.{k} 누적 드리프트 {drift:.3f} > {STRATEGY_MAX_CUMULATIVE_DRIFT} "
                        f"(baseline {initial_fact_w[k]:.3f} → 제안 {new_v:.3f})"
                    )

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
            # Brain Audit §2-E: 값 범위 검증 — 음수/이상치 weight 차단
            if not (0 <= v <= 0.5):
                return False, f"sentiment.{k}={v} out of [0, 0.5]"
            if abs(v - current[k]) > STRATEGY_MAX_WEIGHT_DELTA + 0.001:
                return False, f"{k} 변경폭 {abs(v - current[k]):.3f} > 최대 {STRATEGY_MAX_WEIGHT_DELTA}"
        # 누적 드리프트 체크 (baseline 대비)
        initial_sent_w = baseline_snapshot.get("sentiment_score_weights", {}) or {}
        for k, new_v in sent_changes.items():
            if k in initial_sent_w:
                drift = abs(new_v - initial_sent_w[k])
                if drift > STRATEGY_MAX_CUMULATIVE_DRIFT + 0.001:
                    return False, (
                        f"sentiment.{k} 누적 드리프트 {drift:.3f} > {STRATEGY_MAX_CUMULATIVE_DRIFT} "
                        f"(baseline {initial_sent_w[k]:.3f} → 제안 {new_v:.3f})"
                    )

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
    lookback_days: int = 30,
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

    return backtest_brain_strategy(override, lookback_days=lookback_days)


# ── 제안 적용 ────────────────────────────────────────────

def apply_proposal(proposal: Dict[str, Any], backtest_result: Dict[str, Any]):
    """제안을 constitution에 반영하고 registry에 버전 기록.
    롤백을 위해 변경 전 가중치/임계값 스냅샷을 registry.versions[].pre_change_snapshot 에 저장."""
    constitution = _load_constitution()
    registry = _load_registry()
    changes = proposal.get("changes", {})

    # ── 변경 전 스냅샷 (rollback_strategy가 사용) ──
    pre_snapshot = {
        "fact_score_weights": dict(
            (constitution.get("fact_score", {}) or {}).get("weights", {})
        ),
        "sentiment_score_weights": dict(
            (constitution.get("sentiment_score", {}) or {}).get("weights", {})
        ),
        "grade_thresholds": {
            g: info.get("min_brain_score")
            for g, info in (constitution.get("decision_tree", {}) or {})
            .get("grades", {}).items()
        },
    }

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

    # Brain Audit §2-F: 가중치 합 자동 정규화.
    # validator 가 ±0.01 허용해 통과한 0.99/1.01 같은 합도 정확히 1.0 으로 강제.
    # 100회 누적 시 발생하는 부동소수점 system bias 차단.
    for section in ("fact_score", "sentiment_score"):
        weights = (constitution.get(section) or {}).get("weights")
        if not weights:
            continue
        s = sum(weights.values())
        if s > 0 and abs(s - 1.0) > 1e-6:
            constitution[section]["weights"] = {
                k: round(v / s, 6) for k, v in weights.items()
            }

    _save_constitution(constitution)

    new_version = registry.get("current_version", 1) + 1
    registry["current_version"] = new_version
    registry["versions"].append({
        "version": new_version,
        "applied_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "proposed_by": proposal.get("_model", CLAUDE_MODEL_DEFAULT),
        "change_summary": proposal.get("reason", ""),
        "reason": proposal.get("expected_improvement", ""),
        "backtest_before": None,
        "backtest_after": backtest_result,
        "actual_performance": None,
        "pre_change_snapshot": pre_snapshot,
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
    """직전 apply_proposal 직전 스냅샷으로 constitution을 실제 복원.
    versions[] 역순으로 스캔해 pre_change_snapshot 이 있는 가장 최근 엔트리를 사용."""
    registry = _load_registry()
    versions = registry.get("versions", [])
    if not versions:
        return None

    target = None
    for v in reversed(versions):
        if v.get("pre_change_snapshot"):
            target = v
            break
    if not target:
        # 구 버전 registry(스냅샷 없음)는 롤백 불가 — 사용자에게 명확히 전달
        return None

    snap = target["pre_change_snapshot"]
    constitution = _load_constitution()

    if "fact_score_weights" in snap and snap["fact_score_weights"]:
        constitution.setdefault("fact_score", {})["weights"] = dict(snap["fact_score_weights"])
    if "sentiment_score_weights" in snap and snap["sentiment_score_weights"]:
        constitution.setdefault("sentiment_score", {})["weights"] = dict(snap["sentiment_score_weights"])
    if "grade_thresholds" in snap and snap["grade_thresholds"]:
        grades = constitution.setdefault("decision_tree", {}).setdefault("grades", {})
        for g, score in snap["grade_thresholds"].items():
            if g in grades and score is not None:
                grades[g]["min_brain_score"] = score

    _save_constitution(constitution)

    current_ver = registry["current_version"]
    new_ver = current_ver + 1
    registry["current_version"] = new_ver
    registry["versions"].append({
        "version": new_ver,
        "applied_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "proposed_by": "rollback",
        "change_summary": f"v{current_ver} 롤백 → v{target['version']} 직전 스냅샷 기반 복원",
        "reason": "사령관 롤백 명령",
        "backtest_before": None,
        "backtest_after": None,
        "actual_performance": None,
        "rolled_back_from": current_ver,
        "rolled_back_to_snapshot_of": target["version"],
    })
    _save_registry(registry)

    return new_ver


def _classify_regime(portfolio: Optional[Dict[str, Any]] = None) -> str:
    """다중 시그널 매크로 레짐 분류.

    Sprint 11 (베테랑 결함 6 대응) — leading indicator 추가:
      Trailing (현재 상태):
        1) Fear & Greed Index
        2) 경기 사분면 (expansion/contraction) — 후행 (지난 분기 GDP)
        3) VIX 수준 — 동시
        4) 시장 심리 점수 — 동시
        5) 주요 지수 일간 변동률 — 후행 (이미 발생)
      Leading (베테랑 결함 6 추가):
        6) Yield curve slope (2y10y) — 침체 6-18개월 선행. 음수=경고, 0.5 미만=watch
        7) Copper/Gold ratio — risk-on/off 의 빠른 신호. 변화율 기반
        8) HY spread (data 가용 시) — 신용위험 첫 신호. 미수집 시 skip

    leading score 와 trailing score 를 분리 계산해서 portfolio.regime_diagnostics 에
    노출 — 두 score 의 divergence 가 regime 전환 임박 시그널.
    """
    if not portfolio:
        return "unknown"
    macro = portfolio.get("macro", {})
    ms = portfolio.get("market_summary", {})
    trailing: List[int] = []
    leading: List[int] = []

    # ── Trailing signals (5개) ─────────────────────────────────
    fg = macro.get("fear_greed", {}).get("score", macro.get("fear_greed_score"))
    if isinstance(fg, (int, float)):
        trailing.append(1 if fg >= 50 else -1)

    quadrant = macro.get("economic_quadrant", "").upper()
    if quadrant in ("EXPANSION", "RECOVERY"):
        trailing.append(1)
    elif quadrant in ("CONTRACTION", "SLOWDOWN"):
        trailing.append(-1)

    vix_raw = macro.get("vix", {}).get("value")
    if vix_raw is not None:
        try:
            vix = float(vix_raw)
            trailing.append(-1 if vix > 25 else (1 if vix < 18 else 0))
        except (ValueError, TypeError):
            pass

    mood_score = macro.get("market_mood", {}).get("score")
    if isinstance(mood_score, (int, float)):
        trailing.append(1 if mood_score >= 60 else (-1 if mood_score <= 40 else 0))

    for idx_key in ("kospi", "sp500", "ndx"):
        chg = ms.get(idx_key, {}).get("change_pct")
        if isinstance(chg, (int, float)):
            trailing.append(1 if chg > 0.5 else (-1 if chg < -0.5 else 0))

    # ── Leading signals (3개, Sprint 11 신규) ──────────────────
    # 1) Yield curve slope (2y10y) — 침체 6-18개월 선행
    yield_spread = macro.get("yield_spread", {})
    spread_val = yield_spread.get("value") if isinstance(yield_spread, dict) else None
    if not isinstance(spread_val, (int, float)):
        # fallback: us_10y - us_2y 직접 계산
        us10 = (macro.get("us_10y") or {}).get("value")
        us2 = (macro.get("us_2y") or {}).get("value")
        if isinstance(us10, (int, float)) and isinstance(us2, (int, float)):
            spread_val = us10 - us2
    if isinstance(spread_val, (int, float)):
        # 음수(역전) = 강한 침체 선행 신호. 0.5 미만 = watch. 1.0 이상 = 정상
        if spread_val < 0:
            leading.append(-2)  # 강신호 — 가중 2x
        elif spread_val < 0.5:
            leading.append(-1)
        elif spread_val >= 1.0:
            leading.append(1)
        else:
            leading.append(0)

    # 2) Copper/Gold ratio — risk-on/off 빠른 신호
    copper_chg = (macro.get("copper") or {}).get("change_pct")
    gold_chg = (macro.get("gold") or {}).get("change_pct")
    if isinstance(copper_chg, (int, float)) and isinstance(gold_chg, (int, float)):
        # copper > gold 변화율 = risk-on (산업수요↑), 반대 = risk-off (안전자산 선호)
        diff = copper_chg - gold_chg
        if diff > 1.0:
            leading.append(1)
        elif diff < -1.0:
            leading.append(-1)
        else:
            leading.append(0)

    # 3) HY spread (option) — 미수집 시 skip
    hy = macro.get("hy_spread") or macro.get("credit_spread")
    if isinstance(hy, dict):
        hy_val = hy.get("value")
        if isinstance(hy_val, (int, float)):
            # HY spread 5%+ = 신용 stress, 3% 미만 = 안정
            if hy_val >= 5.0:
                leading.append(-2)
            elif hy_val >= 4.0:
                leading.append(-1)
            elif hy_val < 3.0:
                leading.append(1)
            else:
                leading.append(0)

    # ── 종합 판정 ─────────────────────────────────────────────
    signals = trailing + leading
    if not signals:
        return "unknown"

    # 진단 메타 attach (portfolio dict 에 직접 — 호출자가 활용)
    if isinstance(portfolio, dict):
        try:
            t_avg = sum(trailing) / len(trailing) if trailing else 0
            l_avg = sum(leading) / len(leading) if leading else None
            portfolio.setdefault("regime_diagnostics", {})
            portfolio["regime_diagnostics"].update({
                "trailing_score": round(t_avg, 3),
                "leading_score": round(l_avg, 3) if l_avg is not None else None,
                "trailing_count": len(trailing),
                "leading_count": len(leading),
                "yield_spread_pp": spread_val if isinstance(spread_val, (int, float)) else None,
                # divergence: leading 이 trailing 보다 0.5 이상 차이 시 regime 전환 임박 신호
                "divergence_warning": (
                    l_avg is not None
                    and abs(l_avg - t_avg) >= 0.5
                ),
            })
        except Exception:
            pass

    avg = sum(signals) / len(signals)
    if avg > 0.3:
        return "bull"
    elif avg < -0.3:
        return "bear"
    return "mixed"


def _compute_rolling_metrics(versions: List[Dict[str, Any]], window: int = 8) -> Dict[str, Any]:
    """최근 N개 적용 버전의 성과 메트릭 (롤백 제외)."""
    relevant = [
        v for v in versions
        if v.get("backtest_after") and v.get("proposed_by") not in ("rollback",)
    ]
    recent = relevant[-window:] if len(relevant) >= window else relevant

    if not recent:
        return {"count": 0, "hit_rate": 0, "avg_sharpe_improvement": 0, "max_mdd": 0}

    hits = 0
    sharpe_improvements: List[float] = []
    mdds: List[float] = []

    for i, v in enumerate(recent):
        bt = v.get("backtest_after", {})
        proposed_sharpe = bt.get("sharpe", 0)
        current_sharpe = bt.get("current_sharpe", 0)
        sharpe_improvements.append(proposed_sharpe - current_sharpe)

        mdd = abs(bt.get("max_drawdown", 0))
        if mdd:
            mdds.append(mdd)

        idx_in_all = relevant.index(v) if v in relevant else -1
        if idx_in_all >= 0 and idx_in_all + 1 < len(relevant):
            next_bt = relevant[idx_in_all + 1].get("backtest_after", {})
            actual_sharpe = next_bt.get("current_sharpe", 0)
            if actual_sharpe >= current_sharpe:
                hits += 1
        elif proposed_sharpe > current_sharpe and proposed_sharpe > 0:
            hits += 1

    return {
        "count": len(recent),
        "hit_rate": (hits / len(recent) * 100) if recent else 0,
        "avg_sharpe_improvement": (
            sum(sharpe_improvements) / len(sharpe_improvements)
            if sharpe_improvements else 0
        ),
        "max_mdd": max(mdds) if mdds else 0,
        "sharpe_trend": (
            sharpe_improvements[-3:] if len(sharpe_improvements) >= 3 else sharpe_improvements
        ),
    }


def _should_circuit_break(rolling: Dict[str, Any], cb_cfg: Dict[str, Any]) -> Optional[str]:
    """서킷 브레이커 발동 조건 검사. 발동 시 사유 문자열 반환, 아니면 None."""
    if rolling["count"] < 3:
        return None

    min_hit = cb_cfg.get("min_rolling_hit_rate_pct", 55)
    if rolling["hit_rate"] < min_hit:
        return f"롤링 적중률 {rolling['hit_rate']:.0f}% < {min_hit}%"

    min_sharpe = cb_cfg.get("min_rolling_sharpe_improvement", -0.10)
    if rolling["avg_sharpe_improvement"] < min_sharpe:
        return (
            f"평균 Sharpe 개선 {rolling['avg_sharpe_improvement']:.2f} < {min_sharpe}"
        )

    max_mdd = cb_cfg.get("max_rolling_mdd_pct", 15)
    if rolling["max_mdd"] > max_mdd:
        return f"최대 MDD {rolling['max_mdd']:.1f}% > {max_mdd}%"

    trend = rolling.get("sharpe_trend", [])
    if len(trend) >= 3 and all(t < 0 for t in trend):
        return f"Sharpe 3연속 하락: {[round(t, 2) for t in trend]}"

    return None


def _check_auto_approve_transition(registry: Dict[str, Any]):
    """양방향 자동 승인 전환 + 서킷 브레이커.

    활성화 조건 (ALL):
      - 누적 제안 10건+
      - 누적 적중률 80%+
      - 강세 레짐 적중률 75%+ (최소 3건)
      - 약세 레짐 적중률 70%+ (최소 3건)
      - 롤링 윈도우 적중률 65%+ (최소 5건)
      - 쿨다운 완료 (서킷 브레이커 후 5건 수동 승인)

    비활성화 조건 (ANY → 서킷 브레이커):
      - 롤링 적중률 < 55%
      - 평균 Sharpe 개선 < -0.10
      - 최대 MDD > 15%
      - Sharpe 3연속 하락
    """
    threshold = registry.get("auto_approve_threshold", {})
    stats = registry.get("cumulative_stats", {})
    versions = registry.get("versions", [])
    cb_cfg = registry.get("circuit_breaker", dict(_CIRCUIT_BREAKER_DEFAULTS))
    window = cb_cfg.get("rolling_window", 8)

    rolling = _compute_rolling_metrics(versions, window)

    if registry.get("auto_approve"):
        reason = _should_circuit_break(rolling, cb_cfg)
        if reason:
            registry["auto_approve"] = False
            cb_cfg["triggered_at"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
            cb_cfg["reason"] = reason
            cb_cfg["proposals_since_trigger"] = 0
            registry["circuit_breaker"] = cb_cfg
            print(f"  [V2] 🚨 서킷 브레이커 발동: {reason} → 자동 승인 해제")
            try:
                from api.notifications.telegram import send_message
                send_message(
                    f"🚨 Brain V2 서킷 브레이커 발동\n"
                    f"사유: {reason}\n"
                    f"롤링 적중률: {rolling['hit_rate']:.0f}% | "
                    f"Sharpe 개선: {rolling['avg_sharpe_improvement']:.2f} | "
                    f"MDD: {rolling['max_mdd']:.1f}%\n"
                    f"→ 자동 승인 해제됨. 수동 승인 모드로 전환."
                )
            except Exception:
                pass
        return

    cooldown_required = cb_cfg.get("cooldown_proposals", 5)
    proposals_since = cb_cfg.get("proposals_since_trigger", 0)
    had_breaker = cb_cfg.get("triggered_at") is not None
    if had_breaker and proposals_since < cooldown_required:
        cb_cfg["proposals_since_trigger"] = proposals_since + 1
        registry["circuit_breaker"] = cb_cfg
        return

    cumulative_ok = all([
        stats.get("total_proposals", 0) >= threshold.get("min_proposals", 10),
        stats.get("hit_rate_pct", 0) >= threshold.get("hit_rate_pct", 80),
        stats.get("bull_proposals", 0) >= 3
        and stats.get("bull_hit_rate_pct", 0) >= threshold.get("bull_hit_rate_pct", 75),
        stats.get("bear_proposals", 0) >= 3
        and stats.get("bear_hit_rate_pct", 0) >= threshold.get("bear_hit_rate_pct", 70),
    ])

    rolling_ok = rolling["count"] >= 5 and rolling["hit_rate"] >= 65

    if cumulative_ok and rolling_ok:
        registry["auto_approve"] = True
        cb_cfg["triggered_at"] = None
        cb_cfg["reason"] = ""
        cb_cfg["proposals_since_trigger"] = 0
        registry["circuit_breaker"] = cb_cfg
        print(
            f"  [V2] 자동 승인 모드 전환: "
            f"누적 {stats.get('hit_rate_pct', 0):.1f}% | "
            f"롤링 {rolling['hit_rate']:.1f}% | "
            f"강세 {stats.get('bull_hit_rate_pct', 0):.1f}% | "
            f"약세 {stats.get('bear_hit_rate_pct', 0):.1f}%"
        )


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

def run_evolution_cycle(
    portfolio: Dict[str, Any],
    trigger_context: Optional[Dict[str, Any]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """전략 진화 사이클. full 분석 또는 정기 리포트 완료 후 호출.

    Args:
        portfolio: 현재 포트폴리오 데이터
        trigger_context: 정기 리포트에서 호출 시 주기 정보
            - period: "daily" | "weekly" | "quarterly" | "semi" | "annual"
            - period_end: 캘린더 식별 키 (예: "2026-04-11", "2026Q1")
            - days_available: 분석에 사용된 스냅샷 일수
            - hit_rate_pct: 리포트 내 적중률
            - brain_accuracy: 브레인 등급 정확도 분석 결과
        force: 수동 trigger — 스냅샷 기준을 STRATEGY_MIN_SNAPSHOT_DAYS_FORCED
            (기본 5일) 로 완화. 디버깅/첫 발화용. 여전히 MAX_WEIGHT_DELTA 와
            MAX_CUMULATIVE_DRIFT 는 과적합 방어로 작동.
    """
    from api.workflows.archiver import list_available_dates

    ctx = trigger_context or {}
    period = ctx.get("period", "full")
    period_label = {
        "daily": "일일", "weekly": "주간", "monthly": "월간",
        "quarterly": "분기", "semi": "반기", "annual": "연간",
        "full": "full 분석",
    }.get(period, period)

    result = {
        "status": "skipped",
        "reason": "",
        "trigger": "manual" if force else period,
        "forced": force,
        "period_end": ctx.get("period_end", ""),
        "generated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }

    min_days = STRATEGY_MIN_SNAPSHOT_DAYS_FORCED if force else STRATEGY_MIN_SNAPSHOT_DAYS
    dates = list_available_dates()
    if len(dates) < min_days:
        result["reason"] = f"스냅샷 {len(dates)}일 < 최소 {min_days}일{' (forced)' if force else ''}"
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

    print(f"  [V2] 성과 데이터 수집... (트리거: {period_label})")
    perf = collect_performance_data(portfolio)

    if ctx:
        perf["trigger_context"] = ctx

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

    regime = _classify_regime(portfolio)
    stats = registry["cumulative_stats"]
    stats["total_proposals"] = stats.get("total_proposals", 0) + 1
    if regime == "bull":
        stats["bull_proposals"] = stats.get("bull_proposals", 0) + 1
    elif regime == "bear":
        stats["bear_proposals"] = stats.get("bear_proposals", 0) + 1
    _save_registry(registry)

    print("  [V2] 백테스트 검증...")
    oos_days = max(STRATEGY_MIN_OOS_DAYS, 30)
    bt_result = simulate_proposal(proposal, constitution, lookback_days=oos_days)

    current_bt = backtest_brain_strategy_current()
    bt_result["current_sharpe"] = current_bt.get("sharpe", 0)
    bt_result["current_max_drawdown"] = current_bt.get("max_drawdown", 0)
    bt_result["oos_days"] = oos_days

    if bt_result.get("sharpe", 0) <= current_bt.get("sharpe", 0):
        result["status"] = "rejected_by_backtest"
        result["reason"] = f"Sharpe 미개선: 현행 {current_bt.get('sharpe', 0):.2f} >= 제안 {bt_result.get('sharpe', 0):.2f}"
        print(f"  [V2] {result['reason']}")
        return result

    if registry.get("auto_approve"):
        proposed_mdd = bt_result.get("max_drawdown", 0)
        current_mdd = current_bt.get("max_drawdown", 0)
        if proposed_mdd > current_mdd * 1.2 and current_mdd > 0:
            result["status"] = "rejected_by_mdd"
            result["reason"] = (
                f"MDD 악화: 현행 {current_mdd:.2f}% → 제안 {proposed_mdd:.2f}% "
                f"(허용 범위 {current_mdd * 1.2:.2f}% 초과)"
            )
            print(f"  [V2] {result['reason']}")
            return result

        actual_oos = bt_result.get("total_trades", 0)
        if oos_days < STRATEGY_MIN_OOS_DAYS:
            result["status"] = "rejected_by_oos"
            result["reason"] = f"OOS 기간 부족: {oos_days}일 < 최소 {STRATEGY_MIN_OOS_DAYS}일"
            print(f"  [V2] {result['reason']}")
            return result

        rolling_pre = _compute_rolling_metrics(
            registry.get("versions", []),
            registry.get("circuit_breaker", {}).get("rolling_window", 8),
        )

        print("  [V2] 자동 승인 모드 → 즉시 적용")
        new_ver = apply_proposal(proposal, bt_result)
        result["status"] = "auto_applied"
        result["new_version"] = new_ver
        result["proposal"] = proposal
        result["backtest"] = bt_result
        result["rolling_metrics"] = rolling_pre

        try:
            from api.notifications.telegram import send_message
            send_message(
                f"🧠 Brain V2 자동 적용 완료 (v{new_ver})\n"
                f"트리거: {period_label} ({ctx.get('period_end', '')})\n"
                f"레짐: {regime} | OOS: {oos_days}일\n"
                f"사유: {proposal.get('reason', '?')}\n"
                f"Sharpe: {current_bt.get('sharpe', 0):.2f} → {bt_result.get('sharpe', 0):.2f}\n"
                f"MDD: {current_mdd:.2f}% → {proposed_mdd:.2f}%\n"
                f"롤링 적중률: {rolling_pre['hit_rate']:.0f}%"
            )
        except Exception:
            pass

        return result

    registry["pending_proposal"] = {
        "proposal": proposal,
        "backtest_result": bt_result,
        "trigger": period,
        "period_end": ctx.get("period_end", ""),
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
    versions = registry.get("versions", [])
    cb = registry.get("circuit_breaker", {})
    rolling = _compute_rolling_metrics(versions, cb.get("rolling_window", 8))

    return {
        "current_version": registry.get("current_version", 1),
        "auto_approve": registry.get("auto_approve", False),
        "stats": registry.get("cumulative_stats", {}),
        "rolling_metrics": {
            "hit_rate": round(rolling["hit_rate"], 1),
            "avg_sharpe_improvement": round(rolling["avg_sharpe_improvement"], 3),
            "max_mdd": round(rolling["max_mdd"], 1),
            "window_size": rolling["count"],
        },
        "circuit_breaker": {
            "triggered_at": cb.get("triggered_at"),
            "reason": cb.get("reason", ""),
            "cooldown_remaining": max(
                0,
                cb.get("cooldown_proposals", 5) - cb.get("proposals_since_trigger", 0),
            ) if cb.get("triggered_at") else 0,
        },
        "pending": registry.get("pending_proposal") is not None,
        "fact_weights": constitution.get("fact_score", {}).get("weights", {}),
        "sentiment_weights": constitution.get("sentiment_score", {}).get("weights", {}),
    }
