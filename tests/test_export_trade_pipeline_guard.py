# -*- coding: utf-8 -*-
"""export_trade 파이프라인 전량 실패 가드 + 단계 계측 (#46).

🚨 옛 코드는 세 가지가 겹쳐 있었다.
   ① 매핑 0건이어도 stocks=[] 인 trade_analysis.json 을 정상 종료로 저장 —
      신선도 보드는 mtime 만 보고 통과시킨다.
   ② __main__ 이 반환값을 버려서 어떤 실패든 exit 0.
   ③ 단계별 소요가 안 남아 30분 timeout(8/4·8/5·8/6 cancelled) 원인을 특정 못 했다.

   여기는 증분 피드가 아니라 **입력이 보장된 스냅샷**이다(1단계가 종목을 확보하지
   못하면 이미 raise). 그래서 산출 0건 = 사고로 판정한다.
   [[feedback_silent_total_failure_guard]] · [[feedback_diagnose_before_fix_jsonl_n_check]]
"""
from __future__ import annotations

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.workflows import export_trade_pipeline as etp  # noqa: E402


def _stock(name="테스트종목"):
    return types.SimpleNamespace(name=name, ticker="000000", trademoney_million_krw=1234)


@pytest.fixture
def _wired(monkeypatch, tmp_path):
    monkeypatch.setattr(etp, "HSCODE_MAPPING_PATH", str(tmp_path / "hs.json"))
    monkeypatch.setattr(etp, "TRADE_ANALYSIS_PATH", str(tmp_path / "trade_analysis.json"))
    monkeypatch.setattr(etp, "PUBLIC_DATA_API_KEY", "")
    monkeypatch.setattr(etp, "scan_top_trading_value", lambda top_n: [_stock()])
    return tmp_path


def test_mapping_total_failure_raises_and_skips_output(_wired, monkeypatch):
    """1단계는 종목을 확보했는데 매핑 0건 = Gemini 전량 실패."""
    monkeypatch.setattr(etp, "map_stocks_to_hscode_batch", lambda s: {})

    with pytest.raises(RuntimeError, match="HS 매핑 전량 실패"):
        etp.run_export_trade_pipeline(top_scan=1, telegram=False)

    assert not (_wired / "trade_analysis.json").exists()


def test_empty_stock_rows_is_formula_failure(_wired, monkeypatch):
    """매핑은 됐는데 종목행 0 = 데이터 부재가 아니라 산식 문제."""
    monkeypatch.setattr(etp, "map_stocks_to_hscode_batch", lambda s: {"테스트종목": {"hscode": "1"}})
    monkeypatch.setattr(etp, "build_stock_analysis", lambda m, df: [])

    with pytest.raises(RuntimeError, match="산식 문제"):
        etp.run_export_trade_pipeline(top_scan=1, telegram=False)

    assert not (_wired / "trade_analysis.json").exists()


def test_success_records_stage_seconds(_wired, monkeypatch):
    """정상 경로는 단계별 소요를 산출에 남긴다 — timeout 원인 추적용."""
    monkeypatch.setattr(etp, "map_stocks_to_hscode_batch", lambda s: {"테스트종목": {"hscode": "1"}})
    monkeypatch.setattr(etp, "build_stock_analysis", lambda m, df: [{"name": "테스트종목"}])
    monkeypatch.setattr(etp, "rank_top_export_stocks", lambda rows, top_k: [])

    out = etp.run_export_trade_pipeline(top_scan=1, telegram=False)

    assert (_wired / "trade_analysis.json").exists()
    assert set(out["stage_seconds"]) >= {"scan", "gemini_mapping", "customs", "total"}
    assert all(isinstance(v, (int, float)) for v in out["stage_seconds"].values())
