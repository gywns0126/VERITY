"""
wide_scan step (a) 회귀 테스트.

검증:
- DISABLED 모드: 호출 자체 skip (skipped=True), jsonl 미적재
- SHADOW 모드: jsonl 1줄 적재 + decision 영향 0 보장
- 7차원 stub 함수 import 가능 (step b 진입 전 시그니처 고정)
- F-Score / Altman Z stub 함수 import 가능 (step c 진입 전 시그니처 고정)

메모리 원칙 5 (회귀 테스트 의무) 정합.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sample_stocks() -> list[dict]:
    """get_all_stock_data 결과 흉내 — 5종목."""
    return [
        {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "currency": "KRW",
         "price": 70000, "per": 12.5, "pbr": 1.3, "roe": 12.0, "debt_ratio": 25.0},
        {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI", "currency": "KRW",
         "price": 200000, "per": 15.0, "pbr": 1.8, "roe": 15.0, "debt_ratio": 35.0},
        {"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "currency": "USD",
         "price": 180.0, "per": 28.0, "pbr": 5.5, "roe": 150.0, "debt_ratio": 200.0},
        {"ticker": "316140", "name": "우리금융지주", "market": "KOSPI", "currency": "KRW",
         "price": 13000, "per": 6.0, "pbr": 0.5, "roe": 8.0, "debt_ratio": 80.0},
        {"ticker": "251270", "name": "넷마블", "market": "KOSPI", "currency": "KRW",
         "price": 43000, "per": 0, "pbr": 1.0, "roe": -5.0, "debt_ratio": 50.0},
    ]


def test_disabled_mode_skips(tmp_path, monkeypatch):
    """WIDE_SCAN_MODE=DISABLED → run_wide_scan_shadow 가 jsonl 미적재 + skipped=True."""
    log_path = tmp_path / "wide_scan_log.jsonl"
    monkeypatch.setenv("WIDE_SCAN_MODE", "DISABLED")
    # config 모듈 reload 후 wide_scan reload — env 반영 보장
    import importlib
    import api.config as _cfg
    importlib.reload(_cfg)
    import api.analyzers.wide_scan as ws
    importlib.reload(ws)
    monkeypatch.setattr(ws, "WIDE_SCAN_LOG_PATH", log_path)

    result = ws.run_wide_scan_shadow(_sample_stocks())
    assert result["mode"] == "DISABLED"
    assert result["skipped"] is True
    assert result["logged"] is False
    assert not log_path.exists(), "DISABLED 모드는 jsonl 적재 금지"


def test_shadow_mode_appends_jsonl(tmp_path, monkeypatch):
    """WIDE_SCAN_MODE=SHADOW → jsonl 1줄 append + decision 영향 0."""
    log_path = tmp_path / "wide_scan_log.jsonl"
    monkeypatch.setenv("WIDE_SCAN_MODE", "SHADOW")
    import importlib
    import api.config as _cfg
    importlib.reload(_cfg)
    import api.analyzers.wide_scan as ws
    importlib.reload(ws)
    monkeypatch.setattr(ws, "WIDE_SCAN_LOG_PATH", log_path)

    stocks = _sample_stocks()
    result = ws.run_wide_scan_shadow(stocks, run_at_iso="2026-05-10T13:00:00+09:00")

    assert result["mode"] == "SHADOW"
    assert result["skipped"] is False
    assert result["logged"] is True
    assert result["input_n"] == 5
    assert result["target_n"] == 1  # 5 × 0.22 = 1.1 → int 1
    assert result["passed_n"] == 0  # step (a) — 7차원 미구현

    # jsonl schema 검증
    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["label"] == "v0_heuristic"
    assert entry["mode"] == "SHADOW"
    assert entry["step"] == "a_infra"
    assert entry["input_n"] == 5
    assert entry["target_n"] == 1
    assert entry["ts"] == "2026-05-10T13:00:00+09:00"


def test_decision_impact_zero(tmp_path, monkeypatch):
    """SHADOW 모드 호출이 입력 stocks 리스트를 mutate 하지 않음 보장."""
    log_path = tmp_path / "wide_scan_log.jsonl"
    monkeypatch.setenv("WIDE_SCAN_MODE", "SHADOW")
    import importlib
    import api.config as _cfg
    importlib.reload(_cfg)
    import api.analyzers.wide_scan as ws
    importlib.reload(ws)
    monkeypatch.setattr(ws, "WIDE_SCAN_LOG_PATH", log_path)

    stocks = _sample_stocks()
    snapshot = json.dumps(stocks, sort_keys=True, ensure_ascii=False)
    ws.run_wide_scan_shadow(stocks)
    after = json.dumps(stocks, sort_keys=True, ensure_ascii=False)
    assert snapshot == after, "wide_scan SHADOW 가 production stocks 를 mutate 함 — decision 영향 0 위반"


def test_seven_dimension_stubs_importable():
    """step (b) 진입 전 7차원 함수 시그니처 고정 — placeholder 0.0 반환 OK."""
    from api.analyzers import wide_scan as ws
    sample = _sample_stocks()[0]
    assert ws._score_liquidity(sample) == 0.0
    assert ws._score_value(sample, sector="IT") == 0.0
    assert ws._score_profitability(sample) == 0.0
    assert ws._score_growth(sample, sector="IT") == 0.0
    assert ws._score_safety(sample) == 0.0
    assert ws._score_payout(sample) == 0.0
    assert ws._score_momentum(sample) == 0.0


def test_strong_gate_stubs_importable():
    """step (c) 진입 전 F-Score / Altman Z 시그니처 고정 — None 반환 OK."""
    from api.analyzers import wide_scan as ws
    sample = _sample_stocks()[0]
    assert ws._piotroski_f_score(sample) is None
    assert ws._altman_z_score(sample, sector="제조") is None


def test_invalid_mode_falls_back_to_disabled(monkeypatch):
    """알 수 없는 WIDE_SCAN_MODE 값 → DISABLED 강제 정합 (config 가드)."""
    monkeypatch.setenv("WIDE_SCAN_MODE", "MAYBE_LATER")
    import importlib
    import api.config as _cfg
    importlib.reload(_cfg)
    assert _cfg.WIDE_SCAN_MODE == "DISABLED"
