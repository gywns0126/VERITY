import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEWS_PATH = ROOT / "vercel-api" / "api" / "stock_news.py"
SPEC = importlib.util.spec_from_file_location("stock_news_api", NEWS_PATH)
NEWS = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(NEWS)

EXPECTED_CODES = {
    "CMD_GOLD",
    "CMD_SILVER",
    "CMD_COPPER",
    "CMD_WTI",
    "CMD_BRENT",
    "CMD_NATGAS",
    "CMD_CORN",
    "CMD_WHEAT",
    "CMD_SOYBEAN",
    "CMD_COFFEE",
    "CMD_SUGAR",
    "CMD_COTTON",
}


def test_commodity_topic_denominator_is_12():
    assert set(NEWS.COMMODITY_TOPICS) == EXPECTED_CODES


def test_commodity_news_filters_unrelated_titles(monkeypatch):
    naver = [
        {
            "title": "국제 금값, 달러 약세에 상승",
            "url": "https://example.com/gold",
            "source": "연합뉴스",
            "datetime": "2026.09.01 01:00",
        },
        {
            "title": "국내 증시 마감",
            "url": "https://example.com/market",
            "source": "한국경제",
            "datetime": "2026.09.01 02:00",
        },
    ]
    google = [
        {
            "title": "Gold futures edge higher",
            "url": "https://example.com/gold-en",
            "source": "Reuters",
            "datetime": "2026.09.01 03:00",
        }
    ]
    monkeypatch.setattr(NEWS, "_fetch_search_api", lambda *_args, **_kwargs: naver)
    monkeypatch.setattr(NEWS, "_fetch_google_news", lambda *_args, **_kwargs: google)

    items = NEWS.fetch_commodity_news("CMD_GOLD")

    assert len(items) == 2
    assert all(item["category"] == "가격·시장" for item in items)
    assert all(item["related_disclosure"] is None for item in items)
    assert all("증시 마감" not in item["title"] for item in items)


def test_framer_surfaces_cover_same_commodity_codes():
    chart = (
        ROOT
        / "framer-components"
        / "public-probe"
        / "PublicLiveChartRouter.tsx"
    ).read_text()
    news = (ROOT / "framer-components" / "public-probe" / "PublicStockNews.tsx").read_text()
    for code in EXPECTED_CODES:
        assert code in chart
        assert code in news


def test_report_router_yields_to_commodity_report():
    router = (
        ROOT / "framer-components" / "public-probe" / "PublicReportRouter.tsx"
    ).read_text()
    assert 'test(ticker)) return <Suspense' in router
    assert 'if (!/^CMD_/.test(ticker))' in router


def test_stock_only_surfaces_hide_direct_commodities():
    paths = [
        "PublicStockChangeCenter.tsx",
        "PublicStockDetailKR.tsx",
        "PublicStockDetailUS.tsx",
        "PublicEventHistory.tsx",
        "PublicCompanyReports.tsx",
        "PublicDividendHistory.tsx",
        "PublicStockBrief.tsx",
    ]
    for name in paths:
        text = (ROOT / "framer-components" / "public-probe" / name).read_text()
        assert 'startsWith("CMD_")' in text or "/^CMD_/" in text, name
