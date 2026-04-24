"""brain_knowledge_base.json v2 + gemini_analyst 트리거 복원 검증.

배경:
  2026-04-24 이전 `_build_knowledge_context` 는 하드코드 4 프레임만 있었고
  `_load_knowledge_base()` 는 정의만 있고 호출되지 않아 30권 KB 가 사장.
  이번 개편으로 KB v2 (trigger_index + key_principles) 를 로드해 종목 지표에 따라
  동적으로 책 2~3권의 원칙을 인용하고, 지표 결손(per=0 등) 시에도 fallback 경로로
  universal_principles + 기본 책을 항상 주입하도록 복원.
"""
import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _use_real_kb_path(monkeypatch):
    """conftest autouse 가 DATA_DIR 을 tmp 로 돌려 _KNOWLEDGE_BASE_PATH 가 잘못 계산된 상태.
    gemini_analyst 의 KB 경로를 repo 실파일로 고정 + 캐시 리셋."""
    from api.analyzers import gemini_analyst as ga
    real_path = str(
        Path(__file__).resolve().parent.parent / "data" / "brain_knowledge_base.json"
    )
    monkeypatch.setattr(ga, "_knowledge_cache", None)
    monkeypatch.setattr(ga, "_KNOWLEDGE_BASE_PATH", real_path)


# ──────────────────────────────────────────────
# 1. KB 파일 구조 — v2 핵심 섹션 존재
# ──────────────────────────────────────────────

def _load_kb():
    path = Path(__file__).resolve().parent.parent / "data" / "brain_knowledge_base.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_kb_file_is_v2():
    kb = _load_kb()
    assert kb.get("version") == "2.0"
    assert kb.get("processed_count") == 17


def test_kb_preserves_v1_categories():
    kb = _load_kb()
    for cat in ("value_investing", "trend_momentum", "risk_psychology",
                "quantitative", "technical_candle", "unified_decision_framework"):
        assert cat in kb, f"v1 category {cat!r} missing"
        assert isinstance(kb[cat], dict) and kb[cat], f"{cat} empty"


def test_kb_has_new_sections():
    kb = _load_kb()
    assert "frameworks" in kb and kb["frameworks"]
    assert "trigger_index" in kb and kb["trigger_index"]
    assert "report_sources" in kb and kb["report_sources"]


def test_kb_enriched_books_have_key_principles():
    """enrich 대상 책들이 최소 3원칙씩 key_principles 가져야."""
    kb = _load_kb()
    expected = {
        ("value_investing", "graham_intelligent_investor"),
        ("value_investing", "buffett_essays"),
        ("value_investing", "bogle_common_sense"),
        ("trend_momentum", "livermore_operator"),
        ("trend_momentum", "oneil_canslim"),
        ("risk_psychology", "taleb_fooled_by_randomness"),
        ("risk_psychology", "douglas_trading_in_zone"),
        ("risk_psychology", "douglas_disciplined_trader"),
        ("risk_psychology", "mackay_madness_crowds"),
        ("risk_psychology", "elder_trading_for_living"),
        ("risk_psychology", "lowenstein_when_genius_failed"),
        ("risk_psychology", "schwager_new_market_wizards"),
        ("quantitative", "chan_algorithmic_trading"),
        ("quantitative", "shiller_irrational_exuberance"),
        ("technical_candle", "nison_candlestick_psychology"),
    }
    for cat, book_id in expected:
        book = kb[cat][book_id]
        assert "key_principles" in book, f"{cat}.{book_id} missing key_principles"
        assert len(book["key_principles"]) >= 3, (
            f"{cat}.{book_id} key_principles 최소 3 필요"
        )
        assert "trigger_conditions" in book, f"{cat}.{book_id} missing trigger_conditions"


def test_trigger_index_references_existing_books():
    """trigger_index 에 나오는 book_id 는 실제 KB 어딘가에 존재."""
    kb = _load_kb()
    all_book_ids = set()
    for cat in ("value_investing", "trend_momentum", "risk_psychology",
                "quantitative", "technical_candle"):
        all_book_ids.update(kb[cat].keys())
    for trigger, book_ids in kb["trigger_index"].items():
        for bid in book_ids:
            assert bid in all_book_ids, (
                f"trigger {trigger!r} references unknown book {bid!r}"
            )


# ──────────────────────────────────────────────
# 2. _eval_kb_triggers — 지표 → 트리거 매핑
# ──────────────────────────────────────────────

def _eval():
    from api.analyzers.gemini_analyst import _eval_kb_triggers
    return _eval_kb_triggers


def test_trigger_value_stock():
    fn = _eval()
    assert "per_lte_15_pbr_lt_1_5" in fn({"per": 10, "pbr": 1.2})


