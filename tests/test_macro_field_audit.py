"""거시 필드 단위 감사 계약 (PM 지시 2026-08-19 "신선도 추적 + 데이터소스 추적해서 검증까지").

파일 단위 SLA(`freshness_sla.json` 71스트림)로는 못 보는 두 축을 고정한다:
  ① 파일은 신선한데 **안의 값이 오래된** 경우 (파일나이 ≠ 기준일)
  ② 값이 **이름과 다른 출처**에서 온 경우 (source_note 를 안 읽으면 오독)
"""
from datetime import date

import pytest

from scripts.audit import macro_field_audit as A


def _snap(fred):
    return {"collected_at": "2026-08-19T20:32:11+09:00", "macro": {"fred": fred}}


def test_same_series_id_under_two_names_is_flagged():
    """🚨 실측 결함 형태 — gdp_growth 와 us_recession_smoothed_prob 이 둘 다 RECPROUSM156N."""
    f, _ = A.audit(_snap({
        "gdp_growth": {"value": 2.45, "date": "2026-06-01", "series_id": "RECPROUSM156N",
                       "source_note": "proxy from us_recession_smoothed_prob"},
        "us_recession_smoothed_prob": {"pct": 0.6, "date": "2026-06-01",
                                       "series_id": "RECPROUSM156N"},
    }), today=date(2026, 6, 15))
    assert any(x.startswith("D1-a") and "RECPROUSM156N" in x for x in f)


def test_unregistered_derived_field_is_flagged():
    """새 파생이 조용히 끼어들면 잡는다. 등록은 '괜찮다' 가 아니라 '알고 있다' 는 뜻."""
    f, _ = A.audit(_snap({
        "some_new_metric": {"value": 1.0, "date": "2026-08-18", "series_id": "XYZ",
                            "source_note": "proxy from something else"},
    }), today=date(2026, 8, 19))
    assert any(x.startswith("D2") and "some_new_metric" in x for x in f)


def test_registered_derived_field_is_not_noise():
    """이미 등록된 파생은 재보고하지 않는다 — 경보 피로가 감사를 죽인다."""
    f, _ = A.audit(_snap({
        "cpi_yoy": {"value": 2.79, "date": "2026-08-18", "series_id": "CPILFESL",
                    "source_note": "derived from core_cpi.yoy_pct"},
    }), today=date(2026, 8, 19))
    assert not any(x.startswith("D2") for x in f)


def test_stale_field_inside_fresh_file_is_flagged():
    """🚨 핵심 — 파일은 방금 받아왔는데 값은 몇 달 전. 파일 SLA 로는 안 보인다."""
    f, _ = A.audit(_snap({
        "dgs10": {"value": 4.72, "date": "2026-06-01", "series_id": "DGS10"},
    }), today=date(2026, 8, 19))
    assert any(x.startswith("D3") and "dgs10" in x for x in f)


def test_monthly_series_is_not_flagged_by_daily_yardstick():
    """월간 지표에 일간 잣대를 대면 전부 빨개져 감사가 무의미해진다."""
    f, _ = A.audit(_snap({
        "unemployment_rate": {"pct": 4.1, "date": "2026-07-01", "series_id": "UNRATE"},
    }), today=date(2026, 8, 19))
    assert not any(x.startswith("D3") for x in f)


def test_semantic_pin_violation_is_flagged():
    """이름이 암시하는 의미와 실제 계열이 어긋나면 잡는다."""
    f, _ = A.audit(_snap({
        "vix_close": {"value": 15.19, "date": "2026-08-18", "series_id": "WRONG_ID"},
    }), today=date(2026, 8, 19))
    assert any(x.startswith("D1-b") and "vix_close" in x for x in f)


def test_derived_registry_documents_the_risk_not_just_the_fact():
    """🚨 등록 항목은 **왜 위험한지**를 적어야 한다. 이름만 나열하면 다음 사람이 판단 못 한다."""
    for name, why in A.DERIVED_REGISTRY.items():
        assert len(why) > 40, f"{name} 등록 사유가 너무 짧다 — 위험을 적을 것"
        assert "아님" in why or "not" in why.lower(), \
            f"{name} — 무엇이 **아닌지**를 명시할 것 (이름 오독이 핵심 위험)"


def test_live_snapshot_has_per_field_provenance():
    """실 산출물이 필드별 기준일·출처를 실제로 들고 있는지 (있다고 가정하지 않는다)."""
    import json
    import os
    if not os.path.exists(A.SNAP):
        pytest.skip("macro_snapshot 부재")
    with open(A.SNAP, encoding="utf-8") as fh:
        snap = json.load(fh)
    fields = A.collect_fields(snap)
    assert len(fields) >= 10, f"필드 {len(fields)}개 — 수집 축이 무너졌는지 확인"
    with_date = sum(1 for v in fields.values() if v.get("date"))
    assert with_date == len(fields), \
        f"기준일 없는 필드 {len(fields)-with_date}개 — 시점 질문에 답할 수 없게 된다"
