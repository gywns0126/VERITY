# -*- coding: utf-8 -*-
"""연간재무 백필 재개 상태 = (티커, 연도) 셀 단위 (2026-08-23 신설).

## 왜 — 48일 조용히 얼어 있던 결손

2026-07-06 `c7b78b41c` 가 오염 행 **72개(37종목)** 를 purge 하고 "재큐" 했다. 그런데
재개 상태가 **티커 단위 `done`** 이었고, 재큐 신호는 "오염 행이 **존재**한다" 였다.
행을 지우면서 신호까지 지운 것이다. 티커는 `done` 에 남아 todo 에서 영구 제외됐다.

실측(2026-08-23 확인): purge 72칸 중 **48칸(19종목) 미복구**. 삼성전자 9년 포함 —
`fin_series` 가 2년뿐이었다. 알림·에러·워크플로 실패는 **전부 0**. 커버리지 지표도
"1,718종목 보유" 로 정상으로 보였다. 분모가 종목이었기 때문이다(RULE 13).

## 여기서 고정하는 것

- todo 는 **셀**에서 나온다. `done` 에 있어도 빈 칸이 있으면 다시 대상이 된다.
- 빈 응답은 셀 원장에 시도 횟수로 남는다 — 상장 전 연도를 매 run 재조회하지 않기 위해서.
- 시도 상한에 걸린 칸은 `--retry-exhausted` 로만 다시 두드린다.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "fin_bf", str(_ROOT / "scripts" / "dart_kr_fin_backfill.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def bf(tmp_path, monkeypatch):
    mod = _load_module()
    monkeypatch.setattr(mod, "OUT_PATH", str(tmp_path / "hist.json"))
    monkeypatch.setattr(mod, "DONE_PATH", str(tmp_path / "done.json"))
    monkeypatch.setattr(mod, "MISSING_PATH", str(tmp_path / "missing.json"))
    uni = tmp_path / "universe.json"
    uni.write_text(json.dumps({"stocks": [{"ticker": "005930", "name": "삼성전자"}]}),
                   encoding="utf-8")
    monkeypatch.setattr(mod, "DEFAULT_UNIVERSE", str(uni))
    return mod


def _run(mod, monkeypatch, capsys, *extra):
    """quota-cap 0 = 요청 0. todo 계산만 하고 즉시 멈춘다(네트워크 없음)."""
    argv = ["dart_kr_fin_backfill.py", "--start-year", "2023", "--quota-cap", "0", *extra]
    monkeypatch.setattr(sys, "argv", argv)
    rc = mod.main()
    assert rc == 0
    return capsys.readouterr().err


def _write(mod, rows=(), done=(), cells=None):
    with open(mod.OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"rows": list(rows)}, f, ensure_ascii=False)
    with open(mod.DONE_PATH, "w", encoding="utf-8") as f:
        json.dump({"tickers": list(done)}, f, ensure_ascii=False)
    if cells is not None:
        with open(mod.MISSING_PATH, "w", encoding="utf-8") as f:
            json.dump({"cells": cells}, f, ensure_ascii=False)


# 스크립트와 같은 규칙: 완결 연도만 (당해 사업보고서 미공시)
YEARS = list(range(2023, date.today().year))
ALL_BUT_FIRST = YEARS[1:]


def _row(year):
    return {"ticker": "005930", "name": "삼성전자", "fiscal_year": year, "period": "annual",
            "fundamentals": {"revenue": 3e14, "operating_profit": 3e13,
                             "net_income": 3e13, "investment_property": None}}


def test_purged_cells_are_requeued_even_when_ticker_is_done(bf, monkeypatch, capsys):
    """🚨 07-06 회귀 방지 — `done` 티커라도 빈 연도가 있으면 대상이다."""
    # 첫 연도만 비어 있다(= purge 된 칸). 종전 규칙이면 done 이라 대상 0.
    _write(bf, rows=[_row(y) for y in ALL_BUT_FIRST], done=["005930"])
    err = _run(bf, monkeypatch, capsys)
    assert "대상종목 1" in err
    assert "대상칸 1" in err


def test_fully_covered_ticker_is_not_requeued(bf, monkeypatch, capsys):
    _write(bf, rows=[_row(y) for y in YEARS], done=["005930"])
    err = _run(bf, monkeypatch, capsys)
    assert "대상종목 0" in err
    assert "대상칸 0" in err


def test_exhausted_cells_are_skipped(bf, monkeypatch, capsys):
    """상장 전 연도는 영원히 status 013 이다 — 상한까지만 두드리고 접는다."""
    _write(bf, rows=[_row(y) for y in ALL_BUT_FIRST], done=["005930"],
           cells={f"005930|{YEARS[0]}": {"n": bf.MAX_CELL_ATTEMPTS, "last": "2026-08-23",
                                         "status": "013"}})
    err = _run(bf, monkeypatch, capsys)
    assert "대상칸 0" in err
    assert "시도포기칸 1" in err


def test_retry_exhausted_reopens_them(bf, monkeypatch, capsys):
    _write(bf, rows=[_row(y) for y in ALL_BUT_FIRST], done=["005930"],
           cells={f"005930|{YEARS[0]}": {"n": bf.MAX_CELL_ATTEMPTS, "last": "2026-08-23",
                                         "status": "013"}})
    err = _run(bf, monkeypatch, capsys, "--retry-exhausted")
    assert "대상칸 1" in err


def test_partial_attempts_still_retry(bf, monkeypatch, capsys):
    _write(bf, rows=[_row(y) for y in ALL_BUT_FIRST], done=["005930"],
           cells={f"005930|{YEARS[0]}": {"n": 1, "last": "2026-08-20", "status": "013"}})
    err = _run(bf, monkeypatch, capsys)
    assert "대상칸 1" in err


def test_dirty_row_is_recollected(bf, monkeypatch, capsys):
    """op 오파싱(매출 큰데 영업이익 극소) 행은 보유로 치지 않는다 — 기존 규율 유지."""
    rows = [_row(y) for y in YEARS]
    rows[0]["fundamentals"]["operating_profit"] = 5287.0     # LGES 실측 형태
    _write(bf, rows=rows, done=["005930"])
    err = _run(bf, monkeypatch, capsys)
    assert "대상칸 1" in err


def test_output_carries_self_reported_meta(bf, monkeypatch, capsys):
    """🚨 RULE 12 ② — 산출물이 자기 커버리지를 신고한다. 소비자는 rows 만 읽으므로 안전."""
    _write(bf, rows=[_row(y) for y in YEARS], done=[])
    _run(bf, monkeypatch, capsys)
    with open(bf.OUT_PATH, encoding="utf-8") as f:
        out = json.load(f)
    assert out["_meta"]["artifact"] == "dart_kr_fin_history"
    assert out["_meta"]["rows_n"] == len(YEARS)
    assert out["_meta"]["tickers_n"] == 1
    assert out["_meta"]["years_per_ticker_hist"] == {str(len(YEARS)): 1}
    assert len(out["rows"]) == len(YEARS)      # 소비자 계약 — rows 키 불변


@pytest.mark.parametrize("values", [
    {"revenue": 0, "operating_profit": 0, "net_income": 0, "investment_property": None},
    {"revenue": 100, "operating_profit": 0, "net_income": -20, "investment_property": None},
    {"revenue": None, "operating_profit": -10, "net_income": 0, "investment_property": None},
])
def test_collected_zero_and_loss_are_preserved(bf, monkeypatch, values):
    """Exercise collection through persisted rows; never call DART or mapping refresh."""
    _write(bf, rows=[_row(y) for y in ALL_BUT_FIRST])
    monkeypatch.setattr(bf, "get_corp_code", lambda _ticker: "00126380")
    accounts = {"revenue": ("ifrs-full_Revenue", "매출액"),
                "operating_profit": ("dart_OperatingIncomeLoss", "영업이익"),
                "net_income": ("ifrs-full_ProfitLoss", "당기순이익")}
    rows = [{"sj_div": "IS", "account_id": aid, "account_nm": label,
             "thstrm_amount": str(values[field])}
            for field, (aid, label) in accounts.items() if values[field] is not None]
    monkeypatch.setattr(bf, "_fetch_fnltt_all_cached", lambda *_args: json.dumps({"status": "000", "list": rows}))
    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--start-year", "2023", "--quota-cap", "1"])
    assert bf.main() == 0
    output = json.loads(Path(bf.OUT_PATH).read_text())
    collected = next(row for row in output["rows"] if row["fiscal_year"] == YEARS[0])
    assert collected["fundamentals"] == values
    assert f"005930|{YEARS[0]}" not in json.loads(Path(bf.MISSING_PATH).read_text())["cells"]


def test_all_missing_metrics_remain_missing_without_a_synthetic_zero(bf, monkeypatch):
    _write(bf, rows=[_row(y) for y in ALL_BUT_FIRST])
    monkeypatch.setattr(bf, "get_corp_code", lambda _ticker: "00126380")
    # An unrelated row leaves the legacy extractor's PL fields at their zero defaults.
    monkeypatch.setattr(bf, "_fetch_fnltt_all_cached", lambda *_args: '{"status":"000","list":[{"sj_div":"BS","account_nm":"자본금","thstrm_amount":"100"}]}')
    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--start-year", "2023", "--quota-cap", "1"])
    assert bf.main() == 0
    output = json.loads(Path(bf.OUT_PATH).read_text())
    assert not any(row["fiscal_year"] == YEARS[0] for row in output["rows"])
    missing = json.loads(Path(bf.MISSING_PATH).read_text())
    cell = missing["cells"][f"005930|{YEARS[0]}"]
    assert cell["status"] == "error"
    assert cell["last_error"] == "no_target_metrics"
    assert cell["n"] == 0


@pytest.mark.parametrize("amount", ["", "-", " ", "N/A"])
def test_blank_selected_account_is_not_promoted_to_reported_zero(bf, monkeypatch, amount):
    _write(bf, rows=[_row(y) for y in ALL_BUT_FIRST])
    monkeypatch.setattr(bf, "get_corp_code", lambda _ticker: "00126380")
    raw = json.dumps({"status": "000", "list": [{"sj_div": "IS", "account_id": "ifrs-full_ProfitLoss",
                                "account_nm": "당기순이익", "thstrm_amount": amount}]})
    monkeypatch.setattr(bf, "_fetch_fnltt_all_cached", lambda *_args: raw)
    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--start-year", "2023", "--quota-cap", "1"])
    assert bf.main() == 0
    output = json.loads(Path(bf.OUT_PATH).read_text())
    assert not any(row["fiscal_year"] == YEARS[0] for row in output["rows"])


def test_only_official_013_falls_back_to_ofs_and_consumes_empty_attempt(bf, monkeypatch):
    _write(bf, rows=[_row(y) for y in ALL_BUT_FIRST])
    monkeypatch.setattr(bf, "get_corp_code", lambda _ticker: "00126380")
    calls = []

    def fetch(_corp, year, fs_div):
        calls.append((year, fs_div))
        return json.dumps({"status": "013", "message": "no data", "list": []})

    monkeypatch.setattr(bf, "_fetch_fnltt_all_cached", fetch)
    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--start-year", "2023", "--quota-cap", "2"])
    assert bf.main() == 0

    assert calls == [(str(YEARS[0]), "CFS"), (str(YEARS[0]), "OFS")]
    missing = json.loads(Path(bf.MISSING_PATH).read_text())
    empty_cell = missing["cells"][f"005930|{YEARS[0]}"]
    assert empty_cell["n"] == 1
    assert empty_cell["status"] == "013"
    run = missing["_meta"]["last_run"]
    assert run["requested"] == 1
    assert run["attempted"] == 1
    assert run["success"] == 0
    assert run["empty"] == 1
    assert run["error"] == 0
    assert run["deferred"] == 0
    assert run["requests"] == 2
    assert run["touched"] == 1
    assert datetime.fromisoformat(run["attempted_at"]).utcoffset() is not None


def test_cfs_source_error_does_not_fallback_and_preserves_existing_row(bf, monkeypatch):
    old = {**_row(YEARS[0]), "fundamentals": {
        "revenue": 1000, "operating_profit": -200, "net_income": None,
        "investment_property": None,
    }}
    _write(bf, rows=[old, *[_row(y) for y in ALL_BUT_FIRST]])
    key = f"005930|{YEARS[0]}"
    with open(bf.MISSING_PATH, "w", encoding="utf-8") as f:
        json.dump({"cells": {key: {"n": 2, "last": "2026-10-01", "status": "error"}}}, f)
    monkeypatch.setattr(bf, "get_corp_code", lambda _ticker: "00126380")
    calls = []

    def fetch(_corp, _year, fs_div):
        calls.append(fs_div)
        return json.dumps({"status": "error", "message": "SECRET_URL?key=secret", "list": []})

    monkeypatch.setattr(bf, "_fetch_fnltt_all_cached", fetch)
    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--start-year", "2023", "--quota-cap", "1"])
    assert bf.main() == 0

    output = json.loads(Path(bf.OUT_PATH).read_text())
    assert output["rows"][0] == old
    assert calls == ["CFS"]
    missing = json.loads(Path(bf.MISSING_PATH).read_text())
    cell = missing["cells"][key]
    assert cell["n"] == 2  # source failure does not consume no-data attempts
    assert cell["status"] == "error"
    assert cell["error_count"] == 1
    assert cell["no_data_attempts"] == 0
    assert cell["last_error"] == "unexpected_status"
    assert "SECRET_URL" not in Path(bf.MISSING_PATH).read_text()
    run = missing["_meta"]["last_run"]
    assert (run["requested"], run["attempted"], run["error"], run["empty"]) == (1, 1, 1, 0)
    assert run["requested"] == run["success"] + run["empty"] + run["error"] + run["deferred"]


def test_partial_replacement_preserves_existing_row_and_remains_retryable(bf, monkeypatch):
    old = {**_row(YEARS[0]), "fundamentals": {
        "revenue": 100, "operating_profit": -20, "net_income": None,
        "investment_property": None,
    }}
    _write(bf, rows=[old, *[_row(y) for y in ALL_BUT_FIRST]])
    monkeypatch.setattr(bf, "get_corp_code", lambda _ticker: "00126380")
    raw = json.dumps({"status": "000", "list": [{
        "sj_div": "IS", "account_id": "ifrs-full_ProfitLoss",
        "account_nm": "당기순이익", "thstrm_amount": "10",
    }]})
    monkeypatch.setattr(bf, "_fetch_fnltt_all_cached", lambda *_args: raw)
    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--start-year", "2023", "--quota-cap", "1"])
    assert bf.main() == 0

    output = json.loads(Path(bf.OUT_PATH).read_text())
    assert output["rows"][0] == old
    missing = json.loads(Path(bf.MISSING_PATH).read_text())
    cell = missing["cells"][f"005930|{YEARS[0]}"]
    assert cell["status"] == "error"
    assert cell["last_error"] == "partial_replacement"
    run = missing["_meta"]["last_run"]
    assert (run["success"], run["error"], run["requested"]) == (0, 1, 1)


def test_complete_replacement_accepts_zero_and_negative_values(bf, monkeypatch):
    old = {**_row(YEARS[0]), "fundamentals": {
        "revenue": 100, "operating_profit": -20, "net_income": None,
        "investment_property": None,
    }}
    _write(bf, rows=[old, *[_row(y) for y in ALL_BUT_FIRST]])
    monkeypatch.setattr(bf, "get_corp_code", lambda _ticker: "00126380")
    accounts = [
        ("ifrs-full_Revenue", "매출액", "0"),
        ("dart_OperatingIncomeLoss", "영업이익", "-30"),
        ("ifrs-full_ProfitLoss", "당기순이익", "10"),
    ]
    raw = json.dumps({"status": "000", "list": [
        {"sj_div": "IS", "account_id": account_id, "account_nm": label,
         "thstrm_amount": amount}
        for account_id, label, amount in accounts
    ]})
    monkeypatch.setattr(bf, "_fetch_fnltt_all_cached", lambda *_args: raw)
    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--start-year", "2023", "--quota-cap", "1"])
    assert bf.main() == 0

    output = json.loads(Path(bf.OUT_PATH).read_text())
    assert output["rows"][0]["fundamentals"] == {
        "revenue": 0, "operating_profit": -30, "net_income": 10,
        "investment_property": None,
    }
    missing = json.loads(Path(bf.MISSING_PATH).read_text())
    assert f"005930|{YEARS[0]}" not in missing["cells"]
    assert missing["_meta"]["last_run"]["success"] == 1


def test_legacy_error_attempts_do_not_exhaust_first_confirmed_no_data(bf, monkeypatch):
    _write(bf, rows=[_row(y) for y in ALL_BUT_FIRST],
           cells={f"005930|{YEARS[0]}": {"n": 2, "status": "error"}})
    monkeypatch.setattr(bf, "get_corp_code", lambda _ticker: "00126380")
    responses = iter([
        '{"status":"error","list":[]}',
        '{"status":"013","list":[]}',
        '{"status":"013","list":[]}',
    ])
    monkeypatch.setattr(bf, "_fetch_fnltt_all_cached", lambda *_args: next(responses))
    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--start-year", "2023", "--quota-cap", "1"])
    assert bf.main() == 0

    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--start-year", "2023", "--quota-cap", "2"])
    assert bf.main() == 0
    key = f"005930|{YEARS[0]}"
    missing = json.loads(Path(bf.MISSING_PATH).read_text())
    cell = missing["cells"][key]
    assert cell["n"] == 3  # Legacy total attempts remain compatible.
    assert cell["no_data_attempts"] == 1
    assert cell["status"] == "013"
    assert not bf._is_exhausted_no_data(cell)
    run = missing["_meta"]["last_run"]
    assert run["requested"] == run["success"] + run["empty"] + run["error"] + run["deferred"]


def test_typed_error_preserves_prior_official_no_data_budget(bf):
    cells = {"005930|2023": {"n": 1, "status": "013"}}
    bf._record_error(cells, "005930|2023", "unexpected_status")
    assert cells["005930|2023"]["no_data_attempts"] == 1
    bf._record_empty(cells, "005930|2023")
    assert cells["005930|2023"]["no_data_attempts"] == 2
    assert bf._is_exhausted_no_data(cells["005930|2023"])


def test_corp_code_failure_counts_cell_attempt_and_ticker_touch(bf, monkeypatch, capsys):
    _write(bf, rows=[_row(y) for y in ALL_BUT_FIRST])
    lookups = []
    monkeypatch.setattr(bf, "get_corp_code", lambda ticker: lookups.append(ticker) or None)
    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--start-year", "2023", "--quota-cap", "1"])
    assert bf.main() == 0
    missing = json.loads(Path(bf.MISSING_PATH).read_text())
    run = missing["_meta"]["last_run"]
    assert lookups == ["005930"]
    assert (run["requested"], run["attempted"], run["error"], run["deferred"], run["touched"]) == (1, 1, 1, 0, 1)
    assert run["requests"] == 0  # No DART financial endpoint was called.
    assert run["requested"] == run["success"] + run["empty"] + run["error"] + run["deferred"]
    assert run["attempted"] >= run["success"] + run["empty"] + run["error"]


def test_cfs_013_without_quota_for_ofs_is_deferred_not_exhausted(bf, monkeypatch):
    _write(bf, rows=[_row(y) for y in ALL_BUT_FIRST])
    monkeypatch.setattr(bf, "get_corp_code", lambda _ticker: "00126380")
    calls = []
    monkeypatch.setattr(bf, "_fetch_fnltt_all_cached", lambda _corp, _year, fs_div:
                        calls.append(fs_div) or '{"status":"013","list":[]}')
    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--start-year", "2023", "--quota-cap", "1"])
    assert bf.main() == 0

    missing = json.loads(Path(bf.MISSING_PATH).read_text())
    run = missing["_meta"]["last_run"]
    assert calls == ["CFS"]
    assert (run["requested"], run["attempted"], run["empty"], run["error"], run["deferred"]) == (1, 1, 0, 0, 1)
    assert f"005930|{YEARS[0]}" not in missing["cells"]


@pytest.mark.parametrize(("raw", "reason"), [
    ("not-json", "invalid_json"),
    ('{"status":"000"}', "invalid_payload"),
])
def test_malformed_cfs_response_is_retryable_without_ofs_fallback(bf, monkeypatch, raw, reason):
    _write(bf, rows=[_row(y) for y in ALL_BUT_FIRST])
    monkeypatch.setattr(bf, "get_corp_code", lambda _ticker: "00126380")
    calls = []
    monkeypatch.setattr(bf, "_fetch_fnltt_all_cached", lambda _corp, _year, fs_div:
                        calls.append(fs_div) or raw)
    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--start-year", "2023", "--quota-cap", "1"])
    assert bf.main() == 0

    cell = json.loads(Path(bf.MISSING_PATH).read_text())["cells"][f"005930|{YEARS[0]}"]
    assert calls == ["CFS"]
    assert cell["n"] == 0
    assert cell["status"] == "error"
    assert cell["last_error"] == reason


def test_first_four_months_cannot_be_recollected_without_reviewed_history(bf, monkeypatch):
    universe = Path(bf.DEFAULT_UNIVERSE)
    universe.write_text(json.dumps({"stocks": [{"ticker": "489790", "name": "한화비전"}]}), encoding="utf-8")
    _write(bf, rows=[])
    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--start-year", "2024", "--quota-cap", "0"])
    monkeypatch.setattr(bf, "get_corp_code", lambda _: (_ for _ in ()).throw(AssertionError("no API lookup")))
    with pytest.raises(ValueError, match="489790 first close"):
        bf.main()
    old = {"ticker":"489790", "name":"한화비전", "fiscal_year":2024, "period":"annual",
           "fundamentals":{"revenue":None,"operating_profit":-120362075,"net_income":31701255717}}
    _write(bf, rows=[old])
    assert bf.main() == 0  # The known row is held, never treated as a 12-month value.
    universe.write_text(json.dumps({"stocks": [{"ticker": "111111", "name": "unrelated"}]}), encoding="utf-8")
    _write(bf, rows=[{**old, "fundamentals": {**old["fundamentals"], "net_income": 0}}])
    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--ticker", "111111", "--start-year", "2024", "--quota-cap", "0"])
    assert bf.main() == 0  # An unrelated caller does not validate this issuer's held history.


def _principal_rows(ticker="005930", corp="00126380", year=2023, scope="CFS",
                    column="thstrm", values=(100, -20, 10)):
    return [{"corp_code": corp, "stock_code": ticker, "reprt_code": "11011",
             "bsns_year": str(year if column == "thstrm" else year + 1),
             "rcept_no": "20260324000091", "fs_div": scope, "sj_div": "IS",
             "account_nm": name, "currency": "KRW",
             f"{column}_dt": f"{year}.01.01 ~ {year}.12.31",
             f"{column}_amount": "-" if value is None else str(value)}
            for name, value in zip(("매출액", "영업이익", "당기순이익(손실)"), values)]


def test_selected_tickers_share_one_run_quota_and_reject_invalid_selection(bf, tmp_path):
    universe = tmp_path / "selection.json"
    universe.write_text(json.dumps({"stocks": [{"ticker": t} for t in ("136490", "082660", "192080", "005930")]}))
    assert [t for t, _ in bf._universe(str(universe), None, "136490,082660,192080")] == ["136490", "082660", "192080"]
    with pytest.raises(ValueError, match="ticker"):
        bf._universe(str(universe), None, "136490;ignored")


@pytest.mark.parametrize("ticker,corp,year,scope,column,values", [
    ("136490", "00855093", 2024, "CFS", "thstrm", (1681370807177, 124085515096, 6642150612)),
    ("082660", "00442455", 2024, "CFS", "frmtrm", (9745770767, -8285302600, -19463045883)),
    ("192080", "01010110", 2015, "OFS", "thstrm", (122441546376, 31899043444, 34161459082)),
])
def test_confirmed_source_blocks_and_explicit_comparative_period(bf, ticker, corp, year, scope, column, values):
    rows = _principal_rows(ticker, corp, year, scope, column, values)
    if scope == "OFS":
        rows += _principal_rows(ticker, corp, year, "CFS", values=(None,) * 3)
    block, source, reason = bf._principal_annual_block({"status": "000", "list": rows}, corp, ticker, year)
    assert reason is None
    assert tuple(block.values()) == values
    assert (source["fs_div"], source["amount_column"], source["period_end"]) == (scope, column + "_amount", f"{year}-12-31")
    assert len(source["response_sha256"]) == 64


@pytest.mark.parametrize("field,value", [
    ("corp_code", "99999999"), ("stock_code", "999999"), ("reprt_code", "11012"),
    ("currency", "USD"), ("fs_div", "unknown"), ("rcept_no", "bad"),
    ("thstrm_dt", "2023.04.01 ~ 2023.12.31"), ("thstrm_dt", "2024.01.01 ~ 2024.12.31"),
])
def test_principal_wrong_identity_currency_or_duration_cannot_fill(bf, field, value):
    rows = [{**row, field: value} for row in _principal_rows()]
    block, _, reason = bf._principal_annual_block({"status": "000", "list": rows}, "00126380", "005930", 2023)
    assert block is None
    assert reason == "principal_period_unverified"


def test_current_blank_is_never_filled_from_previous_column(bf):
    rows = _principal_rows(year=2025, values=(None,) * 3)
    for row in rows:
        row.update(frmtrm_dt="2024.01.01 ~ 2024.12.31", frmtrm_amount="9999999")
    block, source, reason = bf._principal_annual_block({"status": "000", "list": rows}, "00126380", "005930", 2025)
    assert block is None
    assert reason == "source_period_blank"
    assert source["amount_column"] == "thstrm_amount"


@pytest.mark.parametrize("change", ["conflict", "partial", "different_filing", "invalid_amount"])
def test_principal_does_not_mix_or_hide_ambiguous_blocks(bf, change):
    rows = _principal_rows()
    if change == "conflict":
        rows.append({**rows[0], "thstrm_amount": "101"})
    elif change == "partial":
        rows[0]["thstrm_amount"] = "-"
        rows += _principal_rows(scope="OFS")
    elif change == "different_filing":
        rows[-1]["rcept_no"] = "20250324000028"
    else:
        rows[0]["thstrm_amount"] = "N/A"
    assert bf._principal_annual_block({"status": "000", "list": rows}, "00126380", "005930", 2023)[0] is None


@pytest.mark.parametrize("values", [(0, -20, 0), (None,) * 3])
def test_recovery_persists_whole_block_or_visible_source_gap(bf, monkeypatch, values):
    _write(bf, rows=[_row(y) for y in ALL_BUT_FIRST], cells={
        "005930|2023": {"n": 2, "status": "error", "error_count": 1}})
    monkeypatch.setattr(bf, "get_corp_code", lambda _: "00126380")
    calls = []
    monkeypatch.setattr(bf, "_fetch_fnltt_all_cached", lambda *_: calls.append("all") or '{"status":"000","list":[]}')
    monkeypatch.setattr(bf, "_get_principal_accounts", lambda *_: calls.append("principal") or {
        "status": "000", "list": _principal_rows(values=values)})
    monkeypatch.setattr(sys, "argv", ["backfill", "--start-year", "2023", "--quota-cap", "2"])
    assert bf.main() == 0
    doc = json.loads(Path(bf.MISSING_PATH).read_text())
    run = doc["_meta"]["last_run"]
    assert calls == ["all", "principal"]
    assert run["requests"] == 2 and run["error"] == 0
    assert run["requested"] == run["success"] + run["empty"] + run["error"] + run["source_gap"] + run["deferred"]
    rows = json.loads(Path(bf.OUT_PATH).read_text())["rows"]
    if values[0] is None:
        assert run["source_gap"] == 1
        cell = doc["cells"]["005930|2023"]
        assert cell["status"] == "source_blank" and cell["no_data_attempts"] == 0
        assert not bf._is_exhausted_no_data(cell)
        assert not any(r["fiscal_year"] == 2023 for r in rows)
    else:
        row = next(r for r in rows if r["fiscal_year"] == 2023)
        assert tuple(row["fundamentals"][f] for f in bf._PL_FIELDS) == values
        assert row["source"]["endpoint"] == "fnlttSinglAcnt.json"
        assert row["fs_div"] == "CFS"
        assert not doc["cells"]


def test_ofs_fallback_cannot_replace_existing_unknown_scope(bf, monkeypatch):
    old = _row(2023)
    old["fundamentals"]["net_income"] = None
    _write(bf, rows=[old, *[_row(y) for y in ALL_BUT_FIRST]])
    monkeypatch.setattr(bf, "get_corp_code", lambda _: "00126380")
    monkeypatch.setattr(bf, "_fetch_fnltt_all_cached", lambda *_: '{"status":"000","list":[]}')
    monkeypatch.setattr(bf, "_get_principal_accounts", lambda *_: {
        "status": "000", "list": _principal_rows(scope="OFS")})
    monkeypatch.setattr(sys, "argv", ["backfill", "--start-year", "2023", "--quota-cap", "2"])
    assert bf.main() == 0
    assert json.loads(Path(bf.OUT_PATH).read_text())["rows"][0] == old
    cell = json.loads(Path(bf.MISSING_PATH).read_text())["cells"]["005930|2023"]
    assert cell["last_error"] == "scope_change_unverified"
