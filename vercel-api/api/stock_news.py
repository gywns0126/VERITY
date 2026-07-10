"""
VERITY 종목별 뉴스 API (정보 밀도형) — GET /api/stock_news?code=005930

네이버 금융 종목 뉴스(finance.naver.com/item/news_news) → 건당 구조적 사실 밀도.
RULE 6: LLM 해설·요약 0. 전부 사전/사실 (카테고리·신뢰티어·매체수·시각).
RULE 7: 호재/악재 판단·중요도 랭킹·방향성 0. 사실만.
self-contained (루트 api/ 미의존 — Vercel 번들 안전). 공시 연결은 프론트 client-side 조인.
Vercel 10초 제한 — 페이지 동시 fetch(ThreadPool), pages=2.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import re
import logging
import traceback
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup

_logger = logging.getLogger(__name__)

NEWS_URL = "https://finance.naver.com/item/news_news.naver?code={code}&page={page}"
# 정직 식별 UA (브라우저 위장 제거, 2026-07-01 권리감사 — UA/Referer 위장=접근제어 우회 리스크 회피)
_UA = "VERITY-news-fetcher/1.0 (+https://github.com/gywns0126; 종목 헤드라인 링크아웃)"
# 짬뽕 — 뉴스×공시 연결. 기업이벤트 카테고리 뉴스 ±2일 내 DART 공시 있으면 link (우리 차별점).
DISC_FEED_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/public_disclosure_feed.json"
_EVENT_CATS = {"공시", "실적", "계약·수주", "M&A·지분", "인사"}
_disc_index = None  # {ticker: {date: {title,url}}} 모듈 캐시(콜드 컨테이너당 1회 fetch)

# 출처 신뢰 사전 (news_headlines.CREDIBLE_SOURCES 동기 — 1차 출처 >=4).
CREDIBLE_SOURCES = {
    "한국경제": 5, "매일경제": 5, "서울경제": 4, "조선비즈": 4,
    "이데일리": 4, "머니투데이": 4, "연합뉴스": 5, "뉴스핌": 3,
    "파이낸셜뉴스": 4, "헤럴드경제": 3, "아시아경제": 3, "ZDNet": 3,
    "전자신문": 3, "디지털타임스": 3, "블룸버그": 5, "로이터": 5,
    "연합인포맥스": 5, "한겨레": 3, "중앙일보": 3, "동아일보": 3,
}

# 카테고리 사전 (우선순위 순). 제목 키워드 = 사실 분류(LLM 0).
_CATEGORY_RULES = [
    ("실적", ["실적", "영업이익", "영업손실", "순이익", "매출", "어닝", "잠정실적", "분기 실적", "적자", "흑자전환"]),
    ("공시", ["공시", "유상증자", "무상증자", "자사주", "자기주식", "전환사채", "신주인수권", "배당", "감자"]),
    ("계약·수주", ["수주", "공급계약", "납품", "계약 체결", "수주잔고", "MOU", "협약", "단일판매"]),
    ("M&A·지분", ["인수", "합병", "지분", "최대주주", "매각", "분할", "출자", "경영권"]),
    ("인사", ["대표이사", "사장", "임원", "선임", "사임", "CEO", "회장", "내정"]),
    ("신사업·투자", ["출시", "신제품", "증설", "공장", "개발", "진출", "수출", "특허"]),
]


_STOCKS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "krx_stocks.json"))
_name_map = None


def _resolve_name(code):
    """code → 종목명 (krx_stocks.json, 번들 내). 노이즈 필터 정밀도용. 부재 시 ''."""
    global _name_map
    if _name_map is None:
        try:
            with open(_STOCKS_PATH, encoding="utf-8") as f:
                _name_map = {str(s.get("ticker")): s.get("name") or "" for s in json.load(f)}
        except Exception:  # noqa: BLE001
            _name_map = {}
    return _name_map.get(str(code), "")


def _disclosures_for(code):
    """공시 피드(Blob) 캐시 → 해당 종목 {date(YYYY-MM-DD): {title,url}}. 실패=빈 dict(짬뽕 graceful)."""
    global _disc_index
    if _disc_index is None:
        idx = {}
        try:
            r = requests.get(DISC_FEED_URL, timeout=4)
            for it in (r.json().get("items") or []):
                tk = str(it.get("ticker") or "")
                if not tk:
                    continue
                dd = {}
                for d in (it.get("disclosures") or []):
                    dt = str(d.get("date") or "")
                    if dt and dt not in dd:
                        dd[dt] = {"title": d.get("title"), "url": d.get("source_url")}
                if dd:
                    idx[tk] = dd
            _disc_index = idx
        except Exception as e:  # noqa: BLE001
            _logger.warning("공시 피드 로드 실패: %s", e)
            _disc_index = {}
    return _disc_index.get(str(code), {})


def _related_disclosure(disc_by_date, dt):
    """이벤트 뉴스일(dt) ±2일 내 공시 → {title,url,date} 또는 None."""
    if not dt or not disc_by_date:
        return None
    from datetime import timedelta as _td
    for off in range(-2, 3):
        key = (dt + _td(days=off)).strftime("%Y-%m-%d")
        if key in disc_by_date:
            d = disc_by_date[key]
            return {"title": d["title"], "url": d["url"], "date": key}
    return None


def _category(title):
    t = title or ""
    for label, kws in _CATEGORY_RULES:
        if any(k in t for k in kws):
            return label
    return "시장"


def _norm_title(t):
    t = re.sub(r"\[.*?\]|\(.*?\)|[^가-힣A-Za-z0-9]", "", t or "")
    return t[:24].lower()


def _parse_dt(s):
    try:
        return datetime.strptime((s or "").strip(), "%Y.%m.%d %H:%M")
    except (ValueError, AttributeError):
        return None


def _rel_time(dt, now):
    if not dt:
        return ""
    sec = (now - dt).total_seconds()
    if sec < 0:
        return "방금"
    if sec < 3600:
        return f"{int(sec // 60)}분 전"
    if sec < 86400:
        return f"{int(sec // 3600)}시간 전"
    return f"{int(sec // 86400)}일 전"


# ── 네이버 검색 API (공식) — 2026-07-01 권리감사: 스크래핑/위장 탈출 ──
_NAVER_NEWS_API = "https://openapi.naver.com/v1/search/news.json"
# originallink 도메인 → 매체명 (CREDIBLE_SOURCES 매칭용). 미매칭 = 도메인 fallback.
_DOMAIN_SOURCE = {
    "hankyung.com": "한국경제", "mk.co.kr": "매일경제", "sedaily.com": "서울경제",
    "chosun.com": "조선비즈", "edaily.co.kr": "이데일리", "mt.co.kr": "머니투데이",
    "yna.co.kr": "연합뉴스", "newspim.com": "뉴스핌", "fnnews.com": "파이낸셜뉴스",
    "heraldcorp.com": "헤럴드경제", "asiae.co.kr": "아시아경제", "zdnet.co.kr": "ZDNet",
    "etnews.com": "전자신문", "dt.co.kr": "디지털타임스", "infomax": "연합인포맥스",
    "hani.co.kr": "한겨레", "joongang.co.kr": "중앙일보", "donga.com": "동아일보",
}


def _strip_html(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    for a, b in (("&quot;", '"'), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&#39;", "'"), ("&apos;", "'")):
        s = s.replace(a, b)
    return s.strip()


def _source_from_link(link):
    try:
        host = urlparse(link).netloc.lower().replace("www.", "")
        for dom, nm in _DOMAIN_SOURCE.items():
            if dom in host:
                return nm
        return host.split(".")[0] if host else ""
    except Exception:  # noqa: BLE001
        return ""


def _fetch_search_api(name, display=30):
    """네이버 검색 API(공식·ToS-OK) — 종목명 키워드. 스크래핑/UA위장 대체(권리감사 쟁점5).
    키 = NAVER_Client_ID / NAVER_Client_Secret (Vercel env 등록 필요)."""
    cid = os.environ.get("NAVER_Client_ID") or os.environ.get("NAVER_CLIENT_ID", "")
    csec = os.environ.get("NAVER_Client_Secret") or os.environ.get("NAVER_CLIENT_SECRET", "")
    if not name or not cid or not csec:
        return []
    try:
        r = requests.get(
            _NAVER_NEWS_API,
            params={"query": name, "display": display, "sort": "date"},
            headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec},
            timeout=5,
        )
        if not r.ok:
            _logger.warning("naver search api %s HTTP %s", name, r.status_code)
            return []
        out = []
        for it in r.json().get("items", []):
            link = it.get("originallink") or it.get("link") or ""
            dt_s = ""
            try:
                from email.utils import parsedate_to_datetime
                from datetime import timezone as _tz
                pd = parsedate_to_datetime(it.get("pubDate", ""))
                if pd:  # now=datetime.now()(UTC) 과 정합 위해 UTC naive 로
                    dt_s = pd.astimezone(_tz.utc).replace(tzinfo=None).strftime("%Y.%m.%d %H:%M")
            except Exception:  # noqa: BLE001
                pass
            out.append({
                "title": _strip_html(it.get("title")),
                "url": link,
                "source": _source_from_link(link),
                "datetime": dt_s,
            })
        return out
    except Exception as e:  # noqa: BLE001
        _logger.warning("naver search api %s 실패: %s", name, e)
        return []


# ── Google News RSS (종목명 키워드, 무료·헤드라인+링크아웃) — 2번째 온디맨드 소스 (2026-07-06 소스확장) ──
# 네이버 검색 API 미인덱스분 + 비네이버 매체 보강. RSS=헤드라인+링크아웃(권리 안전, news_headlines 동일 관행).
_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
_GN_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.DOTALL)
_GN_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.DOTALL)
_GN_LINK_RE = re.compile(r"<link>(.*?)</link>", re.DOTALL)
_GN_DATE_RE = re.compile(r"<pubDate>(.*?)</pubDate>", re.DOTALL)
_GN_SRC_RE = re.compile(r"<source[^>]*>(.*?)</source>", re.DOTALL)


def _fetch_google_news(query, limit=20):
    """Google News RSS(종목명 키워드) — 헤드라인+링크아웃. 정규식 파싱(lxml 미의존)."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        r = requests.get(_GOOGLE_NEWS_RSS,
                         params={"q": q, "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
                         headers={"User-Agent": "VERITY-news-fetcher/1.0 (+https://github.com/gywns0126)"}, timeout=5)
        if not r.ok:
            return []
        out = []
        for block in _GN_ITEM_RE.findall(r.text)[:limit]:
            tm = _GN_TITLE_RE.search(block)
            title = _strip_html(tm.group(1)) if tm else ""
            if not title:
                continue
            sm = _GN_SRC_RE.search(block)
            source = _strip_html(sm.group(1)) if sm else ""
            if source:  # Google title 끝 " - 매체" 접미사 제거 (하이픈/대시 변형 flex)
                title = re.sub(r"\s*[-–—]\s*" + re.escape(source) + r"\s*$", "", title).strip()
            lm = _GN_LINK_RE.search(block)
            url = _strip_html(lm.group(1)) if lm else ""
            dt_s = ""
            dm = _GN_DATE_RE.search(block)
            if dm:
                try:
                    from email.utils import parsedate_to_datetime
                    from datetime import timezone as _tz
                    pd = parsedate_to_datetime(dm.group(1).strip())
                    if pd:
                        dt_s = pd.astimezone(_tz.utc).replace(tzinfo=None).strftime("%Y.%m.%d %H:%M")
                except Exception:  # noqa: BLE001
                    pass
            out.append({"title": title, "url": url, "source": source, "datetime": dt_s})
        return out
    except Exception as e:  # noqa: BLE001
        _logger.warning("google news %s 실패: %s", query, e)
        return []


