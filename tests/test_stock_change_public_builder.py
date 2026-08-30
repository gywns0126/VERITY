from api.builders.stock_change_public_builder import (
    _business_comparison,
    _employment_performance,
    _market_changes,
)


def test_market_changes_keeps_dates_and_numeric_delta():
    out = _market_changes(
        [
            {"ts": "2026-08-26T16:00:00+09:00", "price": 100, "roe": None},
            {"ts": "2026-08-27T16:00:00+09:00", "price": 110, "roe": None},
        ]
    )
    assert out["status"] == "changed"
    assert out["as_of"] == "2026-08-27"
    assert out["previous_as_of"] == "2026-08-26"
    assert out["fields"] == [
        {
            "key": "price",
            "label": "가격",
            "before": 100.0,
            "after": 110.0,
            "delta": 10.0,
            "delta_pct": 10.0,
        }
    ]


def test_business_comparison_reports_added_and_removed_sentences():
    previous = {
        "fiscal_year": "2024",
        "filed_at": "20250320",
        "text": "회사는 반도체 장비를 제조합니다. 국내 고객에게 판매합니다.",
    }
    current = {
        "fiscal_year": "2025",
        "filed_at": "20260320",
        "text": "회사는 반도체 장비를 제조합니다. 해외 고객 비중이 늘었습니다.",
    }
    out = _business_comparison(current, previous)
    assert out["status"] == "changed"
    assert out["added"] == ["해외 고객 비중이 늘었습니다."]
    assert out["removed"] == ["국내 고객에게 판매합니다."]


def test_employment_performance_keeps_independent_periods():
    out = _employment_performance(
        "005930",
        {"jnngp_cnt": 110, "hire": 3, "leave": 1, "net": 2},
        {"005930": {"202506": {"cnt": 100}}},
        "202606",
        [
            {"year": 2024, "revenue": 1000, "op": 100},
            {"year": 2025, "revenue": 1200, "op": 90},
        ],
    )
    assert out["employment"]["growth_pct"] == 10.0
    assert out["performance"]["revenue_growth_pct"] == 20.0
    assert out["performance"]["operating_profit_growth_pct"] == -10.0
    assert out["relationship"] == "mixed_direction"
