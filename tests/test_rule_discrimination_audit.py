# -*- coding: utf-8 -*-
"""검사 D — 규칙 판별력 자동 검출 + baseline (2026-08-06 신설).

배경: 8/6 하루에 같은 부류 결함을 세 번 잡았는데 셋 다 기존 A~C 검사가 못 잡는 종류였다.
셋 다 손으로 찾았고 방법이 매번 같았다 — 발동률을 히스토리로 재고 임계를 분포와 대조.
그 방법을 코드로 옮긴 것이 검사 D 다.

그리고 8/6 에 하나 더 배웠다: `price_scale` 이 통화 혼재를 **매일** 신고하고 있었는데
아무도 읽지 않았다. 매일 FAIL 인 경보는 경보가 아니다 → baseline 도입.

계약: ① 상시 발동(≥90%)·거의 미발동(≤5%) 등급 규칙 검출 ② 85~90% 는 watch 로 노출
③ 등급 cap 이 0개인 날이 0 이면 최상위 등급 구조적 불가 신고 ④ 알려진 미해결분은
KNOWN 으로 내리고 **초과분만 FAIL** ⑤ 점수 입력 0 · 임계 조정 0(판정만).
"""
import json

import api.observability.measurement_audit as MA


def _snap(tmp_path, day, sigs):
    """sigs = [(mode, max_grade), ...] — 첫 항목이 primary."""
    d = tmp_path / "history"
    d.mkdir(exist_ok=True)
    ov = {"mode": sigs[0][0], "max_grade": sigs[0][1],
          "secondary_signals": [{"mode": m, "max_grade": g} for m, g in sigs[1:]]}
    (d / f"{day}.json").write_text(
        json.dumps({"verity_brain": {"macro_override": ov}}), encoding="utf-8")


def _days(tmp_path, n, sigs_for):
    for i in range(n):
        _snap(tmp_path, f"2026-05-{i + 1:02d}" if i < 31 else f"2026-06-{i - 30:02d}",
              sigs_for(i))


def _wire(monkeypatch, tmp_path):
    monkeypatch.setattr(MA, "DATA_DIR", str(tmp_path))


# ── 상시 발동 검출 ───────────────────────────────────────────────────

def test_always_on_cap_rule_detected(monkeypatch, tmp_path):
    """🚨 핵심 — 매일 켜진 등급 규칙은 국면을 구분하지 못한다."""
    _wire(monkeypatch, tmp_path)
    _days(tmp_path, 60, lambda i: [("always_cap", "WATCH")])
    r = MA.audit_rule_discrimination()
    modes = {d["rule"] for d in r["degenerate_rules"]}
    assert "always_cap" in modes
    assert r["ok"] is False


def test_threshold_is_90_not_95(monkeypatch, tmp_path):
    """실측 근거 — cape_bubble 94.3% 가 95 임계 아래로 빠져나갔다. 93% 도 잡아야 한다."""
    _wire(monkeypatch, tmp_path)
    # 100일 중 93일 발동 = 93.0%
    _days(tmp_path, 100, lambda i: [("cap_93", "WATCH")] if i < 93 else [("other", "BUY")])
    r = MA.audit_rule_discrimination()
    assert "cap_93" in {d["rule"] for d in r["degenerate_rules"]}


def test_watch_band_surfaces_near_miss(monkeypatch, tmp_path):
    """85~90% 는 판정하지 않되 조용히 통과시키지도 않는다."""
    _wire(monkeypatch, tmp_path)
    _days(tmp_path, 100, lambda i: [("cap_87", "WATCH")] if i < 87 else [("other", "BUY")])
    r = MA.audit_rule_discrimination()
    assert "cap_87" not in {d["rule"] for d in r["degenerate_rules"]}
    assert "cap_87" in {d["rule"] for d in r["watch_rules"]}


def test_healthy_rule_passes(monkeypatch, tmp_path):
    """켜지고 꺼지는 규칙은 통과 — 정상 규칙까지 잡으면 경보가 무의미해진다."""
    _wire(monkeypatch, tmp_path)
    _days(tmp_path, 100, lambda i: [("cap_30", "WATCH")] if i < 30 else [("other", "BUY")])
    r = MA.audit_rule_discrimination()
    assert not r["degenerate_rules"]
    assert r["ok"] is True


