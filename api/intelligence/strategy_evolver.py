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

import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import anthropic

from api.mocks import mockable
from api.config import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL_DEFAULT,
    CLAUDE_MODEL_HEAVY,
    CLAUDE_OPUS_ENABLE,
    is_claude_5_family,
    DATA_DIR,
    STRATEGY_REGISTRY_PATH,
    STRATEGY_MAX_WEIGHT_DELTA,
    STRATEGY_MAX_CUMULATIVE_DRIFT,
    STRATEGY_MIN_OOS_DAYS,
    now_kst,
)

_CONSTITUTION_PATH = os.path.join(DATA_DIR, "verity_constitution.json")
_CONSTITUTION_BACKUP_DIR = os.path.join(DATA_DIR, "constitution_backups")
_PROPOSAL_TTL_HOURS = 168
_MUTATION_POLICY_DEFAULT = "frozen"


class ProposalValidationError(ValueError):
    """A proposal no longer matches the constitution it was created against."""


def _constitution_sha256(constitution: Dict[str, Any]) -> str:
    canonical = json.dumps(
        constitution,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _proposal_context(
    constitution: Dict[str, Any],
    registry: Dict[str, Any],
) -> Dict[str, Any]:
    created = now_kst()
    return {
        "base_registry_version": registry.get("current_version"),
        "base_constitution_version": constitution.get("version"),
        "base_constitution_sha256": _constitution_sha256(constitution),
        "created_at": created.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "expires_at": (created + timedelta(hours=_PROPOSAL_TTL_HOURS)).strftime(
            "%Y-%m-%dT%H:%M:%S+09:00"
        ),
    }


def _parse_kst_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=now_kst().tzinfo)
    return parsed

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
        reg.setdefault("mutation_policy", {
            "mode": _MUTATION_POLICY_DEFAULT,
            "requires_pm_approval": True,
        })
        reg.setdefault("invalidated_proposals", [])
        reg["auto_approve"] = False
        stats = reg.setdefault("cumulative_stats", {})
        stats.setdefault("accepted", 0)
        stats.setdefault("rejected", 0)
        stats.setdefault("invalidated", 0)
        if "unclassified" not in stats:
            pending_count = 1 if reg.get("pending_proposal") else 0
            classified = (
                stats["accepted"]
                + stats["rejected"]
                + stats["invalidated"]
                + pending_count
            )
            stats["unclassified"] = max(
                int(stats.get("total_proposals", 0)) - classified,
                0,
            )
        return reg
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "current_version": 1,
            "auto_approve": False,
            "circuit_breaker": dict(_CIRCUIT_BREAKER_DEFAULTS),
            "cumulative_stats": {
                "total_proposals": 0, "accepted": 0, "rejected": 0,
                "invalidated": 0, "unclassified": 0,
                "hit_count": 0, "hit_rate_pct": 0,
                "bull_proposals": 0, "bull_hits": 0, "bull_hit_rate_pct": 0,
                "bear_proposals": 0, "bear_hits": 0, "bear_hit_rate_pct": 0,
            },
            "versions": [],
            "pending_proposal": None,
            "invalidated_proposals": [],
            "mutation_policy": {
                "mode": _MUTATION_POLICY_DEFAULT,
                "requires_pm_approval": True,
            },
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

    # Report findings + brain_learning 누적 (2026-05-03):
    # 리포트가 매일 산출하는 정성 findings + 정량 시그널 누적값을 진화 prompt 입력에 합류.
    # 둘 다 직교 — findings 는 "Brain 이 뭘 봤나" / brain_learning 은 "결과가 어땠나".
    report_findings_recent: List[Dict[str, Any]] = []
    brain_learning_trend: List[Dict[str, Any]] = []
    try:
        from api.metadata import report_findings as _rf
        report_findings_recent = _rf.load_recent(days=14, report_type="daily")
    except Exception:
        pass
    try:
        from api.metadata import brain_learning as _bl
        brain_learning_trend = _bl.load_signals(days=14)
    except Exception:
        pass

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
        "report_findings_recent": report_findings_recent,
        "brain_learning_trend": brain_learning_trend,
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

    # 2026-05-17 quarterly_research 폐기 — research_section 빈 문자열 유지.
    # 이전 = build_research_context_for_evolution() 호출 (Perplexity 분기 deep research → prompt 첨부).
    # 폐기 사유: data/research_archive/ 부재 (한 번도 실행 안 됨) + LLM 차별점 0 + 비용 발생.
    # 대체: Brain v5 자체 산식 (verity_brain) + market_horizon 5축 verdict 이미 prompt 에 포함됨.
    research_section = ""

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

    # 리포트 findings + brain_learning 누적 (2026-05-03 신설):
    # 리포트의 #1 목적 = Brain 학습 input. 누적 시그널을 prompt 에 합류해
    # 가중치 진화 제안에 정량(brain_learning) + 정성(report_findings) 양면 사용.
    findings_section = ""
    rf_recent = perf.get("report_findings_recent") or []
    bl_trend = perf.get("brain_learning_trend") or []
    if rf_recent or bl_trend:
        # findings 압축 — 최근 7건 (2주 미만치) 핵심만
        rf_lines: List[str] = []
        for e in rf_recent[-7:]:
            f = e.get("findings") or {}
            buys = ", ".join(p.get("ticker", "?") for p in (f.get("top_buy_picks") or [])[:3]) or "-"
            rf_lines.append(
                f"  {e.get('date', '?')}: tone={f.get('briefing_tone', '-')} | "
                f"buy_picks={buys} | hit14d={f.get('backtest_hit_rate_14d', '-')}% "
                f"avg14d={f.get('backtest_avg_return_14d', '-')}% (n={f.get('backtest_total_recs_14d', 0)}) | "
                f"head: {(f.get('briefing_headline') or '')[:80]}"
            )
        # brain_learning 추세 — 적중률/등급분포 변화
        bl_summary = ""
        if bl_trend:
            first = bl_trend[0]
            last = bl_trend[-1]
            f_buy = (first.get("grade_distribution") or {}).get("BUY", 0) + (first.get("grade_distribution") or {}).get("STRONG_BUY", 0)
            l_buy = (last.get("grade_distribution") or {}).get("BUY", 0) + (last.get("grade_distribution") or {}).get("STRONG_BUY", 0)
            hits = [s.get("backtest_hit_rate_14d") for s in bl_trend if s.get("backtest_hit_rate_14d") is not None]
            hit_avg = round(sum(hits) / len(hits), 1) if hits else None
            bl_summary = (
                f"  최근 14일 누적: BUY 발생 {f_buy}→{l_buy}건 추세, "
                f"적중률 14d 평균 {hit_avg}% (samples={len(hits)})"
            )
        findings_section = f"""
═══ 리포트 findings + 학습 트랙 (지속 진화 input) ═══
{bl_summary or '  brain_learning 누적 없음'}
최근 일별 findings:
{chr(10).join(rf_lines) if rf_lines else '  report_findings 누적 없음'}
※ tone/headline/picks 패턴 + 적중률 추세를 함께 보고 가중치 조정 방향 판단
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

    return f"""[알파브레인 가중치 최적화 요청]

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
{quant_section}{trigger_section}{research_section}{bw_cv_section}{trade_plan_section}{findings_section}
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
        # 5족 가드 (2026-08-03) — thinking 기본 on 이라 JSON 경로는 disabled 명시,
        # content[0] 이 thinking 블록일 수 있어 text 블록 순회로 추출.
        _extra = {"thinking": {"type": "disabled"}} if is_claude_5_family(model) else {}
        message = client.messages.create(
            model=model,
            max_tokens=800,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            **_extra,
        )
        try:  # 관측 배선 — import 실패 환경(복제본 등)에서도 본업 무영향
            from api.metadata.llm_cost import log_anthropic
            log_anthropic(message, "strategy_evolver")
        except Exception:  # noqa: BLE001
            pass
        text = next((b.text for b in message.content if b.type == "text"), "").strip()
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
        unknown = sorted(set(fact_changes) - set(current))
        if unknown:
            return False, f"존재하지 않는 fact 키: {', '.join(unknown)}"
        merged = {**current, **fact_changes}
        total = sum(merged.values())
        if abs(total - 1.0) > 0.01:
            return False, f"fact_score 가중치 합 {total:.3f} != 1.0"
        for k, v in fact_changes.items():
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
        unknown = sorted(set(sent_changes) - set(current))
        if unknown:
            return False, f"존재하지 않는 sentiment 키: {', '.join(unknown)}"
        merged = {**current, **sent_changes}
        total = sum(merged.values())
        if abs(total - 1.0) > 0.01:
            return False, f"sentiment 가중치 합 {total:.3f} != 1.0"
        for k, v in sent_changes.items():
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
        current_grades = (
            (constitution.get("decision_tree") or {}).get("grades") or {}
        )
        unknown = sorted(set(grade_changes) - set(current_grades))
        if unknown:
            return False, f"존재하지 않는 grade 키: {', '.join(unknown)}"
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

