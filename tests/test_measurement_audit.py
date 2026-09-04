# -*- coding: utf-8 -*-
"""측정 오염 자동 검출 3종 + VAMS 통화 정규화 (2026-08-05).

배경: 8/4~8/5 감사 확정 결함이 전부 "조용히 죽어 아무도 몰랐던" 종류였다. 사람이
478개 모듈을 훑는 방식은 끝나지 않으므로, 그날 결함을 **실제로 잡아낸 세 대조**를
상시 검사로 고정한다. 이 테스트는 그 검출력이 유지되는지를 지킨다.
"""
import json

import api.observability.measurement_audit as MA


# ── C. 단위 스케일 ───────────────────────────────────────────────────────

def _pf(tmp_path, holdings):
    p = tmp_path / "portfolio.json"
    p.write_text(json.dumps({"vams": {"holdings": holdings}}), encoding="utf-8")
    return p


def test_scale_detects_currency_mix(monkeypatch, tmp_path):
    """실사고 재현 — 매수가 KRW / 타깃 USD 면 비율이 환율(≈1,300배)로 나온다."""
    _pf(tmp_path, [{"name": "EXE", "ticker": "EXE", "buy_price": 132650,
                    "exit_targets": {"target_1": {"price": 99}}}])
    monkeypatch.setattr(MA, "DATA_DIR", str(tmp_path))
    r = MA.audit_price_scale()
    assert r["ok"] is False
    assert r["scale_mismatches"][0]["ratio"] > 1000


def test_scale_passes_normal_targets(monkeypatch, tmp_path):
    _pf(tmp_path, [{"name": "티쓰리", "buy_price": 2520,
                    "exit_targets": {"target_1": {"price": 2976}}}])
    monkeypatch.setattr(MA, "DATA_DIR", str(tmp_path))
    assert MA.audit_price_scale()["ok"] is True


def test_scale_ignores_absent_targets(monkeypatch, tmp_path):
    """WATCH 매수 = trade_plan 미생성 → 타깃 없음. 결측은 스케일 오류가 아니다."""
    _pf(tmp_path, [{"name": "A", "buy_price": 1000, "exit_targets": None}])
    monkeypatch.setattr(MA, "DATA_DIR", str(tmp_path))
    assert MA.audit_price_scale()["ok"] is True


def test_scale_checks_stop_price_too(monkeypatch, tmp_path):
    _pf(tmp_path, [{"name": "X", "buy_price": 50000, "stop_price": 36}])
    monkeypatch.setattr(MA, "DATA_DIR", str(tmp_path))
    assert any(b["field"] == "stop_price" for b in MA.audit_price_scale()["scale_mismatches"])


# ── B. 키 커버리지 ───────────────────────────────────────────────────────