def test_observation_rules_exempt(monkeypatch, tmp_path):
    """등급에 영향 없는 관측 mode 는 상시여도 대상 아님 (8/6 도입한 *_observation)."""
    _wire(monkeypatch, tmp_path)
    _days(tmp_path, 60, lambda i: [("cape_observation", None), ("real", "WATCH")]
          if i < 20 else [("cape_observation", None)])
    r = MA.audit_rule_discrimination()
    assert "cape_observation" not in {d["rule"] for d in r["degenerate_rules"]}


# ── 최상위 등급 구조적 불가 ──────────────────────────────────────────

def test_zero_uncapped_days_flagged(monkeypatch, tmp_path):
    """cap 이 하루도 안 풀리면 최상위 등급이 구조적으로 불가능하다 — 8/6 실측 0/87일."""
    _wire(monkeypatch, tmp_path)
    _days(tmp_path, 60, lambda i: [("a", "WATCH")] if i % 2 else [("b", "CAUTION")])
    r = MA.audit_rule_discrimination()
    assert r["days_without_any_cap"] == 0
    assert "구조적으로 불가능" in r["detail"]
    assert r["ok"] is False


def test_uncapped_days_counted(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path)
    _days(tmp_path, 60, lambda i: [("a", "WATCH")] if i < 30 else [("obs", None)])
    r = MA.audit_rule_discrimination()
    assert r["days_without_any_cap"] == 30


def test_skips_when_history_thin(monkeypatch, tmp_path):
    """표본 부족은 판정 보류 — 없는 결론을 만들지 않는다."""
    _wire(monkeypatch, tmp_path)
    _days(tmp_path, 10, lambda i: [("a", "WATCH")])
    r = MA.audit_rule_discrimination()
    assert r["ok"] is None and "판정 보류" in r["skipped"]


# ── baseline — 매일 FAIL 인 경보는 경보가 아니다 ─────────────────────

def test_known_unresolved_downgraded_from_fail():
    """알려진 미해결분(유령 58·죽은키 10·통화 3)은 KNOWN 으로 내려간다."""
    for name, base in MA._KNOWN_BASELINE.items():
        field, limit = next(iter(base.items()))
        chk = {"ok": False, field: limit}
        assert MA._exceeds_baseline(name, chk) is False


def test_regression_above_baseline_is_fail():
    """baseline 초과 = 신규 발생 = FAIL. 이게 경보의 의미다."""
    for name, base in MA._KNOWN_BASELINE.items():
        field, limit = next(iter(base.items()))
        assert MA._exceeds_baseline(name, {"ok": False, field: limit + 1}) is True


def test_baseline_accepts_list_valued_fields():
    """dead_keys 처럼 리스트로 오는 필드도 길이로 비교된다."""
    n = MA._KNOWN_BASELINE["key_coverage"]["dead_keys"]
    assert MA._exceeds_baseline("key_coverage", {"ok": False, "dead_keys": [0] * n}) is False
    assert MA._exceeds_baseline("key_coverage", {"ok": False, "dead_keys": [0] * (n + 1)}) is True


def test_passing_check_not_baselined():
    assert MA._exceeds_baseline("ledger_integrity", {"ok": True, "phantom_sells": 0}) is None


