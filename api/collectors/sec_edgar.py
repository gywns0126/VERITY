"""
SEC EDGAR 미국 공시 데이터 수집기 (DART 대체)
- 최근 공시 목록 (10-K, 10-Q, 8-K)
- 내부자 거래 (Form 4)
- XBRL 핵심 재무 추출 (FCF, 순이익, 부채비율 → Brain용)

Rate limit: 10 req/sec, User-Agent 필수
"""
import time
import logging
import requests
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_BASE = "https://efts.sec.gov/LATEST"
_DATA_BASE = "https://data.sec.gov"
_SESSION = requests.Session()
_LAST_CALL = 0.0
_MIN_INTERVAL = 0.12  # 10req/sec → ~0.1s


def _headers(user_agent: str) -> dict:
    return {"User-Agent": user_agent, "Accept": "application/json"}


def _throttle():
    global _LAST_CALL
    elapsed = time.time() - _LAST_CALL
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _LAST_CALL = time.time()


def _resolve_cik(ticker: str, user_agent: str) -> Optional[str]:
    """티커 → CIK 10자리 (SEC company_tickers.json 매핑)."""
    _throttle()
    try:
        r = _SESSION.get(f"{_DATA_BASE}/files/company_tickers.json",
                         headers=_headers(user_agent), timeout=10)
        r.raise_for_status()
        data = r.json()
        for _, entry in data.items():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry.get("cik_str", ""))
                return cik.zfill(10)
        return None
    except Exception as e:
        logger.warning("SEC CIK resolve failed for %s: %s", ticker, e)
        return None


def get_recent_filings(ticker: str, user_agent: str,
                       form_types: Optional[List[str]] = None) -> List[Dict]:
    """최근 공시 목록 (10-K, 10-Q, 8-K 등)."""
    if not user_agent:
        return []
    if form_types is None:
        form_types = ["10-K", "10-Q", "8-K"]

    cik = _resolve_cik(ticker, user_agent)
    if not cik:
        return []

    _throttle()
    try:
        url = f"{_DATA_BASE}/submissions/CIK{cik}.json"
        r = _SESSION.get(url, headers=_headers(user_agent), timeout=12)
        r.raise_for_status()
        data = r.json()

        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        descriptions = recent.get("primaryDocDescription", [])
        accessions = recent.get("accessionNumber", [])

        results = []
        for i, form in enumerate(forms):
            if form in form_types:
                acc = accessions[i].replace("-", "") if i < len(accessions) else ""
                results.append({
                    "form_type": form,
                    "filed_date": dates[i] if i < len(dates) else "",
                    "description": descriptions[i] if i < len(descriptions) else form,
                    "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form}&dateb=&owner=include&count=5" if not acc else f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{acc}/",
                })
            if len(results) >= 10:
                break
        return results
    except Exception as e:
        logger.warning("SEC filings failed for %s: %s", ticker, e)
        return []


def get_insider_transactions(ticker: str, user_agent: str) -> List[Dict]:
    """최근 내부자 거래 (Form 4) — EDGAR full-text search."""
    if not user_agent:
        return []

    _throttle()
    try:
        url = f"{_BASE}/search-index"
        params = {
            "q": f'"{ticker}"',
            "forms": "4",
            "dateRange": "custom",
            "startdt": (time.strftime("%Y-%m-%d", time.gmtime(time.time() - 90 * 86400))),
            "enddt": time.strftime("%Y-%m-%d"),
        }
        r = _SESSION.get(url, params=params, headers=_headers(user_agent), timeout=12)
        r.raise_for_status()
        data = r.json()

        hits = data.get("hits", {}).get("hits", [])
        results = []
        for hit in hits[:10]:
            src = hit.get("_source", {})
            results.append({
                "filer": src.get("display_names", [""])[0] if src.get("display_names") else "",
                "filed_date": src.get("file_date", ""),
                "form_type": "4",
                "url": f"https://www.sec.gov/Archives/edgar/data/{src.get('entity_id', '')}/{src.get('file_num', '')}",
            })
        return results
    except Exception as e:
        logger.warning("SEC insider tx failed for %s: %s", ticker, e)
        return []


def get_financial_facts(ticker: str, user_agent: str) -> Dict:
    """XBRL 핵심 재무 데이터 추출 (Brain용 FCF, 순이익, 부채 등)."""
    result = {
        "fcf": None, "net_income": None, "total_debt": None,
        "total_equity": None, "debt_ratio": None,
        "revenue": None, "operating_income": None,
    }
    if not user_agent:
        return result

    cik = _resolve_cik(ticker, user_agent)
    if not cik:
        return result

    _throttle()
    try:
        url = f"{_DATA_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
        r = _SESSION.get(url, headers=_headers(user_agent), timeout=15)
        r.raise_for_status()
        data = r.json()

        facts = data.get("facts", {})
        us_gaap = facts.get("us-gaap", {})

        def _latest_annual(concept: str) -> Optional[float]:
            entry = us_gaap.get(concept, {})
            units = entry.get("units", {})
            usd = units.get("USD", [])
            annuals = [u for u in usd if u.get("form") in ("10-K", "10-K/A")]
            if not annuals:
                return None
            annuals.sort(key=lambda x: x.get("end", ""), reverse=True)
            val = annuals[0].get("val")
            return float(val) if val is not None else None

        result["net_income"] = _latest_annual("NetIncomeLoss")
        result["revenue"] = _latest_annual("Revenues") or _latest_annual("RevenueFromContractWithCustomerExcludingAssessedTax")
        result["operating_income"] = _latest_annual("OperatingIncomeLoss")

        ops_cf = _latest_annual("NetCashProvidedByUsedInOperatingActivities")
        capex = _latest_annual("PaymentsToAcquirePropertyPlantAndEquipment")
        if ops_cf is not None:
            result["fcf"] = ops_cf - (capex or 0)

        total_debt = _latest_annual("LongTermDebt") or _latest_annual("LongTermDebtNoncurrent")
        short_debt = _latest_annual("ShortTermBorrowings") or 0
        if total_debt is not None:
            result["total_debt"] = total_debt + (short_debt or 0)

        equity = _latest_annual("StockholdersEquity")
        if equity:
            result["total_equity"] = equity
            if result["total_debt"] and equity > 0:
                result["debt_ratio"] = round(result["total_debt"] / equity * 100, 1)

        return result
    except Exception as e:
        logger.warning("SEC financial facts failed for %s: %s", ticker, e)
        return result
