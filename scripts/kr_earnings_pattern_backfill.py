#!/usr/bin/env python3
"""kr_earnings_pattern_backfill — KR 실적 공시 제출 패턴 초기 적재 (어닝 캘린더 스프린트 2026-07-04).

US(EDGAR 제출 패턴)와 동일 설계의 KR 판: DART list.json(A=정기공시)에서 종목별 최근 정기보고서
(분기·반기·사업보고서) + 잠정실적(수시) 제출일 이력 → data/kr_earnings_pattern.json.
빌더가 제출 간격 중앙값으로 "다음 실적 공시 예상 창" 계산 (외부 캘린더 소스 불요·권리 0).

🚨 DART 쿼터: 종목당 1콜 × ~1,621 = 일회성. 백필(연간·분기·카탈리스트)과 쿼터 공유 —
   여유일에 실행 (기본 --max 0 = 전체, 분할 시 --max N 멱등 재개).
usage: python scripts/kr_earnings_pattern_backfill.py [--max N] [--refresh]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta

import requests

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from api.config import DART_API_KEY  # noqa: E402
from api.collectors.dart_corp_code import get_corp_code  # noqa: E402

OUT_PATH = os.path.join(_ROOT, "data", "kr_earnings_pattern.json")
REPORT_PATH = os.path.join(_ROOT, "data", "stock_report_public.json")
KEEP = 10
THROTTLE = 0.15
LOOKBACK_DAYS = 400   # 정기보고서 4~5회 + 잠정실적 포함 창

# 제출 패턴 대상 report_nm 마커 — 정기보고서(법정) + 잠정실적(자율, 대형주 정밀 신호)
_PERIODIC = ("분기보고서", "반기보고서", "사업보고서")
_PROVISIONAL = ("영업(잠정)실적", "연결재무제표기준영업(잠정)실적")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _fetch_history(corp_code: str):
    end = date.today()
    bgn = end - timedelta(days=LOOKBACK_DAYS)
    r = requests.get("https://opendart.fss.or.kr/api/list.json", params={
        "crtfc_key": DART_API_KEY, "corp_code": corp_code,
        "bgn_de": bgn.strftime("%Y%m%d"), "end_de": end.strftime("%Y%m%d"),
        "page_count": "100", "sort": "date", "sort_mth": "desc",
    }, timeout=20)
    r.raise_for_status()
    d = r.json()
    if d.get("status") != "000":
        return []
    rows = []
    for it in d.get("list") or []:
        nm = (it.get("report_nm") or "").replace(" ", "")
        dt = str(it.get("rcept_dt") or "")
        if len(dt) != 8:
            continue
        iso = f"{dt[:4]}-{dt[4:6]}-{dt[6:]}"
        if any(m in nm for m in _PROVISIONAL):
            rows.append({"form": "잠정실적", "filed": iso})
        elif any(m in nm for m in _PERIODIC) and "정정" not in nm:
            rows.append({"form": "정기보고서", "filed": iso})
        if len(rows) >= KEEP:
            break
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    if not DART_API_KEY:
        print("[kr_earn_pattern] DART_API_KEY 없음 — skip", file=sys.stderr)
        return 0

    rep = _load(REPORT_PATH, {})
    universe = sorted({str(s.get("ticker") or "") for s in (rep.get("stocks") or [])
                       if str(s.get("ticker") or "").isdigit()})
    doc = _load(OUT_PATH, {"_meta": {}, "patterns": {}})
    pats = doc.get("patterns") or {}
    todo = [t for t in universe if args.refresh or t not in pats]
    if args.max:
        todo = todo[: args.max]
    print(f"[kr_earn_pattern] 대상 {len(todo)} / 유니버스 {len(universe)}", file=sys.stderr)

    ok = err = 0
    for i, tk in enumerate(todo, 1):
        try:
            cc = get_corp_code(tk)
            if cc:
                rows = _fetch_history(cc)
                if rows:
                    pats[tk] = rows
                    ok += 1
        except Exception as e:
            err += 1
            if err <= 5:
                print(f"[kr_earn_pattern] {tk} 실패: {type(e).__name__}", file=sys.stderr)
        if i % 100 == 0:
            print(f"[kr_earn_pattern] 진행 {i}/{len(todo)} (ok={ok})", file=sys.stderr)
            doc["patterns"] = pats
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
        time.sleep(THROTTLE)

    doc["patterns"] = pats
    doc["_meta"] = {"count": len(pats), "source": "DART list.json (정기보고서·잠정실적 제출 이력, 자체 패턴 계산용)", "keep": KEEP}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    print(f"[kr_earn_pattern] logged=True · 신규 {ok} (오류 {err}) → 총 {len(pats)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
