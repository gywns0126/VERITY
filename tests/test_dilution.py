"""dilution 헬퍼 — 4개 메모리 가드 + v2.0 변환 사전 회귀 테스트."""
import pytest

from api.utils import dilution
from api.utils.dilution import (
    ContentBlocked,
    apply_grade_guard,
    apply_label_guard,
    block_ticker_content,
    brain_grade_from_score,
    dilute,
    get_principles,
    grade_label,
    load_rules,
    timestamp_label,
    translate_ai_fallback,
)


# ── 룰북 로딩 ───────────────────────────────────────────

def test_rules_loaded():
    r = load_rules(force_reload=True)
    assert r.get("version") == "2.0"
    assert len(r.get("principles") or []) == 6
    assert len(r.get("guards") or {}) == 4
    # v2.0: 11 categories (real_estate 추가)
    assert len(r.get("categories") or {}) == 11
    # 97개 항목 누적 — 카테고리 변경 시 이 숫자도 같이 검토
    assert r.get("categories_total_loaded", 0) >= 90


def test_principles_have_required_fields():
    for p in get_principles():
        assert "id" in p
        assert "rule" in p


# ── 가드 1: 검증 워터마크 — 등급 강등 ──────────────────────

def test_grade_guard_admin_unaffected():
    assert apply_grade_guard("STRONG_BUY", validated=False, channel="admin") == "STRONG_BUY"


def test_grade_guard_public_strong_buy_demoted():
    assert apply_grade_guard("STRONG_BUY", validated=False, channel="public") == "BUY"


def test_grade_guard_public_strong_avoid_demoted():
    assert apply_grade_guard("STRONG_AVOID", validated=False, channel="public") == "AVOID"


def test_grade_guard_public_validated_no_demote():
    assert apply_grade_guard("STRONG_BUY", validated=True, channel="public") == "STRONG_BUY"


def test_grade_guard_instagram_demoted():
    assert apply_grade_guard("STRONG_BUY", validated=False, channel="instagram") == "BUY"


def test_grade_guard_buy_unchanged():
    assert apply_grade_guard("BUY", validated=False, channel="public") == "BUY"


# ── 가드 1b: 검증 워터마크 — 라벨 강등 (🔥) ───────────────

def test_label_guard_fire_demoted_in_public():
    assert apply_label_guard("🔥 지금이 기회", validated=False, channel="public") == "🟢 지금이 기회"


def test_label_guard_admin_unchanged():
    assert apply_label_guard("🔥 지금이 기회", validated=False, channel="admin") == "🔥 지금이 기회"


def test_label_guard_validated_unchanged():
    assert apply_label_guard("🔥 지금이 기회", validated=True, channel="public") == "🔥 지금이 기회"


# ── 가드 1c: 종목명 + 등급 조합 차단 ─────────────────────

def test_block_ticker_instagram_buy_raises():
    with pytest.raises(ContentBlocked):
        block_ticker_content("삼성전자", "BUY", validated=False, channel="instagram")


def test_block_ticker_instagram_strong_buy_raises():
    with pytest.raises(ContentBlocked):
        block_ticker_content("Apple", "STRONG_BUY", validated=False, channel="instagram")


def test_block_ticker_instagram_validated_passes():
    block_ticker_content("삼성전자", "BUY", validated=True, channel="instagram")  # no raise


def test_block_ticker_admin_channel_passes():
    block_ticker_content("삼성전자", "BUY", validated=False, channel="admin")  # no raise


def test_block_ticker_watch_grade_passes():
    block_ticker_content("삼성전자", "WATCH", validated=False, channel="instagram")  # WATCH 는 차단 대상 아님


def test_block_ticker_no_name_passes():
    block_ticker_content(None, "BUY", validated=False, channel="instagram")  # 종목명 없으면 통과


# ── 가드 2: 시점 표현 ─────────────────────────────────────

def test_timestamp_yfinance_with_date():
    assert timestamp_label("yfinance", "2026-04-25") == "(2026-04-25 종가 기준)"


def test_timestamp_yfinance_without_date():
    assert timestamp_label("yfinance") == "(실시간 또는 가장 최근 거래일 기준)"


def test_timestamp_fred_with_date():
    assert timestamp_label("fred", "2026-04-24") == "(2026-04-24 종가 기준)"


def test_timestamp_fred_without_date():
    assert timestamp_label("fred") == "(지난 거래일 종가 기준)"


def test_timestamp_ecos():
    assert "한국은행" in timestamp_label("ecos")
    assert "2026-04" in timestamp_label("ecos", "2026-04-15")


def test_timestamp_no_source():
    assert timestamp_label(None) == ""
    assert timestamp_label("") == ""


