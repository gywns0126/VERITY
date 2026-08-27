"""종목 뉴스 엔티티 경계 계약."""
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "vercel-api" / "api" / "stock_news.py"
SPEC = importlib.util.spec_from_file_location("stock_news_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
NEWS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NEWS)


def test_short_korean_name_rejects_longer_unrelated_word():
    assert NEWS._entity_matches_title(
        "쿠쿠홀딩스", "쿠쿠", "쿠쿠홀딩스 밥솥 판매 확대"
    )
    assert NEWS._name_in_title("쿠쿠", "쿠쿠가 신제품을 출시")
    assert not NEWS._name_in_title("쿠쿠", "첼시 쿠쿠렐라 재계약")


def test_short_korean_core_is_not_used_for_broad_search():
    assert not NEWS._safe_search_core("쿠쿠")
    assert NEWS._safe_search_core("삼성전자")
    assert NEWS._safe_search_core("JYP")


def test_entity_match_allows_exact_or_disclosure_only():
    assert NEWS._entity_matches_title("쿠쿠홀딩스", "쿠쿠", "쿠쿠홀딩스 실적 발표")
    assert NEWS._entity_matches_title("쿠쿠홀딩스", "쿠쿠", "쿠쿠, 신제품 밥솥 출시")
    assert not NEWS._entity_matches_title("쿠쿠홀딩스", "쿠쿠", "쿠쿠렐라 이적설")
    assert NEWS._entity_matches_title(
        "쿠쿠홀딩스", "쿠쿠", "생활가전 기업 공급계약", {"title": "단일판매계약"}
    )