def validate_proposal_context(
    approval_context: Dict[str, Any],
    constitution: Dict[str, Any],
    registry: Dict[str, Any],
) -> tuple[bool, str]:
    """Fail closed when proposal provenance is missing, expired, or stale."""
    required = {
        "base_registry_version",
        "base_constitution_version",
        "base_constitution_sha256",
        "created_at",
        "expires_at",
    }
    missing = sorted(required - set(approval_context or {}))
    if missing:
        return False, f"proposal context missing: {', '.join(missing)}"

    expires_at = _parse_kst_iso(approval_context.get("expires_at"))
    if expires_at is None:
        return False, "proposal expiry is invalid"
    if now_kst() >= expires_at:
        return False, "proposal expired"

    if approval_context.get("base_registry_version") != registry.get("current_version"):
        return False, "registry version changed after proposal creation"
    if approval_context.get("base_constitution_version") != constitution.get("version"):
        return False, "constitution version changed after proposal creation"
    if approval_context.get("base_constitution_sha256") != _constitution_sha256(constitution):
        return False, "constitution content changed after proposal creation"
    return True, "proposal context valid"


def _invalidate_pending(registry: Dict[str, Any], reason: str) -> None:
    pending = registry.get("pending_proposal")
    if not pending:
        return
    archived = dict(pending)
    archived["status"] = "invalidated_stale"
    archived["invalidated_at"] = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    archived["invalidation_reason"] = reason
    registry.setdefault("invalidated_proposals", []).append(archived)
    registry["pending_proposal"] = None
    stats = registry.setdefault("cumulative_stats", {})
    stats["invalidated"] = stats.get("invalidated", 0) + 1


