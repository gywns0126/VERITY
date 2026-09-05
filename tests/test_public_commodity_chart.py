from pathlib import Path


CHART = Path("framer-components/public-probe/PublicLiveChartRouter.tsx")


def test_available_ranges_match_the_stock_chart_and_use_real_history() -> None:
    body = CHART.read_text(encoding="utf-8")
    assert 'type RangeKey = "1M" | "3M" | "6M" | "1Y"' in body
    for key in ("1M", "3M", "6M", "1Y"):
        assert f'["{key}", "{key}"]' in body
    assert 'onClick={() => enabled && setRange(key)}' in body
    assert "history_daily" in body
    assert "rangeEnabled(key)" in body
    assert '"5Y"' not in body
    assert '"5년"' not in body


def test_chart_exposes_price_context_and_extrema_markers() -> None:
    body = CHART.read_text(encoding="utf-8")
    for label in (
        "기간 최고종가",
        "기간 최저종가",
        "기간 수익률",
        "고점 대비",
        "최대 낙폭",
        "연환산 변동성",
        "상승 관측 비중",
        "평균 종가",
        "관측 수",
    ):
        assert label in body
    assert 'name: "최고"' in body
    assert 'name: "최저"' in body
    assert "Math.max(...points.map" in body
    assert "Math.min(...points.map" in body


def test_chart_card_uses_the_same_outer_geometry_as_the_stock_chart() -> None:
    body = CHART.read_text(encoding="utf-8")
    assert 'padding: "0 0 4px"' in body
    assert "borderRadius: 16" in body
    assert "padding: 4" in body
    assert 'padding: "10px 10px 0"' in body
    assert 'padding: "0 10px"' in body
    assert 'aspectRatio: "1.75 / 1"' in body
    assert "height - 250" not in body


def test_chart_does_not_coerce_missing_values_to_zero_and_explains_disabled_ranges() -> None:
    body = CHART.read_text(encoding="utf-8")
    assert 'value === null || value === undefined || value === ""' in body
    assert "nextUnavailableRange" in body
    assert "개부터 사용할 수 있어요" in body
