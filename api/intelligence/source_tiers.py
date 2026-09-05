"""source_tiers — 서술형 외부 데이터의 출처 신뢰 tier (데이터 필터 5번째 겹, PM 승인 2026-08-03).

배경: 기존 4겹(신선도 SLA·채움율 게이트·측정 정화·sanitizer)은 구조화 1차 데이터용.
Gemini 구글 그라운딩 프로브 실측(2026-08-03)에서 서술형 축의 갭 확인 — 출처 22건 중
주류 73% / 저품질(tistory·무관 해외지) 27%. 이 모듈이 유일한 차단·tier 소스(이중 목록 금지).

소비처 2곳: news_headlines(수집 차단) · macro_synthesis(Gemini 그라운딩 출처 필터 +
Perplexity citations).

역할 분리: 기존 news_headlines.CREDIBLE_SOURCES = 가점(정렬용) 유지. 여기는 tier/차단만.
원칙: 수치는 항상 우리 1차 API(KIS·DART·금융위·FRED·Binance) 우선 — 외부 서술은 맥락 전용.
"""
from __future__ import annotations

from urllib.parse import urlparse

# T1 — 1차 기관 (중앙은행·감독·통계·거래소)
T1_DOMAINS = (
    "bok.or.kr", "fss.or.kr", "dart.fss.or.kr", "fsc.go.kr", "krx.co.kr",
    "kostat.go.kr", "moef.go.kr",
    "federalreserve.gov", "stlouisfed.org", "treasury.gov", "bls.gov", "bea.gov",
    "sec.gov", "imf.org", "bis.org", "worldbank.org",
    "ecb.europa.eu", "boj.or.jp", "esma.europa.eu",
)

# T2 — 주류 언론·데이터 벤더 (국내 + 글로벌)
T2_DOMAINS = (
    # 국내
    "yna.co.kr", "yonhapnewstv.co.kr", "chosun.com", "hankyung.com", "mk.co.kr",
    "sedaily.com", "edaily.co.kr", "mt.co.kr", "fnnews.com", "joongang.co.kr",
    "donga.com", "hani.co.kr", "khan.co.kr", "kbs.co.kr", "sbs.co.kr", "imbc.com",
    "ytn.co.kr", "newsis.com", "news1.kr", "koreatimes.co.kr", "koreaherald.com",
    "biz.chosun.com", "asiae.co.kr", "heraldcorp.com",
    # 글로벌
    "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "cnbc.com",
    "marketwatch.com", "barrons.com", "economist.com", "nikkei.com", "apnews.com",
    "bbc.com", "nytimes.com", "tradingeconomics.com", "investing.com",
)

# 차단 — UGC·개인 블로그 플랫폼 (매체 아님). 미등재 도메인은 unknown(0) — 차단 아님.
BLOCKED_DOMAINS = (
    "tistory.com", "blog.naver.com", "post.naver.com", "cafe.naver.com",
    "blogspot.com", "brunch.co.kr", "medium.com", "velog.io", "note.com",
    "dcinside.com", "fmkorea.com", "clien.net", "ruliweb.com", "reddit.com",
)

# 헤드라인 item["source"] 가 URL 아닌 매체명 문자열일 때의 차단 매칭 (부분 문자열)
BLOCKED_NAMES = ("티스토리", "블로그", "카페", "brunch", "velog")


def domain_of(s: str) -> str:
    """URL 또는 도메인 문자열 → 소문자 도메인 (www. 제거). 실패 시 원문 소문자."""
    t = (s or "").strip().lower()
    if not t:
        return ""
    if "://" in t:
        try:
            t = urlparse(t).netloc or t
        except Exception:
            pass
    return t[4:] if t.startswith("www.") else t


def _match(domain: str, table: tuple) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in table)


def tier_of(s: str) -> int:
    """2=T1 기관 · 1=T2 주류 · 0=미등재(unknown, 차단 아님) · -1=차단."""
    d = domain_of(s)
    if not d:
        return 0
    if _match(d, BLOCKED_DOMAINS):
        return -1
    if _match(d, T1_DOMAINS):
        return 2
    if _match(d, T2_DOMAINS):
        return 1
    return 0


def is_blocked(s: str) -> bool:
    """URL/도메인 차단 여부 + 매체명 문자열 차단(BLOCKED_NAMES 부분매칭)."""
    if tier_of(s) == -1:
        return True
    low = (s or "").lower()
    return any(n in low for n in BLOCKED_NAMES)


def filter_citations(urls: list, limit: int = 6, min_tier: int = 0) -> list:
    """citations 정리 — 차단 제거 + tier 내림차순(원순서 보조) + 상한."""
    scored = []
    for i, u in enumerate(urls or []):
        if not isinstance(u, str) or is_blocked(u):
            continue
        t = tier_of(u)
        if t < min_tier:
            continue
        scored.append((-t, i, u))
    scored.sort()
    return [u for _, _, u in scored[:limit]]
