from pathlib import Path


COMPONENT = Path("framer-components/public-probe/PublicPageReadingGuide.tsx")


def source() -> str:
    return COMPONENT.read_text(encoding="utf-8")


def test_all_three_page_modes_exist() -> None:
    text = source()
    for mode in ("market", "disclosure", "nest"):
        assert f"    {mode}: {{" in text


def test_guide_is_optional_and_accessible() -> None:
    text = source()
    assert "useState(() => onCanvas || !!props.defaultOpen)" in text
    assert "aria-expanded={open}" in text
    assert 'aria-label="다음으로 볼 페이지"' in text


def test_guide_contains_reading_contract() -> None:
    text = source()
    for phrase in (
        "기준시각 + 단위 + 자금 흐름",
        "접수일 + 사건 기준일 + 정정 여부",
        "원가 분모 + 가격·환율 기준일 + 집중도",
        "위험성향과 적합 자산을 판정하지 않습니다",
    ):
        assert phrase in text


def test_guide_has_no_data_or_ai_call() -> None:
    text = source()
    for token in ("fetch(", "XMLHttpRequest", "EventSource", "WebSocket", "generateText", "streamText"):
        assert token not in text
