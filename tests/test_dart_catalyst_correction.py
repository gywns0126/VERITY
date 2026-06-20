"""dart_catalyst 정정공시 감지 회귀 가드 (2026-06-20 버그 fix).

버그: list.json 이 corr_yn 미제공 → corr_yn=="Y" 항상 False → 제목 [기재정정] 명시
정정공시 181건이 is_correction=0 으로 누락. fix = report_nm 정정 마커 보강.
"""
from api.collectors.dart_catalyst import _detect_correction


def test_corr_yn_flag_detected():
    assert _detect_correction({"corr_yn": "Y", "report_nm": "주요사항보고서"}) is True


def test_title_marker_detected_when_corr_yn_missing():
    # list.json 이 corr_yn 미제공해도 제목으로 감지 (버그 fix 핵심)
    assert _detect_correction({"report_nm": "[기재정정]주요사항보고서(유상증자결정)"}) is True
    assert _detect_correction({"report_nm": "[첨부정정]주요사항보고서(전환사채발행결정)"}) is True


def test_non_correction_not_flagged():
    assert _detect_correction({"report_nm": "주요사항보고서(유상증자결정)"}) is False
    assert _detect_correction({"report_nm": "", "corr_yn": "N"}) is False
    assert _detect_correction({}) is False
