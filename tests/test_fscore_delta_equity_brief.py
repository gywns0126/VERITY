"""fscore_delta + equity_brief_attach unit test (2026-05-17).

회귀 방지 — 박은 인프라 변경 시 산식/load 동작 검증.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

KST = timezone(timedelta(hours=9))


# ─── fscore_delta ────────────────────────────────────────────

class TestFScoreDelta:
    def test_compute_all_deltas_positive(self):
        from api.utils.fscore_delta import compute_fscore_deltas
        cur = {"roa": 0.08, "debt_ratio": 1.2, "current_ratio": 1.5,
               "gross_margin": 0.35, "asset_turnover": 0.7}
        prior = {"roa": 0.06, "debt_ratio": 1.3, "current_ratio": 1.4,
                 "gross_margin": 0.32, "asset_turnover": 0.65}
        deltas = compute_fscore_deltas(cur, prior)
        assert deltas["delta_roa"] == pytest.approx(0.02, abs=0.001)
        assert deltas["c5_delta_leverage_negative"] is True  # 1.2 < 1.3
        assert deltas["c6_delta_current_ratio_positive"] is True  # 1.5 > 1.4
        assert deltas["c8_delta_gross_margin_positive"] is True
        assert deltas["c9_delta_asset_turnover_positive"] is True
        assert deltas["n_delta_computed"] == 5

    def test_no_prior_returns_nones(self):
        from api.utils.fscore_delta import compute_fscore_deltas
        cur = {"roa": 0.05}
        deltas = compute_fscore_deltas(cur, prior=None)
        assert deltas["delta_roa"] is None
        assert deltas["data_source"] == "no_prior"
        assert deltas["n_delta_computed"] == 0

    def test_partial_prior(self):
        from api.utils.fscore_delta import compute_fscore_deltas
        cur = {"roa": 0.08, "debt_ratio": 1.2}
        prior = {"roa": 0.06}  # debt_ratio 부재
        deltas = compute_fscore_deltas(cur, prior)
        assert deltas["delta_roa"] is not None
        assert deltas["c5_delta_leverage_negative"] is None  # prior 부재

    def test_find_yoy_prior_match(self):
        from api.utils.fscore_delta import find_yoy_prior
        snapshots = [
            {"quarter_end": "2026-03-31"},
            {"quarter_end": "2025-12-31"},
            {"quarter_end": "2025-03-31"},  # 1년 전
            {"quarter_end": "2024-12-31"},
        ]
        prior = find_yoy_prior("2026-03-31", snapshots[1:])  # 현재 분기 제외
        assert prior is not None
        assert prior["quarter_end"] == "2025-03-31"

    def test_find_yoy_prior_no_match(self):
        from api.utils.fscore_delta import find_yoy_prior
        snapshots = [{"quarter_end": "2025-12-31"}]  # 365일 ± 30일 밖
        prior = find_yoy_prior("2026-03-31", snapshots)
        assert prior is None

    def test_load_quarterly_snapshots_filter_ticker(self, tmp_path):
        from api.utils.fscore_delta import load_quarterly_snapshots
        # monkeypatch path
        import api.utils.fscore_delta as fd
        original = fd.QUARTERLY_SNAPSHOT_PATH
        try:
            jsonl = tmp_path / "snapshots.jsonl"
            jsonl.write_text(
                '{"ticker": "AAPL", "quarter_end": "2026-03-31", "roa": 0.08}\n'
                '{"ticker": "MSFT", "quarter_end": "2026-03-31", "roa": 0.10}\n'
                '{"ticker": "AAPL", "quarter_end": "2025-12-31", "roa": 0.07}\n'
            )
            fd.QUARTERLY_SNAPSHOT_PATH = jsonl
            snaps = load_quarterly_snapshots("AAPL")
            assert len(snaps) == 2
            # desc sort: 최근 부터
            assert snaps[0]["quarter_end"] == "2026-03-31"
            assert snaps[1]["quarter_end"] == "2025-12-31"
        finally:
            fd.QUARTERLY_SNAPSHOT_PATH = original


# ─── equity_brief_attach ────────────────────────────────────────

class TestEquityBriefAttach:
    def test_load_brief_not_found(self, tmp_path):
        from api.utils.equity_brief_attach import load_equity_brief
        result = load_equity_brief("NONEXISTENT", base_dir=tmp_path)
        assert result is None

    def test_load_brief_valid(self, tmp_path):
        from api.utils.equity_brief_attach import load_equity_brief
        brief_file = tmp_path / "TEST.json"
        brief_data = {
            "ticker": "TEST",
            "brief_verdict": "BUY",
            "generated_at": datetime.now(KST).isoformat(),
        }
        brief_file.write_text(json.dumps(brief_data))
        result = load_equity_brief("TEST", base_dir=tmp_path)
        assert result is not None
        assert result["brief_verdict"] == "BUY"

    def test_load_brief_stale(self, tmp_path):
        from api.utils.equity_brief_attach import load_equity_brief
        brief_file = tmp_path / "STALE.json"
        # 15일 전 = max_stale_days 10 초과
        old_date = datetime.now(KST) - timedelta(days=15)
        brief_data = {
            "ticker": "STALE",
            "brief_verdict": "BUY",
            "generated_at": old_date.isoformat(),
        }
        brief_file.write_text(json.dumps(brief_data))
        result = load_equity_brief("STALE", max_stale_days=10, base_dir=tmp_path)
        assert result is None

    def test_load_brief_skips_error_entries(self, tmp_path):
        from api.utils.equity_brief_attach import load_equity_brief
        brief_file = tmp_path / "ERR.json"
        brief_data = {
            "ticker": "ERR",
            "_error": "fetch failed",
            "generated_at": datetime.now(KST).isoformat(),
        }
        brief_file.write_text(json.dumps(brief_data))
        result = load_equity_brief("ERR", base_dir=tmp_path)
        assert result is None  # _error 박힌 entry skip

    def test_attach_us_only(self, tmp_path):
        from api.utils.equity_brief_attach import attach_briefs_to_stocks
        # 1 US (brief 있음) + 1 KR + 1 US (brief 없음)
        brief_file = tmp_path / "USABCD.json"
        brief_data = {
            "ticker": "USABCD",
            "brief_verdict": "BUY",
            "generated_at": datetime.now(KST).isoformat(),
        }
        brief_file.write_text(json.dumps(brief_data))

        stocks = [
            {"ticker": "USABCD", "market": "NYSE"},
            {"ticker": "005930", "market": "KR"},
            {"ticker": "NOBRIE", "market": "NASDAQ"},
        ]
        attached = attach_briefs_to_stocks(stocks, base_dir=tmp_path)
        assert attached == 1
        assert "equity_research_brief" in stocks[0]
        assert "equity_research_brief" not in stocks[1]  # KR 종목 skip
        assert "equity_research_brief" not in stocks[2]  # brief 없음
