"""
DartScout — OpenDART 핵심 데이터 수집기

대상 API
  1. 공시검색           (list.json)
  2. 주요사항 CB/BW     (cvbdIsDecsn.json, bdwtIsDecsn.json)
  3. 지분공시 대주주     (hyslrSttus.json)
  4. 직원현황 → 퇴사율  (empSttus.json)
  5. 재무제표 → 부채비율 (fnlttSinglAcnt.json)
  6. 배당정보           (alotMatter.json)
  7. 타법인 출자 현황    (otcprSttus.json) — 관계회사 지분 구조

사전 게이트: 감사의견(accnutAdtorNmNdAdtOpinion.json)이
             '적정'이 아니면 즉시 CriticalAuditError 반환
"""
import functools
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api.config import DART_API_KEY, DATA_DIR, now_kst
from api.collectors.dart_corp_code import get_corp_code
from api.collectors.stock_data import ALL_STOCKS

BASE_URL = "https://opendart.fss.or.kr/api"
RAW_DATA_PATH = os.path.join(DATA_DIR, "raw_data.json")
ANNUAL_REPORT = "11011"
API_DELAY = 0.5

_SESSION = requests.Session()
_SESSION.mount("https://", HTTPAdapter(
    max_retries=Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    ),
    pool_connections=4,
    pool_maxsize=4,
))


class CriticalAuditError(Exception):
    """감사의견이 '적정'이 아닐 때 발생"""
    pass


# ── 유틸리티 ──────────────────────────────────────────────

def _parse_int(value: Any) -> int:
    if value is None:
        return 0
    s = str(value).replace(",", "").replace(" ", "").strip()
    if not s or s == "-":
        return 0
    try:
        return int(s)
    except ValueError:
        return 0


def _call(endpoint: str, params: Dict[str, str]) -> Dict[str, Any]:
    """OpenDART API 호출 공통 래퍼. 세션 재사용 + 자동/수동 재시도."""
    params["crtfc_key"] = DART_API_KEY
    url = f"{BASE_URL}/{endpoint}"
    last_err: Optional[Exception] = None

    for attempt in range(3):
        try:
            resp = _SESSION.get(url, params=params, timeout=(10, 30))
            resp.raise_for_status()
            time.sleep(API_DELAY)

            data = resp.json()
            status = data.get("status", "")
            if status == "013":
                return {"status": "013", "list": []}
            if status != "000":
                return {"status": status, "message": data.get("message", ""), "list": []}
            return data
        except (requests.ReadTimeout, requests.ConnectionError) as e:
            last_err = e
            wait = 1.5 * (attempt + 1)
            print(f"  ⚠ DART 재시도 {attempt+1}/3 ({endpoint}): {e.__class__.__name__} — {wait:.1f}s 대기")
            time.sleep(wait)

    return {"status": "timeout", "message": str(last_err), "list": []}


# ── 감사의견 게이트 ───────────────────────────────────────

