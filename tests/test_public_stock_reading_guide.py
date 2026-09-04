from pathlib import Path


COMPONENT = Path("framer-components/public-probe/PublicStockChangeCenter.tsx")


def source() -> str:
    return COMPONENT.read_text(encoding="utf-8")


def test_stock_guide_is_optional_and_accessible() -> None:
    text = source()
    assert 'const [guideOpen, setGuideOpen] = useState(false)' in text
    assert 'aria-controls="stock-reading-guide"' in text
    assert 'id="stock-reading-guide"' in text
    assert 'aria-labelledby="stock-reading-guide-title"' in text


def test_stock_guide_teaches_sequence_and_cautions() -> None:
    text = source()
    for phrase in (
        "최근 변화",
        "사업 변화",
        "고용과 실적",
        "인과관계로 해석하지 않습니다",
        "자본조달과 희석",
        "실제 발행·전환을 구분",
    ):
        assert phrase in text


def test_stock_guide_preserves_ticker_in_next_routes() -> None:
    text = source()
    assert '`/disclosure?q=${encodeURIComponent(ticker)}`' in text
    assert '`/glassbox?q=${encodeURIComponent(ticker)}`' in text
    assert 'href="/nest"' in text


def test_stock_guide_adds_no_network_request() -> None:
    text = source()
    guide = text[
        text.index('aria-controls="stock-reading-guide"'):
        text.index('{missing.length > 0')
    ]
    assert "fetch(" not in guide


def test_stock_guide_has_no_added_outline() -> None:
    text = source()
    guide = text[
        text.index('aria-controls="stock-reading-guide"'):
        text.index('{missing.length > 0')
    ]
    assert 'border: `1px solid ${C.line}`' not in guide
    assert 'borderTop: `1px solid ${C.line}`' not in guide
