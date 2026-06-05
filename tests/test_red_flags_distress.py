"""DART distress red-flag 3종 점수 사전등록 검증 (2026-06-05, RULE 7 PM 승인).

going_concern_doubt + distress_events = auto_avoid(critical), unfaithful = downgrade.
binary 신호(임계 없음) → 곡선맞추기 surface 0. KR only(US 가드).
"""
from api.intelligence.factors.red_flags import _detect_red_flags


def _kr(**extra):
    s = {"ticker": "005930", "currency": "KRW"}
    s.update(extra)
    return s


def _texts(r):
    return r["auto_avoid"] + r["downgrade"]


def test_going_concern_doubt_auto_avoid():
    r = _detect_red_flags(_kr(dart_audit_signals={"going_concern_doubt": True}), {})
    assert r["has_critical"] is True
    assert any("계속기업" in x for x in r["auto_avoid"])


def test_distress_events_auto_avoid():
    r = _detect_red_flags(
        _kr(dart_disclosure_events={"distress_events": ["회생절차 개시신청"]}), {}
    )
    assert r["has_critical"] is True
    assert any("distress" in x for x in r["auto_avoid"])


def test_unfaithful_downgrade():
    r = _detect_red_flags(
        _kr(dart_disclosure_events={"unfaithful_disclosure": True}), {}
    )
    assert any("불성실공시" in x for x in r["downgrade"])


def test_clean_kr_no_distress_flags():
    r = _detect_red_flags(
        _kr(
            dart_audit_signals={"going_concern_doubt": False},
            dart_disclosure_events={"distress_events": [], "unfaithful_disclosure": False},
        ),
        {},
    )
    assert not any(
        ("계속기업" in x) or ("distress" in x) or ("불성실공시" in x) for x in _texts(r)
    )


def test_us_stock_distress_fields_ignored():
    """US 종목(currency=USD)은 KR 분기 밖 → DART distress 블록 미발동."""
    s = {
        "ticker": "AAPL",
        "currency": "USD",
        "dart_audit_signals": {"going_concern_doubt": True},
        "dart_disclosure_events": {
            "distress_events": ["x"],
            "unfaithful_disclosure": True,
        },
    }
    r = _detect_red_flags(s, {})
    assert not any(
        ("계속기업" in x) or ("distress 공시" in x) or ("불성실공시" in x)
        for x in _texts(r)
    )
