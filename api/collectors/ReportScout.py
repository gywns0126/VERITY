"""
ReportScout — 증권사 애널리스트 리포트 메타데이터 + PDF URL 수집기

소스:
  1) 네이버 금융 리서치 (EUC-KR encoding)
     - 기업: finance.naver.com/research/company_list.naver
     - 산업: finance.naver.com/research/industry_list.naver
  2) 한경 컨센서스 (graceful fallback — 404/구조변경 시 빈 list)
     - consensus.hankyung.com/apps.analysis/analysis.list

설계 원칙:
  - PDF는 URL 만 수집 — 실 다운로드는 download_report_pdf() 별도 호출
  - 종목명 → ticker 매핑은 네이버 page 의 ?code= 직접 추출 (이름 fuzzy 매칭 우회)
  - ticker6 → ticker_yf (.KS/.KQ) 는 stock_data.ALL_STOCKS_WITH_US 역매핑
  - DartScout 의 _SESSION (Retry + HTTPAdapter) 패턴 동일
  - API_DELAY = 1.0s, 페이지네이션 max 5
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

# ─── 상수 ───────────────────────────────────────────────

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}

TIMEOUT = 15
API_DELAY = 1.0
MAX_PAGES = 5
DEFAULT_LOOKBACK_DAYS = 7

NAVER_COMPANY_LIST = "https://finance.naver.com/research/company_list.naver"
NAVER_INDUSTRY_LIST = "https://finance.naver.com/research/industry_list.naver"
NAVER_BASE = "https://finance.naver.com/research/"

HANKYUNG_LIST = "http://consensus.hankyung.com/apps.analysis/analysis.list"

REPORTS_DIR = os.path.join(DATA_DIR, "reports")
OUTPUT_PATH = os.path.join(DATA_DIR, "analyst_reports.json")

# Session + Retry (DartScout 패턴)
_SESSION = requests.Session()
_SESSION.mount("https://", HTTPAdapter(
    max_retries=Retry(total=3, backoff_factor=1.5,
                      status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["GET"]),
    pool_connections=4, pool_maxsize=4,
))
_SESSION.mount("http://", HTTPAdapter(
    max_retries=Retry(total=2, backoff_factor=1.5,
                      status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["GET"]),
    pool_connections=2, pool_maxsize=2,
))

os.makedirs(REPORTS_DIR, exist_ok=True)


# ─── 헬퍼 ────────────────────────────────────────────────


def _parse_date(text: str) -> Optional[str]:
    """26.04.17 → 2026-04-17. YYYY-MM-DD / YYYY.MM.DD 도 지원."""
    s = (text or "").strip()
    m = re.match(r"^(\d{2})\.(\d{1,2})\.(\d{1,2})$", s)
    if m:
        yy = int(m.group(1))
        year = 2000 + yy if yy < 50 else 1900 + yy
        return f"{year:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"^(\d{4})[-\.](\d{1,2})[-\.](\d{1,2})$", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def _parse_int(text: str) -> Optional[int]:
    s = re.sub(r"[^\d\-]", "", (text or "").replace(",", ""))
    if not s or s == "-":
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _extract_ticker_from_naver_url(href: str) -> Optional[str]:
    """/item/main.naver?code=010950 → 010950"""
    try:
        qs = parse_qs(urlparse(href).query)
        code = qs.get("code", [None])[0]
        if code and re.match(r"^\d{6}$", code):
            return code
    except Exception:
        pass
    return None


def _resolve_ticker_to_yf(ticker6: str) -> Optional[str]:
    """6자리 KR 코드 → yfinance ticker (.KS / .KQ).
    ALL_STOCKS_WITH_US 에 등록된 종목만 매핑. 없으면 None.
    """
    try:
        from api.collectors.stock_data import ALL_STOCKS_WITH_US
        for t_yf in ALL_STOCKS_WITH_US:
            if t_yf.startswith(ticker6 + "."):
                return t_yf
    except ImportError:
        pass
    return None


def _absolutize(url: str, base: str = NAVER_BASE) -> str:
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        # base 의 도메인 부분만
        p = urlparse(base)
        return f"{p.scheme}://{p.netloc}{url}"
    return base + url


# ─── 네이버 기업 리포트 ──────────────────────────────────


def fetch_naver_company_reports(
    bgn_date: str, end_date: str, max_pages: int = MAX_PAGES,
) -> List[Dict[str, Any]]:
    """네이버 금융 기업 리포트 수집.

    HTML 표 구조 (table.type_1):
      td[0]=종목명+/item/main.naver?code link
      td[1]=제목
      td[2]=증권사
      td[3]=PDF download icon (a href=...pdf)
      td[4]=날짜 (YY.MM.DD)
      td[5]=조회수
    """
    out: List[Dict[str, Any]] = []
    seen = set()
    for page in range(1, max_pages + 1):
        try:
            r = _SESSION.get(NAVER_COMPANY_LIST, params={"page": page},
                             headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            r.encoding = "euc-kr"
        except Exception as e:
            logger.warning("[Naver Company] page %d fetch 실패: %s", page, e)
            break

        soup = BeautifulSoup(r.text, "html.parser")
        tables = [t for t in soup.find_all("table") if "type_1" in (t.get("class") or [])]
        if not tables:
            logger.warning("[Naver Company] page %d: type_1 table 부재 — 사이트 구조 변경?", page)
            break

        rows = tables[0].find_all("tr")
        page_added = 0
        page_oldest: Optional[str] = None
        for row in rows:
            tds = row.find_all("td")
            if len(tds) < 6:
                continue

            company_a = tds[0].find("a", href=True)
            company_name = tds[0].get_text(strip=True)
            ticker6 = _extract_ticker_from_naver_url(company_a["href"]) if company_a else None

            title = tds[1].get_text(strip=True)
            firm = tds[2].get_text(strip=True)

            pdf_url = None
            for a in row.find_all("a", href=True):
                href = a["href"]
                if href.lower().endswith(".pdf"):
                    pdf_url = _absolutize(href)
                    break

            date_str = _parse_date(tds[4].get_text(strip=True))
            if not date_str:
                continue
            page_oldest = date_str
            if not (bgn_date <= date_str <= end_date):
                continue

            ticker_yf = _resolve_ticker_to_yf(ticker6) if ticker6 else None
            key = (pdf_url, title, date_str)
            if key in seen:
                continue
            seen.add(key)

            out.append({
                "source": "naver",
                "ticker": ticker6,
                "ticker_yf": ticker_yf,
                "company_name": company_name,
                "title": title,
                "firm": firm,
                "author": None,
                "date": date_str,
                "target_price": None,
                "opinion": None,
                "pdf_url": pdf_url,
                "view_count": _parse_int(tds[5].get_text(strip=True)),
            })
            page_added += 1

        logger.info("[Naver Company] page %d: +%d (oldest %s)", page, page_added, page_oldest)
        if page_oldest and page_oldest < bgn_date:
            break
        time.sleep(API_DELAY)
    return out


# ─── 네이버 산업 리포트 ──────────────────────────────────


def fetch_naver_industry_reports(
    bgn_date: str, end_date: str, max_pages: int = MAX_PAGES,
) -> List[Dict[str, Any]]:
    """네이버 금융 산업 리포트 수집.

    PDF URL 직접 없을 시 industry_read.naver?nid=... read_url 만 저장
    (다운로드 시 read 페이지 통해 추가 fetch 가능).
    """
    out: List[Dict[str, Any]] = []
    seen = set()
    for page in range(1, max_pages + 1):
        try:
            r = _SESSION.get(NAVER_INDUSTRY_LIST, params={"page": page},
                             headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            r.encoding = "euc-kr"
        except Exception as e:
            logger.warning("[Naver Industry] page %d 실패: %s", page, e)
            break

        soup = BeautifulSoup(r.text, "html.parser")
        tables = [t for t in soup.find_all("table") if "type_1" in (t.get("class") or [])]
        if not tables:
            break

        rows = tables[0].find_all("tr")
        page_added = 0
        page_oldest: Optional[str] = None
        for row in rows:
            tds = row.find_all("td")
            if len(tds) < 6:
                continue
            sector = tds[0].get_text(strip=True)
            title = tds[1].get_text(strip=True)
            firm = tds[2].get_text(strip=True)
            date_str = _parse_date(tds[4].get_text(strip=True))
            if not date_str:
                continue
            page_oldest = date_str
            if not (bgn_date <= date_str <= end_date):
                continue

            pdf_url = None
            read_url = None
            for a in row.find_all("a", href=True):
                href = a["href"]
                if href.lower().endswith(".pdf"):
                    pdf_url = _absolutize(href)
                    break
                if "industry_read.naver" in href:
                    read_url = _absolutize(href)

            key = (pdf_url or read_url, title, date_str)
            if key in seen:
                continue
            seen.add(key)

            out.append({
                "source": "naver",
                "sector": sector,
                "title": title,
                "firm": firm,
                "date": date_str,
                "pdf_url": pdf_url,
                "read_url": read_url,
                "view_count": _parse_int(tds[5].get_text(strip=True)),
            })
            page_added += 1

        logger.info("[Naver Industry] page %d: +%d (oldest %s)", page, page_added, page_oldest)
        if page_oldest and page_oldest < bgn_date:
            break
        time.sleep(API_DELAY)
    return out


# ─── 한경 컨센서스 (graceful fallback) ──────────────────────


def fetch_hankyung_reports(
    bgn_date: str, end_date: str, max_pages: int = MAX_PAGES,
) -> List[Dict[str, Any]]:
    """한경 컨센서스. 사이트 접근 실패/구조 변경 시 빈 list (로그)."""
    out: List[Dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        try:
            r = _SESSION.get(HANKYUNG_LIST, params={
                "sdate": bgn_date, "edate": end_date,
                "report_type": "CO", "now_page": page,
            }, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code != 200:
                logger.warning("[Hankyung] page %d status %d — graceful skip", page, r.status_code)
                return out
            r.encoding = "euc-kr"
        except Exception as e:
            logger.warning("[Hankyung] page %d 실패: %s — graceful skip", page, e)
            return out

        soup = BeautifulSoup(r.text, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            return out

        target = None
        for t in tables:
            for row in t.find_all("tr"):
                if len(row.find_all("td")) >= 6:
                    target = t
                    break
            if target:
                break
        if target is None:
            logger.info("[Hankyung] page %d: 데이터 표 미발견 (구조 변경?)", page)
            return out

        rows = target.find_all("tr")
        page_added = 0
        for row in rows:
            tds = row.find_all("td")
            if len(tds) < 6:
                continue
            try:
                date_str = _parse_date(tds[0].get_text(strip=True))
                if not date_str or not (bgn_date <= date_str <= end_date):
                    continue
                company_name = tds[1].get_text(strip=True)
                ticker_raw = tds[2].get_text(strip=True)
                ticker6 = ticker_raw if re.match(r"^\d{6}$", ticker_raw) else None
                title = tds[3].get_text(strip=True)
                target_price = _parse_int(tds[4].get_text(strip=True)) if len(tds) > 4 else None
                opinion = tds[5].get_text(strip=True) if len(tds) > 5 else None
                author = tds[6].get_text(strip=True) if len(tds) > 6 else None
                firm = tds[7].get_text(strip=True) if len(tds) > 7 else None

                pdf_url = None
                for a in row.find_all("a", href=True):
                    href = a["href"]
                    if href.lower().endswith(".pdf") or "down" in href.lower():
                        pdf_url = href if href.startswith("http") else f"http://consensus.hankyung.com{href}"
                        break

                ticker_yf = _resolve_ticker_to_yf(ticker6) if ticker6 else None

                out.append({
                    "source": "hankyung",
                    "ticker": ticker6,
                    "ticker_yf": ticker_yf,
                    "company_name": company_name,
                    "title": title,
                    "firm": firm,
                    "author": author,
                    "date": date_str,
                    "target_price": target_price,
                    "opinion": opinion,
                    "pdf_url": pdf_url,
                })
                page_added += 1
            except Exception as e:
                logger.debug("[Hankyung] row parse 실패: %s", e)
                continue

        logger.info("[Hankyung] page %d: +%d", page, page_added)
        if page_added == 0:
            break
        time.sleep(API_DELAY)
    return out


# ─── 메인 진입점 ────────────────────────────────────────


def scout_reports(
    bgn_date: Optional[str] = None,
    end_date: Optional[str] = None,
    max_pages: int = MAX_PAGES,
) -> Dict[str, Any]:
    """증권사 리포트 종합 수집.

    Args:
        bgn_date / end_date: YYYY-MM-DD. None 이면 오늘 ~ 7일 전.
    Returns:
        company_reports + industry_reports + stats payload.
        data/analyst_reports.json 에 atomic 저장.
    """
    today = now_kst().date()
    if not end_date:
        end_date = today.strftime("%Y-%m-%d")
    if not bgn_date:
        bgn_date = (today - timedelta(days=DEFAULT_LOOKBACK_DAYS)).strftime("%Y-%m-%d")

    company_naver = fetch_naver_company_reports(bgn_date, end_date, max_pages)
    industry_naver = fetch_naver_industry_reports(bgn_date, end_date, max_pages)
    company_hk = fetch_hankyung_reports(bgn_date, end_date, max_pages)

    company_reports = company_naver + company_hk

    payload = {
        "updated_at": now_kst().isoformat(),
        "date_range": {"bgn": bgn_date, "end": end_date},
        "company_reports": company_reports,
        "industry_reports": industry_naver,
        "stats": {
            "company_total": len(company_reports),
            "company_naver": len(company_naver),
            "company_hankyung": len(company_hk),
            "industry_total": len(industry_naver),
            "with_ticker": sum(1 for r in company_reports if r.get("ticker")),
            "with_ticker_yf": sum(1 for r in company_reports if r.get("ticker_yf")),
            "with_pdf": sum(1 for r in company_reports if r.get("pdf_url")),
        },
    }

    tmp = OUTPUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, OUTPUT_PATH)

    return payload


# ─── PDF 다운로드 (분석기 호출용) ────────────────────────


def download_report_pdf(
    url: str,
    save_dir: Optional[str] = None,
    filename: Optional[str] = None,
    overwrite: bool = False,
) -> Optional[str]:
    """리포트 PDF 다운로드. 이미 존재하면 스킵 (overwrite=False).

    Args:
        url: PDF URL
        save_dir: 저장 디렉터리 (default: data/reports/)
        filename: 파일명 (default: URL basename, 또는 자동 생성)
        overwrite: 기존 파일 덮어쓰기 여부

    Returns:
        저장된 파일 절대 경로. 실패 시 None.
    """
    if not url:
        return None
    save_dir = save_dir or REPORTS_DIR
    os.makedirs(save_dir, exist_ok=True)

    if not filename:
        filename = os.path.basename(urlparse(url).path) or f"report_{int(time.time())}.pdf"
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"

    path = os.path.join(save_dir, filename)
    if os.path.exists(path) and not overwrite:
        return path

    try:
        r = _SESSION.get(url, headers=HEADERS, timeout=30, stream=True)
        r.raise_for_status()
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        os.replace(tmp, path)
        return path
    except Exception as e:
        logger.warning("[PDF] 다운로드 실패 %s: %s", url, e)
        return None


# ─── CLI 진입점 ─────────────────────────────────────────


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    import sys
    bgn = sys.argv[1] if len(sys.argv) > 1 else None
    end = sys.argv[2] if len(sys.argv) > 2 else None
    result = scout_reports(bgn, end)
    print()
    print("=" * 60)
    print(f"Stats — {result['date_range']['bgn']} ~ {result['date_range']['end']}")
    print("=" * 60)
    for k, v in result["stats"].items():
        print(f"  {k:>20}: {v}")
    print()
    print("샘플 (기업 리포트 첫 5건):")
    for r in result["company_reports"][:5]:
        print(f"  {r['date']} | {r.get('ticker') or '------'} {r['company_name'][:14]:14s} | "
              f"{r['firm'][:10]:10s} | {r['title'][:42]}")
    print()
    print(f"저장: {OUTPUT_PATH}")
