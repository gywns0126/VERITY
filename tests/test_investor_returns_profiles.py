"""복제 수익률 + 인물 프로필 — 정직성 가드.

2026-07-30 (PM "그래프도 만들어서 연간 수익률 / 인물 설명도").
13F 로 실제 성과는 못 낸다. 대신 '공시 롱 북 복제' — 각 분기말 포지션을 다음 분기말까지
그대로 보유했다고 가정한 계산값 — 만 내고, 실제 성과와 다른 이유를 병기한다.

프로필은 내 기억이 아니라 출처 있는 것만 싣는다. 제목 매칭만으로는 틀린 사람이 붙는다 —
실측: 한국어 위키 "캐서린 우드" → 1914년생 소설가 캐서린 마셜.
"""
import api.collectors.investor_profiles as P
from api.collectors.sec_13f_collector import annualize_from_quarters


def test_annualize_needs_four_quarters():
    """4분기 미만은 None — 억지 연율화 금지."""
    assert annualize_from_quarters([]) is None
    assert annualize_from_quarters([{"return_pct": 5}] * 3) is None


def test_annualize_compounds():
    out = annualize_from_quarters([{"return_pct": 10}] * 4)
    assert abs(out - 46.41) < 0.01                 # 1.1^4 - 1


def test_annualize_uses_last_four_only():
    s = [{"return_pct": 999}] + [{"return_pct": 0}] * 4
    assert annualize_from_quarters(s) == 0.0


def test_profile_rejects_wrong_person(monkeypatch):
    """직업 키워드 없는 문서는 폐기 — 동명이인 유입 차단(캐시 우드 실사고)."""
    monkeypatch.setattr(P.requests, "get", lambda *a, **k: type("R", (), {
        "status_code": 200,
        "json": staticmethod(lambda: {
            "type": "standard", "title": "캐서린 마셜",
            "extract": "캐서린 마셜(1914년-1983년)은 미국의 소설가이다.",
            "content_urls": {"desktop": {"page": "https://ko.wikipedia.org/wiki/캐서린_마셜"}},
        })})())
    assert P._fetch_summary("ko", "캐서린 우드") is None


def test_profile_accepts_investor(monkeypatch):
    monkeypatch.setattr(P.requests, "get", lambda *a, **k: type("R", (), {
        "status_code": 200,
        "json": staticmethod(lambda: {
            "type": "standard", "title": "Cathie Wood",
            "extract": "Catherine Wood is an American investor and founder of ARK Invest.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Cathie_Wood"}},
        })})())
    got = P._fetch_summary("en", "Cathie Wood")
    assert got and got["name"] == "Cathie Wood"
    assert got["source"] == "위키백과" and got["source_url"]


def test_profile_rejects_disambiguation(monkeypatch):
    """동음이의 페이지(type != standard) 폐기 — 'Andreas Halvorsen' 실사례."""
    monkeypatch.setattr(P.requests, "get", lambda *a, **k: type("R", (), {
        "status_code": 200,
        "json": staticmethod(lambda: {"type": "disambiguation",
                                      "extract": "Andreas Halvorsen may refer to: hedge fund"})})())
    assert P._fetch_summary("en", "Andreas Halvorsen") is None


def test_profile_exhausted_candidates_returns_none(monkeypatch):
    """후보 소진 시 추측으로 채우지 않고 빈 값."""
    monkeypatch.setattr(P, "_fetch_summary", lambda lang, title: None)
    monkeypatch.setattr(P.time, "sleep", lambda s: None)
    assert P.fetch_profile("Berkshire Hathaway") is None


def test_every_active_manager_has_candidates():
    """매니저 추가 시 후보 등록 누락 방지."""
    from api.builders.us_smart_money_13f_public_builder import ACTIVE_MANAGERS
    missing = [n for n in ACTIVE_MANAGERS.values() if not P.WIKI_CANDIDATES.get(n)]
    assert not missing, f"위키 후보 미등록: {missing}"
