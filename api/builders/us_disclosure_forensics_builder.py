"""미장(US) 8-K forensics 빌더 — 골든구스 미장 소형주 트랙 (Phase 4).

KR disclosure_forensics(DART)의 미장 대응. SEC 8-K item 코드를 카테고리로 집계 —
소형주 위험 신호(희석/상폐/부실/재무재작성)를 '사실 카운트'. 미장 8-K item 은 표준 분류라
KR DART 보다 정밀: restatement / auditor_change = 미장 특화 red flag (KR 엔 없음 = 차별).

매핑 정확도 (SEC 공식 Form 8-K item — 명확 매핑만, 모호/노이즈 제외):
  3.02 → dilution          (Unregistered Sales of Equity Securities)
  3.01 → delisting_risk    (Notice of Delisting / Failure to Satisfy Listing)
  1.03 → bankruptcy        (Bankruptcy or Receivership)
  2.04 → debt_default      (Triggering Events — accelerate Direct Financial Obligation)
  2.06 → impairment        (Material Impairments)
  4.02 → restatement       (Non-Reliance on Previously Issued Financials)  ← 미장 특화
  4.01 → auditor_change    (Changes in Registrant's Certifying Accountant) ← 미장 특화
  2.01 → mna               (Completion of Acquisition or Disposition of Assets)
  3.03 → rights_modification (Material Modification to Rights — reverse split 등)
  5.01 → control_change    (Changes in Control of Registrant)
  2.05 → restructuring     (Costs Associated with Exit or Disposal)

한계 (정직, RULE 7): registered offering(424B/S-1)은 8-K 아님 → dilution 은 Item 3.02
  (unregistered) 만 포착. convertible(CB)은 8-K item(1.01 광범위)으로 정확 식별 불가 → 미집계.
  노이즈(2.02 실적 / 5.07 주총 / 7.01 FD / 8.01 기타 / 9.01 첨부 / 5.02 임원) = 미집계.

입력: data/us_smallcap_corner.json(종목) + data/sec_ticker_cik_map.json(CIK)
출력: data/us_disclosure_forensics.json {stocks:[{ticker, name, counts, latest_8k, n_8k}]}
LLM 0(RULE 6). 점수/랭킹 0(RULE 7) — 사실 카운트만. SEC throttle 0.3s (10 req/s 한도 안전).
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORNER_PATH = os.path.join(_ROOT, "data", "us_smallcap_corner.json")
CIK_MAP_PATH = os.path.join(_ROOT, "data", "sec_ticker_cik_map.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_disclosure_forensics.json")

KST = timezone(timedelta(hours=9))
SEC_USER_AGENT = "VERITY gywns0126@gmail.com"
WINDOW_DAYS = 730  # 8-K 누적 윈도우 (소형주 희석/부실은 수년 누적 신호)

# SEC 공식 Form 8-K item → forensic category (명확 매핑만, WebSearch+SEC 검증 2026-06-24).
ITEM_CATEGORY = {
    "3.02": "dilution",
    "3.01": "delisting_risk",
    "1.03": "bankruptcy",
    "2.04": "debt_default",
    "2.06": "impairment",
    "4.02": "restatement",
    "4.01": "auditor_change",
    "2.01": "mna",
    "3.03": "rights_modification",
    "5.01": "control_change",
    "2.05": "restructuring",
}


def _now_kst() -> datetime:
    return datetime.now(KST)


def _cik10(raw) -> str:
    """sec_ticker_cik_map 값 → 10자리 zero-pad CIK."""
    s = str(raw).upper().replace("CIK", "").strip()
    return s.zfill(10) if s.isdigit() else s


def _fetch_8k_items(cik10: str, cutoff: str):
    """submissions/CIK → 윈도우 내 8-K filing 의 (date, items list). 실패 시 None."""
    url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
    req = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
    d = json.loads(urllib.request.urlopen(req, timeout=25).read())
    recent = d.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    items = recent.get("items", [])
    out = []
    for i, f in enumerate(forms):
        if f != "8-K":
            continue
        fdate = dates[i] if i < len(dates) else ""
        if fdate < cutoff:  # ISO 날짜 문자열 비교
            continue
        raw_items = items[i] if i < len(items) else ""
        codes = [c.strip() for c in str(raw_items).split(",") if c.strip()]
        out.append((fdate, codes))
    return out


def main() -> int:
    if not os.path.exists(CORNER_PATH):
        print(f"[us_forensics] 코너 부재: {CORNER_PATH} — us_smallcap_corner_builder 먼저. skip")
        return 0
    corner = json.load(open(CORNER_PATH, encoding="utf-8")).get("stocks") or []
    cik_map = json.load(open(CIK_MAP_PATH, encoding="utf-8")) if os.path.exists(CIK_MAP_PATH) else {}

    cutoff = (_now_kst() - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    stocks = []
    ok = fail = 0
    for idx, st in enumerate(corner, 1):
        tk = str(st.get("ticker", "")).upper()
        raw_cik = cik_map.get(tk) or cik_map.get(tk.replace("-", "."))
        if not raw_cik:
            fail += 1
            continue
        try:
            filings = _fetch_8k_items(_cik10(raw_cik), cutoff)
        except Exception as e:  # noqa: BLE001
            print(f"[us_forensics] {tk} 8-K fetch 실패: {type(e).__name__}", file=sys.stderr)
            fail += 1
            time.sleep(0.3)
            continue
        counts = {}
        latest = ""
        for fdate, codes in filings:
            if fdate > latest:
                latest = fdate
            for c in codes:
                cat = ITEM_CATEGORY.get(c)
                if cat:
                    counts[cat] = counts.get(cat, 0) + 1
        if counts:  # forensic 신호 보유 종목만 (사실 없으면 비노출, RULE 7)
            stocks.append({
                "ticker": tk,
                "name": st.get("name") or "",
                "counts": counts,
                "n_8k": len(filings),
                "latest_8k": latest,
            })
            ok += 1
        else:
            ok += 1  # fetch 성공이나 forensic 신호 0 (정상 — 깨끗한 종목)
        if idx % 100 == 0:
            print(f"  [{idx}/{len(corner)}] ok={ok} fail={fail} flagged={len(stocks)}", file=sys.stderr, flush=True)
        time.sleep(0.3)  # SEC 10 req/s 한도 안전

    out = {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "track": "us_smallcap_forensics",
            "source": "SEC EDGAR submissions 8-K items",
            "window_days": WINDOW_DAYS,
            "universe_n": len(corner),
            "flagged_n": len(stocks),
            "item_map": ITEM_CATEGORY,
            "disclaimer": "8-K item 사실 카운트 — 점수/추천 아님(RULE 7). dilution=Item 3.02(unregistered)만, "
                          "registered offering(424B) 미포함. convertible(CB) 미집계.",
        },
        "stocks": stocks,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"[us_forensics] 적재 OK | universe {len(corner)} | flagged {len(stocks)} | "
          f"ok={ok} fail={fail} | window {WINDOW_DAYS}d | out={OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