def check_audit(corp_code: str, bsns_year: str) -> str:
    """감사의견 확인. '적정'이 아니면 CriticalAuditError를 발생시킨다."""
    data = _call("accnutAdtorNmNdAdtOpinion.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })

    for item in data.get("list", []):
        opinion = (item.get("adt_opinion") or "").strip()
        if opinion and "적정" not in opinion:
            raise CriticalAuditError(
                f"감사의견 '{opinion}' (corp_code={corp_code}, year={bsns_year})"
            )
        if opinion:
            return opinion

    return "데이터 없음"


# ── 1. 공시검색 ──────────────────────────────────────────

def fetch_disclosures(corp_code: str, bgn_de: str, end_de: str) -> List[Dict]:
    data = _call("list.json", {
        "corp_code": corp_code,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "page_count": "20",
        "sort": "date",
        "sort_mth": "desc",
    })
    return [
        {
            "report_nm": d.get("report_nm", ""),
            "rcept_dt": d.get("rcept_dt", ""),
            "flr_nm": d.get("flr_nm", ""),
        }
        for d in data.get("list", [])
    ]


# ── 2. 주요사항 CB/BW ───────────────────────────────────

def fetch_cb_bw(corp_code: str, bgn_de: str, end_de: str) -> Dict[str, List]:
    common = {"corp_code": corp_code, "bgn_de": bgn_de, "end_de": end_de}

    cb_data = _call("cvbdIsDecsn.json", common)
    cb = [
        {
            "bd_tm": d.get("bd_tm", ""),
            "bd_fta": d.get("bd_fta", ""),
            "cvprc": d.get("cvprc", ""),
            "cvisstk_cnt": d.get("cvisstk_cnt", ""),
            "bddd": d.get("bddd", ""),
        }
        for d in cb_data.get("list", [])
    ]

    bw_data = _call("bdwtIsDecsn.json", common)
    bw = [
        {
            "bd_tm": d.get("bd_tm", ""),
            "bd_fta": d.get("bd_fta", ""),
            "ex_prc": d.get("ex_prc", ""),
            "nstk_isstk_cnt": d.get("nstk_isstk_cnt", ""),
            "bddd": d.get("bddd", ""),
        }
        for d in bw_data.get("list", [])
    ]

    return {"cb": cb, "bw": bw}


# ── 3. 지분공시(대주주) ──────────────────────────────────

def fetch_major_shareholders(corp_code: str, bsns_year: str) -> List[Dict]:
    data = _call("hyslrSttus.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })
    return [
        {
            "nm": d.get("nm", ""),
            "relate": d.get("relate", ""),
            "stock_cnt": d.get("trmend_posesn_stock_co", ""),
            "stock_rate": d.get("trmend_posesn_stock_qota_rt", ""),
        }
        for d in data.get("list", [])
    ]


# ── 4. 직원현황(퇴사율) ─────────────────────────────────

def fetch_employees(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    data = _call("empSttus.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })

    total_prev = 0
    total_curr = 0
    avg_tenure = ""

    for item in data.get("list", []):
        prev = _parse_int(item.get("reform_bfe_emp_co_rgllbr")) + \
               _parse_int(item.get("reform_bfe_emp_co_cnttk"))
        curr = _parse_int(item.get("rgllbr_co")) + \
               _parse_int(item.get("cnttk_co"))
        total_prev += prev
        total_curr += curr
        t = (item.get("avrg_cnwk_sdytrn") or "").strip()
        if t:
            avg_tenure = t

    turnover_rate: Optional[float] = None
    if total_prev > 0:
        turnover_rate = round((total_prev - total_curr) / total_prev * 100, 2)

    return {
        "total_prev": total_prev,
        "total_curr": total_curr,
        "turnover_rate_pct": turnover_rate,
        "avg_tenure": avg_tenure,
    }


# ── 5. 재무제표(부채비율) ────────────────────────────────

@functools.lru_cache(maxsize=512)
def _fetch_fnltt_cached(corp_code: str, bsns_year: str) -> str:
    """fnlttSinglAcnt.json 응답을 캐싱하여 동일 (corp_code, bsns_year) 중복 호출 방지."""
    data = _call("fnlttSinglAcnt.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })
    return json.dumps(data, ensure_ascii=False)


def _get_fnltt_data(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    return json.loads(_fetch_fnltt_cached(corp_code, bsns_year))


def fetch_financials(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    """자산총계·부채총계만 추출하여 부채비율을 계산한다."""
    data = _get_fnltt_data(corp_code, bsns_year)

    total_assets = 0
    total_liabilities = 0

    for item in data.get("list", []):
        if item.get("sj_div") != "BS":
            continue
        acct = item.get("account_nm", "")
        amount = _parse_int(item.get("thstrm_amount"))
        if "자산총계" in acct:
            total_assets = amount
        elif "부채총계" in acct:
            total_liabilities = amount

    equity = total_assets - total_liabilities
    debt_ratio: Optional[float] = None
    if equity > 0:
        debt_ratio = round(total_liabilities / equity * 100, 2)

    return {
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "equity": equity,
        "debt_ratio_pct": debt_ratio,
    }


# ── 5.5. 부동산 자산 ──────────────────────────────────

PROPERTY_KEYWORDS = ["투자부동산", "토지", "건물", "사용권자산", "건설중인자산"]

def fetch_property_assets(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    """재무상태표(BS)에서 부동산 관련 계정과목을 추출한다."""
    data = _get_fnltt_data(corp_code, bsns_year)

    items: List[Dict[str, Any]] = []
    total_current = 0
    total_prev = 0
    total_assets = 0

    for item in data.get("list", []):
        if item.get("sj_div") != "BS":
            continue
        acct = item.get("account_nm", "")

        if "자산총계" in acct:
            total_assets = _parse_int(item.get("thstrm_amount"))

        matched = any(kw in acct for kw in PROPERTY_KEYWORDS)
        if not matched:
            continue

        curr = _parse_int(item.get("thstrm_amount"))
        prev = _parse_int(item.get("frmtrm_amount"))
        items.append({
            "account": acct,
            "current": curr,
            "previous": prev,
            "change": curr - prev,
            "change_pct": round((curr - prev) / prev * 100, 2) if prev else None,
        })
        total_current += curr
        total_prev += prev

    property_ratio: Optional[float] = None
    if total_assets > 0 and total_current > 0:
        property_ratio = round(total_current / total_assets * 100, 2)

    return {
        "items": items,
        "total_current": total_current,
        "total_previous": total_prev,
        "total_change": total_current - total_prev,
        "total_change_pct": (
            round((total_current - total_prev) / total_prev * 100, 2)
            if total_prev > 0 else None
        ),
        "property_to_asset_pct": property_ratio,
        "total_assets": total_assets,
    }


# ── 5.6. 현금흐름표 ────────────────────────────────────

def fetch_business_facilities_raw(
    corp_code: str,
    bsns_year: Optional[str] = None,
) -> Dict[str, Any]:
    """
    최신 사업보고서(A001) 본문에서 'II. 사업의 내용' 섹션 원문 슬라이스.
    - REITs:    투자자산 현황 테이블 (주소·면적·감정가·임대율)
    - 일반 기업: 국내/해외 사업장 현황 (공장·R&D·물류·매장)

    반환: {rcept_no, report_nm, rcept_dt, raw_text, char_count} 또는 error 키.
    LLM 파싱(api.analyzers.facilities_parser)의 입력.
    """
    if not DART_API_KEY:
        return {"error": "no_dart_api_key"}

    now = now_kst()
    if bsns_year is None:
        bsns_year = str(now.year - 1)
    bgn = f"{int(bsns_year)}0101"
    end = now.strftime("%Y%m%d")

    try:
        listing = _call("list.json", {
            "corp_code": corp_code,
            "bgn_de": bgn,
            "end_de": end,
            "pblntf_detail_ty": "A001",
            "page_count": "5",
            "sort": "date",
            "sort_mth": "desc",
        })
    except Exception as e:
        return {"error": f"list:{e}"}

    candidates = [d for d in listing.get("list", []) if "사업보고서" in d.get("report_nm", "")]
    if not candidates:
        try:
            prev_bgn = f"{int(bsns_year) - 1}0101"
            listing2 = _call("list.json", {
                "corp_code": corp_code,
                "bgn_de": prev_bgn,
                "end_de": end,
                "pblntf_detail_ty": "A001",
                "page_count": "5",
                "sort": "date",
                "sort_mth": "desc",
            })
            candidates = [d for d in listing2.get("list", []) if "사업보고서" in d.get("report_nm", "")]
        except Exception:
            pass
    if not candidates:
        return {"error": "no_annual_report"}

    latest = candidates[0]
    rcept_no = latest.get("rcept_no", "")
    if not rcept_no:
        return {"error": "no_rcept_no"}

    try:
        url = f"{BASE_URL}/document.xml"
        resp = _SESSION.get(url, params={"crtfc_key": DART_API_KEY, "rcept_no": rcept_no},
                            timeout=(10, 60))
        resp.raise_for_status()
        time.sleep(API_DELAY)
    except Exception as e:
        return {"error": f"document_fetch:{e}", "rcept_no": rcept_no}

    import io
    import zipfile
    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        inner_names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        if not inner_names:
            return {"error": "no_xml_in_zip", "rcept_no": rcept_no}
        # 사업보고서 ZIP 은 보통 다중 XML 분할 (cover / 회사개요 / 사업의 내용 / 재무 / ...).
        # 첫 파일만 읽으면 cover 페이지만 잡혀 section_not_found 발생 →
        # 모든 XML 파일을 합쳐서 검색. 단일 XML 이면 old==new (영향 없음).
        chunks: list[bytes] = []
        for nm in inner_names:
            try:
                with zf.open(nm) as f:
                    chunks.append(f.read())
            except Exception:
                continue
        raw_bytes = b"\n".join(chunks) if chunks else b""
    except zipfile.BadZipFile:
        ct = resp.headers.get("Content-Type", "")
        if "xml" in ct.lower() or resp.content.lstrip().startswith(b"<"):
            raw_bytes = resp.content
        else:
            return {"error": "bad_zip", "rcept_no": rcept_no}
    except Exception as e:
        return {"error": f"zip:{e}", "rcept_no": rcept_no}

    try:
        for enc in ("utf-8", "euc-kr", "cp949"):
            try:
                raw_text = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raw_text = raw_bytes.decode("utf-8", errors="ignore")
    except Exception as e:
        return {"error": f"decode:{e}", "rcept_no": rcept_no}

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(raw_text, "lxml-xml") if "<?xml" in raw_text[:200] else BeautifulSoup(raw_text, "html.parser")
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()
        text = soup.get_text("\n")
    except Exception as e:
        return {"error": f"parse:{e}", "rcept_no": rcept_no}

    import re
    cleaned = re.sub(r"[ \t]+", " ", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    # "II. 사업의 내용" ~ "III. 재무에 관한 사항" 사이 슬라이스.
    # 한국 사업보고서 표준 목차에 기반.
    patterns = [
        r"(?is)(?:Ⅱ|II|2)[\.\s]+사업의\s*내용(.*?)(?:Ⅲ|III|3)[\.\s]+(?:재무|경영진단|보고서에)",
        r"(?is)사업의\s*내용(.*?)재무에\s*관한\s*사항",
        r"(?is)사업의\s*개요(.*?)(?:이사의\s*경영진단|재무제표)",
    ]
    section = ""
    for pat in patterns:
        matches = re.findall(pat, cleaned)
        if matches:
            section = max(matches, key=len).strip()
            if len(section) > 600:
                break

    if not section or len(section) < 300:
        return {
            "error": "section_not_found",
            "rcept_no": rcept_no,
            "report_nm": latest.get("report_nm", ""),
            "rcept_dt": latest.get("rcept_dt", ""),
            "raw_text": "",
            "char_count": 0,
        }

    MAX_CHARS = 60000
    if len(section) > MAX_CHARS:
        section = section[:MAX_CHARS]

    return {
        "rcept_no": rcept_no,
        "report_nm": latest.get("report_nm", ""),
        "rcept_dt": latest.get("rcept_dt", ""),
        "bsns_year": bsns_year,
        "raw_text": section,
        "char_count": len(section),
    }


def fetch_cashflow(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    """영업/투자/재무 현금흐름 추출. Gemini 재무 건전성 판단용."""
    data = _get_fnltt_data(corp_code, bsns_year)

    cf = {"operating": 0, "investing": 0, "financing": 0, "free_cashflow": 0}

    for item in data.get("list", []):
        if item.get("sj_div") != "CF":
            continue
        acct = item.get("account_nm", "")
        amount = _parse_int(item.get("thstrm_amount"))
        if "영업활동" in acct:
            cf["operating"] = amount
        elif "투자활동" in acct:
            cf["investing"] = amount
        elif "재무활동" in acct:
            cf["financing"] = amount

    cf["free_cashflow"] = cf["operating"] + cf["investing"]
    return cf


# ── 7. 타법인 출자 현황(관계회사 지분) ──────────────────

def _parse_float(value: Any) -> float:
    if value is None:
        return 0.0
    s = str(value).replace(",", "").replace(" ", "").strip()
    if not s or s == "-":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def fetch_subsidiary_investments(corp_code: str, bsns_year: str) -> List[Dict]:
    """타법인 출자 현황 — 이 회사가 보유한 타법인 지분 목록.
    OpenDART otcprSttus.json: 사업보고서의 타법인 출자 현황 공시.
    """
    data = _call("otcprSttus.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })
    results = []
    for d in data.get("list", []):
        inv_name = (d.get("inv_prm") or "").strip()
        if not inv_name or inv_name == "-":
            continue
        results.append({
            "inv_corp_name": inv_name,
            "initial_investment": _parse_int(d.get("frst_acqs_amount")),
            "initial_date": (d.get("frst_acqs_de") or "").strip(),
            "begin_balance_qty": _parse_int(d.get("bsis_blce_co")),
            "increase_qty": _parse_int(d.get("incrs_co")),
            "decrease_qty": _parse_int(d.get("dcrs_co")),
            "end_balance_qty": _parse_int(d.get("trmend_blce_co")),
            "ownership_pct": _parse_float(d.get("trmend_blce_qota_rt")),
            "book_value": _parse_int(d.get("trmend_blce_acntbk_amount")),
            "fair_value": _parse_int(d.get("trmend_blce_mktcap_amount")),
            "recent_biz_year_revenue": _parse_int(d.get("recent_bsns_year_fnnr_sttus_tot_amount")),
            "recent_biz_year_profit": _parse_int(d.get("recent_bsns_year_fnnr_sttus_thstrm_ntpf")),
        })
    return results


# ── 6. 배당정보 ─────────────────────────────────────────

def fetch_dividends(corp_code: str, bsns_year: str) -> List[Dict]:
    data = _call("alotMatter.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })
    return [
        {
            "category": d.get("se", ""),
            "current": d.get("thstrm", ""),
            "previous": d.get("frmtrm", ""),
        }
        for d in data.get("list", [])
    ]


# ── 오케스트레이션 ───────────────────────────────────────

# ── 7. 자사주 취득/처분 현황 ─────────────────────────
#
# Brain audit: 매입 우세 → 주주환원 긍정 시그널 / 처분 우세 → 자금조달·지분매각 주의 시그널.

def fetch_treasury_stock(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    """자기주식 취득 및 처분현황 (사업보고서 기준).

    DART API: tesstkAcqsDspsSttus.json
    Returns: rows + 누적 취득/처분/소각 + signal (positive/warning/neutral).
    """
    data = _call("tesstkAcqsDspsSttus.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })

    rows: List[Dict[str, Any]] = []
    total_acq = 0
    total_dsp = 0
    total_incnr = 0

    for item in data.get("list", []):
        acq = _parse_int(item.get("change_qy_acqs"))
        dsp = _parse_int(item.get("change_qy_dsps"))
        incnr = _parse_int(item.get("change_qy_incnr"))
        rows.append({
            "stock_knd": item.get("stock_knd", ""),
            "acqs_mth1": item.get("acqs_mth1", ""),
            "acqs_mth2": item.get("acqs_mth2", ""),
            "acqs_mth3": item.get("acqs_mth3", ""),
            "bsis_qy": _parse_int(item.get("bsis_qy")),
            "change_qy_acqs": acq,
            "change_qy_dsps": dsp,
            "change_qy_incnr": incnr,
            "trmend_qy": _parse_int(item.get("trmend_qy")),
            "rm": item.get("rm", ""),
        })
        total_acq += acq
        total_dsp += dsp
        total_incnr += incnr

    net_change = total_acq - total_dsp - total_incnr
    if total_acq > total_dsp:
        signal = "positive"
    elif total_dsp > total_acq:
        signal = "warning"
    else:
        signal = "neutral"

    return {
        "rows": rows,
        "row_count": len(rows),
        "total_acquisition_qty": total_acq,
        "total_disposal_qty": total_dsp,
        "total_cancellation_qty": total_incnr,
        "net_change": net_change,
        "signal": signal,
        "status": data.get("status", ""),
    }


# ── 8. 임원 개인별 보수 현황 ───────────────────────────
#
# Brain audit: 5억 이상 공시 대상 임원 개인 보수.
# 매출/영업이익 대비 보수 총액이 과다하면 거버넌스 경고 팩터.

def fetch_exec_compensation(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    """임원 개인별 보수 현황 (5억 이상 공시 대상).

    DART API: hmvAuditIndvdlBySttus.json
    Returns: 개인별 보수 list + 총보수/최고보수/공시인원수.
    """
    data = _call("hmvAuditIndvdlBySttus.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })

    individuals: List[Dict[str, Any]] = []
    total_pay = 0
    top_pay = 0

    for item in data.get("list", []):
        amt = _parse_int(item.get("mendng_totamt"))
        individuals.append({
            "nm": item.get("nm", ""),
            "ofcps": item.get("ofcps", ""),
            "mendng_totamt": amt,
            # 보수 산정 기준 — 길어서 200자 truncate
            "mendng_detail": (item.get("mendng_totamt_ct_incls_mendng") or "")[:200],
        })
        total_pay += amt
        if amt > top_pay:
            top_pay = amt

    return {
        "individuals": individuals,
        "count_disclosed": len(individuals),
        "total_pay_won": total_pay,
        "top_pay_won": top_pay,
        "status": data.get("status", ""),
    }


# ── 9. 대주주 (5% 이상) 지분 변동 ───────────────────────
#
# Brain audit: 변동 후 - 변동 전 지분율 차이로 신호 분류.
# delta < -0.5%p = warning (내부자 매도), > +0.5%p = positive (확신), 그 외 neutral.

def fetch_major_shareholder_changes(corp_code: str, bgn_de: str, end_de: str) -> List[Dict[str, Any]]:
    """대주주 (5% 이상 보유) 지분 변동 보고서 목록 (기간별).

    DART API: hyslrChgSttus.json
    Returns: 변동 보고 list (rcept_dt, hyslr_nm, 변동전/후 지분율, delta, signal).
    """
    data = _call("hyslrChgSttus.json", {
        "corp_code": corp_code,
        "bgn_de": bgn_de,
        "end_de": end_de,
    })

    rows: List[Dict[str, Any]] = []
    for item in data.get("list", []):
        # 변동 전/후 지분율 — DART 응답이 문자열 (e.g. "5.10")
        try:
            rate_before = float(str(item.get("chnge_pos_jb_qota_rt") or "0").replace(",", ""))
        except (TypeError, ValueError):
            rate_before = 0.0
        try:
            rate_after = float(str(item.get("chnge_aft_jb_qota_rt") or "0").replace(",", ""))
        except (TypeError, ValueError):
            rate_after = 0.0
        delta = rate_after - rate_before

        if delta <= -0.5:
            signal = "warning"
        elif delta >= 0.5:
            signal = "positive"
        else:
            signal = "neutral"

        rows.append({
            "rcept_no": item.get("rcept_no", ""),
            "rcept_dt": item.get("rcept_dt", ""),
            "hyslr_nm": item.get("hyslr_nm", ""),
            "chnge_jb_de": item.get("chnge_jb_de", ""),
            "chnge_pos_jb": _parse_int(item.get("chnge_pos_jb")),
            "chnge_aft_jb": _parse_int(item.get("chnge_aft_jb")),
            "chnge_pos_jb_qota_rt": rate_before,
            "chnge_aft_jb_qota_rt": rate_after,
            "delta_pct_pt": round(delta, 4),
            "chnge_resn": item.get("chnge_resn", ""),
            "signal": signal,
        })
    return rows


def scout(ticker: str, bsns_year: Optional[str] = None) -> Dict[str, Any]:
    """단일 종목 6대 데이터 수집. 감사의견 부적정 시 critical_error를 담아 즉시 반환."""
    if not DART_API_KEY:
        raise RuntimeError("DART_API_KEY 환경변수가 설정되지 않았습니다.")

    corp_code = get_corp_code(ticker)
    if not corp_code:
        return {"ticker": ticker, "error": f"매핑 없음: {ticker}"}

    now = now_kst()
    if bsns_year is None:
        bsns_year = str(now.year - 1)
    bgn_de = f"{int(bsns_year)}0101"
    end_de = now.strftime("%Y%m%d")

    result: Dict[str, Any] = {
        "ticker": ticker.split(".")[0],
        "name": ALL_STOCKS.get(ticker, ticker),
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "collected_at": now.isoformat(),
    }

    try:
        result["audit_opinion"] = check_audit(corp_code, bsns_year)
    except CriticalAuditError as e:
        result["audit_opinion"] = str(e)
        result["critical_error"] = True
        return result

    collectors = [
        ("disclosures",            lambda: fetch_disclosures(corp_code, bgn_de, end_de)),
        ("cb_bw",                  lambda: fetch_cb_bw(corp_code, bgn_de, end_de)),
        ("major_shareholders",     lambda: fetch_major_shareholders(corp_code, bsns_year)),
        ("employees",              lambda: fetch_employees(corp_code, bsns_year)),
        ("financials",             lambda: fetch_financials(corp_code, bsns_year)),
        ("property_assets",        lambda: fetch_property_assets(corp_code, bsns_year)),
        ("cashflow",               lambda: fetch_cashflow(corp_code, bsns_year)),
        ("dividends",              lambda: fetch_dividends(corp_code, bsns_year)),
        ("subsidiary_investments", lambda: fetch_subsidiary_investments(corp_code, bsns_year)),
        # ── 거버넌스 시그널 (Brain Audit Phase 1.B) ──
        ("treasury_stock",            lambda: fetch_treasury_stock(corp_code, bsns_year)),
        ("exec_compensation",         lambda: fetch_exec_compensation(corp_code, bsns_year)),
        ("major_shareholder_changes", lambda: fetch_major_shareholder_changes(corp_code, bgn_de, end_de)),
    ]

    for key, fn in collectors:
        try:
            result[key] = fn()
        except Exception as e:
            result[key] = {"error": str(e)}

    _fetch_fnltt_cached.cache_clear()
    return result


def scout_all(
    tickers: Optional[List[str]] = None,
    bsns_year: Optional[str] = None,
) -> Dict[str, Any]:
    """복수 종목을 수집하여 data/raw_data.json에 저장한다."""
    if tickers is None:
        tickers = list(ALL_STOCKS.keys())

    results: Dict[str, Any] = {}
    total = len(tickers)

    for i, ticker in enumerate(tickers, 1):
        name = ALL_STOCKS.get(ticker, ticker)
        print(f"  [{i}/{total}] {name} 스카우팅...", end="")

        data = scout(ticker, bsns_year)
        key = ticker.split(".")[0]
        results[key] = data

        if data.get("critical_error"):
            print(f" CRITICAL — {data.get('audit_opinion')}")
        elif data.get("error"):
            print(f" SKIP — {data['error']}")
        else:
            print(" OK")

    output = {
        "updated_at": now_kst().isoformat(),
        "bsns_year": bsns_year or str(now_kst().year - 1),
        "count": len(results),
        "stocks": results,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(RAW_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output


if __name__ == "__main__":
    print("DartScout — OpenDART 6대 핵심 데이터 수집 시작...")
    result = scout_all()
    critical = sum(1 for v in result["stocks"].values() if v.get("critical_error"))
    print(f"\n완료: {result['count']}개 종목 (critical: {critical}) → {RAW_DATA_PATH}")
