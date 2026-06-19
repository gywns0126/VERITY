"""kr_sector_backfill — KR 전종목 섹터 매핑 백필 (동종업계 비교용).

2026-06-19 신설. 공개 종목리포트 "동종업계 비교" 섹션 = 섹터별 중앙값 필요. dart_fundamentals(1,650)에
섹터 필드 0 → yfinance .info(sector/industry, KR 신뢰 검증됨) 1회 크롤 → data/kr_sector_map.json.
  🚨 yfinance KR PER/PBR=None(검증) → 섹터만 받고, 중앙값은 dart_fundamentals 의 roe/debt/op_margin 로 계산.

유니버스 = dart_fundamentals keys ∪ recommendations KR. 멱등(기존 맵 skip)·throttle·--max(테스트).
사용: python scripts/kr_sector_backfill.py [--max N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FUND_PATH = os.path.join(_ROOT, "data", "dart_fundamentals_kr.json")
LISTED_PATH = os.path.join(_ROOT, "data", "kr_listed.json")
REC_PATH = os.path.join(_ROOT, "data", "recommendations.json")
OUT_PATH = os.path.join(_ROOT, "data", "kr_sector_map.json")

# GICS(yfinance 영문) → 한글 섹터
SECTOR_KO = {
    "Technology": "IT·기술", "Industrials": "산업재", "Basic Materials": "소재",
    "Consumer Cyclical": "경기소비재", "Consumer Defensive": "필수소비재",
    "Healthcare": "헬스케어", "Financial Services": "금융", "Energy": "에너지",
    "Utilities": "유틸리티", "Real Estate": "부동산", "Communication Services": "커뮤니케이션",
}


def _suffix(tk, listed):
    li = listed.get(tk) if isinstance(listed, dict) else None
    mk = (li or {}).get("market") if isinstance(li, dict) else None
    if mk == "KS":
        return ".KS"
    if mk == "KQ":
        return ".KQ"
    return None  # 미상 → .KS 우선 시도


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=None)
    ap.add_argument("--delay", type=float, default=0.25)
    args = ap.parse_args()

    import yfinance as yf

    fund = (json.load(open(FUND_PATH, encoding="utf-8")).get("fundamentals") or {}) if os.path.isfile(FUND_PATH) else {}
    listed = json.load(open(LISTED_PATH, encoding="utf-8")) if os.path.isfile(LISTED_PATH) else {}
    recs = json.load(open(REC_PATH, encoding="utf-8")) if os.path.isfile(REC_PATH) else []
    universe = set(fund.keys())
    for r in (recs if isinstance(recs, list) else []):
        tk = str(r.get("ticker") or "")
        if tk.isdigit() and len(tk) == 6:
            universe.add(tk)

    out = {}
    if os.path.isfile(OUT_PATH):
        try:
            out = json.load(open(OUT_PATH, encoding="utf-8")).get("map") or {}
        except (OSError, json.JSONDecodeError):
            out = {}

    todo = [tk for tk in sorted(universe) if tk not in out]
    if args.max:
        todo = todo[: args.max]
    print(f"[sector] 유니버스 {len(universe)} · 기존 {len(out)} · 신규 대상 {len(todo)}", file=sys.stderr)

    ok = 0
    for i, tk in enumerate(todo):
        suf = _suffix(tk, listed)
        tried = [suf] if suf else [".KS", ".KQ"]
        sector = industry = None
        for sx in tried:
            try:
                info = yf.Ticker(tk + sx).info or {}
                sector = info.get("sector")
                industry = info.get("industry")
                if sector:
                    break
            except Exception:  # noqa: BLE001
                continue
        if sector:
            out[tk] = {"sector": sector, "sector_ko": SECTOR_KO.get(sector, sector), "industry": industry or ""}
            ok += 1
        time.sleep(args.delay)
        if (i + 1) % 100 == 0:
            print(f"[sector] 진행 {i + 1}/{len(todo)} (ok={ok})", file=sys.stderr)
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump({"_meta": {"count": len(out), "source": "yfinance .info sector"}, "map": out}, f, ensure_ascii=False)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"_meta": {"count": len(out), "source": "yfinance .info sector"}, "map": out}, f, ensure_ascii=False)
    print(f"[sector] logged=True · 총 {len(out)} 매핑 (신규 ok {ok}) -> {os.path.relpath(OUT_PATH, _ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
