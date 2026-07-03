#!/usr/bin/env python3
"""kr_sector_dart_fallback — yfinance 미커버 종목 섹터를 DART 기업개황(induty_code)으로 폴백.

2026-07-04 peer 조사 후속: kr_sector_map(yfinance) 재백필 후에도 277종목 미매핑(주로 소형 코스닥,
yfinance .info 커버 밖) → peer 82% 정체. DART company.json 의 induty_code(KSIC) 앞 2자리를
표준 산업분류→11대 섹터 대응표로 매핑해 kr_sector_map 에 병합 (source 구분 표기).

사실성: KSIC = 회사가 공시한 표준 산업분류 — 대응표는 분류 체계 간 표준 대응(자체 판단 최소).
DART 쿼터: 미매핑 수만큼(~300콜) 1회성. 멱등(이미 매핑된 ticker skip).
usage: python scripts/kr_sector_dart_fallback.py [--max N] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from api.config import DART_API_KEY  # noqa: E402
from api.collectors.dart_corp_code import get_corp_code  # noqa: E402

MAP_PATH = os.path.join(_ROOT, "data", "kr_sector_map.json")
FUND_PATH = os.path.join(_ROOT, "data", "dart_fundamentals_kr.json")
REPORT_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")
THROTTLE = 0.15

# KSIC 대분류(2자리) → kr_sector_map 11대 섹터 (표준 분류 체계 대응)
KSIC2_SECTOR: dict = {
    **{k: "필수소비재" for k in ["01", "02", "03", "10", "11", "12"]},          # 농림어업·식품·음료·담배
    **{k: "에너지" for k in ["05", "19"]},                                      # 석탄·석유정제
    **{k: "소재" for k in ["06", "07", "08", "16", "17", "20", "22", "23", "24"]},  # 광업·목재·펄프·화학·고무·비금속·1차금속
    **{k: "경기소비재" for k in ["13", "14", "15", "30", "32", "45", "46", "47", "55", "56", "85", "90", "91"]},
    **{k: "헬스케어" for k in ["21", "27", "70", "86", "87"]},                  # 의약품·의료정밀·연구개발·보건
    **{k: "산업재" for k in ["18", "25", "28", "29", "31", "33", "34", "41", "42", "49", "50", "51", "52", "71", "72", "73", "74", "75", "76"]},
    **{k: "유틸리티" for k in ["35", "36", "37", "38", "39"]},
    **{k: "IT·기술" for k in ["26", "58", "62", "63"]},                         # 전자·출판(SW)·정보서비스
    **{k: "커뮤니케이션" for k in ["59", "60", "61"]},
    **{k: "금융" for k in ["64", "65", "66"]},
    "68": "부동산",
}


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _induty(corp_code: str):
    url = f"https://opendart.fss.or.kr/api/company.json?crtfc_key={DART_API_KEY}&corp_code={corp_code}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    if d.get("status") != "000":
        return None
    return str(d.get("induty_code") or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not DART_API_KEY:
        print("[sector_dart] DART_API_KEY 없음 — skip", file=sys.stderr)
        return 0

    doc = _load(MAP_PATH, {"_meta": {}, "map": {}})
    mp = doc.get("map") or {}

    # 유니버스 = 리포트 KR ∪ dart_fundamentals — 미매핑만
    universe = set()
    rep = _load(REPORT_PATH, {})
    for s in (rep.get("stocks") or []):
        tk = str(s.get("ticker") or "")
        if tk.isdigit() and len(tk) == 6:
            universe.add(tk)
    fund = _load(FUND_PATH, {})
    for tk in (fund if isinstance(fund, dict) else {}):
        if str(tk).isdigit() and len(str(tk)) == 6:
            universe.add(str(tk))
    todo = sorted(t for t in universe if t not in mp)
    if args.max:
        todo = todo[: args.max]
    print(f"[sector_dart] 미매핑 {len(todo)} / 유니버스 {len(universe)}", file=sys.stderr)
    if args.dry_run or not todo:
        return 0

    ok = miss = err = 0
    for i, tk in enumerate(todo, 1):
        try:
            cc = get_corp_code(tk)
            if not cc:
                miss += 1
                continue
            code = _induty(cc)
            sec = KSIC2_SECTOR.get((code or "")[:2]) if code else None
            if not sec:
                miss += 1
                continue
            mp[tk] = {"sector": f"KSIC-{code}", "sector_ko": sec, "industry": f"KSIC {code} (DART 기업개황)"}
            ok += 1
        except Exception as e:
            err += 1
            if err <= 5:
                print(f"[sector_dart] {tk} 실패: {type(e).__name__}", file=sys.stderr)
        if i % 50 == 0:
            print(f"[sector_dart] 진행 {i}/{len(todo)} (ok={ok})", file=sys.stderr)
        time.sleep(THROTTLE)

    doc["map"] = mp
    meta = doc.get("_meta") or {}
    meta.update({"count": len(mp), "source": "yfinance .info sector + DART company.json induty(KSIC) 폴백"})
    doc["_meta"] = meta
    with open(MAP_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print(f"[sector_dart] logged=True · 신규 {ok} 매핑 (미확정 {miss}, 오류 {err}) → 총 {len(mp)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
