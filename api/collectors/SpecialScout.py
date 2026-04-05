"""
SpecialScout — RRA 전파 적합성평가(인증) 현황 + KIPRIS 출원인 특허 메타 수집

- RRA: 적합성평가 현황 검색(상호 + 최근 1개월 인증일). 공식 /ko/license/list.do 는
  비브라우저 접근 시 213 오류가 나는 경우가 있어, 동일 DB를 쓰는 A_c_search_view.do POST 를 사용한다.
- KIPRIS: plus.kipris.or.kr applicantNameSearchInfo REST (XML). 환경변수 KIPRIS_API_KEY 필요.
  초록·명세 전문은 요청하지 않고 발명의 명칭·출원번호·출원일만 저장한다.

병합: data/raw_data.json 의 각 종목 dict 에 rra_data, patent_data 키만 갱신한다.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote, urlencode

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# cwd와 무관하게 프로젝트 루트의 .env 로드
_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api.config import DATA_DIR, now_kst

MAPPING_PATH = os.path.join(DATA_DIR, "mapping.json")
RAW_DATA_PATH = os.path.join(DATA_DIR, "raw_data.json")

# RRA HTML 은 euc-kr
RRA_REFERER = "https://www.rra.go.kr/ko/license/A_c_search.do"
RRA_RESULT_URL = "https://www.rra.go.kr/ko/license/A_c_search_view.do"

KIPRIS_APPLICANT_URL = (
    "http://plus.kipris.or.kr/openapi/rest/patUtiModInfoSearchSevice/applicantNameSearchInfo"
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

REQUEST_PAUSE_SEC = 0.85
MAX_PATENT_ROWS = 20
RRA_MONTHS = 1


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    })
    return s


def company_name_variants(name: str) -> List[str]:
    """상호에 '주식회사' 유무를 바꾼 검색 후보(중복 제거, 순서 유지)."""
    n = (name or "").strip()
    if not n:
        return []
    out: List[str] = []
    seen: Set[str] = set()

    def add(x: str) -> None:
        x = x.strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)

    add(n)
    suffixes = ("주식회사", "(주)", "㈜")
    for suf in suffixes:
        if n.endswith(suf):
            add(n[: -len(suf)].strip())
            break
    else:
        add(n + "주식회사")
        add("(주)" + n)
    return out


def _parse_rra_cert_date(raw: str) -> Optional[date]:
    s = (raw or "").strip()
    if not s:
        return None
    s = s.replace(".", "").replace("-", "").replace("/", "")
    if len(s) >= 8 and s[:8].isdigit():
        y, m, d = int(s[:4]), int(s[4:6]), int(s[6:8])
        try:
            return date(y, m, d)
        except ValueError:
            return None
    m2 = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", raw)
    if m2:
        try:
            return date(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
        except ValueError:
            return None
    return None


def _rra_date_range(months: int = RRA_MONTHS) -> Tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=30 * months)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def fetch_rra_rows(session: requests.Session, firm: str) -> List[Dict[str, str]]:
    """
    상호 firm 으로 적합성평가 현황 검색. 최근 RRA_MONTHS 개월 구간 POST.
    반환: { equipment_name, model_name, cert_date } (인증일은 YYYY-MM-DD)
    """
    from_d, to_d = _rra_date_range()
    data = {
        "category": "",
        "fromdate": from_d,
        "todate": to_d,
        "firm": firm,
        "equip": "",
        "model_no": "",
        "app_no": "",
        "maker": "",
        "nation": "",
    }
    session.headers["Referer"] = RRA_REFERER
    r = session.post(RRA_RESULT_URL, data=data, timeout=45)
    r.raise_for_status()

    enc = r.apparent_encoding or "euc-kr"
    html = r.content.decode(enc, errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    tbl = soup.find("table", class_="table_organ0")
    if not tbl:
        return []

    thead = tbl.find("thead")
    tbody = tbl.find("tbody")
    if not tbody:
        return []

    headers: List[str] = []
    if thead:
        hr = thead.find("tr")
        if hr:
            headers = [th.get_text(strip=True) for th in hr.find_all(["th", "td"])]

    # 기대 헤더: 상호, 기자재명칭, 모델명, ...
    col_idx = {h: i for i, h in enumerate(headers)} if headers else {}

    def idx(name: str, fallback: int) -> int:
        return col_idx.get(name, fallback)

    i_eq = idx("기자재명칭", 1)
    i_mo = idx("모델명", 2)
    i_dt = idx("날짜", 4)

    rows_out: List[Dict[str, str]] = []
    start_dt = datetime.strptime(from_d, "%Y%m%d").date()
    end_dt = datetime.strptime(to_d, "%Y%m%d").date()

    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        if tds[0].get("colspan"):
            continue
        if len(tds) < 4:
            continue

        def cell(i: int) -> str:
            if i < len(tds):
                return tds[i].get_text(strip=True)
            return ""

        equip = cell(i_eq)
        model = cell(i_mo)
        d_raw = cell(i_dt)
        parsed = _parse_rra_cert_date(d_raw)
        if parsed is None:
            continue
        if not (start_dt <= parsed <= end_dt):
            continue
        rows_out.append({
            "equipment_name": equip,
            "model_name": model,
            "cert_date": parsed.isoformat(),
        })
    return rows_out


def fetch_rra_for_company(session: requests.Session, names: List[str]) -> List[Dict[str, str]]:
    """여러 상호 후보로 검색해 합치고, equipment+model+cert_date 기준 중복 제거."""
    merged: Dict[Tuple[str, str, str], Dict[str, str]] = {}
    for nm in names:
        if not nm:
            continue
        for row in fetch_rra_rows(session, nm):
            key = (row["equipment_name"], row["model_name"], row["cert_date"])
            merged[key] = row
        time.sleep(REQUEST_PAUSE_SEC)
    return list(merged.values())


def _local_tag(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _child_text(parent: ET.Element, *local_names: str) -> str:
    want = set(local_names)
    for ch in parent:
        if _local_tag(ch.tag) in want:
            t = (ch.text or "").strip()
            if t:
                return t
    return ""


def _kipris_items_from_xml(content: str) -> List[ET.Element]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []
    items: List[ET.Element] = []
    for el in root.iter():
        if _local_tag(el.tag) == "PatentUtilityInfo":
            items.append(el)
    return items


def fetch_kipris_patents(applicant: str, api_key: str) -> List[Dict[str, str]]:
    """출원인명 검색. inventionTitle / applicationNumber / applicationDate 만 추출."""
    if not api_key or not applicant:
        return []

    q = urlencode(
        {
            "applicant": applicant,
            "docsStart": "1",
            "docsCount": str(MAX_PATENT_ROWS),
            "patent": "true",
            "utility": "true",
            "lastvalue": "",
            "sortSpec": "AD",
            "descSort": "false",
            "accessKey": api_key,
        },
        quote_via=quote,
        safe="",
    )
    url = f"{KIPRIS_APPLICANT_URL}?{q}"
    r = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    r.raise_for_status()

    items = _kipris_items_from_xml(r.text)
    out: List[Dict[str, str]] = []
    for it in items:
        title = _child_text(
            it,
            "inventionTitle",
            "InventionTitle",
            "patentName",
            "PatentName",
            "title",
        )
        app_no = _child_text(
            it,
            "applicationNumber",
            "ApplicationNumber",
            "appReferenceNumber",
            "AppReferenceNumber",
        )
        app_dt = _child_text(
            it,
            "applicationDate",
            "ApplicationDate",
            "filingDate",
            "FilingDate",
        )
        if not title and not app_no:
            continue
        row = {
            "invention_title": title,
            "application_number": app_no,
            "application_date": app_dt,
        }
        out.append(row)
    return out


def fetch_patents_for_company(names: List[str], api_key: str) -> List[Dict[str, str]]:
    if not api_key:
        return []
    by_key: Dict[Tuple[str, str], Dict[str, str]] = {}
    for nm in names:
        if not nm:
            continue
        for row in fetch_kipris_patents(nm, api_key):
            k = (
                row.get("application_number") or "",
                row.get("invention_title") or "",
            )
            if not any(k):
                continue
            if k in by_key:
                continue
            by_key[k] = row
        time.sleep(REQUEST_PAUSE_SEC)
    return list(by_key.values())


def load_mapping_tickers(mapping_path: str) -> Set[str]:
    if not os.path.isfile(mapping_path):
        return set()
    with open(mapping_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return set()
    return set(data.keys())


def merge_special_scout_into_raw(
    raw: Dict[str, Any],
    ticker: str,
    rra_data: List[Dict[str, str]],
    patent_data: List[Dict[str, str]],
) -> None:
    stocks = raw.setdefault("stocks", {})
    if ticker not in stocks:
        return
    block = stocks[ticker]
    if not isinstance(block, dict):
        return
    block["rra_data"] = rra_data
    block["patent_data"] = patent_data
    block["special_scout_at"] = now_kst().isoformat()


def run_special_scout(
    raw_path: str = RAW_DATA_PATH,
    mapping_path: str = MAPPING_PATH,
) -> Dict[str, Any]:
    """
    mapping.json 에 등록된 티커 중, raw_data.json 에 존재하는 종목만 스카우트 후 병합 저장.
    기업명은 raw_data 의 name 필드를 사용한다.
    """
    if not os.path.isfile(raw_path):
        raise FileNotFoundError(raw_path)

    with open(raw_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    mapping_tickers = load_mapping_tickers(mapping_path)
    if not mapping_tickers:
        print("[SpecialScout] 경고: mapping.json 이 없거나 비어 있습니다. raw_data 내 모든 종목을 대상으로 합니다.")
        mapping_tickers = set(raw.get("stocks") or [])

    stocks: Dict[str, Any] = raw.get("stocks") or {}
    kipris_key = (os.environ.get("KIPRIS_API_KEY") or os.environ.get("KIPRIS_ACCESS_KEY") or "").strip()

    if not kipris_key:
        print(
            "[SpecialScout] 알림: KIPRIS_API_KEY(또는 KIPRIS_ACCESS_KEY) 미설정 — "
            "특허는 수집하지 않습니다. KIPRIS Plus(plus.kipris.or.kr) 에서 발급 후 .env 에 추가하세요."
        )

    session = _session()
    raw["special_scout_updated_at"] = now_kst().isoformat()

    for ticker, block in list(stocks.items()):
        if mapping_tickers and ticker not in mapping_tickers:
            continue
        if not isinstance(block, dict):
            continue
        name = (block.get("name") or "").strip()
        if not name:
            print(f"[SpecialScout] {ticker}: 종목명(name) 없음 — 건너뜀")
            continue

        variants = company_name_variants(name)
        try:
            rra_list = fetch_rra_for_company(session, variants)
        except Exception as e:
            print(f"[SpecialScout] {name}({ticker}): RRA 오류 — {e}")
            rra_list = []

        if kipris_key:
            try:
                patent_list = fetch_patents_for_company(variants, kipris_key)
            except Exception as e:
                print(f"[SpecialScout] {name}({ticker}): KIPRIS 오류 — {e}")
                patent_list = []
        else:
            patent_list = []

        merge_special_scout_into_raw(raw, ticker, rra_list, patent_list)

        if len(rra_list) > 0:
            print(f"[SpecialScout] {name} 신규 인증 {len(rra_list)}건 발견 ({ticker})")
        else:
            print(f"[SpecialScout] {name}: RRA 최근 구간 조회 {len(rra_list)}건 ({ticker})")

        if kipris_key:
            print(f"[SpecialScout] {name}: 특허 메타 {len(patent_list)}건 수집 ({ticker})")

        time.sleep(REQUEST_PAUSE_SEC)

    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)

    return raw


if __name__ == "__main__":
    print("SpecialScout — RRA + KIPRIS 병합 수집 시작...")
    run_special_scout()
    print(f"완료 → {RAW_DATA_PATH}")
