# -*- coding: utf-8 -*-
"""커버리지 게이트 — 분모 증가와 분자 붕괴를 구분한다.

🚨 2026-08-12 실사고. 미장 유니버스가 SEC 벌크로 1,505 → 5,148(3.4배)이 되자
   us.field.facts.PER 86.3%→44.1% · us.companion.us_quarterly 99.5%→30.4% 로 찍혀
   publish 가 차단됐다. 그런데 종목 단위로 대조하니 **데이터 손실이 0** 이었다:
     PER 채움 1,299 → 2,265 · PBR 1,428 → 3,710 · 재무 1,499 → 4,243
     기존 1,505 종목 중 PER/PBR/재무를 잃은 종목 = 0
   커버리지가 개선됐는데 게이트가 붕괴로 읽었다. 게이트가 **비율만** 봤기 때문이다.

   🚨 완화하되 원래 목적은 보존해야 한다 — 이 게이트는 2026-07-11
   us_quarterly 1,494 → 10종 실사고로 도입됐다. 그건 절대 건수가 붕괴한 경우이므로
   "건수 유지·증가면 통과" 규칙으로도 그대로 잡힌다. 아래가 그 계약이다.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.builders import coverage_report_builder as cb  # noqa: E402


def _report(us_total: int, per_filled: int, quarterly: int) -> dict:
    return {
        "kr_total": 0, "fields": {}, "companions": {},
        "us_total": us_total,
        "us_fields": {"facts.PER": {"filled": per_filled,
                                    "pct": round(per_filled / us_total * 100, 1)}},
        "us_companions": {"us_quarterly": {"count": quarterly,
                                           "pct_of_us": round(quarterly / us_total * 100, 1)}},
        "us_smallcap_fields": {},
    }


def test_flat_counts_mirrors_flat_pcts_keys():
    r = _report(1000, 800, 900)
    pcts, counts = cb._flat_pcts(r), cb._flat_counts(r)
    assert set(pcts) == set(counts), "두 평탄화의 키 체계가 어긋나면 대조가 불가능하다"
    assert counts["us.field.facts.PER"] == 800
    assert counts["us.companion.us_quarterly"] == 900


def test_denominator_growth_keeps_counts_so_not_a_collapse():
    """실사고 재현 — 유니버스 3.4배, 건수는 증가."""
    old = _report(1505, 1299, 1498)
    new = _report(5148, 2265, 1530)

    op, np_ = cb._flat_pcts(old), cb._flat_pcts(new)
    on, nn = cb._flat_counts(old), cb._flat_counts(new)

    for k in ("us.field.facts.PER", "us.companion.us_quarterly"):
        assert op[k] - np_[k] > cb.CORE_FAIL_PP, "비율 낙폭은 옛 기준으로 FAIL 조건이다"
        assert nn[k] >= on[k], "그러나 절대 건수는 유지·증가 — 차단 대상이 아니다"


def test_real_collapse_still_blocked():
    """🚨 2026-07-11 형태(us_quarterly 1,494 → 10종)는 여전히 잡혀야 한다."""
    old = _report(1505, 1299, 1494)
    new = _report(1505, 1299, 10)

    op, np_ = cb._flat_pcts(old), cb._flat_pcts(new)
    on, nn = cb._flat_counts(old), cb._flat_counts(new)

    k = "us.companion.us_quarterly"
    assert op[k] - np_[k] > cb.CORE_FAIL_PP
    assert nn[k] < on[k], "건수가 붕괴했으므로 완화 규칙이 적용되지 않는다 = 차단 유지"


def test_partial_shrink_still_blocked():
    """건수가 조금이라도 줄면 완화하지 않는다 — 경계는 '유지·증가' 다."""
    old = _report(1505, 1299, 1498)
    new = _report(5148, 1298, 1497)   # 유니버스는 늘었지만 건수는 1 감소
    on, nn = cb._flat_counts(old), cb._flat_counts(new)
    for k in ("us.field.facts.PER", "us.companion.us_quarterly"):
        assert not (nn[k] >= on[k]), "1건이라도 줄면 완화 조건 불성립"


# ── 발행 최소선 (PM 2026-08-12 "데이터 없이는 좀 그렇잖아") ──────────────────

def test_empty_shell_excluded_from_publish():
    """핵심축 4종이 전부 빈 행은 발행하지 않는다. 수집은 전량 유지한다."""
    from api.builders import us_stock_report_public_builder as ub
    import inspect
    src = inspect.getsource(ub.main)
    assert "_core_axes" in src, "발행 최소선 필터가 사라지면 빈 껍데기 662종목이 다시 나간다"
    assert "핵심축 0" in src or "빈 껍데기" in src


def test_partial_financial_cache_cannot_replace_richer_compact_history():
    from api.builders import us_stock_report_public_builder as ub

    cached = [{"year": y} for y in (2021, 2022, 2023, 2024, 2025)]
    partial = [{"year": y} for y in (2024, 2025)]
    cached_fin = {"period": "2025", "groups": [{"title": "annual"}]}

    fs, fin = ub._prefer_richer_annual_pack(partial, None, cached, cached_fin)
    assert fs == cached
    assert fin == cached_fin


def test_equal_or_longer_fresh_history_wins():
    from api.builders import us_stock_report_public_builder as ub

    cached = [{"year": 2023}, {"year": 2024}]
    fresh = [{"year": 2023}, {"year": 2024}, {"year": 2025}]
    fresh_fin = {"period": "2025"}

    fs, fin = ub._prefer_richer_annual_pack(fresh, fresh_fin, cached, {"period": "2024"})
    assert fs == fresh
    assert fin == fresh_fin


def test_existing_public_report_is_available_as_regeneration_floor(tmp_path):
    from api.builders import us_stock_report_public_builder as ub

    path = tmp_path / "us_stock_report_public.json"
    path.write_text(json.dumps({"stocks": [{
        "ticker": "AAPL",
        "fin_series": [{"year": 2024}, {"year": 2025}],
        "financials": {"period": "2025"},
    }]}), encoding="utf-8")

    got = ub._load_existing_public_annual_packs(str(path))
    assert got["AAPL"]["fs"] == [{"year": 2024}, {"year": 2025}]
    assert got["AAPL"]["fin"] == {"period": "2025"}


@pytest.mark.parametrize("value", [None, "", "  ", {}, [], {"PER": None}, [None, ""],
                                  {"values": {"revenue": None}, "rows": []}])
def test_filled_rejects_empty_payloads(value):
    assert not cb._filled(value)


@pytest.mark.parametrize("value", [0, False, "0", {"value": 0}, [None, {"value": 0}],
                                  {"status": "not_applicable"}])
def test_filled_preserves_zero_and_explicit_status(value):
    assert cb._filled(value)


def _run_gate(monkeypatch, tmp_path, current, previous=None):
    baseline = tmp_path / "coverage_report.json"
    if previous is not None:
        baseline.write_text(json.dumps(previous), encoding="utf-8")
    monkeypatch.setattr(cb, "_META", str(tmp_path))
    monkeypatch.setattr(cb, "REPORT_PATH", str(baseline))
    monkeypatch.setattr(cb, "HISTORY_PATH", str(tmp_path / "coverage_history.jsonl"))
    monkeypatch.setattr(cb, "build", lambda: current)
    return baseline


def test_all_sources_missing_blocks_without_overwriting_good_baseline(monkeypatch, tmp_path):
    previous = _report(1000, 800, 900)
    with monkeypatch.context() as mp:
        mp.setattr(cb, "_load", lambda name: None)
        current = cb.build()
    path = _run_gate(monkeypatch, tmp_path, current, previous)
    before = path.read_bytes()
    with pytest.raises(SystemExit, match="1"):
        cb.main()
    assert path.read_bytes() == before
    assert json.loads((tmp_path / "coverage_history.jsonl").read_text())["blocked"] is True


def test_empty_first_run_is_not_a_good_baseline(monkeypatch, tmp_path):
    current = {"kr_total": 0, "us_total": 0, "us_smallcap_total": 0}
    path = _run_gate(monkeypatch, tmp_path, current)
    with pytest.raises(SystemExit):
        cb.main()
    assert not path.exists()


def test_missing_critical_companion_blocks_even_with_healthy_report(monkeypatch, tmp_path):
    previous = _report(1000, 800, 900)
    current = _report(1000, 800, 900)
    current["us_companions"]["us_quarterly"] = None
    path = _run_gate(monkeypatch, tmp_path, current, previous)
    with pytest.raises(SystemExit):
        cb.main()
    assert json.loads(path.read_text()) == previous


def test_missing_one_market_blocks_while_other_market_remains(monkeypatch, tmp_path):
    previous = _report(1000, 800, 900)
    previous["kr_total"] = 1000
    current = _report(1000, 800, 900)
    _run_gate(monkeypatch, tmp_path, current, previous)
    with pytest.raises(SystemExit):
        cb.main()


def test_partial_initial_run_and_unobserved_optional_sources_are_allowed(monkeypatch, tmp_path):
    current = _report(1000, 800, 900)
    path = _run_gate(monkeypatch, tmp_path, current)
    cb.main()
    assert json.loads(path.read_text()) == current


def test_denominator_expansion_still_passes_full_gate(monkeypatch, tmp_path):
    previous = _report(1505, 1299, 1498)
    current = _report(5148, 2265, 1530)
    path = _run_gate(monkeypatch, tmp_path, current, previous)
    cb.main()
    assert json.loads(path.read_text()) == current


@pytest.mark.parametrize("value", [None, True, False, {}, [], "", " ", "NaN", "Infinity",
                                  float("nan"), float("inf"), "not a number", "1,000", "10배", "１２"])
def test_multiple_coverage_rejects_non_numeric_or_nonfinite(value):
    assert not cb._finite_multiple(value)


@pytest.mark.parametrize("value", [0, -1, 1.5, "0", "-1.2", "+.2", "1.", "1e3", "-2E-2", " 12 "])
def test_multiple_coverage_preserves_valid_numbers(value):
    assert cb._finite_multiple(value)


def test_all_report_scopes_count_numeric_multiple_values_only(monkeypatch):
    rows = [{"ticker": str(100000 + i), "facts": {"PER": value, "PBR": value}}
            for i, value in enumerate([0, "-2.5", None, True, "NaN", "--", {}])]
    reports = {name: {"stocks": rows} for name in (
        "stock_report_public.json", "us_stock_report_public.json", "us_stock_report_us_smallcap.json")}
    monkeypatch.setattr(cb, "_load", reports.get)
    result = cb.build()
    for field in ("fields", "us_fields", "us_smallcap_fields"):
        assert result[field]["facts.PER"]["filled"] == 2
        assert result[field]["facts.PBR"]["filled"] == 2


@pytest.mark.parametrize("shape,value", [
    (dict, {"000001": {}, "000002": {}, "999999": {}}),
    (list, [{"ticker": "000001"}, {"ticker": "000002"}, {"ticker": "999999"}]),
])
def test_companion_coverage_uses_report_intersection(shape, value):
    rows = [{"ticker": "000001"}, {"ticker": "000001"}, {"ticker": "000002"}]
    result = cb._companion_coverage({"stocks": value}, "stocks", rows, "pct_of_kr", shape)
    assert result["count"] == 3  # raw source count remains inspectable
    assert result["report_ticker_count"] == 2
    assert result["matched_count"] == 2
    assert result["unmatched_count"] == 1
    assert result["pct_of_kr"] == 100.0


def test_duplicate_companion_rows_do_not_inflate_coverage():
    value = [{"ticker": ticker} for ticker in ("A", "A", "Z")]
    result = cb._companion_coverage({"stocks": value}, "stocks", [{"ticker": "A"}], "pct_of_us", list)
    assert result["count"] == 3
    assert result["matched_count"] == 1
    assert result["unmatched_count"] == 1
    assert result["duplicate_count"] == 1
    assert result["unidentified_count"] == 0
    assert result["pct_of_us"] == 100.0


@pytest.mark.parametrize("value,shape,reason", [
    ([{"name": "not a ticker"}], list, "unidentified_ticker"),
    ([{"ticker": None}], list, "unidentified_ticker"),
    ([{"ticker": 123}], list, "unidentified_ticker"),
    (["A"], list, "unidentified_ticker"),
    ({"": {}}, dict, "unidentified_ticker"),
    ({"A": {}}, list, "unexpected_companion_schema"),
    ([], dict, "unexpected_companion_schema"),
    (None, dict, "unexpected_companion_schema"),
])
def test_unidentifiable_companion_is_not_zero_or_complete(value, shape, reason):
    result = cb._companion_coverage({"stocks": value}, "stocks", [{"ticker": "A"}], "pct_of_us", shape)
    assert result["pct_of_us"] is None
    assert result["unmeasurable_reason"] == reason


@pytest.mark.parametrize("shape", [dict, list])
def test_valid_empty_companion_measures_zero(shape):
    result = cb._companion_coverage({"stocks": shape()}, "stocks", [{"ticker": "A"}], "pct_of_us", shape)
    assert result["count"] == result["matched_count"] == 0
    assert result["pct_of_us"] == 0.0
    assert result["unmeasurable_reason"] is None


def test_all_seven_companions_use_their_confirmed_schema(monkeypatch):
    docs = {"stock_report_public.json": {"stocks": [{"ticker": "000001"}]},
            "us_stock_report_public.json": {"stocks": [{"ticker": "A"}]}}
    for name, key, shape, ticker in [
        ("dart_quarterly_public.json", "stocks", dict, "000001"),
        ("disclosure_forensics.json", "stocks", list, "000001"),
        ("insider_trades.json", "stocks", list, "000001"),
        ("securities_lending.json", "stocks", list, "000001"),
        ("stock_flow_5d.json", "flows", dict, "000001"),
        ("us_quarterly_public.json", "stocks", dict, "A"),
        ("us_insider_trades.json", "stocks", list, "A"),
    ]:
        docs[name] = {key: {ticker: {}, "EXTRA": {}} if shape is dict
                      else [{"ticker": ticker}, {"ticker": "EXTRA"}]}
    monkeypatch.setattr(cb, "_load", docs.get)
    result = cb.build()
    for group, pct_key in (("companions", "pct_of_kr"), ("us_companions", "pct_of_us")):
        for metric in result[group].values():
            assert metric["count"] == 2
            assert metric["matched_count"] == 1
            assert metric["unmatched_count"] == 1
            assert metric[pct_key] == 100.0


def _intersection_report(total, raw_count, matched_count):
    result = _report(total, total, raw_count)
    result["us_companions"]["us_quarterly"].update(
        coverage_basis=cb.COMPANION_BASIS, matched_count=matched_count,
        pct_of_us=round(matched_count / total * 100, 1))
    return result


def test_legacy_raw_baseline_migration_does_not_fake_a_collapse(monkeypatch, tmp_path):
    previous = _report(1000, 1000, 1000)
    current = _intersection_report(1000, 1000, 600)
    path = _run_gate(monkeypatch, tmp_path, current, previous)
    cb.main()
    assert json.loads(path.read_text()) == current
    history = json.loads((tmp_path / "coverage_history.jsonl").read_text())
    assert history["basis_migrations"] == ["us.companion.us_quarterly"]
    assert history["us.companion.us_quarterly"] == 60.0
    assert cb._flat_counts(current)["us.companion.us_quarterly"] == 600


@pytest.mark.parametrize("previous,current", [
    (_report(1000, 1000, 1000), _intersection_report(1000, 100, 100)),
    (_report(1000, 1000, 1000), _intersection_report(1000, 1000, 0)),
    (_intersection_report(1000, 1000, 600), _intersection_report(1000, 1000, 100)),
])
def test_intersection_gate_keeps_raw_loss_floor_and_matched_loss_guards(monkeypatch, tmp_path, previous, current):
    path = _run_gate(monkeypatch, tmp_path, current, previous)
    with pytest.raises(SystemExit):
        cb.main()
    assert json.loads(path.read_text()) == previous


def test_intersection_denominator_growth_preserves_existing_exemption(monkeypatch, tmp_path):
    previous = _intersection_report(1000, 1000, 800)
    current = _intersection_report(3000, 1000, 800)
    path = _run_gate(monkeypatch, tmp_path, current, previous)
    cb.main()
    assert json.loads(path.read_text()) == current


def test_new_basis_unmeasurable_core_does_not_replace_legacy_good(monkeypatch, tmp_path):
    previous = _report(1000, 1000, 1000)
    current = _intersection_report(1000, 1000, 600)
    current["us_companions"]["us_quarterly"].update(
        pct_of_us=None, unmeasurable_reason="unidentified_ticker")
    path = _run_gate(monkeypatch, tmp_path, current, previous)
    with pytest.raises(SystemExit):
        cb.main()
    assert json.loads(path.read_text()) == previous