def approve_pending_proposal() -> int:
    """Revalidate and apply the one pending proposal as a single approval path."""
    registry = _load_registry()
    pending = registry.get("pending_proposal")
    if not pending:
        raise ProposalValidationError("no pending proposal")

    constitution = _load_constitution()
    context = pending.get("approval_context") or {}
    valid, reason = validate_proposal_context(context, constitution, registry)
    if not valid:
        _invalidate_pending(registry, reason)
        _save_registry(registry)
        raise ProposalValidationError(reason)

    proposal = pending.get("proposal") or {}
    proposal_valid, proposal_reason = validate_proposal(proposal, constitution)
    if not proposal_valid:
        _invalidate_pending(registry, proposal_reason)
        _save_registry(registry)
        raise ProposalValidationError(proposal_reason)

    new_version = apply_proposal(
        proposal,
        pending.get("backtest_result") or {},
        approval_context=context,
    )
    latest = _load_registry()
    latest["pending_proposal"] = None
    stats = latest.setdefault("cumulative_stats", {})
    stats["hit_count"] = stats.get("hit_count", 0) + 1
    accepted = stats.get("accepted", 0)
    if accepted > 0:
        stats["hit_rate_pct"] = round(stats["hit_count"] / accepted * 100, 1)
    _save_registry(latest)
    return new_version


