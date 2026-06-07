"""
ipo_prospectus_parser — 증권신고서(지분증권) 문서 본문 파서 (IPO watch v0.1)

DART document.xml 원문 ZIP 을 받아 HTML 표를 직접 파싱한다.
flattened 텍스트 regex 보다 표 단위 라벨 추출이 견고 (한 문서 1500+ 표, 병합셀 多).

추출 필드:
  - stage          : report_nm 기반 lifecycle (최초/정정/확정)
  - offering        : 공모주식수, 주당 모집가액(예정·확정), 모집총액(예정·확정),
                      청약기일(시작~종료), 납입기일
  - summary_fin     : 발행사 요약손익 (매출액/영업이익/당기순이익, 사업연도별) — best-effort

표준 서식 근거 (Perplexity 2026-06-07 + DART 실물 매드업/스트라드비젼 검증):
  - 공모가·청약일 = 제1부 Ⅰ "모집 또는 매출 조건" 표 (라벨: 주당 모집가액 / 모집총액 /
    청약기일 / 납입기일). "예정가액→확정가액" 전환은 [발행조건확정] 정정신고서 시점.
  - 요약재무 = 제2부 Ⅲ. 헤더에 "(제N기)" 기수 표기 = 발행사 자기 표 (비교기업 peer 표와 구분).

⚠️ 검증 한계 (RULE 7): 상장 전 데이터 = 가설. watch 보강용일 뿐 추천 근거 아님.
"""
import io
import re
import warnings
import zipfile
from typing import Any, Dict, List, Optional

import requests

from api.config import DART_API_KEY

DOC_URL = "https://opendart.fss.or.kr/api/document.xml"

# 공모 조건 표 라벨 (공백·"주N)" 제거 후 정규화 매칭)
_OFFER_ANCHORS = ("주당모집가액", "모집총액", "청약기일", "납입기일", "모집또는매출주식의수")


def classify_stage(report_nm: str) -> str:
    """공시명 기반 lifecycle 단계. 확정 = 공모가·청약일 확정 (수요예측 후)."""
    if "발행조건확정" in report_nm:
        return "확정"
    if "정정" in report_nm:
        return "정정"
    return "최초"


def _norm(s: str) -> str:
    """라벨 정규화 — 공백·'주N)' 각주·'또는 매출' 변형 제거."""
    s = re.sub(r"주\d+\)?", "", s)
    s = s.replace("또는매출", "").replace("또는 매출", "")
    return re.sub(r"\s+", "", s)


def _to_won(s: str) -> Optional[int]:
    """'14,000,000,000원', '7,000원 주1)' → int. '-'/빈칸 → None."""
    if not s:
        return None
    s = s.replace(",", "")
    m = re.search(r"(\d{3,})", s)  # 공모가는 최소 3자리(천원대~)
    return int(m.group(1)) if m else None


def _norm_date(s: str) -> str:
    """'2026.06. 23' / '2026년 06월 23일(화)' → '2026.06.23'. 못 찾으면 원본."""
    m = re.search(r"(\d{4})\D{0,2}(\d{1,2})\D{0,2}(\d{1,2})", s)
    if not m:
        return s.strip()
    y, mo, d = m.groups()
    return f"{y}.{int(mo):02d}.{int(d):02d}"


