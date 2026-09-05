from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
COMPONENT_DIR = ROOT / "framer-components" / "public-probe"
RECENT_SURFACES = (
    "PublicCommodityReport.tsx",
    "PublicLiveChartRouter.tsx",
    "PublicPortfolioLab.tsx",
    "PublicStockChangeCenter.tsx",
    "PublicPageReadingGuide.tsx",
)
CANONICAL_CARD_SHADOW = "0 1px 3px rgba(0,0,0,0.04)"


def source(name: str) -> str:
    return (COMPONENT_DIR / name).read_text(encoding="utf-8")


def test_recent_public_surfaces_use_existing_card_elevation() -> None:
    for name in RECENT_SURFACES:
        assert CANONICAL_CARD_SHADOW in source(name), name

    assert "0 8px 28px" not in source("PublicCommodityReport.tsx")
    assert "0 10px 34px" not in source("PublicLiveChartRouter.tsx")
    assert "`0 8px 24px ${C.shadow}`" not in source("PublicPortfolioLab.tsx")


def test_recent_public_surfaces_use_existing_weight_scale() -> None:
    noncanonical_weight = re.compile(r"fontWeight:\s*(?:750|850|900)\b")
    for name in RECENT_SURFACES:
        assert not noncanonical_weight.search(source(name)), name


def test_recent_public_surfaces_keep_existing_geometry_contract() -> None:
    commodity = source("PublicCommodityReport.tsx")
    guide = source("PublicPageReadingGuide.tsx")
    change_center = source("PublicStockChangeCenter.tsx")

    assert "borderRadius: 16, padding: narrow ? 14 : 18" in commodity
    assert 'padding: "0 clamp(12px, 2vw, 18px)"' in guide
    assert "borderRadius: 16, padding: 16" in change_center
