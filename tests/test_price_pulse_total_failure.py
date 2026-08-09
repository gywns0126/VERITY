# -*- coding: utf-8 -*-
"""price_pulse 전량 실패 가드 (#46, P0 스트림).

🚨 price_pulse.json 은 신선도 SLA P0 다. 지수·KR·US 를 전부 못 받았는데 파일을
   새로 쓰면 내용은 빈 채로 mtime 만 갱신되어 보드가 "0분 경과" 로 통과시킨다.
   한쪽 시장만 휴장인 경우는 정상이므로 **전량 0** 일 때만 실패로 본다.
   [[feedback_silent_total_failure_guard]]
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.cron import price_pulse as pp  # noqa: E402


@pytest.fixture
def _out(tmp_path, monkeypatch):
    out = tmp_path / "price_pulse.json"
    monkeypatch.setattr(pp, "_DATA", str(tmp_path))
    monkeypatch.setattr(pp, "_OUT", str(out))
    # 입력 파일은 없는 것으로 — 티커 0, 지수만 요청된다
    monkeypatch.setattr(pp, "_load_json", lambda *a, **k: {})
    return out


def test_total_failure_returns_1_and_leaves_output_untouched(_out, monkeypatch):
    monkeypatch.setattr(pp, "fetch_yahoo_quotes", lambda syms: {})
    monkeypatch.setattr(pp, "fetch_kis_prices", lambda tks: {})

    assert pp.main() == 1
    assert not _out.exists(), "전량 실패에 산출 파일을 새로 쓰면 보드가 오통과한다"


def test_stale_output_mtime_preserved_on_total_failure(_out, monkeypatch):
    _out.write_text('{"updated_at": "old"}', encoding="utf-8")
    before = _out.stat().st_mtime_ns
    monkeypatch.setattr(pp, "fetch_yahoo_quotes", lambda syms: {})
    monkeypatch.setattr(pp, "fetch_kis_prices", lambda tks: {})

    assert pp.main() == 1
    assert _out.stat().st_mtime_ns == before


def test_partial_success_still_writes(_out, monkeypatch):
    """지수만 받아도 성공이다 — 한쪽 시장 휴장은 정상."""
    def _yahoo(syms):
        return {s: {"price": 100.0, "change_pct": 0.5} for s in syms}

    monkeypatch.setattr(pp, "fetch_yahoo_quotes", _yahoo)
    monkeypatch.setattr(pp, "fetch_kis_prices", lambda tks: {})

    assert pp.main() == 0
    assert _out.exists()
