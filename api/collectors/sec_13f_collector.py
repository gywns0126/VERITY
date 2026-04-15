"""
EDGAR 13F-HR 기관 투자자 포지션 수집기
periodic_quarterly 모드 실행 / value_hunter.py 연계
"""
from __future__ import annotations
import os, re, time, json, logging, requests
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)
EDGAR_HEADERS = {"User-Agent": os.getenv("SEC_EDGAR_USER_AGENT", "VERITY verity@example.com")}

TRACKED_INSTITUTIONS = {
    "1067983":  "Berkshire Hathaway",
    "1350694":  "Bridgewater Associates",
    "1037389":  "Renaissance Technologies",
    "1336528":  "Pershing Square",
    "1534492":  "Third Point",
    "1423053":  "Tiger Global",
    "0000102909": "Vanguard Group",
    "0000093751": "BlackRock",
    "0000831001": "State Street",
}

def get_latest_13f_filing(cik: str) -> Optional[dict]:
    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    try:
        data     = requests.get(url, headers=EDGAR_HEADERS, timeout=15).json()
        filings  = data.get("filings", {}).get("recent", {})
        forms    = filings.get("form", [])
        dates    = filings.get("filingDate", [])
        accnos   = filings.get("accessionNumber", [])
        for i, form in enumerate(forms):
            if form in ("13F-HR", "13F-HR/A"):
                return {
                    "cik": cik,
                    "institution": TRACKED_INSTITUTIONS.get(cik, f"CIK_{cik}"),
                    "form_type": form,
                    "filed_at": dates[i] if i < len(dates) else None,
                    "accession_no": accnos[i] if i < len(accnos) else None,
                }
    except Exception as e:
        logger.error(f"[13F] 제출 조회 실패 CIK={cik}: {e}")
    return None

def parse_13f_holdings(accession_no: str, cik: str) -> list[dict]:
    acc = accession_no.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/infotable.xml"
    try:
        resp = requests.get(url, headers=EDGAR_HEADERS, timeout=20)
        if resp.status_code != 200:
            return []
        xml = re.sub(r' xmlns[^"]*"[^"]*"', '', resp.text)
        xml = re.sub(r'ns\d+:', '', xml)
        root = ET.fromstring(xml)
        holdings = []
        for info in root.findall(".//infoTable"):
            try:
                value  = float(info.findtext(".//value", "0") or 0)
                shares = float((info.findtext(".//sshPrnamt","0") or "0").replace(",",""))
                holdings.append({
                    "issuer":    info.findtext(".//nameOfIssuer","").strip(),
                    "cusip":     info.findtext(".//cusip","").strip(),
                    "value_usd": value * 1000,
                    "shares":    shares,
                    "put_call":  info.findtext(".//putCall",""),
                })
            except Exception:
                continue
        return sorted(holdings, key=lambda x: x["value_usd"], reverse=True)
    except Exception as e:
        logger.error(f"[13F] 보유 파싱 실패: {e}")
        return []

def compare_holdings(curr: list[dict], prev: list[dict]) -> dict:
    cm = {h["cusip"]: h for h in curr if h["cusip"]}
    pm = {h["cusip"]: h for h in prev if h["cusip"]}
    new, inc, dec, liq = [], [], [], []
    for cusip, c in cm.items():
        if cusip not in pm:
            new.append({**c, "change_type": "NEW"})
        else:
            chg = c["shares"] - pm[cusip]["shares"]
            entry = {**c, "shares_change": chg,
                     "value_change_usd": c["value_usd"] - pm[cusip]["value_usd"]}
            if chg > 0:   entry["change_type"] = "INCREASED"; inc.append(entry)
            elif chg < 0: entry["change_type"] = "DECREASED"; dec.append(entry)
    for cusip, p in pm.items():
        if cusip not in cm:
            liq.append({**p, "change_type": "LIQUIDATED",
                         "value_change_usd": -p["value_usd"]})
    return {
        "new_positions":    sorted(new, key=lambda x: x["value_usd"], reverse=True)[:10],
        "increased_top10":  sorted(inc, key=lambda x: x["value_change_usd"], reverse=True)[:10],
        "decreased_top10":  sorted(dec, key=lambda x: x["value_change_usd"])[:10],
        "liquidated_top10": sorted(liq, key=lambda x: abs(x["value_change_usd"]), reverse=True)[:10],
    }

def collect_all_13f(save_path: str = "data/13f_cache.json") -> dict:
    """periodic_quarterly 메인 호출"""
    results = {}
    for cik, name in TRACKED_INSTITUTIONS.items():
        logger.info(f"[13F] 수집: {name}")
        time.sleep(0.5)
        filing = get_latest_13f_filing(cik)
        if not filing: continue
        holdings = parse_13f_holdings(filing.get("accession_no",""), cik)
        results[cik] = {
            "institution": name,
            "filed_at":    filing.get("filed_at"),
            "top_holdings": holdings[:20],
            "total_aum_usd": sum(h["value_usd"] for h in holdings),
        }
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    return results