def test_trigger_growth_stock():
    fn = _eval()
    ts = fn({"consensus": {"eps_growth_yoy_pct": 35}})
    assert "eps_growth_qoq_gte_20" in ts


def test_trigger_roe_high():
    fn = _eval()
    assert "roe_gt_15" in fn({"roe": 20})


def test_trigger_bubble_overvalued():
    fn = _eval()
    ts = fn({"per": 50, "pbr": 6, "roe": 8})
    assert "per_gt_40" in ts
    assert "pbr_gt_5_roe_lt_15" in ts


def test_trigger_candle_signals():
    fn = _eval()
    ts = fn({"technical": {"signals": ["A", "B"]}})
    assert "candle_signals_gte_2" in ts


def test_trigger_drop_from_high():
    fn = _eval()
    assert "drop_from_high_gt_30" in fn({"drop_from_high_pct": -35})


def test_trigger_cape_macro():
    fn = _eval()
    assert "cape_gt_30" in fn({"_macro_cape": 32})
    assert "cape_lt_15" in fn({"_macro_cape": 12})


def test_trigger_leverage_warning():
    fn = _eval()
    assert "leverage_gt_15" in fn({"leverage_ratio": 20})


def test_trigger_fallback_on_missing_indicators():
    """per/pbr/roe 전부 0/None 이면 fallback_universal."""
    fn = _eval()
    assert fn({"per": 0, "pbr": 0, "roe": 0}) == ["fallback_universal"]
    assert fn({}) == ["fallback_universal"]


def test_trigger_ignores_bad_numeric():
    """eps_g 가 문자열 등 이상값이어도 예외 없이 무시."""
    fn = _eval()
    ts = fn({"consensus": {"eps_growth_yoy_pct": "n/a"}})
    # 예외 없이 처리되면 성공 (fallback 일 수도)
    assert isinstance(ts, list)


# ──────────────────────────────────────────────
# 3. _build_knowledge_context — 최종 출력
# ──────────────────────────────────────────────

def _build():
    from api.analyzers.gemini_analyst import _build_knowledge_context
    return _build_knowledge_context


def test_context_always_includes_universal_principles():
    """모든 종목에 공통 주입되는 기본 원칙 블록이 있어야."""
    fn = _build()
    for stock in [
        {"per": 0, "pbr": 0},           # fallback
        {"per": 10, "pbr": 1.2},         # 가치주
        {"per": 50, "pbr": 6, "roe": 8}, # 버블
    ]:
        ctx = fn(stock)
        assert "기본 원칙" in ctx, f"universal principles missing for {stock}"


def test_context_fallback_for_data_gap_stock():
    """per=0 한국 종목도 비어있지 않은 context 반환 (이전엔 "")."""
    fn = _build()
    ctx = fn({"per": 0, "pbr": 0, "roe": 0})
    assert len(ctx) > 100
    # fallback_universal → Bogle + Douglas 가 들어감
    assert "Bogle" in ctx or "Douglas" in ctx


def test_context_value_stock_cites_graham():
    fn = _build()
    ctx = fn({"per": 10, "pbr": 1.2, "roe": 10})
    assert "Graham" in ctx
    assert "안전마진" in ctx


def test_context_growth_stock_cites_canslim():
    fn = _build()
    ctx = fn({
        "per": 25, "pbr": 4, "roe": 22,
        "consensus": {"eps_growth_yoy_pct": 35},
    })
    assert "CANSLIM" in ctx or "O'Neil" in ctx


def test_context_bubble_cites_shiller_mackay():
    fn = _build()
    ctx = fn({"per": 50, "pbr": 6, "roe": 8})
    # per > 40 + pbr>5 & roe<15 → 3권 매칭 (Shiller, Mackay, Taleb)
    assert "Shiller" in ctx
    assert ("Mackay" in ctx) or ("Taleb" in ctx)


def test_context_length_bounded():
    """프롬프트 비대화 방지 — 최악 케이스에도 2000자 이내."""
    fn = _build()
    stock = {
        "per": 50, "pbr": 6, "roe": 8,
        "drop_from_high_pct": -40,
        "technical": {"signals": ["A", "B", "C"]},
        "consensus": {"eps_growth_yoy_pct": 35},
        "_macro_cape": 32,
        "leverage_ratio": 20,
    }
    ctx = fn(stock)
    assert len(ctx) < 2000, f"context too long: {len(ctx)} chars"


def test_context_empty_when_kb_missing(monkeypatch):
    """KB 파일이 사라져도 예외 없이 빈 문자열 반환."""
    from api.analyzers import gemini_analyst
    monkeypatch.setattr(gemini_analyst, "_knowledge_cache", None)
    monkeypatch.setattr(gemini_analyst, "_KNOWLEDGE_BASE_PATH", "/nonexistent/path.json")
    ctx = gemini_analyst._build_knowledge_context({"per": 10})
    assert ctx == ""