def _name_in_title(name, title):
    """종목명이 제목에 '단어 경계'로 등장하는지 — 앞 글자가 한글/영숫자면 다른 단어의 꼬리.
    예: '하이닉스' 제목에 '이닉스' 검색 = 하[이닉스] 부분매칭 → 오매칭(2026-07-10 사용자 보고).
    한국어는 조사(가/는/도)가 이름 뒤에 바로 붙으므로 뒤 경계는 검사하지 않음."""
    if not name or not title:
        return False
    try:
        return re.search(r"(?<![가-힣A-Za-z0-9])" + re.escape(name), title) is not None
    except re.error:
        return name in title


def fetch_stock_news(code, name="", max_items=15, pages=2):
    now = datetime.utcnow()  # dt_s(UTC naive)와 정합 (Vercel/로컬 TZ 무관)
    nm = (name or "").strip()
    # 종목명 핵심 토큰 (접미사 제거) — "JYP Ent."→"JYP", 한국 뉴스 제목 매칭률↑
    core = re.sub(r"\s*(Ent\.?|Corp\.?|Inc\.?|Co\.?,?\s*Ltd\.?|Ltd\.?|Holdings|홀딩스|그룹|㈜)\s*$",
                  "", nm, flags=re.IGNORECASE).strip()
    if " " in core:
        core = core.split()[0]
    # 온디맨드 2소스 병렬 (네이버 검색 API + Google News RSS) — 10초 예산 내, 커버리지·화제성↑
    raw = []
    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_naver = ex.submit(_fetch_search_api, nm, 30)
            f_google = ex.submit(_fetch_google_news, core or nm)
            raw = (f_naver.result() or []) + (f_google.result() or [])
    except Exception as e:  # noqa: BLE001
        _logger.warning("news 병렬 fetch 실패: %s", e)
        raw = _fetch_search_api(nm, 30)
    clusters = {}
    for it in raw:
        if not it["title"]:
            continue
        key = _norm_title(it["title"])
        if not key:
            continue
        cred = CREDIBLE_SOURCES.get((it["source"] or "").strip(), 2)
        dt = _parse_dt(it["datetime"])
        c = clusters.get(key)
        if c is None:
            clusters[key] = {"item": it, "cred": cred, "dt": dt, "outlets": {it["source"]}}
        else:
            c["outlets"].add(it["source"])
            if cred > c["cred"]:
                c["item"], c["cred"], c["dt"] = it, cred, dt

    disc = _disclosures_for(code)  # 짬뽕 — 종목 공시 인덱스
    kept, spill = [], []
    for c in clusters.values():
        it, dt = c["item"], c["dt"]
        cat = _category(it["title"])
        related = _related_disclosure(disc, dt) if cat in _EVENT_CATS else None
        rec = {
            "title": it["title"], "url": it["url"], "source": it["source"], "category": cat,
            "credibility": c["cred"], "credible": c["cred"] >= 4, "outlets": len(c["outlets"]),
            "datetime": it["datetime"], "rel_time": _rel_time(dt, now),
            "related_disclosure": related,
            "_sort": dt.timestamp() if dt else 0,
        }
        # 노이즈 판정 (2026-07-10 경계매칭 강화 — 이닉스 페이지에 하이닉스 기사 유입 fix):
        #  · 제목에 핵심토큰이 '부분매칭으로만' 존재(하[이닉스]) = 다른 종목 기사 강신호 → 카테고리 무관 spill
        #  · '시장' 카테고리 + 경계매칭 없음 → spill (기존 룰의 경계 강화)
        #  · 제목에 토큰 자체가 없는 비'시장' 기사 = 검색 질의 연관성 신뢰(기존 동작 유지)
        _embedded_only = bool(core) and (core in it["title"]) and not _name_in_title(core, it["title"])
        _market_nomatch = cat == "시장" and bool(core) and not _name_in_title(core, it["title"])
        (spill if (_embedded_only or _market_nomatch) else kept).append(rec)

    kept.sort(key=lambda x: x["_sort"], reverse=True)
    spill.sort(key=lambda x: x["_sort"], reverse=True)
    out = kept if len(kept) >= 6 else kept + spill   # soft filter — 과필터로 빈약해지면 노이즈도 보충
    for o in out:
        o.pop("_sort", None)
    return out[:max_items]


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            code = (qs.get("code", [""])[0] or qs.get("q", [""])[0] or "").strip()
            name = (qs.get("name", [""])[0] or "").strip() or _resolve_name(code)
            if not re.fullmatch(r"\d{6}", code):
                body = json.dumps({"error": "code=6자리 종목코드 필요", "items": []}, ensure_ascii=False)
                cache = "no-store"
            else:
                items = fetch_stock_news(code, name)
                body = json.dumps({"code": code, "count": len(items), "items": items,
                                   "note": "네이버 금융 종목뉴스 · 사실만(점수·추천 아님)"}, ensure_ascii=False)
                cache = "public, max-age=300, s-maxage=300"  # 5분 — Naver 부하·차단 완화
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            _logger.error("stock_news error: %s\n%s", exc, traceback.format_exc())
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "서버 오류", "items": []}, ensure_ascii=False).encode("utf-8"))

# deploy: 짬뽕 엔드포인트(news×disclosure) 활성화 — HEAD가 vercel-api 변경이라야 ignoreCommand 통과(RULE2)
