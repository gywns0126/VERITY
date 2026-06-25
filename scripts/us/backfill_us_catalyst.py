#!/usr/bin/env python3
"""
backfill_us_catalyst.py — US 과거 8-K 카탈리스트 backfill (SEC EDGAR) → US 이벤트스터디 입력.

2026-06-25 신설 (PM 결정 "전부"). KR dart_catalyst_backfill 의 US 대응. SEC submissions(recent 1000 + 과거
shard) 의 8-K + items 코드 → 유형 분류(실적/계약/M&A/주식발행/상장폐지 등). 무료·UA only(키 0), 로컬 실행 가능.

출력: data/us_catalyst_backfill.jsonl  {ticker,name,date,items,label,tone,acc,url}
resume: data/us_catalyst_backfill_done.json (스캔 완료 ticker). 멱등: accession dedup.
usage: python3 scripts/us/backfill_us_catalyst.py [--since-year 2015] [--limit N] [--universe PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _ROOT)

from api.config import DATA_DIR, now_kst
from api.collectors.sec_edgar import _resolve_cik, _throttle, _headers, _SESSION, _DATA_BASE
from api.intelligence.us_financials import SEC_USER_AGENT

OUT_PATH = os.path.join(DATA_DIR, "us_catalyst_backfill.jsonl")
DONE_PATH = os.path.join(DATA_DIR, "us_catalyst_backfill_done.json")
DEFAULT_UNIVERSE = os.path.join(DATA_DIR, "us_stock_report_public.json")

# 8-K item 코드 → (한글 라벨, tone). 우선순위 = alert > dilution > 나머지(첫 매칭 유형 채택).
# 절차성(5.07 주총결과·5.03 정관·7.01 RegFD·9.01 첨부)·generic(8.01) = 미분류(skip).
ITEM_MAP = {
    "1.03": ("파산·법정관리", "alert"),
    "2.03": ("채무 발생", "alert"),
    "2.04": ("채무 가속", "alert"),
    "3.01": ("상장폐지 통지", "alert"),
    "4.01": ("회계법인 변경", "alert"),
    "4.02": ("재무제표 정정", "alert"),
    "3.02": ("주식 발행(사모)", "dilution"),
    "1.01": ("주요계약 체결", "favor"),
    "2.01": ("인수·합병 완료", "neutral"),
    "2.02": ("실적 발표", "neutral"),
    "5.02": ("경영진 변동", "neutral"),
    "1.02": ("주요계약 종료", "alert"),
}
# 분류 우선순위 (한 8-K 에 여러 item → 가장 중대한 1개 채택).
_PRIORITY = ["1.03", "4.02", "3.01", "2.04", "2.03", "4.01", "1.02", "3.02", "2.01", "1.01", "2.02", "5.02"]


def _classify(items_str: str):
    """'2.02,9.01' → (라벨, tone) 또는 None(분류 가능 item 없음)."""
    codes = {c.strip() for c in (items_str or "").split(",") if c.strip()}
    for p in _PRIORITY:
        if p in codes:
            return ITEM_MAP[p]
    return None


def _load_done():
    try:
        with open(DONE_PATH, encoding="utf-8") as f:
            return set(json.load(f).get("tickers") or [])
    except (OSError, json.JSONDecodeError):
        return set()


def _save_done(done):
    tmp = DONE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"tickers": sorted(done)}, f, ensure_ascii=False)
    os.replace(tmp, DONE_PATH)


def _universe(path, limit, only):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    stocks = d if isinstance(d, list) else (d.get("stocks") or [])
    out = []
    for s in stocks:
        tk = str(s.get("ticker") or "").strip().upper()
        if only and tk != only:
            continue
        if tk:
            out.append((tk, s.get("name") or tk))
    return out[:limit] if limit else out


def _fetch_8k_history(ticker: str, ua: str, since: str):
    """submissions recent + 과거 shard 의 8-K → [{date, items, acc, cik}] (since 이상)."""
    cik = _resolve_cik(ticker, ua)
    if not cik:
        return None
    out = []

    def _proc(rec):
        forms = rec.get("form", [])
        dates = rec.get("filingDate", [])
        items = rec.get("items", [])
        accs = rec.get("accessionNumber", [])
        for i, fm in enumerate(forms):
            if fm != "8-K":
                continue
            dt = dates[i] if i < len(dates) else ""
            if not dt or dt < since:
                continue
            out.append({
                "date": dt,
                "items": items[i] if i < len(items) else "",
                "acc": (accs[i] if i < len(accs) else "").replace("-", ""),
                "cik": cik,
            })

    _throttle()
    d = _SESSION.get(f"{_DATA_BASE}/submissions/CIK{cik}.json", headers=_headers(ua), timeout=15).json()
    _proc(d.get("filings", {}).get("recent", {}))
    for shard in d.get("filings", {}).get("files", []):
        nm = shard.get("name")
        if not nm:
            continue
        # shard 의 filingDate 범위가 since 이전이면 skip (호출 절약)
        if shard.get("filingTo", "") and shard.get("filingTo") < since:
            continue
        _throttle()
        try:
            sd = _SESSION.get(f"{_DATA_BASE}/submissions/{nm}", headers=_headers(ua), timeout=15).json()
            _proc(sd)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"[us-cat] {ticker} shard {nm} 실패: {str(e)[:60]}\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-year", type=int, default=2015)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ticker", default=None)
    ap.add_argument("--universe", default=None)
    args = ap.parse_args()

    since = f"{args.since_year}-01-01"
    ua = SEC_USER_AGENT
    universe = _universe(args.universe or DEFAULT_UNIVERSE, args.limit, (args.ticker or "").upper() or None)
    done = _load_done()
    seen = set()
    if os.path.isfile(OUT_PATH):
        with open(OUT_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    seen.add(json.loads(line).get("acc"))
                except (json.JSONDecodeError, AttributeError):
                    pass
    todo = [(t, n) for (t, n) in universe if t not in done]
    print(f"[us-cat] 유니버스 {len(universe)} | 완료 {len(done)} | 잔여 {len(todo)} (since {since})", file=sys.stderr)

    new_n = 0
    with open(OUT_PATH, "a", encoding="utf-8") as out:
        for idx, (tk, name) in enumerate(todo, 1):
            try:
                events = _fetch_8k_history(tk, ua, since)
            except Exception as e:  # noqa: BLE001
                sys.stderr.write(f"[us-cat] {tk} 실패: {type(e).__name__}: {str(e)[:60]}\n")
                continue
            if events is None:
                sys.stderr.write(f"[us-cat] {tk} CIK 없음 — skip\n")
                done.add(tk); _save_done(done)
                continue
            tk_n = 0
            for e in events:
                acc = e["acc"]
                if not acc or acc in seen:
                    continue
                cls = _classify(e["items"])
                if not cls:
                    continue
                seen.add(acc)
                out.write(json.dumps({
                    "ticker": tk, "name": name, "date": e["date"], "items": e["items"],
                    "label": cls[0], "tone": cls[1], "acc": acc,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{e['cik'].lstrip('0')}/{acc}/",
                }, ensure_ascii=False) + "\n")
                new_n += 1; tk_n += 1
            done.add(tk); _save_done(done)
            if idx % 50 == 0 or idx == len(todo):
                print(f"[us-cat] {idx}/{len(todo)} — 신규 {new_n}건", file=sys.stderr)
    print(f"[us-cat] 완료 — 신규 {new_n}건 · done={len(done)} -> {os.path.relpath(OUT_PATH, _ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
