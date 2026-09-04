from pathlib import Path


CHART = Path("framer-components/public-probe/PublicLiveChartRouter.tsx")


def test_available_ranges_are_interactive_and_do_not_offer_empty_five_year_data() -> None:
    body = CHART.read_text(encoding="utf-8")
    assert 'type RangeKey = "1W" | "1M"' in body
    assert '["1W", "1주", allPoints.length >= 5]' in body
    assert '["1M", "1개월", allPoints.length >= 2]' in body
    assert 'onClick={() => enabled && setRange(key)}' in body
    assert '? "1주 전"' in body
    assert '"repeat(auto-fit, minmax(112px, 1fr))"' in body
    assert '"5Y"' not in body
    assert '"5년"' not in body


def test_chart_exposes_price_context_and_extrema_markers() -> None:
    body = CHART.read_text(encoding="utf-8")
    for label in (
        "기간 최고가",
        "기간 최저가",
        "시작가",
        "현재가",
        "기간 변동률",
        "평균가",
        "관측 수",
    ):
        assert label in body
    assert 'name: "최고"' in body
    assert 'name: "최저"' in body
    assert "Math.max(...points.map" in body
    assert "Math.min(...points.map" in body
