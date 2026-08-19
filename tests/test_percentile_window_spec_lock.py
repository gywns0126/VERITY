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


# ── A1 정명 (PREREG_CAPE_AXIS_DISPOSITION_2026_08_19, PM 승인 2026-08-19) ──────


def test_cape_axis_declares_itself_as_policy_not_signal():
    """🚨 A1 정명의 핵심 — 이 축은 '거시 신호' 가 아니라 **노출 정책**이다.

    14개월째 상수인 축이 '신호' 라는 이름을 달고 있던 게 문제였다(성과 문제가 아니다 —
    H3 대로 승수는 Sharpe·Calmar 중립). 이름과 실제를 맞추는 것이 A1 이다.
    """
    from api.intelligence.verity_brain import _cape_pct_meta

    m = _cape_pct_meta(99.0)
    assert m["axis_role"] == "valuation_exposure_policy", "정명이 되돌아갔다"
    assert "신호 아님" in m["role_note"]


def test_cape_saturation_uses_penalty_cap_not_table_top():
    """🚨 2026-08-19 실측 정정 — 포화 시작은 테이블 상단(99)이 아니라 **96.67** 이다.

    종전 판정이 `pct >= 99` 였어서 96.7~99 구간(= CAPE 36.50~40.0)의 포화를 통째로
    놓쳤다. 그 구간이 바로 지금(2025-07~ 14개월) 우리가 있는 곳이다.
    """
    from api.intelligence.verity_brain import (_CAPE_MAX_PENALTY,
                                               _CAPE_SATURATION_PCT, _cape_pct_meta)

    assert abs(_CAPE_SATURATION_PCT - 96.67) < 0.01, "포화 임계가 바뀌었다"
    # 산식 역산과 일치해야 한다 — 상한을 바꾸면 임계도 따라와야 한다
    assert abs(_CAPE_SATURATION_PCT - (90.0 + _CAPE_MAX_PENALTY / 0.15 * 10.0)) < 1e-9

    assert _cape_pct_meta(96.0)["saturated"] is False
    assert _cape_pct_meta(97.0)["saturated"] is True      # 🚨 종전 로직은 여기를 놓쳤다
    assert _cape_pct_meta(99.0)["saturated"] is True


def test_cape_max_penalty_is_module_level_single_source():
    """상한 리터럴이 두 곳에 갈리면 포화 신고와 실제 페널티가 어긋난다."""
    import inspect

    from api.intelligence import verity_brain as B
    assert B._CAPE_MAX_PENALTY == 0.10
    src = inspect.getsource(B)
    # 함수 안에서 다시 정의하면 신고와 실제가 갈린다
    assert "\n    _CAPE_MAX_PENALTY = " not in src, "지역 재정의가 되살아났다"


def test_a1_changes_no_numbers():
    """🚨 A1 은 **산식 변경 0** 이다. 페널티 값이 바뀌면 그건 A1 이 아니다.

    정명이 축을 '고치는' 것으로 오해되지 않도록 값 불변을 계약으로 고정한다.
    """
    from api.intelligence.verity_brain import _CAPE_MAX_PENALTY

    def pen(pct):
        return 0.0 if pct < 90 else max(0.0, min(_CAPE_MAX_PENALTY, (pct - 90) / 10 * 0.15))

    # 등록 전과 동일해야 하는 대표점
    assert pen(89.9) == 0.0
    assert abs(pen(93.0) - 0.045) < 1e-9
    assert abs(pen(96.0) - 0.09) < 1e-9
    assert pen(96.67) == _CAPE_MAX_PENALTY
    assert pen(99.0) == _CAPE_MAX_PENALTY
    assert pen(100.0) == _CAPE_MAX_PENALTY