def _rows(table) -> List[List[str]]:
    return [
        [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        for tr in table.find_all("tr")
    ]


def _fetch_tables(rcept_no: str):
    """document.xml → ZIP 해제 → BeautifulSoup 표 리스트. DartScout 디코드 패턴 재사용."""
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

    resp = requests.get(DOC_URL, params={"crtfc_key": DART_API_KEY, "rcept_no": rcept_no},
                        timeout=(10, 60))
    resp.raise_for_status()

    chunks: List[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        for nm in [n for n in zf.namelist() if n.lower().endswith(".xml")]:
            b = zf.read(nm)
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    chunks.append(b.decode(enc))
                    break
                except UnicodeDecodeError:
                    continue
            else:
                chunks.append(b.decode("utf-8", errors="ignore"))
    except zipfile.BadZipFile:
        for enc in ("utf-8", "euc-kr", "cp949"):
            try:
                chunks.append(resp.content.decode(enc))
                break
            except UnicodeDecodeError:
                continue
        else:
            chunks.append(resp.content.decode("utf-8", errors="ignore"))

    raw = "\n".join(chunks)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(raw, "html.parser")
    return soup.find_all("table")


def _extract_offering(tables) -> Dict[str, Any]:
    """'모집 또는 매출 조건' 표(라벨 2열)에서 공모 조건 추출."""
    target = None
    for t in tables:
        rows = _rows(t)
        labels = {_norm(r[0]) for r in rows if r}
        if sum(any(a in lb for lb in labels) for a in _OFFER_ANCHORS) >= 3:
            target = rows
            break
    if not target:
        return {}

    out: Dict[str, Any] = {}
    section: Optional[str] = None  # 예정/확정 sub-row 가 어느 항목에 속하는지
    sub_dates: List[str] = []
    for r in target:
        if not r:
            continue
        head = _norm(r[0])
        rest = " ".join(r[1:])
        rowtxt = " ".join(r)

        if "주당모집가액" in head:
            section = "price"
        elif "모집총액" in head:
            section = "total"
        elif "청약기일" in head:
            section = "subscribe"
        elif "납입기일" in head:
            out["payment_date"] = _norm_date(rowtxt)
            section = None
        elif "모집매출주식의수" in head or "모집주식의수" in head:
            m = re.search(r"([\d,]+)\s*주", rowtxt)
            if m:
                out["shares"] = int(m.group(1).replace(",", ""))
            section = None

        # 예정/확정가액 값 행 (현재 section 귀속)
        if section in ("price", "total"):
            if "예정가액" in rowtxt:
                v = _to_won(rest if "예정가액" in head else rowtxt)
                if v:
                    out[f"{section}_planned"] = v
            if "확정가액" in rowtxt:
                v = _to_won(rowtxt)
                if v:
                    out[f"{section}_confirmed"] = v
        if section == "subscribe":
            for d in re.findall(r"\d{4}\D{0,2}\d{1,2}\D{0,2}\d{1,2}", rowtxt):
                sub_dates.append(_norm_date(d))

    if sub_dates:
        out["subscribe_start"] = min(sub_dates)
        out["subscribe_end"] = max(sub_dates)

    # 깔끔한 일정 표(헤더=청약기일/납입기일/청약공고일, 값 행) 보강
    for t in tables:
        rows = _rows(t)
        if len(rows) >= 2 and rows[0]:
            hdr = [_norm(c) for c in rows[0]]
            if "청약기일" in hdr and "납입기일" in hdr and len(rows[1]) >= 2:
                vals = rows[1]
                try:
                    si = hdr.index("청약기일")
                    pi = hdr.index("납입기일")
                except ValueError:
                    continue
                if si < len(vals):
                    ds = re.findall(r"\d{4}\D{0,2}\d{1,2}\D{0,2}\d{1,2}", vals[si])
                    if ds:
                        out.setdefault("subscribe_start", _norm_date(ds[0]))
                        out["subscribe_end"] = _norm_date(ds[-1])
                if pi < len(vals) and vals[pi]:
                    out.setdefault("payment_date", _norm_date(vals[pi]))
                break

    return out


_NET_INCOME_LABELS = ("당기순이익", "분기순이익", "반기순이익", "순이익", "순손익")


def _extract_summary_financials(tables) -> Dict[str, Any]:
    """발행사 요약손익 — 헤더에 '(제N기)' 기수 표기 + 회계기준 행 = 자기 표 (peer 표 배제)."""
    for t in tables:
        rows = _rows(t)
        if len(rows) < 3 or not rows[0]:
            continue
        header = rows[0]
        if not any(re.search(r"제\s*\d+\s*기", c) for c in header[1:]):
            continue
        periods = [c.strip() for c in header[1:]]
        if not (2 <= len(periods) <= 6):  # 자기 요약표 컬럼 범위 (peer 다열표 배제)
            continue
        rowmap = {_norm(r[0]): r for r in rows if r}
        if "매출액" not in rowmap or "영업이익" not in rowmap:
            continue
        # peer 비교표는 헤더가 회사명 — '제N기' 기수 + 컬럼≤6 이 발행사 자기 표 신호 (회계기준은 soft).

        n = len(periods)

        def series(labels) -> List[Optional[int]]:
            keys = (labels,) if isinstance(labels, str) else labels
            cells: List[str] = []
            for k in keys:  # 정확 매칭 우선
                if k in rowmap:
                    cells = rowmap[k]
                    break
            if not cells:  # 부분(substring) 매칭 — 라벨 변형 흡수
                for rk, rv in rowmap.items():
                    if any(k in rk for k in keys):
                        cells = rv
                        break
            # 라벨/중복 라벨 셀 흡수 — 값은 뒤에서 periods 개수만큼 정렬
            vals = cells[-n:] if len(cells) >= n else cells
            out: List[Optional[int]] = []
            for v in vals:
                neg = "(" in v or v.strip().startswith("-")
                m = re.search(r"\d[\d,]*", v.replace(" ", ""))
                if not m:
                    out.append(None)
                    continue
                num = int(m.group(0).replace(",", ""))
                out.append(-num if neg else num)
            return out

        # 단위 — 명시값만 채택, 없으면 미상 (RULE 10: 추정 단위 오표시 회피).
        # 표 안 → 직전 캡션 sibling("(단위 : 백만원)") 순. 한국 요약표 단위는 캡션에 통상 위치.
        unit = "미상"
        um = re.search(r"단위\s*[:：]?\s*(백만원|천원|억원|원)", t.get_text(" ", strip=True))
        if um:
            unit = um.group(1)
        else:
            prev = t.find_previous(string=re.compile(r"단위"))
            if prev:
                um2 = re.search(r"단위\s*[:：]?\s*(백만원|천원|억원|원)", str(prev))
                if um2:
                    unit = um2.group(1)

        return {
            "available": True,
            "unit": unit,
            "periods": periods,
            "revenue": series("매출액"),
            "operating_income": series("영업이익"),
            "net_income": series(_NET_INCOME_LABELS),
        }
    return {"available": False}


def parse_prospectus(rcept_no: str, report_nm: str = "") -> Dict[str, Any]:
    """단일 증권신고서 파싱. 네트워크/파싱 실패 시 error 키."""
    if not DART_API_KEY:
        return {"error": "no_dart_api_key"}
    result: Dict[str, Any] = {"stage": classify_stage(report_nm)}
    try:
        tables = _fetch_tables(rcept_no)
    except Exception as e:
        result["error"] = f"fetch:{type(e).__name__}"
        return result
    try:
        result["offering"] = _extract_offering(tables)
        result["summary_financials"] = _extract_summary_financials(tables)
    except Exception as e:
        result["error"] = f"parse:{type(e).__name__}"
    return result
