from pathlib import Path


REPORT = Path("framer-components/public-probe/PublicCommodityReport.tsx")


def test_report_covers_all_twelve_public_commodities() -> None:
    body = REPORT.read_text(encoding="utf-8")
    assert body.count('ticker: "CMD_') == 12
    for key in (
        "gold",
        "silver",
        "copper",
        "wti_oil",
        "brent",
        "natural_gas",
        "corn",
        "wheat",
        "soybean",
        "coffee",
        "sugar",
        "cotton",
    ):
        assert f'macroKey: "{key}"' in body


def test_report_joins_existing_fact_sources_without_a_new_narrative() -> None:
    body = REPORT.read_text(encoding="utf-8")
    assert "macro_snapshot.json" in body
    assert "commodity_exposure.json" in body
    assert "cross_asset_corr" in body
    assert "global_events" in body
    assert "국내 연결 기업" in body
    assert "다가오는 일정" in body
    assert "30일 상관" in body
    assert "commodity_impact.json" not in body


def test_report_only_labels_a_return_when_enough_observations_exist() -> None:
    body = REPORT.read_text(encoding="utf-8")
    assert "history.length >= 180" in body
    assert "pct(history, 21)" in body
    assert "pct(history, 65)" in body
    assert "pct(history, 131)" in body
    assert 'value === null || value === undefined || value === ""' in body
    assert "coverageNote(history.length, 180)" in body
    assert "fmtRange(quote?.low_52w, quote?.high_52w)" in body
    assert "가격 관측 범위" in body


def test_report_fetches_independent_sources_in_parallel_with_local_fallbacks() -> None:
    body = REPORT.read_text(encoding="utf-8")
    assert "Promise.all([" in body
    assert body.count(".catch(() => null)") == 2
