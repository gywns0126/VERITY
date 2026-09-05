"""미장(US) 8-K forensics 빌더 — AlphaNest 미장 소형주 트랙 (Phase 4).

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

등록 공모 (2026-08-09 추가 — 옛 "한계" 항목을 메움):
  S-1 / S-3 / F-1 (+/A) → offering_registered  (등록 신고 = 발행 준비)
  424B*               → offering_priced       (프로스펙터스 = 실제 발행·매출)
  🚨 dilution(8-K 3.02) 과 **합치지 않는다**. 3.02 는 비등록 매출이고 이쪽은 등록 공모라
  성격이 다르다. 합치면 기존 dilution 카운트의 의미가 바뀐다. 같은 submissions 응답에
  이미 들어 있어 추가 HTTP 호출은 0.

위임장 (2026-08-09 추가 — DEF 14A 축):
  DEFC14A / PREC14A → proxy_contest (위임장 대결 = 경영권 분쟁)
  DEFM14A / PREM14A → proxy_merger  (합병·중대거래 승인 안건)
  DEF 14A / PRE 14A → proxy_annual  (정기 주총)
  DEFA14A(추가 권유자료)는 같은 건에 여러 번 붙어 카운트를 부풀리므로 제외.

소비처 = 오퍼레이터 판단 레이어. ticker_facts 가 us_disclosure_forensics.json 을
  이미 소스로 등록하고 있어 별도 배선 없이 종목 질의에 조인된다(공개 화면 아님).

희석 3단계 관측 (이 빌더가 한 화면에서 잇는 것):
  ① proxy_annual 안건에서 수권주식수 증가 승인 → ② offering_registered(S-1/S-3)
  → ③ offering_priced(424B). ①의 안건 내용은 문서 파싱이 필요해 미구현이고,
  지금은 "정기 주총이 있었다" 까지만 사실이다. 단계 간 인과 단정 금지.

한계 (정직, RULE 7): convertible(CB)은 8-K item(1.01 광범위)으로 정확 식별 불가 → 미집계.
  노이즈(2.02 실적 / 5.07 주총 / 7.01 FD / 8.01 기타 / 9.01 첨부 / 5.02 임원) = 미집계.
  등록 신고는 철회·미발행으로 끝날 수 있다 — offering_registered 는 "발행 확정" 이 아니다.
  🚨 위임장은 **폼 코드까지만** 사실이다. 역분할·수권주식수 증가 같은 안건 내용은
  문서 파싱이 필요해 미구현 — proxy_annual 을 "희석 예고" 로 읽으면 안 된다.

입력: data/us_smallcap_corner.json(종목) + data/sec_ticker_cik_map.json(CIK)
출력: data/us_disclosure_forensics.json — 전 US 유니버스 수집 상태 + 최근 8-K + 심화 분류.
LLM 0(RULE 6). 점수/랭킹 0(RULE 7) — 사실 카운트만. SEC throttle 0.3s (10 req/s 한도 안전).
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORNER_PATH = os.path.join(_ROOT, "data", "us_smallcap_corner.json")
CIK_MAP_PATH = os.path.join(_ROOT, "data", "sec_ticker_cik_map.json")
UNIVERSE_PATH = os.path.join(_ROOT, "data", "us_universe_combined.json")
FEED_PATH = os.path.join(_ROOT, "data", "us_disclosure_feed.json")
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


def _offering_category(form: str) -> str:
    """등록 공모 form → 카테고리. 해당 없으면 빈 문자열.

    424B* = 프로스펙터스(실제 발행·매출). S-1/S-3/F-1 = 등록 신고(준비 단계).
    둘을 나누는 이유 = 등록만 하고 발행 안 하는 경우가 흔해 신호 강도가 다르다.
    """
    f = form.upper().strip()
    if f.startswith("424B"):
        return "offering_priced"
    base = f.split("/")[0]  # S-1/A → S-1
    if base in ("S-1", "S-3", "F-1", "F-3"):
        return "offering_registered"
    return ""


def _proxy_category(form: str) -> str:
    """위임장 권유 신고서(14A 계열) → 카테고리. 해당 없으면 빈 문자열.

    SEC 폼 코드 자체가 성격을 구분해 준다 — 문서를 열지 않아도 여기까지는 사실이다.
      DEFC14A / PREC14A → proxy_contest (위임장 대결 = 경영권 분쟁)
      DEFM14A / PREM14A → proxy_merger  (합병·중대거래 승인 안건)
      DEF 14A / PRE 14A → proxy_annual  (정기 주총)
    DEFA14A(추가 권유자료)는 같은 건에 여러 번 붙어 카운트를 부풀리므로 제외한다.
    """
    f = form.upper().replace(" ", "").strip()
    if f in ("DEFC14A", "PREC14A"):
        return "proxy_contest"
    if f in ("DEFM14A", "PREM14A"):
        return "proxy_merger"
    if f in ("DEF14A", "PRE14A"):
        return "proxy_annual"
    return ""


def _fetch_filings(cik10: str, cutoff: str):
    """submissions/CIK → 윈도우 내 (8-K 목록, 등록공모 목록, 위임장 목록).

    셋 다 같은 응답에서 뽑는다 — 축을 늘려도 추가 HTTP 호출은 0이다.
    """
    url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
    req = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
    d = json.loads(urllib.request.urlopen(req, timeout=25).read())
    recent = d.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    items = recent.get("items", [])
    out = []
    offerings = []
    proxies = []
    for i, f in enumerate(forms):
        fdate = dates[i] if i < len(dates) else ""
        if fdate < cutoff:  # ISO 날짜 문자열 비교
            continue
        if f == "8-K":
            raw_items = items[i] if i < len(items) else ""
            codes = [c.strip() for c in str(raw_items).split(",") if c.strip()]
            out.append((fdate, codes))
            continue
        cat = _offering_category(str(f))
        if cat:
            offerings.append((fdate, cat, str(f).upper().strip()))
            continue
        pcat = _proxy_category(str(f))
        if pcat:
            proxies.append((fdate, pcat, str(f).upper().strip()))
    return out, offerings, proxies


def _load_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _deep_existing() -> list:
    """기존 2년 심화 결과만 회수한다.

    첫 전환 전 산출물은 전 행이 심화 결과다. 전환 뒤에는 deep_window_days가 있는
    행만 이어받아, 90일 기본 행이 2년 결과로 승격되는 일을 막는다.
    """
    doc = _load_json(OUTPUT_PATH, {})
    rows = doc.get("stocks") or []
    if (doc.get("_meta") or {}).get("track") == "us_smallcap_forensics":
        return rows
    return [row for row in rows if row.get("deep_window_days")]


def _recent_counts(disclosures: list) -> dict:
    counts = {}
    for disclosure in disclosures:
        for code in disclosure.get("item_codes") or []:
            category = ITEM_CATEGORY.get(str(code).strip())
            if category:
                counts[category] = counts.get(category, 0) + 1
    return counts


def _merge_with_feed(deep_stocks: list) -> dict:
    """일간 8-K feed와 월간 2년 심화 결과를 전 US 유니버스로 합친다.

    feed의 성공 대장을 사용해 `최근 공시 없음`과 `미수집`을 분리한다. 이전 feed처럼
    성공 티커 대장이 없더라도 처리 수가 분모와 같을 때만 전수 성공으로 인정한다.
    """
    universe_doc = _load_json(UNIVERSE_PATH, {})
    universe = [
        str(ticker).strip().upper()
        for ticker in universe_doc.get("tickers") or []
        if str(ticker).strip()
    ]
    names = universe_doc.get("names") or {}
    feed_doc = _load_json(FEED_PATH, {})
    feed_meta = feed_doc.get("_meta") or {}
    feed_rows = {
        str(row.get("ticker") or "").upper(): row
        for row in feed_doc.get("items") or []
        if row.get("ticker")
    }
    deep_rows = {
        str(row.get("ticker") or "").upper(): row
        for row in deep_stocks
        if row.get("ticker")
    }

    coverage = feed_doc.get("_coverage") or {}
    processed_list = coverage.get("processed_tickers")
    if isinstance(processed_list, list):
        processed = {str(ticker).upper() for ticker in processed_list}
    elif int(feed_meta.get("processed_n") or feed_meta.get("covered_this_run") or 0) >= len(universe):
        processed = set(universe)
    else:
        # 성공 대장이 없는 구버전 부분 실행에서는 공시 행이 있는 종목만 최소 성공으로 본다.
        processed = set(feed_rows)

    unavailable = {
        str(ticker).upper()
        for ticker in coverage.get("unavailable_tickers") or []
    }
    unresolved = {
        str(ticker).upper()
        for ticker in coverage.get("unresolved_tickers") or []
    }
    max_recent = int(feed_meta.get("max_per_ticker") or 5)
    recent_window = int(feed_meta.get("window_days") or 90)

    rows = []
    event_present = no_recent = classified = 0
    for ticker in universe:
        recent = feed_rows.get(ticker) or {}
        disclosures = list(recent.get("disclosures") or [])
        recent_counts = _recent_counts(disclosures)
        deep = deep_rows.get(ticker)
        if deep:
            row = dict(deep)
            row["deep_window_days"] = int(
                row.get("deep_window_days") or WINDOW_DAYS
            )
            counts = dict(row.get("counts") or {})
            # 2년 결과가 없는 신규 카테고리만 최근 item code로 보강한다. 겹치는 기간을 합산하지 않는다.
            for key, value in recent_counts.items():
                counts.setdefault(key, value)
            row["counts"] = counts
            row["classification_window_days"] = row["deep_window_days"]
        else:
            row = {
                "ticker": ticker,
                "name": names.get(ticker) or recent.get("name") or ticker,
                "counts": recent_counts,
                "n_8k": len(disclosures),
                "latest_8k": recent.get("latest") or "",
                "classification_window_days": recent_window,
            }

        row["recent_window_days"] = recent_window
        row["recent_8k_n"] = len(disclosures)
        row["recent_8k_truncated"] = len(disclosures) >= max_recent
        row["recent_filings"] = disclosures
        if ticker in processed:
            row["collection_status"] = "covered"
            row["event_state"] = "recent_8k" if disclosures else "no_recent_8k"
        elif ticker in unavailable:
            row["collection_status"] = "source_unavailable"
            row["event_state"] = "unknown"
        elif ticker in unresolved:
            row["collection_status"] = "cik_unresolved"
            row["event_state"] = "unknown"
        else:
            row["collection_status"] = "unprocessed"
            row["event_state"] = "unknown"

        if disclosures:
            event_present += 1
            newest = max(str(row.get("latest_8k") or ""), str(recent.get("latest") or ""))
            row["latest_8k"] = newest
        elif row["event_state"] == "no_recent_8k":
            no_recent += 1
        if row.get("counts"):
            classified += 1
        rows.append(row)

    unprocessed = sorted(set(universe) - processed)
    return {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "track": "us_forensics_full_universe",
            "source": "SEC EDGAR 일간 8-K feed(최근 기간) + 월간 소형주 8-K item 심화",
            "universe_n": len(universe),
            "processed_n": len(processed),
            "unprocessed_n": len(unprocessed),
            "unprocessed_tickers": unprocessed,
            "event_present_n": event_present,
            "no_recent_8k_n": no_recent,
            "deep_flagged_n": len(deep_rows),
            "classified_n": classified,
            "recent_window_days": recent_window,
            "deep_window_days": WINDOW_DAYS,
            "item_map": ITEM_CATEGORY,
            "disclaimer": "8-K 제출과 SEC item 분류 사실만 표시한다. 분류는 위험도 판단이 아니다. "
                          "최근 목록은 종목당 상한이 있어 recent_8k_truncated=true면 최소 건수다.",
        },
        "stocks": rows,
    }


def _write_output(doc: dict) -> None:
    tmp = OUTPUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUTPUT_PATH)


def main(merge_feed_only: bool = False) -> int:
    if merge_feed_only:
        out = _merge_with_feed(_deep_existing())
        if not out.get("stocks"):
            print("[us_forensics] full universe 0종 — 기존 snapshot 보존", file=sys.stderr)
            return 1
        _write_output(out)
        meta = out["_meta"]
        print(
            f"[us_forensics] feed merge OK | processed {meta['processed_n']}/{meta['universe_n']} "
            f"| recent {meta['event_present_n']} | no_recent {meta['no_recent_8k_n']}"
        )
        return 0

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
            filings, offerings, proxies = _fetch_filings(_cik10(raw_cik), cutoff)
        except Exception as e:  # noqa: BLE001
            print(f"[us_forensics] {tk} 공시 fetch 실패: {type(e).__name__}", file=sys.stderr)
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

        # 등록 공모 — dilution(3.02) 과 별도 키로 집계한다.
        latest_offering = ""
        latest_offering_form = ""
        for fdate, cat, form in offerings:
            counts[cat] = counts.get(cat, 0) + 1
            if fdate > latest_offering:
                latest_offering = fdate
                latest_offering_form = form

        # 위임장 — 폼 코드만으로 구분 가능한 범위까지만 집계한다.
        latest_proxy = ""
        latest_proxy_form = ""
        for fdate, cat, form in proxies:
            counts[cat] = counts.get(cat, 0) + 1
            if fdate > latest_proxy:
                latest_proxy = fdate
                latest_proxy_form = form

        if counts:  # forensic 신호 보유 종목만 (사실 없으면 비노출, RULE 7)
            stocks.append({
                "ticker": tk,
                "name": st.get("name") or "",
                "counts": counts,
                "n_8k": len(filings),
                "latest_8k": latest,
                "n_offering": len(offerings),
                "latest_offering": latest_offering,
                "latest_offering_form": latest_offering_form,
                "n_proxy": len(proxies),
                "latest_proxy": latest_proxy,
                "latest_proxy_form": latest_proxy_form,
            })
            ok += 1
        else:
            ok += 1  # fetch 성공이나 forensic 신호 0 (정상 — 깨끗한 종목)
        if idx % 100 == 0:
            print(f"  [{idx}/{len(corner)}] ok={ok} fail={fail} flagged={len(stocks)}", file=sys.stderr, flush=True)
        time.sleep(0.3)  # SEC 10 req/s 한도 안전

    deep_out = {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "track": "us_smallcap_forensics",
            "source": "SEC EDGAR submissions — 8-K items + 등록공모(S-1/S-3/F-1/424B) + 위임장(14A)",
            "window_days": WINDOW_DAYS,
            "universe_n": len(corner),
            "flagged_n": len(stocks),
            "item_map": ITEM_CATEGORY,
            "disclaimer": "8-K item 사실 카운트 — 점수/추천 아님(RULE 7). dilution=Item 3.02(unregistered)만, "
                          "registered offering(424B) 미포함. convertible(CB) 미집계.",
        },
        "stocks": stocks,
    }
    out = _merge_with_feed(deep_out["stocks"])
    _write_output(out)
    print(f"[us_forensics] 적재 OK | universe {len(corner)} | flagged {len(stocks)} | "
          f"ok={ok} fail={fail} | window {WINDOW_DAYS}d | out={OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--merge-feed-only", action="store_true")
    args = parser.parse_args()
    raise SystemExit(main(merge_feed_only=args.merge_feed_only))
