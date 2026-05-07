"""RTMS 단지명 clustering — 단위 테스트.

검증 13 case:
  normalize_apt_name (괄호/번호/공백/특수문자 흡수)
  cluster_trades (그룹 키 + 면적 다양성 보존 + raw 예시)
  make_complex_id (안정 키)
  filter_trades_by_cluster (역추적)
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CLU_PATH = os.path.join(_REPO_ROOT, "vercel-api", "api", "landex", "_clustering.py")

_spec = importlib.util.spec_from_file_location("landex_clustering", _CLU_PATH)
clu = importlib.util.module_from_spec(_spec)
sys.modules["landex_clustering"] = clu
_spec.loader.exec_module(clu)


class TestNormalize:
    @pytest.mark.parametrize("raw,expected", [
        ("래미안 강남", "래미안강남"),
        ("래미안강남", "래미안강남"),
        ("래미안 강남(1단지)", "래미안강남"),
        ("래미안강남 1차", "래미안강남"),
        ("래미안·강남", "래미안강남"),
        ("강남 푸르지오 [104동]", "강남푸르지오"),
        ("도곡렉슬·1단지", "도곡렉슬"),
        ("힐스테이트2단지", "힐스테이트"),
        ("  은마  ", "은마"),
    ])
    def test_normalize_variants(self, raw, expected):
        assert clu.normalize_apt_name(raw) == expected

    def test_empty_returns_empty(self):
        assert clu.normalize_apt_name("") == ""
        assert clu.normalize_apt_name(None) == ""


class TestComplexId:
    def test_stable_key(self):
        cid = clu.make_complex_id("강남구", "역삼동", "래미안강남", 2015)
        assert cid == "강남구_역삼동_래미안강남_2015"

    def test_handles_missing_year(self):
        cid = clu.make_complex_id("강남구", "역삼동", "래미안강남", 0)
        assert cid.endswith("_0")

    def test_strips_spaces_in_dong(self):
        cid = clu.make_complex_id("강남구", "역 삼동", "래미안강남", 2015)
        assert " " not in cid


class TestClusterTrades:
    def _trade(self, apt, dong, area, price_won, build_year, deal_date):
        return {
            "apt": apt, "dong": dong,
            "area_m2": area, "price_won": price_won,
            "price_pyeong": price_won / (area / 3.305785),
            "build_year": build_year,
            "deal_date": deal_date, "trade_type": "중개거래",
        }

    def test_variants_collapse_to_single_cluster(self):
        trades = [
            self._trade("래미안 강남(1단지)", "역삼동", 84, 12e8, 2015, "2026-04-01"),
            self._trade("래미안강남", "역삼동", 84, 12.5e8, 2015, "2026-04-15"),
            self._trade("래미안 강남 1차", "역삼동", 114, 16e8, 2015, "2026-04-20"),
        ]
        clusters = clu.cluster_trades(trades, gu="강남구")
        assert len(clusters) == 1
        c = clusters[0]
        assert c["apt_normalized"] == "래미안강남"
        assert c["trade_count"] == 3
        assert c["area_m2"]["min"] == 84
        assert c["area_m2"]["max"] == 114
        assert len(c["apt_raw_examples"]) == 3

    def test_different_dong_separate_clusters(self):
        trades = [
            self._trade("래미안", "역삼동", 84, 12e8, 2015, "2026-04-01"),
            self._trade("래미안", "삼성동", 84, 13e8, 2015, "2026-04-01"),
        ]
        clusters = clu.cluster_trades(trades, gu="강남구")
        assert len(clusters) == 2

    def test_different_build_year_separate_clusters(self):
        trades = [
            self._trade("래미안", "역삼동", 84, 12e8, 2015, "2026-04-01"),
            self._trade("래미안", "역삼동", 84, 13e8, 2018, "2026-04-01"),
        ]
        clusters = clu.cluster_trades(trades, gu="강남구")
        assert len(clusters) == 2

    def test_empty_apt_skipped(self):
        trades = [
            self._trade("", "역삼동", 84, 12e8, 2015, "2026-04-01"),
            self._trade("래미안", "역삼동", 84, 12e8, 2015, "2026-04-01"),
        ]
        clusters = clu.cluster_trades(trades, gu="강남구")
        assert len(clusters) == 1
        assert clusters[0]["apt_normalized"] == "래미안"

    def test_sort_by_trade_count_desc(self):
        trades = [
            self._trade("작은단지", "역삼동", 84, 10e8, 2010, "2026-04-01"),
            self._trade("큰단지", "역삼동", 84, 12e8, 2015, "2026-04-01"),
            self._trade("큰단지", "역삼동", 84, 12e8, 2015, "2026-04-02"),
            self._trade("큰단지", "역삼동", 84, 12e8, 2015, "2026-04-03"),
        ]
        clusters = clu.cluster_trades(trades, gu="강남구")
        assert clusters[0]["apt_normalized"] == "큰단지"
        assert clusters[0]["trade_count"] == 3
        assert clusters[1]["apt_normalized"] == "작은단지"

    def test_deal_date_range(self):
        trades = [
            self._trade("래미안", "역삼동", 84, 12e8, 2015, "2026-04-01"),
            self._trade("래미안", "역삼동", 84, 12e8, 2015, "2026-04-20"),
            self._trade("래미안", "역삼동", 84, 12e8, 2015, "2026-04-10"),
        ]
        c = clu.cluster_trades(trades, gu="강남구")[0]
        assert c["latest_deal_date"] == "2026-04-20"
        assert c["oldest_deal_date"] == "2026-04-01"


class TestFilterTradesByCluster:
    def test_roundtrip(self):
        trades = [
            {"apt": "래미안 강남(1단지)", "dong": "역삼동", "build_year": 2015,
             "area_m2": 84, "price_won": 12e8, "price_pyeong": 47e6, "deal_date": "2026-04-01"},
            {"apt": "래미안강남", "dong": "역삼동", "build_year": 2015,
             "area_m2": 114, "price_won": 16e8, "price_pyeong": 46e6, "deal_date": "2026-04-15"},
            {"apt": "은마", "dong": "대치동", "build_year": 1979,
             "area_m2": 76, "price_won": 22e8, "price_pyeong": 95e6, "deal_date": "2026-04-10"},
        ]
        clusters = clu.cluster_trades(trades, gu="강남구")
        target = next(c for c in clusters if c["apt_normalized"] == "래미안강남")
        members = clu.filter_trades_by_cluster(trades, target)
        assert len(members) == 2
        assert all(m.get("dong") == "역삼동" for m in members)
