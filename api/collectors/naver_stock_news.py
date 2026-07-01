"""naver_stock_news — KR 종목별 뉴스 collector (네이버 금융, 정보 밀도형).

2026-06-27 신설 (PM 결정 "짜장면 제대로 + 밀도"). 기존 종목 뉴스 = Google RSS 3-cap/28종목(빈약).
네이버 금융 종목 뉴스(finance.naver.com/item/news_news)는 한국 retail 실제 소스 = 풍부.

각 뉴스 한 건에 구조적 사실 밀도 (RULE 6: LLM 해설·요약 0. 전부 사전/사실/우리 데이터 연결):
  - category: 제목 키워드 사전 분류 (실적/공시/계약/M&A/인사/신사업/시장) — 공시 톤 배지와 동일 방식
  - source + credibility: 기존 news_headlines.CREDIBLE_SOURCES 재사용 (1차 출처 구분)
  - outlets: 같은 사안 보도 매체 수 (유사제목 클러스터 = 화제성 사실, 편집 아님)
  - related_disclosure: 그 종목 ±3일 내 DART 공시 연결 (우리 차별점 — 뉴스×공시)
  - time: 원본 시각

RULE 7: 사실만. 호재/악재 판단·중요도 랭킹·방향성 추론 0.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from api.collectors.news_headlines import CREDIBLE_SOURCES

NEWS_URL = "https://finance.naver.com/item/news_news.naver?code={code}&page={page}"
# 정직 식별 UA (브라우저 위장 제거, 2026-07-01 권리감사) — UA/Referer 위장=접근제어 우회 리스크 회피
_UA = "VERITY-news-fetcher/1.0 (+https://github.com/gywns0126; 종목 헤드라인 링크아웃)"

# 카테고리 사전 (우선순위 순, 첫 매칭 확정). 제목 키워드 = 사실 분류(공시 톤 배지 방식, LLM 0).
_CATEGORY_RULES: List[tuple] = [
    ("실적", ["실적", "영업이익", "영업손실", "순이익", "매출", "어닝", "잠정실적", "분기 실적", "적자", "흑자전환"]),
    ("공시", ["공시", "유상증자", "무상증자", "자사주", "자기주식", "전환사채", "신주인수권", "배당", "감자"]),
    ("계약·수주", ["수주", "공급계약", "납품", "계약 체결", "수주잔고", "MOU", "협약", "단일판매"]),
    ("M&A·지분", ["인수", "합병", "지분", "최대주주", "매각", "분할", "출자", "경영권"]),
    ("인사", ["대표이사", "사장", "임원", "선임", "사임", "CEO", "회장", "내정"]),
    ("신사업·투자", ["출시", "신제품", "증설", "공장", "투자", "개발", "진출", "수출", "특허"]),
]


def _category(title: str) -> str:
    t = title or ""
    for label, kws in _CATEGORY_RULES:
        if any(k in t for k in kws):
            return label
    return "시장"


def _credibility(source: str) -> int:
    """기존 사전 재사용 — 매핑 없으면 2(일반). 1차 출처(>=4)= 신뢰 배지."""
    return CREDIBLE_SOURCES.get((source or "").strip(), 2)


def _norm_title(t: str) -> str:
    """클러스터링용 정규화 — 괄호·특수문자·공백 제거, 앞 24자."""
    t = re.sub(r"\[.*?\]|\(.*?\)|[^가-힣A-Za-z0-9]", "", t or "")
    return t[:24].lower()


def _parse_dt(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s.strip(), "%Y.%m.%d %H:%M")
    except (ValueError, AttributeError):
        return None


def _rel_time(dt: Optional[datetime], now: datetime) -> str:
    if not dt:
        return ""
    sec = (now - dt).total_seconds()
    if sec < 3600:
        return f"{int(sec // 60)}분 전"
    if sec < 86400:
        return f"{int(sec // 3600)}시간 전"
    return f"{int(sec // 86400)}일 전"


# ── 네이버 검색 API (공식) — 2026-07-01 권리감사: 스크래핑/위장 탈출 ──
import os
from datetime import timezone

_NAVER_NEWS_API = "https://openapi.naver.com/v1/search/news.json"
_KST = timezone(timedelta(hours=9))
_DOMAIN_SOURCE = {
    "hankyung.com": "한국경제", "mk.co.kr": "매일경제", "sedaily.com": "서울경제",
    "chosun.com": "조선비즈", "edaily.co.kr": "이데일리", "mt.co.kr": "머니투데이",
    "yna.co.kr": "연합뉴스", "newspim.com": "뉴스핌", "fnnews.com": "파이낸셜뉴스",
    "heraldcorp.com": "헤럴드경제", "asiae.co.kr": "아시아경제", "zdnet.co.kr": "ZDNet",
    "etnews.com": "전자신문", "dt.co.kr": "디지털타임스", "infomax": "연합인포맥스",
    "hani.co.kr": "한겨레", "joongang.co.kr": "중앙일보", "donga.com": "동아일보",
}


def _strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    for a, b in (("&quot;", '"'), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&#39;", "'"), ("&apos;", "'")):
        s = s.replace(a, b)
    return s.strip()


def _source_from_link(link: str) -> str:
    try:
        from urllib.parse import urlparse
        host = urlparse(link).netloc.lower().replace("www.", "")
        for dom, nm in _DOMAIN_SOURCE.items():
            if dom in host:
                return nm
        return host.split(".")[0] if host else ""
    except Exception:  # noqa: BLE001
        return ""


def _fetch_search_api(name: str, display: int = 30) -> List[Dict[str, Any]]:
    """네이버 검색 API(공식·ToS-OK) — 종목명 키워드. 스크래핑/UA위장 대체(권리감사 쟁점5).
    키 = NAVER_Client_ID / NAVER_Client_Secret (env)."""
    cid = os.environ.get("NAVER_Client_ID") or os.environ.get("NAVER_CLIENT_ID", "")
    csec = os.environ.get("NAVER_Client_Secret") or os.environ.get("NAVER_CLIENT_SECRET", "")
    if not name or not cid or not csec:
        return []
    try:
        r = requests.get(
            _NAVER_NEWS_API,
            params={"query": name, "display": display, "sort": "date"},
            headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec},
            timeout=6,
        )
        if not r.ok:
            return []
        from email.utils import parsedate_to_datetime
        out: List[Dict[str, Any]] = []
        for it in r.json().get("items", []):
            link = it.get("originallink") or it.get("link") or ""
            dt_s = ""
            try:
                pd = parsedate_to_datetime(it.get("pubDate", ""))
                if pd:  # now(KST) 정합
                    dt_s = pd.astimezone(_KST).replace(tzinfo=None).strftime("%Y.%m.%d %H:%M")
            except Exception:  # noqa: BLE001
                pass
            out.append({
                "title": _strip_html(it.get("title")),
                "url": link,
                "source": _source_from_link(link),
                "datetime": dt_s,
            })
        return out
    except Exception:  # noqa: BLE001
        return []


def fetch_stock_news(code: str, name: str = "", max_items: int = 15, pages: int = 3,
                     disclosures: Optional[List[Dict[str, Any]]] = None,
                     now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """종목 뉴스 + 밀도 enrichment. disclosures = 그 종목 공시 list[{title,date,source_url}] (±3일 연결)."""
    if now is None:
        try:
            from api.config import now_kst
            now = now_kst().replace(tzinfo=None)
        except Exception:  # noqa: BLE001
            now = datetime.now()
    # 스크래핑 → 네이버 공식 검색 API (2026-07-01 권리감사 쟁점5). 종목명 키워드, 단일 호출(pages 불요).
    raw: List[Dict[str, Any]] = _fetch_search_api(name)

    # 공시 날짜 인덱스 (±3일 연결)
    disc_by_date: Dict[str, Dict[str, Any]] = {}
    for d in (disclosures or []):
        dt = str(d.get("date") or "")
        if dt:
            disc_by_date[dt] = d

    # 클러스터링 — 정규화 제목으로 묶어 매체 수 집계, 대표는 최고 신뢰도.
    clusters: Dict[str, Dict[str, Any]] = {}
    for it in raw:
        if not it["title"]:
            continue
        key = _norm_title(it["title"])
        if not key:
            continue
        cred = _credibility(it["source"])
        dt = _parse_dt(it["datetime"])
        c = clusters.get(key)
        if c is None:
            clusters[key] = {"item": it, "cred": cred, "dt": dt, "outlets": {it["source"]}}
        else:
            c["outlets"].add(it["source"])
            if cred > c["cred"]:  # 더 신뢰도 높은 매체를 대표로
                c["item"], c["cred"], c["dt"] = it, cred, dt

    # 기업이벤트 카테고리만 공시 연결 (시장/신사업 일반뉴스는 공시와 무관 → 헐렁 연결 방지)
    _EVENT_CATS = {"공시", "실적", "계약·수주", "M&A·지분", "인사"}
    nm = (name or "").strip()
    out: List[Dict[str, Any]] = []
    for c in clusters.values():
        it, dt = c["item"], c["dt"]
        cat = _category(it["title"])
        # 노이즈 제외 — 종목명 없고 '시장'(이벤트 키워드 0) = 순수 시장/정치 뉴스(객관적 필터)
        if cat == "시장" and nm and nm not in it["title"]:
            continue
        # 공시 연결 = 기업이벤트 카테고리 + ±2일 (의미 있는 연결만)
        related = None
        if dt and cat in _EVENT_CATS:
            for off in range(-2, 3):
                key = (dt + timedelta(days=off)).strftime("%Y-%m-%d")
                if key in disc_by_date:
                    dd = disc_by_date[key]
                    related = {"title": dd.get("title"), "url": dd.get("source_url"), "date": key}
                    break
        out.append({
            "title": it["title"],
            "url": it["url"],
            "source": it["source"],
            "category": cat,
            "credibility": c["cred"],
            "credible": c["cred"] >= 4,
            "outlets": len(c["outlets"]),
            "datetime": it["datetime"],
            "rel_time": _rel_time(dt, now),
            "related_disclosure": related,
            "_sort": dt.timestamp() if dt else 0,
        })
    out.sort(key=lambda x: x["_sort"], reverse=True)
    for o in out:
        o.pop("_sort", None)
    return out[:max_items]
