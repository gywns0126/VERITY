#!/usr/bin/env python3
"""us_earnings_pattern_backfill — 미장 실적 공시 제출 패턴 초기 적재 (어닝 캘린더 스프린트 2026-07-04).

소스 조사 결론: 어닝 캘린더 = 외부 소스(권리 blocker) 대신 EDGAR 제출 패턴 자체계산.
실측(AAPL) = 10-Q/K 제출이 6분기 연속 분기말+34일 — 기업별 지연이 기계적으로 안정.

submissions API(종목당 1콜, 일일 쿼터 없음·정중 throttle)에서 10-Q/10-K filed 이력(최근 10건)
→ data/us_earnings_pattern.json. 이후 유지 = us_financials_incremental 이 daily index 에서 신규
제출을 같은 파일에 append (일 단위 신선도).

멱등: 이미 적재된 ticker skip (--refresh 로 전체 갱신).
usage: python scripts/us_earnings_pattern_backfill.py [--max N] [--refresh]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(_ROOT, "data", "us_earnings_pattern.json")
SUMMARY_PATHS = [
    os.path.join(_ROOT, "data", "us_financials", "_summary.json"),
    os.path.join(_ROOT, "data", "us_financials", "_summary_smallcap.json"),
]
UA = "VERITY gywns0126@gmail.com"
KEEP = 10
THROTTLE = 0.15
TARGET_FORMS = ("10-Q", "10-K")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _cik_map():
    out = {}
    for p in SUMMARY_PATHS:
        doc = _load(p, {})
        for r in (doc.get("rows") or []):
            if r.get("cik") is not None and r.get("ticker"):
                out[str(r["ticker"])] = int(r["cik"])
    return out


def _fetch_filings(cik: int):
    url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    rec = (d.get("filings") or {}).get("recent") or {}
    rows = []
    for form, filed in zip(rec.get("form") or [], rec.get("filingDate") or []):
        if form in TARGET_FORMS:
            rows.append({"form": form, "filed": filed})
        if len(rows) >= KEEP:
            break
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    ciks = _cik_map()
    doc = _load(OUT_PATH, {"_meta": {}, "patterns": {}})
    pat = doc.get("patterns") or {}
    todo = sorted(t for t in ciks if args.refresh or t not in pat)
    if args.max:
        todo = todo[: args.max]
    print(f"[earn_pattern] 대상 {len(todo)} / 유니버스 {len(ciks)}", file=sys.stderr)

    ok = err = 0
    for i, tk in enumerate(todo, 1):
        try:
            rows = _fetch_filings(ciks[tk])
            if rows:
                pat[tk] = rows
                ok += 1
        except Exception as e:
            err += 1
            if err <= 5:
                print(f"[earn_pattern] {tk} 실패: {type(e).__name__}", file=sys.stderr)
        if i % 100 == 0:
            print(f"[earn_pattern] 진행 {i}/{len(todo)} (ok={ok})", file=sys.stderr)
            # 중간 저장 — 장시간 run 부분 진척 보존
            doc["patterns"] = pat
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
        time.sleep(THROTTLE)

    doc["patterns"] = pat
    doc["_meta"] = {"count": len(pat), "source": "SEC EDGAR submissions (10-Q/10-K filed 이력, 자체 패턴 계산용)",
                    "keep": KEEP}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    print(f"[earn_pattern] logged=True · 신규 {ok} (오류 {err}) → 총 {len(pat)} / {OUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
