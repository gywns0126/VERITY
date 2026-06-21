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
    "1040273":  "Third Point LLC",   # 2026-06-22 fix: 옛 1534492 = 개인(Lunsford) 오등록
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

def get_recent_13f_filings(cik: str, n: int = 2) -> list[dict]:
    """최근 n개 13F-HR 제출 (QoQ 비교용 — [0]=최신, [1]=직전 분기).

    13F-HR/A(정정)는 제외 — 정정본은 동일 분기 중복이라 QoQ 분기 비교 왜곡. 원본 HR 만.
    """
    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
    try:
        data    = requests.get(url, headers=EDGAR_HEADERS, timeout=15).json()
        filings = data.get("filings", {}).get("recent", {})
        forms   = filings.get("form", [])
        dates   = filings.get("filingDate", [])
        accnos  = filings.get("accessionNumber", [])
        out = []
        for i, form in enumerate(forms):
            if form == "13F-HR":
                out.append({
                    "cik": cik,
                    "institution": TRACKED_INSTITUTIONS.get(cik, f"CIK_{cik}"),
                    "filed_at": dates[i] if i < len(dates) else None,
                    "accession_no": accnos[i] if i < len(accnos) else None,
                })
                if len(out) >= n:
                    break
        return out
    except Exception as e:
        logger.error(f"[13F] 최근 제출 조회 실패 CIK={cik}: {e}")
        return []


def _find_infotable_url(cik: str, accession_no: str) -> Optional[str]:
    """13F 보유 information table xml 탐색 (파일명 임의 — 예 '53405.xml').

    하드코딩 'infotable.xml' 은 다수 404 (2026-06-22 발견: Berkshire=53405.xml).
    index.json → primary_doc.xml 제외 최대 xml = 보유 테이블.
    """
    acc = accession_no.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}"
    try:
        idx = requests.get(f"{base}/index.json", headers=EDGAR_HEADERS, timeout=15).json()
    except Exception as e:
        logger.error(f"[13F] index.json 실패 CIK={cik}: {e}")
        return None
    cands = [(it.get("name", ""), int(it.get("size") or 0))
             for it in idx.get("directory", {}).get("item", [])
             if it.get("name", "").endswith(".xml") and it.get("name") != "primary_doc.xml"]
    if not cands:
        return None
    cands.sort(key=lambda x: -x[1])   # 최대 = 보유 테이블
    return f"{base}/{cands[0][0]}"


def _strip_ns(xml_text: str) -> str:
    """namespace 선언·prefix 제거 ('unbound prefix' 파싱 실패 방지).

    태그(<ns:x>) + 속성 prefix(xsi:schemaLocation=) 모두 제거 — 후자 누락 시
    xmlns 선언만 지워져 prefix 미선언 unbound (2026-06-22 Pershing/Tiger 발견).
    """
    x = re.sub(r'\sxmlns(:[\w.]+)?\s*=\s*"[^"]*"', "", xml_text)   # xmlns 선언
    x = re.sub(r"<(/?)[\w.]+:", r"<\1", x)                          # 태그 prefix
    x = re.sub(r"\s[\w.]+:([\w.]+\s*=)", r" \1", x)                 # 속성 prefix
    return x


def parse_13f_holdings(accession_no: str, cik: str) -> list[dict]:
    url = _find_infotable_url(cik, accession_no)
    if not url:
        return []
    try:
        resp = requests.get(url, headers=EDGAR_HEADERS, timeout=20)
        if resp.status_code != 200:
            return []
        root = ET.fromstring(_strip_ns(resp.text))
        # cusip 별 합산 — 한 13F 가 동일 issuer 를 여러 infoTable 행(클래스/투자재량 분리)으로
        # 보고 → 중복 holder 방지. 🚨 value 는 2023+ 실달러(×1000 폐기 — 2026-06-22 ALLY $39/주 검증).
        # putCall 행(옵션) = 직접 보유 아님 → 제외.
        agg: dict = {}
        for info in root.findall(".//infoTable"):
            try:
                if (info.findtext(".//putCall", "") or "").strip():
                    continue
                cusip = (info.findtext(".//cusip", "") or "").strip().upper()
                if not cusip:
                    continue
                value  = float(info.findtext(".//value", "0") or 0)
                shares = float((info.findtext(".//sshPrnamt", "0") or "0").replace(",", ""))
            except (TypeError, ValueError):
                continue
            e = agg.setdefault(cusip, {
                "issuer": (info.findtext(".//nameOfIssuer", "") or "").strip(),
                "cusip": cusip, "value_usd": 0.0, "shares": 0.0,
            })
            e["value_usd"] += value
            e["shares"] += shares
        return sorted(agg.values(), key=lambda x: x["value_usd"], reverse=True)
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


def compute_institutional_signal(cache_path: str = "data/13f_cache.json") -> dict:
    """V6: 13F 캐시 데이터를 종목별 기관 신호로 변환.

    Returns:
        {
            "ticker_signal": {ticker: {score, institutions, total_value}},
            "sector_concentration": {sector: pct},
            "smart_money_consensus": [top tickers],
        }
    """
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"ok": False, "error": "13f_cache.json not found"}

    ticker_agg: dict = {}

    for cik, inst_data in data.items():
        inst_name = inst_data.get("institution", "")
        for h in inst_data.get("top_holdings", []):
            issuer = h.get("issuer", "").upper()
            cusip = h.get("cusip", "")
            value = h.get("value_usd", 0)
            shares = h.get("shares", 0)

            key = cusip or issuer
            if not key:
                continue

            if key not in ticker_agg:
                ticker_agg[key] = {
                    "issuer": h.get("issuer", ""),
                    "cusip": cusip,
                    "total_value_usd": 0,
                    "total_shares": 0,
                    "institution_count": 0,
                    "institutions": [],
                }
            ticker_agg[key]["total_value_usd"] += value
            ticker_agg[key]["total_shares"] += shares
            ticker_agg[key]["institution_count"] += 1
            ticker_agg[key]["institutions"].append(inst_name)

    ranked = sorted(ticker_agg.values(),
                    key=lambda x: x["institution_count"] * 1e12 + x["total_value_usd"],
                    reverse=True)

    ticker_signal = {}
    for item in ranked[:50]:
        inst_count = item["institution_count"]
        total_inst = len(data)
        overlap_pct = (inst_count / max(total_inst, 1)) * 100

        if overlap_pct >= 60:
            score = 80
        elif overlap_pct >= 40:
            score = 70
        elif overlap_pct >= 20:
            score = 60
        else:
            score = 50

        ticker_signal[item["cusip"] or item["issuer"]] = {
            "issuer": item["issuer"],
            "score": score,
            "institution_count": inst_count,
            "institutions": item["institutions"],
            "total_value_usd": item["total_value_usd"],
            "overlap_pct": round(overlap_pct, 1),
        }

    consensus = [
        {"issuer": v["issuer"], "score": v["score"],
         "institutions": v["institution_count"]}
        for v in list(ticker_signal.values())[:20]
    ]

    return {
        "ok": True,
        "ticker_signal": ticker_signal,
        "smart_money_consensus": consensus,
        "total_institutions": len(data),
        "total_tracked_issuers": len(ticker_agg),
    }
