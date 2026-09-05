from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_us_holdings_are_labeled_as_krw_converted_values():
    src = read("operator-web/app/components/HoldingsTable.tsx")
    assert "환산평단" in src
    assert 'const fmtPx = `${Math.round(px).toLocaleString()}원`' in src
    assert '`$${px.toFixed(2)}`' not in src


def test_capital_below_tier_one_does_not_fall_through_to_tier_six():
    src = read("operator-web/app/components/CapitalPathCard.tsx")
    assert "totalAsset < TIERS[0].min_krw" in src


def test_verification_percent_unit_and_sample_contract():
    src = read("operator-web/app/components/VerificationPanel.tsx")
    assert "sample_14d" in src
    assert "hit_rate_14d_ci95" in src
    assert "(v * 100).toFixed" not in src


def test_macro_uses_current_investor_portfolio_shape():
    src = read("operator-web/app/macro/page.tsx")
    assert "Array.isArray(w.top_holdings)" in src
    assert "w.holdings_capped || w.holdings" not in src


def test_workspace_owns_the_single_selected_ticker():
    workspace = read("operator-web/app/components/Workspace.tsx")
    panel = read("operator-web/app/components/StockFactsPanel.tsx")
    assert '<StockFactsPanel ticker={ticker} />' in workspace
    assert "StockFactsPanel({ ticker }" in panel
