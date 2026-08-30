from pathlib import Path


COMPONENT = Path("framer-components/public-probe/PublicHoldingsTab.tsx")


def test_nest_page_title_matches_public_page_header_standard():
    source = COMPONENT.read_text(encoding="utf-8")
    title_at = source.index("나만의 둥지")
    title_block = source[title_at - 500 : title_at]
    assert "fontSize: 18" in title_block
    assert "fontWeight: 800" in title_block
    assert 'letterSpacing: "-0.4px"' in title_block
    assert "lineHeight: 1.3" in title_block
    assert "marginInline: 2" in title_block
    assert "fontSize: narrow ? 18 : 20" not in title_block


def source() -> str:
    return COMPONENT.read_text(encoding="utf-8")


def test_nest_guide_is_optional_and_accessible() -> None:
    text = source()
    assert 'const [nestGuideOpen, setNestGuideOpen] = useState(false)' in text
    assert 'aria-controls="nest-reading-guide"' in text
    assert 'id="nest-reading-guide"' in text
    assert 'aria-expanded={nestGuideOpen}' in text


def test_nest_guide_covers_capital_and_experience_without_recommendation() -> None:
    text = source()
    for phrase in (
        "자본 규모보다 먼저 확인할 순서",
        "입력값·기준일·분모",
        "단일 종목·업종·지역 집중",
        "위험성향과 적합 자산을 판정하지 않습니다",
    ):
        assert phrase in text


def test_nest_guide_has_routes_and_no_outline() -> None:
    text = source()
    guide = text[text.index('aria-controls="nest-reading-guide"'):text.index('{loading ? (')]
    for path in ('"/stock"', '"/disclosure"', '"/market"'):
        assert path in guide
    assert 'border: `1px solid' not in guide
    assert 'borderTop:' not in guide
