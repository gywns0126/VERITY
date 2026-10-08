from pathlib import Path
import re


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
    panel = read("operator-web/app/components/AnalysisReviewPanel.tsx")
    assert workspace.count('<AnalysisReviewPanel key={ticker} ticker={ticker} />') == 1
    assert "AnalysisReviewPanel({ ticker }" in panel
    assert '<TriSynthesisPanel' not in workspace
    assert 'window.addEventListener("verity-ticker", onTicker)' in workspace


def test_saved_review_precedes_charts_and_order_ticket():
    src = read("operator-web/app/components/Workspace.tsx")
    review = src.index('<AnalysisReviewPanel ')
    for component in ('<ProChart ', '<TVChart ', '<OrderTicket '):
        assert review < src.index(component)


def test_actual_portfolio_is_separate_from_collapsed_vams_group():
    src = read("operator-web/app/page.tsx")
    simulation = re.search(r'<details\b[^>]*data-console-simulation="v1"[^>]*>[\s\S]*?</details>', src)
    assert simulation is not None
    group = simulation.group()
    assert not re.search(r'\bopen(?:\s|=|>)', group.split('>', 1)[0])
    assert "VAMS 모의 운용 · 실제 계좌와 별개" in group
    for component in ('<AccountHud ', '<HoldingsTable ', '<Blotter ', '<PicksTable '):
        assert component in group
        assert src.count(component) == group.count(component)
    assert '<PersonalPortfolio />' not in group
    assert src.index('<PersonalPortfolio />') < simulation.start()


def test_personal_portfolio_uses_existing_ticker_selection_button():
    src = read("operator-web/app/components/PersonalPortfolio.tsx")
    assert 'import { selectTicker } from "@/lib/types"' in src
    button = re.search(r'<button\b[^>]*className="af-portfolio-ticker"[\s\S]*?</button>', src)
    assert button is not None
    assert 'type="button"' in button.group()
    assert 'aria-label=' in button.group()
    assert 'selectTicker(row.ticker, row.name)' in button.group()