def apply_proposal(
    proposal: Dict[str, Any],
    backtest_result: Dict[str, Any],
    approval_context: Optional[Dict[str, Any]] = None,
):
    """제안을 constitution에 반영하고 registry에 버전 기록.
    롤백을 위해 변경 전 가중치/임계값 스냅샷을 registry.versions[].pre_change_snapshot 에 저장."""
    constitution = _load_constitution()
    registry = _load_registry()
    context_valid, context_reason = validate_proposal_context(
        approval_context or {}, constitution, registry
    )
    if not context_valid:
        raise ProposalValidationError(context_reason)
    proposal_valid, proposal_reason = validate_proposal(proposal, constitution)
    if not proposal_valid:
        raise ProposalValidationError(proposal_reason)
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

    registry["auto_approve"] = False
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
        force: 수동 trigger 표기. 고정 표본 조건을 완화하거나 승인 권한을 주지 않는다.
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

    registry = _load_registry()
    mutation_mode = (registry.get("mutation_policy") or {}).get(
        "mode", _MUTATION_POLICY_DEFAULT
    )
    if mutation_mode == "frozen":
        result["status"] = "formula_frozen"
        result["reason"] = "formula mutation is frozen pending explicit PM approval"
        return result
    if mutation_mode != "manual_only":
        result["status"] = "mutation_policy_blocked"
        result["reason"] = f"unsupported mutation policy: {mutation_mode}"
        return result

    dates = list_available_dates()
    result["evidence"] = {
        "snapshot_days": len(dates),
        "fixed_sample_gate": False,
        "approval_mode": "manual_only",
    }

    if not ANTHROPIC_API_KEY:
        result["reason"] = "ANTHROPIC_API_KEY 미설정"
        return result

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

    # P1-3 fix (2026-05-16): 자동 reject 3 path 가 cumulative_stats 업데이트 X →
    # accepted=0, rejected=0 (31 total_proposals 인데). visibility 0 = 사용자가 27 cycle
    # reject 못 봄 = 산식 결함 진단 불가. 각 reject path 에 stats 업데이트 + auto_rejects
    # 별 필드 추가해 path 별 분포 추적.
    def _record_auto_reject(reject_kind: str) -> None:
        s = registry.setdefault("cumulative_stats", {})
        s["rejected"] = s.get("rejected", 0) + 1
        ar = s.setdefault("auto_rejects", {})
        ar[reject_kind] = ar.get(reject_kind, 0) + 1
        _save_registry(registry)

    # Perplexity Q4 (2026-05-17) fix: margin 0 → STRATEGY_SHARPE_MIN_MARGIN (default 0.10).
    # 미세 차이 (±0.05) 는 학계 통계적 무의미. 절대 margin 또는 PSR p<0.10 권장.
    # 27 cycle 전부 reject root cause 2번째 fix (lookback 30 → 90 와 동시).
    from api.config import (
        STRATEGY_SHARPE_MIN_MARGIN, STRATEGY_PSR_ENABLED, STRATEGY_PSR_CONFIDENCE,
    )
    _proposal_sr = bt_result.get("sharpe", 0)
    _current_sr = current_bt.get("sharpe", 0)
    _gap = _proposal_sr - _current_sr
    if _gap < STRATEGY_SHARPE_MIN_MARGIN:
        result["status"] = "rejected_by_backtest"
        result["reason"] = (
            f"Sharpe 개선 부족: 제안 {_proposal_sr:.3f} - 현행 {_current_sr:.3f} = "
            f"{_gap:+.3f} (margin {STRATEGY_SHARPE_MIN_MARGIN:.2f} 미달, Perplexity Q4 학계 자문)"
        )
        print(f"  [V2] {result['reason']}")
        _record_auto_reject("backtest_sharpe")
        return result

    # PSR optional gate (STRATEGY_PSR_ENABLED=true 시 활성, Perplexity Q4 v2)
    if STRATEGY_PSR_ENABLED:
        try:
            from api.quant.alpha.psr import compute_psr
            returns_series = bt_result.get("returns_series") or []
            psr_T = bt_result.get("oos_days") or oos_days
            psr_result = compute_psr(
                sr_observed=_proposal_sr,
                sr_benchmark=_current_sr,
                T=psr_T,
                returns=returns_series if returns_series else None,
            )
            bt_result["psr_check"] = psr_result
            _psr_val = psr_result.get("psr")
            if _psr_val is None:
                # 유의성 측정불가(저N×고SR×skew 점근분산 붕괴 → compute_psr None, commit 73cbb847e).
                # PSR 게이트 명시 skip — 옛 `None < float` TypeError 가 except 에 silent 삼켜지던 것
                # 명시화(fail-open 보존, margin gate 적용). 보수적 reject-on-unmeasurable 은 향후 PM 정책.
                print("  [V2] PSR 유의성 측정불가(추정불가) → PSR 게이트 skip, margin gate 적용", file=sys.stderr)
            elif _psr_val < STRATEGY_PSR_CONFIDENCE:
                result["status"] = "rejected_by_psr"
                result["reason"] = (
                    f"PSR {_psr_val:.3f} < {STRATEGY_PSR_CONFIDENCE:.2f} "
                    f"(통계적 유의성 부족, Perplexity Q4 v2 학계 자문)"
                )
                print(f"  [V2] {result['reason']}")
                _record_auto_reject("psr")
                return result
        except Exception as e:
            # PSR 산출 실패 시 margin gate 만 의존 (silent skip 차단 = stderr)
            print(f"  [V2] PSR check 실패 (margin gate 만 적용): {e}", file=sys.stderr)

    # Strategy Pool optional 통합 (Perplexity Q4 v2, STRATEGY_POOL_ENABLED=1 시).
    # margin + PSR gate 통과 후 pool 비교 → worst strategy 교체 또는 reject.
    try:
        from api.config import STRATEGY_POOL_ENABLED, STRATEGY_POOL_MAX_SIZE
    except ImportError:
        STRATEGY_POOL_ENABLED = False
        STRATEGY_POOL_MAX_SIZE = 3
    if STRATEGY_POOL_ENABLED:
        try:
            from api.intelligence.strategy_pool import add_to_pool, load_pool, save_pool
            pool = load_pool(registry)
            new_strat = {
                "version": registry.get("current_version", 1) + 1,
                "sharpe": _proposal_sr,
                "applied_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                "proposal_snapshot": proposal,
            }
            new_pool, decision = add_to_pool(
                pool, new_strat,
                max_size=STRATEGY_POOL_MAX_SIZE,
                min_margin=STRATEGY_SHARPE_MIN_MARGIN,
                T=oos_days,
            )
            bt_result["pool_decision"] = decision
            if not decision["accepted"]:
                result["status"] = "rejected_by_pool"
                result["reason"] = f"Strategy Pool: {decision['reason']}"
                print(f"  [V2] {result['reason']}")
                _record_auto_reject("pool")
                return result
            save_pool(new_pool, registry)
            _save_registry(registry)
        except Exception as e:
            print(f"  [V2] Pool check 실패 (sequential 폴백): {e}", file=sys.stderr)

    approval_context = _proposal_context(constitution, registry)

    registry["pending_proposal"] = {
        "proposal": proposal,
        "backtest_result": bt_result,
        "trigger": period,
        "period_end": ctx.get("period_end", ""),
        "proposed_at": approval_context["created_at"],
        "expires_at": approval_context["expires_at"],
        "approval_context": approval_context,
        "evidence": {
            **result["evidence"],
            "backtest_span_days": bt_result.get("actual_span_days"),
            "backtest_trades": bt_result.get("total_trades"),
            "trail_sufficient": bt_result.get("trail_sufficient"),
        },
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
        "mutation_policy": registry.get("mutation_policy", {}),
        "fact_weights": constitution.get("fact_score", {}).get("weights", {}),
        "sentiment_weights": constitution.get("sentiment_score", {}).get("weights", {}),
    }
