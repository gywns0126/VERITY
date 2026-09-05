from pathlib import Path


COMPONENT = Path("framer-components/public-probe/PublicStockDetailUS.tsx")


def source() -> str:
    return COMPONENT.read_text(encoding="utf-8")


def test_us_detail_uses_single_per_ticker_forensics_request():
    body = source()
    assert "/api/verity/us-forensics?ticker=" in body
    assert "encodeURIComponent(code)" in body
    assert "fetch(props.shortUrl" not in body
    assert "fetch(props.holdUrl" not in body
    assert "fetch(props.forensicUrl" not in body


def test_us_detail_exposes_all_six_fact_sections_and_coverage():
    body = source()
    for key in (
        '"insider"',
        '"holdings"',
        '"smart_money"',
        '"short_interest"',
        '"disclosure_forensics"',
        '"form144"',
    ):
        assert key in body
    for label in (
        "내부자 실제 거래",
        "내부자 매도 예정",
        "기관 분기 보유",
        "공매도 잔고",
        "5%+ 대량보유",
        "8-K 이력",
    ):
        assert label in body
    assert "연결 {sourceHit}/{sourceKeys.length}" in body
    assert "현재 미조회 {unavailable.length}개" in body


def test_us_detail_teaches_timing_and_interpretation_limits():
    body = source()
    for sentence in (
        "예정 신고 · 실제 체결 아님",
        "매도 의향 신고라 실제로 전부 체결됐다는 뜻이 아닙니다",
        "가치 변화에는",
        "순매수 금액으로 읽지 않습니다",
        "공매도 잔고는 사실이며 방향 신호가 아닙니다",
        "분류일 뿐 위험도 판단이",
    ):
        assert sentence in body


def test_us_detail_separates_recent_8k_absence_from_collection_unknown():
    body = source()
    assert 'fx.event_state === "no_recent_8k"' in body
    assert 'fx.event_state === "unknown"' in body
    assert "SEC 원천 조회는 완료됐고 해당 기간에 제출된 8-K가 없습니다" in body
    assert "공시가 없다는 뜻이 아니라 이번 수집에서 확인되지 않은 상태" in body
    assert "recent_filings?: Recent8K[]" in body
    assert "recent8k.map" in body


def test_existing_framer_instance_props_remain_compatible():
    body = source()
    for prop in ("shortUrl", "holdUrl", "forensicUrl"):
        assert f"{prop}: string" in body
    assert "이전 Framer 인스턴스 속성 호환용" in body
