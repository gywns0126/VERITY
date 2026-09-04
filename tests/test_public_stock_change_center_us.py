from pathlib import Path


COMPONENT = Path("framer-components/public-probe/PublicStockChangeCenter.tsx")


def source() -> str:
    return COMPONENT.read_text(encoding="utf-8")


def test_us_change_center_uses_existing_per_ticker_apis():
    body = source()
    assert "if (!isKrTicker(ticker))" in body
    assert "/api/stock_slice?ticker=" in body
    assert "/api/verity/us-forensics?ticker=" in body
    assert "미국 종목 변화 데이터를 불러오지 못했습니다." in body


def test_us_change_center_exposes_fact_sections_and_source_dates():
    body = source()
    for label in (
        "미국 종목 변화 센터",
        "최근 연간 실적 변화",
        "최근 SEC 공시",
        "시장 참여자·포지션 변화",
        "소스 생성 시각",
    ):
        assert label in body
    for source_label in ("Form 4", "13D/G", "13F", "Short", "Form 144"):
        assert source_label in body
    assert "표시 소스 {hit}/8" in body
    assert "해당 사실이 없다는 뜻은 아닙니다." in body


def test_form144_is_labeled_as_notice_not_execution():
    body = source()
    assert "sections.form144" in body
    assert "Form 144 매도 예정 신고" in body
    assert "체결 확인이 아닌 매도 예정 신고이며 미집행될 수 있습니다." in body


def test_missing_numeric_values_do_not_render_as_zero():
    body = source()
    guard = 'value === null || value === undefined || value === ""'
    assert body.count(guard) >= 4


def test_kr_center_shows_content_dates_not_only_build_time():
    body = source()
    assert "데이터 기준일" in body
    assert "생성 시각이 아니라 각 원천 내용의 기준일입니다." in body
    for label in ("가격·시장", "사업", "고용", "연간 실적", "자본"):
        assert label in body
