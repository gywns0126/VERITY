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
from datetime import date
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
    monkeypatch.setattr(bf, "_fetch_fnltt_all_cached", lambda *_args: json.dumps({"list": rows}))
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
    monkeypatch.setattr(bf, "_fetch_fnltt_all_cached", lambda *_args: '{"list":[{"sj_div":"BS","account_nm":"자본금","thstrm_amount":"100"}]}')
    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--start-year", "2023", "--quota-cap", "1"])
    assert bf.main() == 0
    output = json.loads(Path(bf.OUT_PATH).read_text())
    assert not any(row["fiscal_year"] == YEARS[0] for row in output["rows"])
    assert json.loads(Path(bf.MISSING_PATH).read_text())["cells"][f"005930|{YEARS[0]}"]["n"] == 1


@pytest.mark.parametrize("amount", ["", "-", " ", "N/A"])
def test_blank_selected_account_is_not_promoted_to_reported_zero(bf, monkeypatch, amount):
    _write(bf, rows=[_row(y) for y in ALL_BUT_FIRST])
    monkeypatch.setattr(bf, "get_corp_code", lambda _ticker: "00126380")
    raw = json.dumps({"list": [{"sj_div": "IS", "account_id": "ifrs-full_ProfitLoss",
                                "account_nm": "당기순이익", "thstrm_amount": amount}]})
    monkeypatch.setattr(bf, "_fetch_fnltt_all_cached", lambda *_args: raw)
    monkeypatch.setattr(sys, "argv", ["dart_kr_fin_backfill.py", "--start-year", "2023", "--quota-cap", "1"])
    assert bf.main() == 0
    output = json.loads(Path(bf.OUT_PATH).read_text())
    assert not any(row["fiscal_year"] == YEARS[0] for row in output["rows"])


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