# ── 가드 3: AI fallback 변환 ──────────────────────────────

def test_fallback_translate_generic_message():
    assert translate_ai_fallback("AI 분석 일시 불가") == "오늘 분석을 다시 검토 중입니다"


def test_fallback_translate_json_parse_fail_hidden():
    assert translate_ai_fallback("json_parse_failed") is None


def test_fallback_translate_skip_hidden():
    assert translate_ai_fallback("분석 스킵") is None


def test_fallback_translate_underscore_error_hidden():
    """_error 로 시작하는 디버깅 필드는 사용자 노출 절대 금지."""
    assert translate_ai_fallback("_error: RuntimeError") is None


def test_fallback_translate_none_passthrough():
    assert translate_ai_fallback(None) is None
    assert translate_ai_fallback("") is None


# ── 가드 4: cross-reference 일관성 ────────────────────────

def test_cross_reference_section_present():
    r = load_rules()
    crf = r.get("guards", {}).get("cross_reference_consistency")
    assert crf is not None
    assert "rules" in crf
    assert len(crf["rules"]) > 0


# ── dilute 변환 (룰 비어있는 상태에서도 fallback 작동) ───

def test_dilute_unknown_term_fallback():
    assert dilute("UNKNOWN_TERM") == "UNKNOWN_TERM"
    assert dilute("UNKNOWN_TERM", 42) == "UNKNOWN_TERM 42"


def test_dilute_empty_term():
    assert dilute("") == ""
    assert dilute(None) == ""


# ── v2.0 변환 사전 회귀 ─────────────────────────────────

class TestV2MarketIndicators:
    def test_vix_safe_range(self):
        out = dilute("VIX", 12)
        assert "긴장 온도계" in out
        assert "안정" in out

    def test_vix_warning(self):
        out = dilute("VIX", 28)
        assert "주의" in out

    def test_vix_danger(self):
        out = dilute("VIX", 40)
        assert "위험" in out


class TestV2Valuation:
    def test_per_cheap(self):
        out = dilute("PER", 8)
        assert "저렴" in out

    def test_per_expensive(self):
        out = dilute("PER", 35)
        assert "비싼 편" in out

    def test_pbr_undervalued(self):
        out = dilute("PBR", 0.7)
        assert "저평가" in out


class TestV2DebtRatioSectorAware:
    """부채비율 섹터 분기 — feedback_sector_aware_thresholds 정책 핵심."""

    def test_general_normal(self):
        assert "보통" in dilute("부채비율", 80)

    def test_general_dangerous(self):
        assert "위험" in dilute("부채비율", 250)

    def test_financial_normal_range(self):
        """은행/보험 350% — 정상 운영 범위. 일반 기준이면 위험."""
        out = dilute("부채비율", 350, sector="financial")
        assert "정상 운영" in out
        assert "재무 구조" in out

    def test_financial_excessive(self):
        out = dilute("부채비율", 700, sector="financial")
        assert "과도한 레버리지" in out

    def test_construction_warning(self):
        out = dilute("부채비율", 350, sector="construction")
        assert "주의" in out
        assert "업종 특성" in out

    def test_aviation_warning(self):
        out = dilute("부채비율", 400, sector="aviation_shipping")
        assert "주의" in out


class TestV2BrainGrades:
    """v2.0 임계: STRONG_BUY 75+ / BUY 60-74 / WATCH 45-59 / CAUTION 30-44 / AVOID 30↓"""

    def test_strong_buy_at_85(self):
        assert brain_grade_from_score(85) == "STRONG_BUY"

    def test_buy_at_70(self):
        assert brain_grade_from_score(70) == "BUY"

    def test_watch_at_50(self):
        assert brain_grade_from_score(50) == "WATCH"

    def test_caution_at_38(self):
        assert brain_grade_from_score(38) == "CAUTION"

    def test_avoid_at_20(self):
        assert brain_grade_from_score(20) == "AVOID"

    def test_none_defaults_watch(self):
        assert brain_grade_from_score(None) == "WATCH"

    def test_grade_label_includes_icon(self):
        assert "🟢" in grade_label("BUY")
        assert "🔴" in grade_label("AVOID")


class TestV2Aliases:
    def test_alias_returns_same_label(self):
        # us_10y alias 작동
        assert dilute("us_10y", 4.2) == dilute("10년 국채 금리", 4.2)
        # debt_ratio alias 작동
        assert dilute("debt_ratio", 80) == dilute("부채비율", 80)


class TestV2RealEstate:
    def test_jeonse_ratio_warning(self):
        out = dilute("전세가율", 85)
        assert "갭투자" in out

    def test_dsr_safe(self):
        out = dilute("DSR", 35)
        assert "여유" in out