def test_key_coverage_flags_dead_key(monkeypatch, tmp_path):
    mod = tmp_path / "m.py"
    mod.write_text('x = stock.get("alpha_combined")\ny = stock.get("per")\n', encoding="utf-8")
    (tmp_path / "recommendations.json").write_text(
        json.dumps([{"per": 10}, {"per": 12}]), encoding="utf-8")
    monkeypatch.setattr(MA, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(MA, "SCORING_MODULES", ["m.py"])
    r = MA.audit_key_coverage(root=str(tmp_path))
    assert r["ok"] is False
    assert [d["key"] for d in r["dead_keys"]] == ["alpha_combined"]   # per 는 존재 → 통과


def test_key_coverage_whitelists_benign_fallbacks(monkeypatch, tmp_path):
    """per/pbr 이 있으면 price_to_earnings 결측은 무해 — 오탐 배제."""
    mod = tmp_path / "m.py"
    mod.write_text('a = stock.get("price_to_earnings")\n', encoding="utf-8")
    (tmp_path / "recommendations.json").write_text(json.dumps([{"per": 10}]), encoding="utf-8")
    monkeypatch.setattr(MA, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(MA, "SCORING_MODULES", ["m.py"])
    assert MA.audit_key_coverage(root=str(tmp_path))["ok"] is True


def test_key_coverage_accepts_active_fallback_paths(monkeypatch, tmp_path):
    """최상위 별칭이 없어도 실제 채점 대체 경로가 있으면 죽은 축이 아니다."""
    mod = tmp_path / "m.py"
    mod.write_text(
        "\n".join([
            'stock.get("close")',
            'stock.get("operating_income")',
            'stock.get("prev_year")',
            'stock.get("sub_sector")',
            'stock.get("total_debt")',
            'stock.get("quant_factors")',
            'stock.get("dart_financials")',
        ]),
        encoding="utf-8",
    )
    rows = [{
        "current_price": 100,
        "revenue": 1_000,
        "operating_margin": 10,
        "fscore_deltas": {"delta_roa": 0.01},
        "industry": "Software",
        "total_assets": 2_000,
        "debt_ratio": 50,
        "multi_factor": {"quant_factors": {"quality": 70}},
        "dart_source": "dart_pre_attach",
    }]
    (tmp_path / "recommendations.json").write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(MA, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(MA, "SCORING_MODULES", ["m.py"])

    r = MA.audit_key_coverage(root=str(tmp_path))

    assert r["ok"] is True
    assert {item["key"] for item in r["fallback_covered"]} == {
        "close", "operating_income", "prev_year", "sub_sector", "total_debt",
        "quant_factors", "dart_financials",
    }


def test_key_coverage_requires_runtime_evidence_for_stripped_inputs(monkeypatch, tmp_path):
    mod = tmp_path / "m.py"
    mod.write_text(
        'stock.get("quant_factors")\nstock.get("dart_financials")\n', encoding="utf-8")
    (tmp_path / "recommendations.json").write_text(
        json.dumps([{"ticker": "005930", "currency": "KRW"}]), encoding="utf-8")
    monkeypatch.setattr(MA, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(MA, "SCORING_MODULES", ["m.py"])

    r = MA.audit_key_coverage(root=str(tmp_path))

    assert [item["key"] for item in r["dead_keys"]] == ["dart_financials", "quant_factors"]


def test_key_coverage_distinguishes_evaluated_zero_event(monkeypatch, tmp_path):
    """SEC 스캔 성공 후 후보 매칭 0건은 살아 있는 규칙의 정상 0건이다."""
    mod = tmp_path / "m.py"
    mod.write_text('stock.get("sec_risk_flags")\n', encoding="utf-8")
    (tmp_path / "recommendations.json").write_text(
        json.dumps([{"ticker": "AAPL", "currency": "USD"}]), encoding="utf-8")
    (tmp_path / "portfolio.json").write_text(
        json.dumps({"sec_risk_scan": {"ok": True, "count": 19, "filings": [{}] * 19}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(MA, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(MA, "SCORING_MODULES", ["m.py"])

    r = MA.audit_key_coverage(root=str(tmp_path))

    assert r["ok"] is True
    assert r["evaluated_zero"][0]["key"] == "sec_risk_flags"
    assert r["evaluated_zero"][0]["events_scanned"] == 19


def test_key_coverage_keeps_event_key_dead_without_scan_evidence(monkeypatch, tmp_path):
    mod = tmp_path / "m.py"
    mod.write_text('stock.get("sec_risk_flags")\n', encoding="utf-8")
    (tmp_path / "recommendations.json").write_text(
        json.dumps([{"ticker": "AAPL", "currency": "USD"}]), encoding="utf-8")
    monkeypatch.setattr(MA, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(MA, "SCORING_MODULES", ["m.py"])

    r = MA.audit_key_coverage(root=str(tmp_path))

    assert [item["key"] for item in r["dead_keys"]] == ["sec_risk_flags"]


# ── A. 원장 정합 ─────────────────────────────────────────────────────────

def test_ledger_flags_phantom_sells(monkeypatch, tmp_path):
    hist = [{"type": "BUY", "ticker": "A", "date": "2026-06-01", "quantity": 10},
            {"type": "SELL", "ticker": "A", "date": "2026-06-10", "pnl": -100},
            {"type": "SELL", "ticker": "A", "date": "2026-06-11", "pnl": -200}]  # 유령
    (tmp_path / "portfolio.json").write_text(json.dumps({"vams": {}}), encoding="utf-8")
    monkeypatch.setattr(MA, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr("api.vams.engine.load_history", lambda: hist)
    r = MA.audit_ledger()
    assert r["ok"] is False and r["phantom_sells"] == 1 and r["phantom_pnl"] == -200


def test_ledger_ok_when_clean(monkeypatch, tmp_path):
    hist = [{"type": "BUY", "ticker": "A", "date": "2026-06-01", "quantity": 10},
            {"type": "SELL", "ticker": "A", "date": "2026-06-10", "pnl": 500}]
    (tmp_path / "portfolio.json").write_text(json.dumps({"vams": {}}), encoding="utf-8")
    monkeypatch.setattr(MA, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr("api.vams.engine.load_history", lambda: hist)
    assert MA.audit_ledger()["ok"] is True


# ── 종합 ────────────────────────────────────────────────────────────────

def test_run_never_raises_on_missing_inputs(monkeypatch, tmp_path):
    """관측이 파이프라인을 죽이지 않는다 — 입력 결손 시 skip 으로 흐른다."""
    monkeypatch.setattr(MA, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(MA, "OUT_PATH", str(tmp_path / "out.json"))
    monkeypatch.setattr(MA, "TRAIL_PATH", str(tmp_path / "t.jsonl"))
    out = MA.run(root=str(tmp_path))
    assert out["status"] in ("OK", "PARTIAL", "FAIL")
    assert (tmp_path / "out.json").exists()


# ── VAMS 통화 정규화 (execute_buy) ───────────────────────────────────────

def test_engine_normalizes_trade_plan_prices_to_krw():
    """US 매수 시 trade_plan 가격이 KRW 로 정규화돼야 타깃 비교가 성립한다."""
    import inspect
    from api.vams import engine
    src = inspect.getsource(engine.execute_buy)
    assert "_fx_norm" in src
    assert "_exit_targets_norm" in src
    assert '"stop_price": _stop_loss_obj.get' in src   # 파생 영속화


def test_partial_exit_has_scale_guard():
    """기존 보유(정규화 이전분)는 스케일 불일치 시 평가를 건너뛴다 — fail-closed."""
    import inspect
    from api.vams import engine
    src = inspect.getsource(engine.check_partial_exit)
    assert "_ratio > 10" in src and "return []" in src
