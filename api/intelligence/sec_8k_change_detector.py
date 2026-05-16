"""
SEC 8-K (현재 보고서) 신규 filing 매일 detect + Telegram critical alert.

US15 종목 (data/universe_candidates.json) 의 SEC EDGAR submissions API 매일 fetch →
data/sec_8k_cache.json 의 last_seen accession_number 와 diff → 새 8-K 발견 시
Telegram bypass_quiet alert + 가벼운 Perplexity 요약 첨부.

Cron: .github/workflows/sec_8k_alert.yml 매일 KST 06:30 (US 시장 마감 직후).
비용: SEC EDGAR free + yfinance free + Perplexity 요약만 (0~3건/주 추정).

EDGAR API:
  - submissions: https://data.sec.gov/submissions/CIK{10자리}.json
  - User-Agent header 필수 (https://www.sec.gov/os/accessing-edgar-data 정합)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

KST = timezone(timedelta(hours=9))
DATA_DIR = REPO_ROOT / "data"
UNIVERSE_PATH = DATA_DIR / "universe_candidates.json"
CACHE_PATH = DATA_DIR / "sec_8k_cache.json"

# SEC 정책: User-Agent 에 식별 가능한 contact 필수. https://www.sec.gov/os/accessing-edgar-data
_UA = "VERITY Equity Brief Bot gywns0126@gmail.com"
_HEADERS = {"User-Agent": _UA, "Accept": "application/json"}


_TICKER_CIK_CACHE: Optional[Dict[str, str]] = None
_TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
_TICKER_CIK_CACHE_PATH = DATA_DIR / "sec_ticker_cik_map.json"
_TICKER_CIK_TTL_DAYS = 30  # SEC 가 분기별 update. 30일 마진 충분.


def _load_ticker_cik_map() -> Dict[str, str]:
    """SEC 공식 ticker → CIK10 매핑. cache 30일.

    Returns: {"AAPL": "0000320193", "MSFT": "0000789019", ...}
    """
    global _TICKER_CIK_CACHE
    if _TICKER_CIK_CACHE is not None:
        return _TICKER_CIK_CACHE

    # 디스크 cache 30일 안이면 사용
    if _TICKER_CIK_CACHE_PATH.exists():
        try:
            mtime = datetime.fromtimestamp(_TICKER_CIK_CACHE_PATH.stat().st_mtime, tz=KST)
            age_days = (datetime.now(KST) - mtime).days
            if age_days < _TICKER_CIK_TTL_DAYS:
                _TICKER_CIK_CACHE = json.loads(_TICKER_CIK_CACHE_PATH.read_text())
                return _TICKER_CIK_CACHE
        except Exception:
            pass

    # SEC fetch
    try:
        resp = requests.get(_TICKER_CIK_URL, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        print(f"[sec_8k] ticker map fetch fail: {e}", file=sys.stderr)
        return {}

    # raw 형식: {"0": {"cik_str": 320193, "ticker": "AAPL", ...}, ...}
    mapping: Dict[str, str] = {}
    for _, row in raw.items():
        ticker = str(row.get("ticker", "")).upper()
        cik = row.get("cik_str")
        if ticker and cik is not None:
            mapping[ticker] = str(int(cik)).zfill(10)

    try:
        _TICKER_CIK_CACHE_PATH.write_text(json.dumps(mapping, ensure_ascii=False))
    except Exception:
        pass
    _TICKER_CIK_CACHE = mapping
    return mapping


def _ticker_to_cik(ticker: str) -> Optional[str]:
    """SEC 공식 매핑 (free, 모든 US listed 포함)."""
    return _load_ticker_cik_map().get(ticker.upper())


def _fetch_recent_8k(cik10: str, limit: int = 10) -> List[Dict[str, Any]]:
    """EDGAR submissions API → 최근 8-K filing 목록."""
    url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[sec_8k] {cik10} fetch fail: {e}", file=sys.stderr)
        return []

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    items = recent.get("items", [])  # 8-K item numbers (e.g. "1.01,5.02")

    out = []
    for i, form in enumerate(forms):
        if form != "8-K":
            continue
        out.append({
            "accession": accessions[i] if i < len(accessions) else "",
            "filing_date": dates[i] if i < len(dates) else "",
            "primary_doc": primary_docs[i] if i < len(primary_docs) else "",
            "items": items[i] if i < len(items) else "",
        })
        if len(out) >= limit:
            break
    return out


# 8-K Item code → 사람 친화 description (https://www.sec.gov/files/form8-k.pdf 정합)
_ITEM_DESC = {
    "1.01": "Entry into Material Definitive Agreement",
    "1.02": "Termination of Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership",
    "2.01": "Completion of Acquisition or Disposition of Assets",
    "2.02": "Results of Operations and Financial Condition (Earnings)",
    "2.03": "Creation of Material Direct Financial Obligation",
    "2.04": "Triggering Events That Accelerate Obligation",
    "2.05": "Costs Associated with Exit or Disposal Activities",
    "2.06": "Material Impairments",
    "3.01": "Notice of Delisting",
    "3.02": "Unregistered Sales of Equity Securities",
    "3.03": "Material Modification to Rights of Security Holders",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements",
    "5.01": "Changes in Control of Registrant",
    "5.02": "Departure/Election/Appointment of Directors or Officers",
    "5.03": "Amendments to Articles of Incorporation or Bylaws",
    "5.07": "Submission of Matters to a Vote of Security Holders",
    "7.01": "Regulation FD Disclosure",
    "8.01": "Other Events",
    "9.01": "Financial Statements and Exhibits",
}


def _items_human(items_csv: str) -> str:
    """'1.01,5.02' → '계약 체결 / 임원 인사'"""
    if not items_csv:
        return "(items unknown)"
    parts = [p.strip() for p in items_csv.split(",") if p.strip()]
    return " / ".join(_ITEM_DESC.get(p, p) for p in parts)


def _load_cache() -> Dict[str, Any]:
    if not CACHE_PATH.exists():
        return {"by_ticker": {}}
    try:
        return json.loads(CACHE_PATH.read_text())
    except Exception:
        return {"by_ticker": {}}


def _save_cache(cache: Dict[str, Any]) -> None:
    cache["last_checked_at"] = datetime.now(KST).isoformat(timespec="seconds")
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


def load_us_tickers() -> List[str]:
    if not UNIVERSE_PATH.exists():
        return []
    try:
        u = json.loads(UNIVERSE_PATH.read_text())
        return [
            c.get("ticker", "").upper()
            for c in u.get("candidates", [])
            if c.get("market", "").upper() in ("US", "NASDAQ", "NYSE", "NYS")
        ]
    except Exception:
        return []


def _send_telegram(text: str) -> None:
    """Telegram bypass_quiet 발송 — 시간대 quiet hours 무시."""
    try:
        from api.notifications.telegram import send_message
        send_message(text, dedupe=True, bypass_quiet=True)
    except Exception as e:
        print(f"[sec_8k] telegram FAIL: {e}", file=sys.stderr)


def detect_changes(tickers: Optional[List[str]] = None) -> Dict[str, Any]:
    """US15 ticker 별 8-K diff + 새 filing alert."""
    if tickers is None:
        tickers = load_us_tickers()
    if not tickers:
        return {"_error": "no tickers"}

    cache = _load_cache()
    by_ticker = cache.setdefault("by_ticker", {})

    new_filings_summary: List[Dict[str, Any]] = []
    for t in tickers:
        cik10 = _ticker_to_cik(t)
        if not cik10:
            print(f"[sec_8k] {t} CIK 못 찾음 — skip", file=sys.stderr)
            continue

        recent = _fetch_recent_8k(cik10, limit=5)
        time.sleep(0.15)  # SEC rate limit (10 req/sec) 안전 마진

        if not recent:
            continue

        latest_accession = recent[0]["accession"]
        last_seen = by_ticker.get(t, {}).get("last_accession", "")

        if last_seen and latest_accession == last_seen:
            # 변화 없음
            continue

        # 새 8-K (또는 첫 run). 마지막 seen 이후 filings 만 추출.
        new_ones = []
        for f in recent:
            if f["accession"] == last_seen:
                break
            new_ones.append(f)

        if new_ones and last_seen:
            # 진짜 신규 (첫 run 이 아닌)
            for nf in new_ones:
                summary = {
                    "ticker": t,
                    "accession": nf["accession"],
                    "filing_date": nf["filing_date"],
                    "items_csv": nf["items"],
                    "items_human": _items_human(nf["items"]),
                    "primary_doc_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{nf['accession'].replace('-', '')}/{nf['primary_doc']}",
                }
                new_filings_summary.append(summary)

        by_ticker[t] = {
            "cik": cik10,
            "last_accession": latest_accession,
            "last_filing_date": recent[0]["filing_date"],
            "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        }

    _save_cache(cache)

    # Telegram alert (있을 때만)
    if new_filings_summary:
        lines = [f"🚨 *SEC 8-K 신규 filing* ({len(new_filings_summary)}건)\n"]
        for f in new_filings_summary[:10]:  # max 10 in single message
            lines.append(
                f"• `{f['ticker']}` {f['filing_date']} — {f['items_human']}\n"
                f"  {f['primary_doc_url']}"
            )
        _send_telegram("\n".join(lines))
        print(f"[sec_8k] {len(new_filings_summary)}건 신규 — telegram 발송", file=sys.stderr)
    else:
        print(f"[sec_8k] {len(tickers)} ticker 확인 — 신규 0건", file=sys.stderr)

    return {
        "checked_at": datetime.now(KST).isoformat(timespec="seconds"),
        "tickers_checked": len(tickers),
        "new_filings_count": len(new_filings_summary),
        "new_filings": new_filings_summary,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="SEC 8-K change detector")
    ap.add_argument("--tickers", help="comma-separated override (default = US15)")
    ap.add_argument("--reset-cache", action="store_true", help="cache 초기화 (첫 run 또는 강제 재초기화)")
    args = ap.parse_args()

    if args.reset_cache and CACHE_PATH.exists():
        CACHE_PATH.unlink()
        print(f"[sec_8k] cache 초기화: {CACHE_PATH}", file=sys.stderr)

    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    result = detect_changes(tickers)
    print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
