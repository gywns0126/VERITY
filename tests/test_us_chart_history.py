# -*- coding: utf-8 -*-
"""us_chart_history / us_chart_daily 계약 테스트.

🚨 2026-08-08 실사고: us_chart_daily 가 KIS 경로로 **전량 실패(count 0 / missing 47종목
   전부)** 하면서도 워크플로는 성공으로 끝났다. 파일 mtime 은 갱신되니 신선도 보드에는
   "0일 경과" 로 잡혔다. 없는 것보다 나쁜 실패다 — 있다고 착각하게 만든다.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.collectors import us_chart_daily as ucd  # noqa: E402
from api.collectors import us_chart_history as uch  # noqa: E402


# ── 조용한 전량 실패 방지 ──────────────────────────────────────────────────
def test_daily_raises_when_all_fail(tmp_path, monkeypatch):
    """유니버스가 있는데 한 종목도 못 받으면 exit 1 — 성공으로 끝내지 않는다."""
    monkeypatch.setattr(ucd, "OUT_PATH", str(tmp_path / "out.json"))
    monkeypatch.setattr(ucd, "_us_universe", lambda: [("AAPL", "Apple"), ("MSFT", "MS")])
    monkeypatch.setattr(ucd, "_fetch_one", lambda t, want=250: [])
    with pytest.raises(SystemExit) as e:
        ucd.collect()
    assert e.value.code == 1


def test_daily_ok_when_partial(tmp_path, monkeypatch):
    """일부 성공은 정상 — 결측만 기록한다(결측 ≠ 실패)."""
    monkeypatch.setattr(ucd, "OUT_PATH", str(tmp_path / "out.json"))
    monkeypatch.setattr(ucd, "_us_universe", lambda: [("AAPL", "Apple"), ("ZZZZ", "Bad")])
    monkeypatch.setattr(ucd, "_fetch_one",
                        lambda t, want=250: [[20260807, 1, 1, 1, 1.5, 100]] if t == "AAPL" else [])
    doc = ucd.collect()
    assert doc["count"] == 1 and doc["missing"] == ["ZZZZ"]


def test_daily_no_longer_depends_on_kis():
    """🚨 RULE 1 — 대량 US 일봉에 1일 1토큰 자원을 붙이지 않는다."""
    src = open(ucd.__file__, encoding="utf-8").read()
    body = src.split('"""', 2)[2]          # docstring(전환 사유 설명) 제외
    assert "KISBroker" not in body
    assert "kis_broker" not in body
    yml = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       ".github/workflows/us_chart_daily.yml")
    with open(yml, encoding="utf-8") as f:
        w = f.read()
    assert "KIS_APP_KEY" not in w and "KIS_SHARED_TOKEN" not in w


def test_daily_workflow_has_no_silent_skip_guard():
    """이전 결함이 '조건 미충족 → exit 0' 였다. 그 가드가 남아 있으면 안 된다."""
    yml = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       ".github/workflows/us_chart_daily.yml")
    with open(yml, encoding="utf-8") as f:
        w = f.read()
    assert "미설정 — skip" not in w


# ── 이력 레이크 ────────────────────────────────────────────────────────────
def test_history_universe_normalizes_dot_tickers(tmp_path, monkeypatch):
    """yfinance 는 BRK.B 를 BRK-B 로 쓴다."""
    assert uch._yf_symbol("BRK.B") == "BRK-B"
    assert uch._yf_symbol("AAPL") == "AAPL"


def test_history_universe_dedupes_and_sorts(tmp_path, monkeypatch):
    p = tmp_path / "u.json"
    p.write_text(json.dumps({"tickers": ["MSFT", "AAPL", "MSFT", "", "TOOLONGTICKER"]}),
                 encoding="utf-8")
    monkeypatch.setattr(uch, "UNIVERSE_PATHS", (str(p),))
    assert uch.load_universe() == ["AAPL", "MSFT"]


def test_history_skips_already_fetched(tmp_path, monkeypatch):
    """파일 존재 자체가 체크포인트 — 중단돼도 다음 run 이 이어받는다."""
    monkeypatch.setattr(uch, "OUT_DIR", str(tmp_path))
    (tmp_path / "AAPL.json").write_text("{}", encoding="utf-8")
    assert uch._have() == {"AAPL"}


def test_history_rejects_short_series(monkeypatch):
    """봉이 너무 적으면 저장하지 않는다 — 신규 상장·불량 데이터."""
    class _H:
        def __len__(self): return 10
        def iterrows(self): return iter([])
    monkeypatch.setattr("api.collectors.yfinance_safe.yf_ticker",
                        lambda t: type("T", (), {"history": lambda self, **k: _H()})())
    assert uch.fetch_one("AAPL") is None


def test_history_lake_is_gitignored():
    """🚨 5,000종목 규모 — 레포에 커밋하면 안 된다 (KR 레이크와 동일 정책)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".gitignore"), encoding="utf-8") as f:
        assert "data/us_chart_history/" in f.read()


def test_history_uses_adjusted_prices():
    """미수정 가격이 섞이면 분할일에 가짜 폭락 → 변동성·모멘텀 오염."""
    src = open(uch.__file__, encoding="utf-8").read()
    assert "auto_adjust=True" in src
