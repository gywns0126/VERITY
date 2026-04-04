"""
DartScout — OpenDART 6대 핵심 데이터 수집기

대상 API
  1. 공시검색           (list.json)
  2. 주요사항 CB/BW     (cvbdIsDecsn.json, bdwtIsDecsn.json)
  3. 지분공시 대주주     (hyslrSttus.json)
  4. 직원현황 → 퇴사율  (empSttus.json)
  5. 재무제표 → 부채비율 (fnlttSinglAcnt.json)
  6. 배당정보           (alotMatter.json)

사전 게이트: 감사의견(accnutAdtorNmNdAdtOpinion.json)이
             '적정'이 아니면 즉시 CriticalAuditError 반환
"""
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from api.config import DART_API_KEY, DATA_DIR, now_kst
from api.collectors.dart_corp_code import get_corp_code
from api.collectors.stock_data import ALL_STOCKS

BASE_URL = "https://opendart.fss.or.kr/api"
RAW_DATA_PATH = os.path.join(DATA_DIR, "raw_data.json")
ANNUAL_REPORT = "11011"
API_DELAY = 0.5


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
    """OpenDART API 호출 공통 래퍼. 호출 간 딜레이로 rate-limit 방지."""
    params["crtfc_key"] = DART_API_KEY
    resp = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=15)
    resp.raise_for_status()
    time.sleep(API_DELAY)

    data = resp.json()
    status = data.get("status", "")
    if status == "013":
        return {"status": "013", "list": []}
    if status != "000":
        return {"status": status, "message": data.get("message", ""), "list": []}
    return data


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

def fetch_financials(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    """자산총계·부채총계만 추출하여 부채비율을 계산한다."""
    data = _call("fnlttSinglAcnt.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })

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


# ── 5.5. 현금흐름표 ────────────────────────────────────

def fetch_cashflow(corp_code: str, bsns_year: str) -> Dict[str, Any]:
    """영업/투자/재무 현금흐름 추출. Gemini 재무 건전성 판단용."""
    data = _call("fnlttSinglAcnt.json", {
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": ANNUAL_REPORT,
    })

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
        ("disclosures",        lambda: fetch_disclosures(corp_code, bgn_de, end_de)),
        ("cb_bw",              lambda: fetch_cb_bw(corp_code, bgn_de, end_de)),
        ("major_shareholders", lambda: fetch_major_shareholders(corp_code, bsns_year)),
        ("employees",          lambda: fetch_employees(corp_code, bsns_year)),
        ("financials",         lambda: fetch_financials(corp_code, bsns_year)),
        ("cashflow",           lambda: fetch_cashflow(corp_code, bsns_year)),
        ("dividends",          lambda: fetch_dividends(corp_code, bsns_year)),
    ]

    for key, fn in collectors:
        try:
            result[key] = fn()
        except Exception as e:
            result[key] = {"error": str(e)}

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
