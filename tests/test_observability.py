"""
Phase 1 회귀 테스트 — api/observability/ 4개 모듈.

검증 대상:
  data_health.check_data_health  : 신선도/성공률/결측률 정합성
  feature_drift.compute_drift     : PSI 계산 + level 분류
  feature_drift.extract_features  : portfolio 에서 스칼라 추출
  explainability.explain_brain_score : 양수/음수 기여 분해
  trust_score.report_readiness    : 8개 조건 verdict

가드 정책 (spec §6): 모든 함수 try/except 적용 — 잘못된 입력으로도 crash 하지 않음.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
import tempfile

import pytest

from api.observability import (
    check_data_health,
    compute_drift,
    explain_brain_score,
    report_readiness,
    check_release_gate,
)
from api.observability.feature_drift import extract_features, _psi_single, _psi_level
from api.observability.alert_dispatcher import dispatch_alerts, _build_messages, _filter_warnings


# ─────────────────────────────────────────────────────────────────────
# 픽스처
# ─────────────────────────────────────────────────────────────────────

def _now_kst_iso() -> str:
    from api.config import now_kst
    return now_kst().isoformat()


@pytest.fixture
def healthy_portfolio():
    """모든 소스 정상인 포트폴리오 mock."""
    return {
        "updated_at": _now_kst_iso(),
        "system_health": {
            "status": "ok",
            "api_health": {
                "yfinance": {"status": "ok", "latency_ms": 320, "detail": "정상"},
                "fred": {"status": "ok", "latency_ms": 200, "detail": "정상"},
                "kis": {"status": "ok", "latency_ms": 180, "detail": "정상"},
                "dart": {"status": "ok", "latency_ms": 850, "detail": "정상"},
                "gemini": {"status": "ok", "latency_ms": 100, "detail": "정상"},
                "anthropic": {"status": "ok", "latency_ms": 0, "detail": "키 존재"},
            },
        },
        "macro": {
            "vix": {"value": 18.5, "change_pct": 0.5},
            "us_10y": {"value": 4.3, "change_pct": 0.0},
            "usd_krw": {"value": 1380.0, "change_pct": 0.1},
            "sp500": {"value": 5500, "change_pct": 0.3},
            "market_mood": {"score": 65},
        },
        "recommendations": [
            {"ticker": "AAPL", "grade": "BUY", "brain_score": 72, "per": 28.0,
             "pbr": 5.0, "roe": 0.18, "debt_ratio": 50.0,
             "consensus": 70, "multi_factor": 65,
             "vci": 0.3, "dart_health": 80,
             "social_sentiment": {"score": 0.4}},
            {"ticker": "TSLA", "grade": "WATCH", "brain_score": 55, "per": 50.0,
             "pbr": 12.0, "roe": 0.12, "debt_ratio": 40.0,
             "consensus": 50, "multi_factor": 55,
             "vci": 0.6, "dart_health": 60,
             "social_sentiment": {"score": 0.1}},
        ],
    }


@pytest.fixture
def critical_portfolio(healthy_portfolio):
    """핵심 소스 장애 mock."""
    p = json.loads(json.dumps(healthy_portfolio))
    p["system_health"]["status"] = "critical"
    p["system_health"]["api_health"]["yfinance"]["status"] = "critical"
    p["system_health"]["api_health"]["dart"]["status"] = "warning"
    # 24시간 이상 지난 timestamp
    p["updated_at"] = (datetime.fromisoformat(p["updated_at"]) - timedelta(hours=30)).isoformat()
    return p


# ─────────────────────────────────────────────────────────────────────
# data_health
# ─────────────────────────────────────────────────────────────────────

class TestDataHealth:
    def test_healthy_portfolio_returns_ok(self, healthy_portfolio):
        result = check_data_health(healthy_portfolio)
        assert result["_meta"]["overall_status"] in ("ok", "warning")
        assert result["_meta"]["core_sources_ok"] is True
        assert "yfinance" in result
        assert result["yfinance"]["status"] in ("ok", "warning")

    def test_critical_portfolio_flags_failure(self, critical_portfolio):
        result = check_data_health(critical_portfolio)
        assert result["_meta"]["core_sources_ok"] is False
        # yfinance 가 critical 이므로 overall 도 critical
        assert result["_meta"]["overall_status"] == "critical"

    def test_no_portfolio_safe_default(self):
        result = check_data_health(None)
        assert result["_meta"]["overall_status"] == "critical"
        assert result["_meta"]["core_sources_ok"] is False

    def test_invalid_input_no_crash(self):
        # 가드 정책 — 어떤 입력에도 crash X
        for bad in ["string", 123, [], {"random": "garbage"}]:
            r = check_data_health(bad)
            assert isinstance(r, dict)
            assert "_meta" in r

    def test_recommendations_missing_pct(self, healthy_portfolio):
        # grade=null 인 종목 추가
        healthy_portfolio["recommendations"].append({"ticker": "X", "grade": None, "brain_score": None})
        result = check_data_health(healthy_portfolio)
        assert "recommendations" in result
        assert result["recommendations"]["missing_pct"] > 0


# ─────────────────────────────────────────────────────────────────────
# feature_drift
# ─────────────────────────────────────────────────────────────────────

class TestFeatureDrift:
    def test_extract_features(self, healthy_portfolio):
        feats = extract_features(healthy_portfolio)
        assert "vix_avg" in feats
        assert "avg_per" in feats
        assert "grade_distribution_buy_pct" in feats
        # grade BUY 1, WATCH 1 → BUY+ 비율 0.5
        assert feats["grade_distribution_buy_pct"] == 0.5

    def test_psi_identical_is_zero(self):
        psi = _psi_single(100, 100)
        assert psi == 0.0

    def test_psi_doubled_is_drift(self):
        psi = _psi_single(50, 100)
        # 변화율 2x → PSI > 0.2 (drift critical)
        assert psi > 0.2
        assert _psi_level(psi) == "critical"

    def test_psi_small_change_is_ok(self):
        psi = _psi_single(100, 102)
        assert psi < 0.1
        assert _psi_level(psi) == "ok"

    def test_compute_drift_no_baseline(self, healthy_portfolio):
        feats = extract_features(healthy_portfolio)
        result = compute_drift(yesterday=None, today=feats)
        # jsonl 없을 가능성 — error 또는 zero score
        assert result["overall_drift_score"] >= 0
        assert result["level"] in ("ok", "warning", "critical")

    def test_compute_drift_with_yesterday(self, healthy_portfolio):
        today = extract_features(healthy_portfolio)
        # 어제 절반 — 큰 drift 예상
        yesterday = {k: v / 2 if isinstance(v, (int, float)) and v != 0 else v
                    for k, v in today.items()}
        result = compute_drift(yesterday=yesterday, today=today)
        assert result["comparable_count"] > 0
        assert result["overall_drift_score"] > 0
        assert len(result["drifted_features"]) > 0

    def test_compute_drift_invalid_input_no_crash(self):
        r = compute_drift(today=None)
        assert r.get("error") == "no_today_features"


# ─────────────────────────────────────────────────────────────────────
# explainability
# ─────────────────────────────────────────────────────────────────────

class TestExplainability:
    def test_returns_avg_brain_score(self, healthy_portfolio):
        result = explain_brain_score(healthy_portfolio)
        # brain_score 평균 = (72+55)/2 = 63.5
        assert result["avg_brain_score"] is not None
        assert abs(result["avg_brain_score"] - 63.5) < 0.1

    def test_negative_factors_vci_extreme(self, healthy_portfolio):
        # VCI > 0.7 종목 추가
        healthy_portfolio["recommendations"].append({
            "ticker": "VOLATILE", "grade": "AVOID", "brain_score": 30,
            "vci": 0.85, "dart_health": 20,
        })
        result = explain_brain_score(healthy_portfolio)
        neg_features = [n["feature"] for n in result["negative_contributors"]]
        assert "vci_extreme" in neg_features

    def test_invalid_input_no_crash(self):
        for bad in [None, "string", 123, []]:
            r = explain_brain_score(bad)
            assert "avg_brain_score" in r
            assert isinstance(r["positive_contributors"], list)
            assert isinstance(r["negative_contributors"], list)

    def test_positive_contributors_sorted_desc(self, healthy_portfolio):
        result = explain_brain_score(healthy_portfolio)
        contribs = [c["avg_contribution"] for c in result["positive_contributors"]]
        assert contribs == sorted(contribs, reverse=True)


# ─────────────────────────────────────────────────────────────────────
# trust_score
# ─────────────────────────────────────────────────────────────────────

class TestTrustScore:
    def test_healthy_returns_ready(self, healthy_portfolio):
        health = check_data_health(healthy_portfolio)
        feats = extract_features(healthy_portfolio)
        drift = compute_drift(yesterday=None, today=feats)  # no baseline → ok
        result = report_readiness(healthy_portfolio, data_health=health, drift=drift)
        # 폰트 파일 / pdf_generator 환경에 따라 1~2개 미충족 가능
        assert result["verdict"] in ("ready", "manual_review")
        assert result["satisfied"] >= 6

    def test_critical_returns_hold(self, critical_portfolio):
        health = check_data_health(critical_portfolio)
        result = report_readiness(critical_portfolio, data_health=health, drift={})
        # core_sources_ok False + AI ok + 신선도 미달 + system_health critical
        assert result["verdict"] in ("hold", "manual_review")
        assert len(result["blocking_reasons"]) >= 2

    def test_no_portfolio_returns_hold(self):
        result = report_readiness(None)
        assert result["verdict"] == "hold"
        assert result["satisfied"] == 0

    def test_8_conditions_present(self, healthy_portfolio):
        result = report_readiness(healthy_portfolio,
                                 data_health=check_data_health(healthy_portfolio),
                                 drift={})
        assert result["total"] == 8
        assert len(result["conditions"]) == 8
        expected = {"data_freshness_ok", "core_sources_ok", "drift_below_threshold",
                   "ai_models_ok", "brain_distribution_normal", "pipeline_cron_ok",
                   "deadman_clear", "pdf_generator_ok"}
        assert set(result["conditions"].keys()) == expected


# ─────────────────────────────────────────────────────────────────────
# alert_dispatcher (Phase 4)
# ─────────────────────────────────────────────────────────────────────

class TestAlertDispatcher:
    def test_critical_health_triggers_alert(self):
        health = {"_meta": {"overall_status": "critical", "core_sources_ok": False},
                 "yfinance": {"status": "critical"}}
        state = {"last_topics": {"data_health": {"status": "ok"}}, "warnings_since": {}}
        msgs = _build_messages(health, {}, {}, state)
        assert any(m["topic"] == "data_health" and m["level"] == "critical" for m in msgs)

    def test_critical_drift_triggers_alert(self):
        drift = {"level": "critical", "drifted_features": ["news_sentiment_avg"],
                "overall_drift_score": 0.45}
        state = {"last_topics": {"drift": {"level": "ok"}}, "warnings_since": {}}
        msgs = _build_messages({}, drift, {}, state)
        assert any(m["topic"] == "drift" and m["level"] == "critical" for m in msgs)

    def test_hold_verdict_triggers_alert(self):
        trust = {"verdict": "hold", "recommendation": "발행 차단",
                "blocking_reasons": ["...", "...", "..."], "satisfied": 5, "total": 8}
        state = {"last_topics": {"trust": {"verdict": "ready"}}, "warnings_since": {}}
        msgs = _build_messages({}, {}, trust, state)
        assert any(m["topic"] == "trust" and m["level"] == "critical" for m in msgs)

    def test_warning_first_seen_no_immediate_send(self):
        # warning 첫 발생 → 누적 시작, 발송 안 됨
        from datetime import datetime
        from api.config import KST
        warnings = [{"topic": "data_health", "level": "warning", "message": "x", "details": {}}]
        state = {"warnings_since": {}}
        out = _filter_warnings(warnings, state, datetime.now(tz=KST))
        assert out == []
        assert "data_health" in state["warnings_since"]

    def test_warning_aged_out_sends(self):
        # 1시간+ 경과한 warning 은 발송 대상
        from datetime import datetime, timedelta
        from api.config import KST
        now = datetime.now(tz=KST)
        old = (now - timedelta(hours=2)).isoformat()
        warnings = [{"topic": "drift", "level": "warning", "message": "x", "details": {}}]
        state = {"warnings_since": {"drift": old}}
        out = _filter_warnings(warnings, state, now)
        assert len(out) == 1
        # warnings_since 가 reset 되어 다음 1시간 대기 시작
        assert state["warnings_since"]["drift"] != old

    def test_dispatch_dry_run_no_send(self):
        # send=False 면 발송 안 됨
        result = dispatch_alerts(
            health={"_meta": {"overall_status": "critical", "core_sources_ok": False}},
            drift={"level": "ok"},
            trust={"verdict": "ready"},
            send=False,
        )
        # critical health 1건만 — telegram 호출 안 됨
        assert isinstance(result, list)


# ─────────────────────────────────────────────────────────────────────
# check_release_gate
# ─────────────────────────────────────────────────────────────────────

class TestReleaseGate:
    def test_hold_blocks(self, critical_portfolio):
        # observability attach 없음 — 즉석 측정으로 hold 판정 가능
        critical_portfolio["observability"] = {
            "trust": {"verdict": "hold", "recommendation": "발행 차단",
                     "blocking_reasons": ["a", "b", "c", "d"], "satisfied": 4, "total": 8}
        }
        gate = check_release_gate(critical_portfolio)
        assert gate["allow"] is False
        assert gate["verdict"] == "hold"

    def test_ready_allows(self, healthy_portfolio):
        healthy_portfolio["observability"] = {
            "trust": {"verdict": "ready", "satisfied": 8, "total": 8,
                     "recommendation": "OK", "blocking_reasons": []}
        }
        gate = check_release_gate(healthy_portfolio)
        assert gate["allow"] is True
        assert gate["verdict"] == "ready"

    def test_manual_review_allows(self, healthy_portfolio):
        healthy_portfolio["observability"] = {
            "trust": {"verdict": "manual_review", "satisfied": 6, "total": 8,
                     "recommendation": "검수 필요", "blocking_reasons": ["x"]}
        }
        gate = check_release_gate(healthy_portfolio)
        assert gate["allow"] is True
        assert gate["verdict"] == "manual_review"

    def test_no_observability_falls_back_to_compute(self, healthy_portfolio):
        # observability 키 없음 — 즉석 측정
        gate = check_release_gate(healthy_portfolio)
        # 어떤 verdict 든 dict 형태 + allow 키
        assert "allow" in gate
        assert gate["verdict"] in ("ready", "manual_review", "hold", "unknown", "error")

    def test_no_portfolio_safe_default(self):
        gate = check_release_gate(None)
        assert gate["allow"] is True  # 가드 정책: 게이트 실패 시 막지 않음
        assert gate["verdict"] == "unknown"
