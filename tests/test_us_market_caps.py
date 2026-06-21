"""us_market_caps wire 검증 — load_market_caps + load_us_externals merge 우선순위.

[[project_us_financials_sec_edgar]] (a) market_cap wire. 네트워크 없음 (tmp 파일 monkeypatch).
yfinance fast_info fetch 자체는 [[feedback_real_call_over_llm_consensus]] 로 실호출 검증함 (테스트 X).
"""
from __future__ import annotations

import json

import pytest

from api.builders import us_financials_builder as b


def _write_caps(tmp_path, caps: dict):
    p = tmp_path / "us_market_caps.json"
    p.write_text(json.dumps({"market_caps": caps}), encoding="utf-8")
    return p


def _write_portfolio(tmp_path, recs: list):
    p = tmp_path / "portfolio.json"
    p.write_text(json.dumps({"recommendations": recs}), encoding="utf-8")
    return p


def test_load_market_caps_filters_invalid(tmp_path, monkeypatch):
    caps = {"AAPL": 4.0e12, "BAD": "x", "ZERO": 0, "NEG": -5, "NAN": float("nan")}
    monkeypatch.setattr(b, "MARKET_CAPS_PATH", _write_caps(tmp_path, caps))
    out = b.load_market_caps()
    assert out == {"AAPL": 4.0e12}  # 비숫자/0/음수/NaN 제거


def test_load_market_caps_absent_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(b, "MARKET_CAPS_PATH", tmp_path / "missing.json")
    assert b.load_market_caps() == {}


def test_externals_sp1500_cap_wired(tmp_path, monkeypatch):
    # sp1500-only ticker(추천 밖)도 market_cap 받음 = 1490 size 미상 gap 닫힘.
    monkeypatch.setattr(b, "MARKET_CAPS_PATH", _write_caps(tmp_path, {"AAON": 11.2e9}))
    monkeypatch.setattr(b, "PORTFOLIO_PATH", _write_portfolio(tmp_path, []))
    ext = b.load_us_externals()
    assert ext["AAON"]["market_cap"] == 11.2e9
    assert ext["AAON"]["div_yield"] is None  # 배당은 portfolio 만 (1500 후속 큐)


def test_externals_portfolio_overlay_precedence(tmp_path, monkeypatch):
    # 추천 15 = 라이브 market_cap 우선 + div_yield overlay. caps 파일값을 portfolio 가 덮음.
    monkeypatch.setattr(b, "MARKET_CAPS_PATH", _write_caps(tmp_path, {"MSFT": 3.0e12}))
    monkeypatch.setattr(b, "PORTFOLIO_PATH", _write_portfolio(
        tmp_path, [{"ticker": "MSFT", "market_cap": 3.5e12, "div_yield": 0.7}]))
    ext = b.load_us_externals()
    assert ext["MSFT"]["market_cap"] == 3.5e12   # portfolio 라이브 우선
    assert ext["MSFT"]["div_yield"] == 0.7


def test_externals_portfolio_null_cap_falls_back_to_caps_file(tmp_path, monkeypatch):
    # portfolio 에 종목 있으나 market_cap 결손 → caps 파일값 유지 (덮어쓰며 None 만들지 않음).
    monkeypatch.setattr(b, "MARKET_CAPS_PATH", _write_caps(tmp_path, {"CRM": 2.5e11}))
    monkeypatch.setattr(b, "PORTFOLIO_PATH", _write_portfolio(
        tmp_path, [{"ticker": "CRM", "market_cap": None, "div_yield": None}]))
    ext = b.load_us_externals()
    assert ext["CRM"]["market_cap"] == 2.5e11
