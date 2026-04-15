"""
SEC Form 4 (내부자 거래) 수집기
fact_score 수급 팩터 및 red_flags 직결
"""
import os, time, logging, requests
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)
EDGAR_HEADERS = {"User-Agent": os.getenv("SEC_EDGAR_USER_AGENT", "VERITY verity@example.com")}

BULLISH_CODES = {"P", "M"}   # 공개시장 매수, 옵션 행사
BEARISH_CODES = {"S", "D"}   # 공개시장 매도, 처분 (F 세금매도 제외)

def _resolve_cik(ticker: str) -> Optional[str]:
    try:
        data = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=EDGAR_HEADERS, timeout=10
        ).json()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                return str(entry["cik_str"])
    except Exception as e:
        logger.error(f"[Form4] CIK 조회 실패: {e}")
    return None

def get_insider_filings(ticker: str, lookback_days: int = 30, limit: int = 10) -> list[dict]:
    start_dt = (date.today() - timedelta(days=lookback_days)).isoformat()
    params = {
        "q": f'"{ticker}"', "forms": "4",
        "dateRange": "custom", "startdt": start_dt,
        "entity": ticker, "$limit": limit,
    }
    try:
        hits = requests.get(
            "https://efts.sec.gov/LATEST/search-index",
            params=params, headers=EDGAR_HEADERS, timeout=15
        ).json().get("hits", {}).get("hits", [])
        return [{"accession_no": h["_source"].get("accession_no",""),
                 "filed_at": h["_source"].get("file_date","")} for h in hits]
    except Exception as e:
        logger.error(f"[Form4] 검색 실패: {e}")
        return []

def parse_form4_xml(accession_no: str, cik: str) -> dict:
    acc = accession_no.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{acc}.xml"
    try:
        resp = requests.get(url, headers=EDGAR_HEADERS, timeout=15)
        root = ET.fromstring(resp.text)
    except Exception as e:
        return {"error": str(e)}

    transactions = []
    for txn in root.findall(".//nonDerivativeTransaction"):
        try:
            code = txn.findtext(".//transactionCode", "").strip()
            shares = float(txn.findtext(".//transactionShares/value", "0") or 0)
            price  = float(txn.findtext(".//transactionPricePerShare/value", "0") or 0)
            disp   = txn.findtext(".//transactionAcquiredDisposedCode/value", "").strip()
            transactions.append({
                "code": code, "shares": shares, "price_usd": price,
                "value_usd": shares * price,
                "signal": "BULLISH" if code in BULLISH_CODES and disp == "A"
                           else "BEARISH" if code in BEARISH_CODES and disp == "D"
                           else "NEUTRAL"
            })
        except Exception:
            continue

    return {
        "reporter": root.findtext(".//rptOwnerName", "Unknown"),
        "is_officer": root.findtext(".//isOfficer", "0") == "1",
        "officer_title": root.findtext(".//officerTitle", ""),
        "transactions": transactions,
    }

def get_insider_signal(ticker: str, lookback_days: int = 30) -> dict:
    cik = _resolve_cik(ticker)
    if not cik:
        return {"ticker": ticker, "insider_signal": "NEUTRAL", "insider_score": 0.0,
                "red_flag": False, "red_flag_reason": None}

    filings = get_insider_filings(ticker, lookback_days)
    bullish_val = bearish_val = bullish_cnt = bearish_cnt = 0.0

    for f in filings[:5]:
        time.sleep(0.15)
        parsed = parse_form4_xml(f["accession_no"], cik)
        if "error" in parsed:
            continue
        for txn in parsed.get("transactions", []):
            if txn["signal"] == "BULLISH":
                bullish_val += txn["value_usd"]; bullish_cnt += 1
            elif txn["signal"] == "BEARISH":
                bearish_val += txn["value_usd"]; bearish_cnt += 1

    net = bullish_val - bearish_val
    score = round(max(-10.0, min(10.0, (net / max(abs(net), 1)) * 10)), 2)
    red_flag = bearish_val > 500_000 and bearish_cnt >= 2

    if score >= 3.0 and bullish_cnt >= 2: signal = "STRONG_BULLISH"
    elif score >= 1.0: signal = "BULLISH"
    elif score <= -3.0 and red_flag: signal = "STRONG_BEARISH"
    elif score <= -1.0: signal = "BEARISH"
    else: signal = "NEUTRAL"

    return {
        "ticker": ticker, "insider_signal": signal, "insider_score": score,
        "bullish_txn_count": int(bullish_cnt), "bearish_txn_count": int(bearish_cnt),
        "total_bullish_value_usd": round(bullish_val, 2),
        "total_bearish_value_usd": round(bearish_val, 2),
        "red_flag": red_flag,
        "red_flag_reason": f"임원 대량 매도: ${bearish_val:,.0f} ({int(bearish_cnt)}건)" if red_flag else None,
    }
