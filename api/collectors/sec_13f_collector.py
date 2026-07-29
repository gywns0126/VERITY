"""
EDGAR 13F-HR 기관 투자자 포지션 수집기
periodic_quarterly 모드 실행 / value_hunter.py 연계
"""
from __future__ import annotations
import os, re, time, json, logging, statistics, requests
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
    # ── 2026-07-30 확장 (PM "전부 ㄱㄱ") ────────────────────────────────────────
    # CIK 는 전부 SEC EDGAR 실조회로 확인 (browse-edgar type=13F-HR → submissions JSON
    # 최근 13F-HR 존재 확인). 추정·기억 등록 금지 — 오등록 선례(Third Point 1534492=개인).
    "1697748":  "ARK Invest",              # 캐서린 우드 — 최근 13F-HR 2026-05-12
    "1603466":  "Point72",                 # 스티븐 코헨 — 2026-05-15
    "1536411":  "Duquesne Family Office",  # 스탠리 드러켄밀러 — 2026-05-15
    "1029160":  "Soros Fund Management",   # 조지 소로스 — 2026-05-15
    "1647251":  "TCI Fund Management",     # 크리스 혼 — 2026-05-15
    "1103804":  "Viking Global",           # 앤드리어스 할보르센 — 2026-05-15
    "1167557":  "AQR Capital",             # 클리프 애즈니스 — 2026-05-15
    "850529":   "Fisher Asset Management",  # 켄 피셔 — 2026-05-05
    "923093":   "Tudor Investment",        # 폴 튜더 존스 — 2026-05-15
    "1166559":  "Gates Foundation Trust",  # 빌 게이츠 — 2026-05-15
    # 🚫 인덱스펀드 — 집중형 신호 희석 + CUSIP 수천 비용. 공개 빌더 ACTIVE_MANAGERS 에서 제외.
    "0000102909": "Vanguard Group",
    "0000093751": "BlackRock",
    "0000831001": "State Street",
}

# 기관명 → 대표 운용역(사람). 인물 축 뷰 라벨용.
# 🚨 "그 사람이 곧 그 펀드" 가 아님 — 달리오(2022 경영일선 은퇴)·사이먼스(2024 작고) 처럼
#    현 운용 주체와 인물이 다른 경우가 있어, 표기는 '기관(대표 연관 인물)' 형태로만 쓴다.
MANAGER_PERSON = {
    "Berkshire Hathaway": "워런 버핏",
    "Bridgewater Associates": "레이 달리오(창업)",
    "Renaissance Technologies": "제임스 사이먼스(창업)",
    "Pershing Square": "빌 애크먼",
    "Third Point LLC": "댄 로브",
    "Tiger Global": "체이스 콜먼",
    "ARK Invest": "캐서린 우드",
    "Point72": "스티븐 코헨",
    "Duquesne Family Office": "스탠리 드러켄밀러",
    "Soros Fund Management": "조지 소로스(창업)",
    "TCI Fund Management": "크리스 혼",
    "Viking Global": "앤드리어스 할보르센",
    "AQR Capital": "클리프 애즈니스",
    "Fisher Asset Management": "켄 피셔",
    "Tudor Investment": "폴 튜더 존스",
    "Gates Foundation Trust": "빌 게이츠",
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
        # 🚨 2026-07-30 — report_date(보유 기준일) 추가. filed_at(제출일)과 다르다:
        #   13F 는 분기말 기준 보유를 최대 45일 뒤에 제출하므로 filed_at 만 노출하면
        #   "언제 시점 보유인지" 를 알 수 없어 최신 보유로 오독된다.
        #   실측 예 — Berkshire: filingDate=2026-05-15 / reportDate=2026-03-31.
        reports = filings.get("reportDate", [])
        out = []
        for i, form in enumerate(forms):
            if form == "13F-HR":
                out.append({
                    "cik": cik,
                    "institution": TRACKED_INSTITUTIONS.get(cik, f"CIK_{cik}"),
                    "filed_at": dates[i] if i < len(dates) else None,
                    "report_date": reports[i] if i < len(reports) else None,
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
    # 🚨 2026-07-30 — 확장자 대소문자 무시. Viking Global 은 'MSFS13F033126.XML'(대문자)로
    #   제출해 endswith('.xml') 이 놓쳤고 보유 파싱이 0건이었다(실측: infotable url=None).
    #   primary_doc 비교도 동일하게 대소문자 무시.
    cands = [(it.get("name", ""), int(it.get("size") or 0))
             for it in idx.get("directory", {}).get("item", [])
             if it.get("name", "").lower().endswith(".xml")
             and it.get("name", "").lower() != "primary_doc.xml"]
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


def _normalize_value_units(rows: list[dict], cik: str = "") -> list[dict]:
    """13F value 열의 단위를 filer 별로 정규화 (천 달러 → 달러).

    🚨 2026-07-30 — 기존 코드는 "2023+ 는 전부 실달러"를 **전역 가정**으로 뒀다
    (주석: "×1000 폐기 — 2026-06-22 ALLY $39/주 검증"). 그런데 그 검증은 filer 1곳 표본이었고,
    실제로는 개정 후에도 **천 달러 단위로 계속 제출하는 filer 가 있다**.
    실측(2026-07-30, 15개 filer 전수 중앙 단가):
       Duquesne Family Office  $0.08   ← 유일 이상치. TSM 을 $0.34 로 표기(실제 ~$340)
       나머지 14곳            $73~$310  ← 정상
    보정 없이 쓰면 Duquesne 이 총액 $2.9M 짜리 펀드로 표시된다(실제는 조 단위).

    판별 = 내재단가(value/shares) 중앙값. 13F 는 $100M+ 보유 기관만 제출 대상이라
    책 전체 중앙 단가가 $1 미만인 정상 포트폴리오는 사실상 없다. 중앙값을 쓰므로 개별
    페니스톡 몇 종목으로는 뒤집히지 않는다. ×1000 후에도 상식 범위를 벗어나면 보정하지 않음
    (양방향 오판 방지 — 조용히 틀린 값을 만들지 않는다).
    """
    px = [r["value_usd"] / r["shares"] for r in rows
          if (r.get("shares") or 0) > 0 and (r.get("value_usd") or 0) > 0]
    if len(px) < 3:
        return rows          # 표본 부족 = 판정 보류 (원본 유지)
    med = statistics.median(px)
    if med >= 1.0:
        return rows          # 정상 단위
    scaled = med * 1000.0
    if not (1.0 <= scaled <= 100000.0):
        logger.warning("[13F] CIK=%s 내재단가 중앙값 %.4f — ×1000 후에도 비정상(%.2f), 보정 보류",
                       cik, med, scaled)
        return rows
    logger.warning("[13F] CIK=%s value 열이 천 달러 단위로 판정 (중앙 단가 $%.4f → $%.2f). ×1000 보정 적용",
                   cik, med, scaled)
    for r in rows:
        r["value_usd"] = (r.get("value_usd") or 0) * 1000.0
        r["value_unit_corrected"] = True
    return rows


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
        rows = sorted(agg.values(), key=lambda x: x["value_usd"], reverse=True)
        return _normalize_value_units(rows, cik)
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
