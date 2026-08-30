"""source_tiers 단위 — 출처 신뢰 tier(데이터 필터 5번째 겹, 2026-08-03)."""
from api.intelligence.source_tiers import domain_of, tier_of, is_blocked, filter_citations
from api.intelligence.macro_synthesis import _filter_citation_refs


def test_tier_levels():
    assert tier_of("https://www.bok.or.kr/portal/main") == 2          # T1 기관
    assert tier_of("hankyung.com") == 1                                # T2 주류 (도메인 문자열)
    assert tier_of("https://biz.chosun.com/economy/x") == 1            # 서브도메인 endswith
    assert tier_of("https://randomsmallpress.co.kr/a") == 0            # 미등재 = unknown (차단 아님)
    assert tier_of("https://foo.tistory.com/123") == -1                # 차단


def test_blocked_by_name_and_domain():
    assert is_blocked("https://blog.naver.com/abc")
    assert is_blocked("경제 티스토리 요약")                            # 매체명 문자열 매칭
    assert not is_blocked("https://www.yna.co.kr/view/AKR1")


def test_filter_citations_orders_and_caps():
    urls = [
        "https://foo.tistory.com/1",            # 차단 → 제거
        "https://smallblog.example.com/2",       # unknown → 유지(후순위)
        "https://www.hankyung.com/3",            # T2
        "https://www.bok.or.kr/4",               # T1 → 최상단
    ]
    out = filter_citations(urls, limit=3)
    assert out[0].endswith("/4") and out[1].endswith("/3")
    assert all("tistory" not in u for u in out)
    assert len(out) == 3


def test_macro_citation_filter_preserves_original_reference_numbers():
    urls = [
        "https://smallblog.example.com/1",
        "https://www.hankyung.com/2",
        "https://www.bok.or.kr/3",
    ]
    filtered, refs = _filter_citation_refs(urls, limit=2)
    assert filtered == [urls[2], urls[1]]
    assert refs == [{"n": 3, "url": urls[2]}, {"n": 2, "url": urls[1]}]


def test_domain_of():
    assert domain_of("https://www.chosun.com/x?y=1") == "chosun.com"
    assert domain_of("Chosun.com") == "chosun.com"
