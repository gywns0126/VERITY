#!/usr/bin/env python3
"""
dart_kr_fin_backfill — KR 종목 연간 재무 시계열 광범위 백필 (재무추이 섹션 부활).

2026-06-27 신설 (PM "죽은 섹션 하나씩 살리자"). 리포트 '재무추이'(fin_series)가 30종목뿐(옛 IC 백필) →
universe(stock_report_public ~1616) × 2015~ 연간 매출/영업이익/순익을 DART fnlttSinglAcntAll 로 수집.
빌더 _load_fin_series 가 dart_kr_fin_history.json 을 dart_kr_backfill_result 와 merge → 대부분 종목 차트.

proven fetcher 재사용: dart_fundamentals._fetch_fnltt_all_cached(캐시 → dart_kr_cache) + _extract_pl_bs_from_dart.
DART only(키 CI 전용·RULE 1 무관). resume(done-ticker)·quota-cap(카탈리스트 백필과 20K/일 공유 — sequencing).
멱등: 캐시 hit 시 API 호출 0. 사실만(매출/영업익/순익) RULE 7.

usage: python scripts/dart_kr_fin_backfill.py [--start-year 2015] [--limit N] [--quota-cap N] [--universe PATH]
출력: data/dart_kr_fin_history.json {rows:[{ticker,name,fiscal_year,period:"annual",fundamentals:{revenue,operating_profit,net_income}}]}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _ROOT)

from api.config import DATA_DIR
from api.collectors.dart_corp_code import get_corp_code
from api.collectors.dart_fundamentals import _fetch_fnltt_all_cached, _extract_pl_bs_from_dart

OUT_PATH = os.path.join(DATA_DIR, "dart_kr_fin_history.json")
DONE_PATH = os.path.join(DATA_DIR, "dart_kr_fin_history_done.json")
DEFAULT_UNIVERSE = os.path.join(DATA_DIR, "stock_report_public.json")


def _universe(path, limit, only):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    stocks = d.get("stocks") if isinstance(d, dict) else d
    out = []
    for s in (stocks or []):
        tk = str(s.get("ticker") or "").strip()
        if only and tk != only:
            continue
        if tk.isdigit() and len(tk) == 6:
            out.append((tk, s.get("name") or tk))
    return out[:limit] if limit else out


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


def _load_rows():
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            return (json.load(f).get("rows") or [])
    except (OSError, json.JSONDecodeError):
        return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2015)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ticker", default=None)
    ap.add_argument("--universe", default=None)
    ap.add_argument("--quota-cap", type=int, default=None, help="이번 run DART 요청 상한(공유 쿼터 throttle, 다일 분할)")
    args = ap.parse_args()

    years = list(range(args.start_year, date.today().year))  # 완결 연도만(당해 사업보고서 미공시)
    universe = _universe(args.universe or DEFAULT_UNIVERSE, args.limit, (args.ticker or "").strip() or None)
    done = _load_done()
    rows = _load_rows()
    seen = {(r.get("ticker"), r.get("fiscal_year")) for r in rows}
    todo = [(t, n) for (t, n) in universe if t not in done]
    print(f"[fin-bf] universe {len(universe)} | done {len(done)} | 잔여 {len(todo)} | years {years[0]}~{years[-1]} | cap {args.quota_cap}", file=sys.stderr)

    new_n, req_n = 0, 0
    for idx, (tk, name) in enumerate(todo, 1):
        if args.quota_cap is not None and req_n >= args.quota_cap:
            print(f"[fin-bf] quota-cap {args.quota_cap} 도달 — 중단(다음 run 이어받음)", file=sys.stderr)
            break
        cc = get_corp_code(tk)
        if not cc:
            done.add(tk); _save_done(done)
            continue
        tk_new = 0
        for y in years:
            if (tk, y) in seen:
                continue
            req_n += 1
            try:
                raw = _fetch_fnltt_all_cached(cc, str(y), "CFS")
                data = json.loads(raw) if raw else {}
                if not (data.get("list")):  # CFS 0건 → OFS fallback
                    req_n += 1
                    raw = _fetch_fnltt_all_cached(cc, str(y), "OFS")
                    data = json.loads(raw) if raw else {}
                plbs = _extract_pl_bs_from_dart(data) if data.get("list") else {}
            except Exception as e:  # noqa: BLE001
                print(f"[fin-bf] {tk} {y} 실패: {str(e)[:60]}", file=sys.stderr)
                continue
            rev, op, net = plbs.get("revenue"), plbs.get("operating_profit"), plbs.get("net_income")
            inv_re = plbs.get("investment_property")
            if not (rev or op or net):
                continue
            rows.append({
                "ticker": tk, "name": name, "fiscal_year": y, "period": "annual",
                "fundamentals": {"revenue": rev or None, "operating_profit": op or None,
                                 "net_income": net or None, "investment_property": inv_re or None},
            })
            seen.add((tk, y))
            new_n += 1; tk_new += 1
        done.add(tk)
        _save_done(done)
        if idx % 25 == 0 or idx == len(todo):
            with open(OUT_PATH, "w", encoding="utf-8") as f:  # 주기 저장(crash-safe)
                json.dump({"rows": rows}, f, ensure_ascii=False)
            print(f"[fin-bf] {idx}/{len(todo)} — 신규행 {new_n} · req {req_n}", file=sys.stderr)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"rows": rows}, f, ensure_ascii=False)
    print(f"[fin-bf] 완료 — 신규행 {new_n} · req {req_n} · done {len(done)} · 총행 {len(rows)} -> {os.path.relpath(OUT_PATH, _ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
