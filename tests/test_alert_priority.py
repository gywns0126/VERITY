# -*- coding: utf-8 -*-
"""알림 우선순위 회귀 — 2026-08-05 텔레그램 레이어 감사에서 1차 자료로 확인한 P0 2건.

① 종목 급등·급락 감지가 실제 데이터 키를 못 봐서 구조적 0건 (change_pct 0/62,
   technical.price_change_pct 61/62).
② VAMS 손절·체결 alert 에 level 키가 없어 비긴급 묶음(quiet hours 준수)으로 떨어짐 —
   실적 D-1 류가 CRITICAL 로 야간을 통과하는 것과 정반대 = 우선순위 역전.
"""
import os
import re

from api.intelligence.alert_engine import _detect_flash_moves


def _rec(name, chg=None, tech_chg=None):
    r = {"name": name, "ticker": "000000"}
    if chg is not None:
        r["change_pct"] = chg
    if tech_chg is not None:
        r["technical"] = {"price_change_pct": tech_chg}
    return r


def _msgs(alerts):
    return " ".join(a.get("message", "") for a in alerts)


def test_flash_drop_detected_from_technical_field():
    # 회귀: 실운영 레코드는 change_pct 가 없고 technical.price_change_pct 만 있다
    alerts = _detect_flash_moves({}, [_rec("급락주", tech_chg=-9.5)])
    assert "급락주" in _msgs(alerts)


def test_flash_surge_detected_from_technical_field():
    alerts = _detect_flash_moves({}, [_rec("급등주", tech_chg=12.0)])
    assert "급등주" in _msgs(alerts)


def test_top_level_key_still_wins_when_present():
    # 폴백이지 대체가 아니다 — top-level 이 있으면 그걸 쓴다
    alerts = _detect_flash_moves({}, [_rec("우선순위", chg=-11.0, tech_chg=0.0)])
    assert "우선순위" in _msgs(alerts)


def test_zero_change_is_not_treated_as_missing():
    # 0.0 은 유효값 — `or` 체인이면 다음 키로 새서 오탐이 난다
    alerts = _detect_flash_moves({}, [_rec("보합", chg=0.0, tech_chg=-30.0)])
    assert "보합" not in _msgs(alerts)


def test_quiet_stock_produces_no_alert():
    assert _msgs(_detect_flash_moves({}, [_rec("평온", tech_chg=1.2)])) == ""


def test_vams_alerts_carry_explicit_level():
    """VAMS 가 만드는 alert 4종에 level 키가 있어야 send_alerts 버킷 분류가 정상 작동."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "api/vams/engine.py"), encoding="utf-8").read()
    for atype, expected in (("STOP_LOSS", "CRITICAL"), ("PARTIAL_EXIT", "WARNING"),
                            ("EXPOSURE_BLOCK", "WARNING"), ("NEW_BUY", "WARNING")):
        m = re.search(r'"type":\s*"%s",\s*\n\s*"level":\s*"([A-Z]+)"' % atype, src)
        assert m, f"{atype} alert 에 level 키 없음 — 비긴급 묶음으로 떨어져 야간 묵음"
        assert m.group(1) == expected, f"{atype} level={m.group(1)} (기대 {expected})"
