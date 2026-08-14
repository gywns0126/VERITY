# -*- coding: utf-8 -*-
"""제출인 단위오류 가드 — '주당 현금배당금' 칸의 배당금 총액 (2026-08-15).

실측 사고: `067900` FY2022~2025 4건. DART 원본에서
`se='주당 현금배당금(원)' knd='보통주' thstrm='904,982,950'` 인데 같은 응답의
`현금배당금총액(백만원)` 이 904 다. 같은 응답의 EPS 1,330 × 현금배당성향 3.76% ≈ 50원이
실제 주당 배당이고 외부 대조(50·50·70·100원)와도 맞는다. **파서가 아니라 원본이 틀렸다.**

소비 측(`kr_valuation_panel`)이 그대로 나누면 배당수익률 2,810만% → 배당 축 1위가 된다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.collectors.dart_dividend_history import (  # noqa: E402
    IMPLAUSIBLE_DPS, flag_filer_unit_error, parse,
)


def _rows(dps: str, total: str = "904"):
    """067900 FY2022 실제 응답의 축약 재현."""
    return [
        {"rcept_no": "20230320000123", "stlm_dt": "2022-12-31",
         "se": "주당 현금배당금(원)", "stock_knd": "보통주", "thstrm": dps, "frmtrm": dps},
        {"rcept_no": "20230320000123", "stlm_dt": "2022-12-31",
         "se": "현금배당금총액(백만원)", "stock_knd": "-", "thstrm": total, "frmtrm": total},
        {"rcept_no": "20230320000123", "stlm_dt": "2022-12-31",
         "se": "현금배당수익률(%)", "stock_knd": "보통주", "thstrm": "0.69", "frmtrm": "0.58"},
        {"rcept_no": "20230320000123", "stlm_dt": "2022-12-31",
         "se": "(연결)주당순이익(원)", "stock_knd": "-", "thstrm": "1,330", "frmtrm": "1,361"},
    ]


def test_total_in_per_share_field_is_dropped_with_reason():
    """총액과 일치하는 거대 dps = 제출인 단위오류. 조용히 지우지 않고 사유를 남긴다."""
    out = parse(_rows("904,982,950"), "067900", 2022)
    assert out, "행이 생성되어야 한다"
    for rec in out:
        assert rec["dps"] is None
        assert rec["dps_dropped"] == "filer_put_total_in_per_share_field"
        # 나머지 필드는 살아 있어야 한다 — 배당수익률·EPS 는 정상값이다
        assert rec["div_yield_reported"] in (0.69, 0.58)
        assert rec["eps_owner"] in (1330.0, 1361.0)


def test_normal_dps_survives():
    """정상 주당 배당은 손대지 않는다."""
    out = parse(_rows("50", total="904"), "067900", 2022)
    assert out
    assert all(r["dps"] == 50.0 for r in out)
    assert all("dps_dropped" not in r for r in out)


def test_implausible_without_total_still_dropped_but_distinct_reason():
    """총액이 없으면 크기만으로 끊되 사유를 구분한다 (원인 단정 금지)."""
    rec = {"dps": IMPLAUSIBLE_DPS * 5}
    flag_filer_unit_error(rec)
    assert rec["dps"] is None
    assert rec["dps_dropped"] == "implausible_dps"


def test_total_mismatch_does_not_claim_filer_error():
    """총액과 크게 다르면 '총액 오파싱' 으로 단정하지 않는다."""
    rec = {"dps": 5_000_000, "cash_div_total_mil": 1}      # 1백만원 = 1e6, dps 는 5e6
    flag_filer_unit_error(rec)
    assert rec["dps"] is None
    assert rec["dps_dropped"] == "implausible_dps"


def test_boundary_is_not_triggered_by_large_but_possible_dps():
    """실측 원장 최대가 10만원대다 — 상한 이하는 통과시킨다."""
    rec = {"dps": 100_000.0, "cash_div_total_mil": 904}
    flag_filer_unit_error(rec)
    assert rec["dps"] == 100_000.0
    assert "dps_dropped" not in rec