def test_run_separates_fail_from_known(monkeypatch, tmp_path):
    """status FAIL = 새로 생겼다. KNOWN = 알려진 범위 안.

    2026-08-07 갱신 — price_scale baseline 이 0 이 되어(#300 해소) 불일치 1건이면 FAIL 이다.
    """
    _wire(monkeypatch, tmp_path)
    _days(tmp_path, 60, lambda i: [("a", "WATCH")] if i < 20 else [("obs", None)])
    monkeypatch.setattr(MA, "OUT_PATH", str(tmp_path / "o.json"))
    monkeypatch.setattr(MA, "TRAIL_PATH", str(tmp_path / "m" / "t.jsonl"))
    monkeypatch.setattr(MA, "audit_ledger", lambda: {"ok": False, "phantom_sells": 58})
    monkeypatch.setattr(MA, "audit_key_coverage", lambda root=".": {"ok": False, "dead_keys": [0] * 10})
    monkeypatch.setattr(MA, "audit_price_scale", lambda: {"ok": False, "scale_mismatches": [0]})
    monkeypatch.setattr(MA, "audit_flag_coverage", lambda root=".": {"ok": False, "never_fired": [0] * 13})
    out = MA.run(str(tmp_path))
    assert out["failing"] == ["price_scale"]               # 신규(통화 혼재 재발)만
    assert set(out["known_unresolved"]) == {"ledger_integrity", "key_coverage", "flag_coverage"}
    assert out["checks"]["ledger_integrity"]["status"] == "KNOWN"


def test_run_flags_regression_over_baseline(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path)
    _days(tmp_path, 60, lambda i: [("a", "WATCH")] if i < 20 else [("obs", None)])
    monkeypatch.setattr(MA, "OUT_PATH", str(tmp_path / "o.json"))
    monkeypatch.setattr(MA, "TRAIL_PATH", str(tmp_path / "m" / "t.jsonl"))
    monkeypatch.setattr(MA, "audit_ledger", lambda: {"ok": False, "phantom_sells": 59})   # +1
    monkeypatch.setattr(MA, "audit_key_coverage", lambda root=".": {"ok": True, "dead_keys": []})
    monkeypatch.setattr(MA, "audit_price_scale", lambda: {"ok": True, "scale_mismatches": []})
    out = MA.run(str(tmp_path))
    assert "ledger_integrity" in out["failing"]
    assert out["checks"]["ledger_integrity"]["status"] == "REGRESSION"
    assert out["status"] == "FAIL"


def test_audit_never_feeds_scores():
    """RULE 7 — 이 모듈은 어떤 점수에도 입력되지 않는다."""
    import inspect
    src = inspect.getsource(MA)
    assert "brain_score" not in src and "recommendation =" not in src


# ── 검사 E — red_flag 규칙 커버리지 ──────────────────────────────────

def _rf_snap(tmp_path, day, per_stock_flags):
    """per_stock_flags = [[flag_text, ...], ...] — 종목별 발동 플래그."""
    d = tmp_path / "history"
    d.mkdir(exist_ok=True)
    recs = [{"ticker": f"00000{i}",
             "verity_brain": {"red_flags": {"auto_avoid": fl, "downgrade": []}}}
            for i, fl in enumerate(per_stock_flags)]
    (d / f"{day}.json").write_text(json.dumps({"recommendations": recs}), encoding="utf-8")


def _rf_days(tmp_path, n, flags):
    for i in range(n):
        _rf_snap(tmp_path, f"2026-05-{i + 1:02d}", flags)


def _rf_code(tmp_path, literals):
    """가짜 red_flags.py 를 만들어 규칙 정의를 통제한다."""
    p = tmp_path / "api" / "intelligence" / "factors"
    p.mkdir(parents=True, exist_ok=True)
    body = "\n".join(f'    _make_flag(f"{lit}")' for lit in literals)
    (p / "red_flags.py").write_text(f"def f():\n{body}\n", encoding="utf-8")


def test_flag_prefix_extraction(tmp_path):
    _rf_code(tmp_path, ["공매도 비율 5일 평균 {x}% (과다)", "부채비율 {d}%"])
    pre = MA._flag_rule_prefixes(str(tmp_path))
    assert "공매도 비율 5일 평균" in pre and "부채비율" in pre


def test_never_fired_rule_detected(monkeypatch, tmp_path):
    """🚨 코드에 있는데 107일 0건 = 확인 대상."""
    _wire(monkeypatch, tmp_path)
    _rf_code(tmp_path, ["살아있는 규칙 {x}", "죽은 규칙 {y}"])
    _rf_days(tmp_path, 40, [["살아있는 규칙 12"]])
    r = MA.audit_flag_coverage(str(tmp_path))
    assert [x["rule"] for x in r["never_fired"]] == ["죽은 규칙"]
    assert r["rules_fired"] == 1 and r["ok"] is False


