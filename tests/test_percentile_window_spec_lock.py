"""백분위 창 사양 사전 고정 잠금 (PM 승인 2026-08-19, 거시 사전등록 §9-F ③).

## 왜 테스트로 잠그나

Q5 답변 = White(2000, Econometrica) "A Reality Check for Data Snooping" ·
Rossi&Inoue(2012, JBES) — **룩백 창 길이는 자유 파라미터**이고, 여러 창을 돌려보고
성능이 좋은 걸 고르면 그 자체가 데이터 스누핑이다. 방어는 **사전 고정**뿐이다.

문서에만 적으면 3일이면 퇴화한다(RULE 12). 그래서 값을 테스트로 잠근다 —
바꾸려면 테스트를 **의도적으로** 고쳐야 하고, 그때 사전등록이 강제된다.

🚨 이 테스트는 "이 값이 옳다" 를 주장하지 않는다. **"이 값이 사전에 고정됐다"** 만 잠근다.
"""
import pytest


# ── 금리 백분위 창 ────────────────────────────────────────────────────────


def test_yield_percentile_window_is_pinned():
    """창 길이·최소표본이 상수로 선언돼 있고 값이 고정돼 있다."""
    from api.intelligence import verity_brain as B

    assert B._YIELD_PCT_WINDOW == 252, "창 길이 변경 — 사전등록 없이 바꾸면 스누핑"
    assert B._YIELD_PCT_MIN_SAMPLE == 60, "최소표본 변경 — 사전등록 필요"


def test_yield_percentile_reports_actual_window_not_just_requested():
    """🚨 요청 창과 실제 창이 다를 수 있다 — 둘 다 신고해야 오독을 막는다.

    실측 2026-08-19: 요청 252 · 실제 118(≈4.5개월). 그 창에서 10Y 폭이 0.49%p 라
    백분위 99.2 는 '역사적 고금리' 가 아니라 '최근 4.5개월 중 최고' 를 뜻했다.
    """
    from api.intelligence import verity_brain as B

    spec = B.yield_percentile_spec()
    for k in ("method", "window_requested", "window_actual", "min_sample", "source"):
        assert k in spec, f"창 사양에 {k} 가 없다 — 산출물만 보고 판별 불가"
    assert spec["window_requested"] == B._YIELD_PCT_WINDOW
    assert isinstance(spec["window_actual"], int)


def test_yield_percentile_uses_the_pinned_constant_not_a_literal():
    """소스에 리터럴이 남아 있으면 상수를 바꿔도 동작이 안 따라온다."""
    import inspect

    from api.intelligence import verity_brain as B
    src = inspect.getsource(B._yield_percentile)
    assert "_YIELD_PCT_WINDOW" in src, "창 길이가 리터럴로 되돌아갔다"
    assert "_YIELD_PCT_MIN_SAMPLE" in src, "최소표본이 리터럴로 되돌아갔다"
    assert "[-252:]" not in src, "리터럴 252 잔존"


# ── CAPE 백분위 테이블 ────────────────────────────────────────────────────


def test_cape_table_spec_is_pinned():
    from api.intelligence.market_horizon import _CAPE_TABLE_SPEC as S

    assert S["coverage"] == "1881~2024"
    assert S["table_max_value"] == 40.0
    assert S["table_max_percentile"] == 99
    assert S["dynamic_v1_implemented"] is False, \
        "V1 동적 계열이 구현됐다면 사양·포화 서술을 갱신할 것"


def test_cape_percentile_declares_saturation():
    """🚨 반환값 99 만으로는 '표 상단 포화' 와 '실제 99분위' 가 구분되지 않는다."""
    from api.intelligence.market_horizon import cape_percentile, cape_percentile_meta

    over = cape_percentile_meta(42.06)          # 실측 2026-08-19 입력
    assert over["percentile"] == 99
    assert over["saturated"] is True, "포화가 신고되지 않는다"
    assert over["saturation_note"]

    under = cape_percentile_meta(30.0)          # 표 안쪽
    assert under["saturated"] is False
    assert under["saturation_note"] is None
    assert cape_percentile(30.0) == 90


def test_saturated_input_range_maps_to_one_value():
    """포화 구간에서는 입력이 달라도 백분위가 같다 — 그 성질 자체를 고정한다."""
    from api.intelligence.market_horizon import cape_percentile

    assert cape_percentile(41.0) == cape_percentile(60.0) == cape_percentile(200.0) == 99


# ── 산출물 자기 신고 ──────────────────────────────────────────────────────


def test_multiplier_meta_carries_percentile_spec():
    """🚨 사양이 산출물에 실려야 한다 — 코드를 안 열고도 판별 가능해야(RULE 12)."""
    import inspect

    from api.intelligence import verity_brain as B
    src = inspect.getsource(B)
    assert '"percentile_spec"' in src, "macro_multiplier meta 에서 창 사양 신고가 사라졌다"
    assert "yield_percentile_spec()" in src
    assert "_cape_pct_meta(" in src