def test_longest_prefix_wins(monkeypatch, tmp_path):
    """짧은 접두어가 긴 규칙을 삼키면 안 된다 — 공매도 비율 vs 공매도 비율 5일 평균."""
    _wire(monkeypatch, tmp_path)
    _rf_code(tmp_path, ["공매도 비율 {a}%", "공매도 비율 5일 평균 {b}% (과다)"])
    _rf_days(tmp_path, 40, [["공매도 비율 5일 평균 20.0% (과다)"]])
    r = MA.audit_flag_coverage(str(tmp_path))
    never = {x["rule"] for x in r["never_fired"]}
    assert never == {"공매도 비율"}          # 긴 쪽이 발동으로 귀속


def test_all_rules_firing_passes(monkeypatch, tmp_path):
    # 접두어는 4자 이상이어야 규칙으로 잡힌다(짧은 조각의 오탐 방지)
    _wire(monkeypatch, tmp_path)
    _rf_code(tmp_path, ["부채비율 경고 {x}", "마진 취약 {y}"])
    _rf_days(tmp_path, 40, [["부채비율 경고 1"], ["마진 취약 2"]])
    r = MA.audit_flag_coverage(str(tmp_path))
    assert r["ok"] is True and not r["never_fired"]


def test_flag_coverage_skips_on_thin_history(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path)
    _rf_code(tmp_path, ["부채비율 경고 {x}"])
    _rf_days(tmp_path, 5, [["부채비율 경고 1"]])
    assert MA.audit_flag_coverage(str(tmp_path))["ok"] is None


def test_flag_coverage_wording_is_not_a_verdict(monkeypatch, tmp_path):
    """미발동 ≠ 고장. 희소 사건일 수 있으므로 단정하지 않는다(RULE 10 정합)."""
    _wire(monkeypatch, tmp_path)
    _rf_code(tmp_path, ["살아있는 {x}", "희소 사건 {y}"])
    _rf_days(tmp_path, 40, [["살아있는 1"]])
    r = MA.audit_flag_coverage(str(tmp_path))
    assert "확인" in r["detail"] and "미발동 ≠ 고장" in r["detail"]


def test_short_literals_are_not_rules(tmp_path):
    """4자 미만 접두어는 규칙으로 세지 않는다 — 조각 매칭으로 오탐이 난다."""
    _rf_code(tmp_path, ["ab {x}", "충분히 긴 규칙 {y}"])
    pre = MA._flag_rule_prefixes(str(tmp_path))
    assert "충분히 긴 규칙" in pre and "ab" not in pre


# ── baseline 갱신 (2026-08-07 N=2 검증 후) ───────────────────────────

def test_price_scale_baseline_is_zero_after_migration():
    """🚨 통화 마이그레이션(#300) 후 실 cron 에서 불일치 0건 확인 → baseline 3→0.

    baseline 을 내려두지 않으면 재발해도 KNOWN 으로 묻힌다. **해소 = baseline 하향**이다.
    """
    assert MA._KNOWN_BASELINE["price_scale"]["scale_mismatches"] == 0
    assert MA._exceeds_baseline("price_scale", {"ok": False, "scale_mismatches": [0]}) is True


def test_rule_discrimination_baselined_until_window_clears():
    """8/6 에 제거한 cape_bubble 이 87일 창에서 빠질 때까지만 유지되는 한시 기준선.

    창에서 빠지면 degenerate 가 줄어들고, 그때 이 항목을 제거해야 한다.
    지금 유지하는 이유 = 매일 FAIL·알림이 가면 '알림 0건이 정상' 원칙이 깨지기 때문.
    """
    base = MA._KNOWN_BASELINE.get("rule_discrimination")
    assert base and base["degenerate_rules"] == 2
    # 늘어나면(새 규칙이 죽으면) 즉시 FAIL
    assert MA._exceeds_baseline(
        "rule_discrimination", {"ok": False, "degenerate_rules": [0, 0, 0]}) is True


def test_alarm_silent_when_everything_is_known(monkeypatch, tmp_path):
    """알림 0건이 정상 baseline — 알려진 범위 안이면 status 가 FAIL 이 아니다."""
    _wire(monkeypatch, tmp_path)
    _days(tmp_path, 60, lambda i: [("a", "WATCH")] if i < 20 else [("obs", None)])
    monkeypatch.setattr(MA, "OUT_PATH", str(tmp_path / "o.json"))
    monkeypatch.setattr(MA, "TRAIL_PATH", str(tmp_path / "m" / "t.jsonl"))
    monkeypatch.setattr(MA, "audit_ledger", lambda: {"ok": False, "phantom_sells": 58})
    monkeypatch.setattr(MA, "audit_key_coverage", lambda root=".": {"ok": False, "dead_keys": [0] * 10})
    monkeypatch.setattr(MA, "audit_price_scale", lambda: {"ok": True, "scale_mismatches": []})
    monkeypatch.setattr(MA, "audit_flag_coverage", lambda root=".": {"ok": False, "never_fired": [0] * 13})
    out = MA.run(str(tmp_path))
    assert out["status"] != "FAIL" and out["failing"] == []


# ── 검사 F — 입력 상수성 (2026-08-07) ────────────────────────────────

def _recs(tmp_path, rows):
    (tmp_path / "recommendations.json").write_text(json.dumps(rows), encoding="utf-8")


def test_constant_zero_input_detected(monkeypatch, tmp_path):
    """🚨 존재하는데 전 종목 동일값(0) = 측정이 아니라 상위 공백.

    실측 2026-08-07: credit_rate·current_ratio 가 19/19 전부 0.0.
    falsy 라 `x or 기본값` 코드에서 결측으로 뭉개져 더 안 보였다.
    """
    _wire(monkeypatch, tmp_path)
    _recs(tmp_path, [{"kis_credit_balance": {"credit_rate": 0.0}} for _ in range(15)])
    r = MA.audit_input_constancy()
    hit = [c for c in r["constant_inputs"] if c["input"] == "kis_credit_balance.credit_rate"]
    assert hit and hit[0]["constant_value"] == 0.0 and hit[0]["severity"] == "high"
    assert r["ok"] is False


def test_varying_input_passes(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path)
    _recs(tmp_path, [{"kis_financial_ratio": {"roe": float(i)}} for i in range(15)])
    r = MA.audit_input_constancy()
    assert not any(c["input"].endswith(".roe") for c in r["constant_inputs"])


def test_constant_nonzero_is_medium(monkeypatch, tmp_path):
    """0 이 아닌 상수도 의심이되 강도는 낮다 — 실제로 같은 값일 수 있다."""
    _wire(monkeypatch, tmp_path)
    _recs(tmp_path, [{"short_interest": {"short_pct": 3.5}} for _ in range(15)])
    r = MA.audit_input_constancy()
    hit = [c for c in r["constant_inputs"] if c["input"] == "short_interest.short_pct"]
    assert hit and hit[0]["severity"] == "medium"


def test_thin_sample_not_judged(monkeypatch, tmp_path):
    """표본 10 미만은 우연히 같을 수 있다 — 판정하지 않는다."""
    _wire(monkeypatch, tmp_path)
    _recs(tmp_path, [{"kis_credit_balance": {"credit_rate": 0.0}} for _ in range(5)])
    assert MA.audit_input_constancy()["constant_inputs"] == []


def test_missing_not_counted_as_constant(monkeypatch, tmp_path):
    """결측(None)은 검사 B 소관 — 여기서 상수로 세면 이중 신고가 된다."""
    _wire(monkeypatch, tmp_path)
    _recs(tmp_path, [{} for _ in range(15)])
    assert MA.audit_input_constancy()["constant_inputs"] == []


def test_constancy_baselined():
    """상위 API 공백 2종은 우리가 못 고친다 — 기준선. 늘어나면 FAIL."""
    assert MA._KNOWN_BASELINE["input_constancy"]["constant_inputs"] == 2
    assert MA._exceeds_baseline(
        "input_constancy", {"ok": False, "constant_inputs": [0, 0, 0]}) is True
