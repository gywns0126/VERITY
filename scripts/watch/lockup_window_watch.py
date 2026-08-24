#!/usr/bin/env python3
"""
lockup_window_watch — 락업 만기 창의 수급 3축을 **숫자만** 적는다. 판정 0.

2026-08-24 신설 (PM 지시). 계기 = PM 이 XE(X-energy)를 매수했고, 가장 가까운 관측점이
락업 최종만기 **2026-10-24** 다. 그 창에서 볼 것은 13G 지분 변동 · 공매도 · FTD 세 축이다.

🚨 **판단을 넣지 않는다.** 이 산출물은 관측 기록이고, 해석은 터미널 대화가 한다.
   경보 문구·등급·매매 시사 금지 (RULE 7). 변동은 **델타 숫자**로만 남긴다.

원천 = 이미 매일/주3회 수집되는 발행물 3종. **신규 수집 0 · 네트워크 0 · 쿼터 0**.
  · `data/us_major_holdings.json`  stocks[] (SEC 13D/13G)
  · `data/us_short_interest.json`  stocks[] (월 2회 공시)
  · `data/us_short_pressure.json`  map{}    (FINRA 일별 공매도 · Reg SHO · FTD)

산출 = `data/metadata/lockup_watch.jsonl` (append-only). 직전 행 대비 델타를 같이 적는다 —
  나중에 읽는 사람이 파일 두 개를 대조하지 않아도 되게.

usage: python scripts/watch/lockup_window_watch.py            # WATCHES 전량
       python scripts/watch/lockup_window_watch.py --ticker XE
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, _ROOT)

DATA = os.path.join(_ROOT, "data")
OUT = os.path.join(DATA, "metadata", "lockup_watch.jsonl")

# 감시 대상. 창이 지나면 목록에서 빼거나 expires 를 갱신한다 — 지난 창을 계속 세지 않는다.
WATCHES: List[Dict[str, str]] = [
    {"ticker": "XE", "name": "X-energy, Inc.", "lockup_final": "2026-10-24",
     "note": "IPO 2026-04-27 · 최종만기(연장분) · 13G 5곳 71.4% 동일 창"},
]


def _load(rel: str) -> Any:
    try:
        with open(os.path.join(DATA, rel), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _row(seq: Any, tk: str) -> Optional[Dict[str, Any]]:
    """stocks[] 에서 ticker 행을 찾는다. 없으면 None (0 으로 채우지 않는다)."""
    if not isinstance(seq, list):
        return None
    for x in seq:
        if isinstance(x, dict) and str(x.get("ticker") or "") == tk:
            return x
    return None


def _prev(tk: str) -> Optional[Dict[str, Any]]:
    try:
        with open(OUT, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
    except (OSError, json.JSONDecodeError):
        return None
    hits = [r for r in rows if r.get("ticker") == tk]
    return hits[-1] if hits else None


def _delta(cur: Optional[float], old: Optional[float]) -> Optional[float]:
    if cur is None or old is None:
        return None
    try:
        return round(float(cur) - float(old), 4)
    except (TypeError, ValueError):
        return None


def snapshot(w: Dict[str, str]) -> Dict[str, Any]:
    tk = w["ticker"]
    mh = _load("us_major_holdings.json") or {}
    si = _load("us_short_interest.json") or {}
    sp = _load("us_short_pressure.json") or {}

    h = _row(mh.get("stocks"), tk)
    s = _row(si.get("stocks"), tk)
    p = (sp.get("map") or {}).get(tk)

    # 🚨 소스별 as_of 를 각각 적는다 — 파일 생성시각이 그 종목의 기준일이 아니다
    #   ([[feedback_rotating_collector_not_a_price_source]] 계열 규율).
    filings = (h or {}).get("filings") or []
    holders = [{"filer": f.get("filer"), "pct": f.get("pct"), "shares": f.get("shares"),
                "type": f.get("type"), "date": f.get("date"), "event_date": f.get("event_date")}
               for f in filings]
    pct_sum = None
    try:
        vals = [float(f["pct"]) for f in filings if f.get("pct") is not None]
        pct_sum = round(sum(vals), 2) if vals else None
    except (TypeError, ValueError):
        pct_sum = None

    lf = w.get("lockup_final") or ""
    d_left = None
    try:
        d_left = (date.fromisoformat(lf) - date.today()).days
    except ValueError:
        pass

    cur: Dict[str, Any] = {
        "ts_kst": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ticker": tk, "name": w.get("name"),
        "lockup_final": lf, "days_to_lockup": d_left,
        # ── 13G/13D
        "holders_n": (h or {}).get("total"),
        "n_13d": (h or {}).get("n_13d"), "n_13g": (h or {}).get("n_13g"),
        "holders_pct_sum": pct_sum,
        "holders": holders,
        "holdings_as_of": (h or {}).get("collected_at"),
        # ── 공매도(월 2회 공시)
        "short_pct": (s or {}).get("short_pct"),
        "short_pct_prior": (s or {}).get("short_pct_prior"),
        "days_to_cover": (s or {}).get("days_to_cover"),
        "shares_short": (s or {}).get("shares_short"),
        "short_as_of": (s or {}).get("report_date"),
        # ── FINRA 일별 · FTD
        "short_ratio": (p or {}).get("short_ratio"),
        "total_vol": (p or {}).get("total_vol"),
        "ftd_qty_max": (p or {}).get("ftd_qty_max"),
        "ftd_days": (p or {}).get("ftd_days"),
        "pressure_as_of": (sp.get("_meta") or {}).get("short_volume_as_of"),
        # ── 결손은 0 이 아니라 이름으로 신고한다
        "missing": [k for k, v in (("major_holdings", h), ("short_interest", s),
                                   ("short_pressure", p)) if v is None],
        "note": w.get("note"),
        "caveat": "관측 기록 — 판정·매매시사 0 (RULE 7). 해석은 터미널 대화가 한다.",
    }

    prev = _prev(tk)
    if prev:
        cur["delta"] = {
            "holders_pct_sum": _delta(cur["holders_pct_sum"], prev.get("holders_pct_sum")),
            "holders_n": _delta(cur["holders_n"], prev.get("holders_n")),
            "short_pct": _delta(cur["short_pct"], prev.get("short_pct")),
            "shares_short": _delta(cur["shares_short"], prev.get("shares_short")),
            "short_ratio": _delta(cur["short_ratio"], prev.get("short_ratio")),
            "ftd_days": _delta(cur["ftd_days"], prev.get("ftd_days")),
            "vs_ts": prev.get("ts_kst"),
        }
        old = {h_["filer"] for h_ in (prev.get("holders") or []) if h_.get("filer")}
        new = {h_["filer"] for h_ in holders if h_.get("filer")}
        cur["holders_entered"] = sorted(new - old)
        cur["holders_exited"] = sorted(old - new)
    return cur


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    watches = [w for w in WATCHES if not a.ticker or w["ticker"] == a.ticker]
    if not watches:
        print(f"[lockup-watch] 감시 대상 없음 (--ticker {a.ticker})", file=sys.stderr)
        return 0

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    for w in watches:
        r = snapshot(w)
        print(f"[lockup-watch] {r['ticker']} D{r['days_to_lockup']:+} · "
              f"13G {r['n_13g']}곳 합 {r['holders_pct_sum']}% (기준 {r['holdings_as_of']}) · "
              f"공매도 {r['short_pct']}%/{r['days_to_cover']}일 (기준 {r['short_as_of']}) · "
              f"FINRA {r['short_ratio']}% · FTD {r['ftd_days']}일 (기준 {r['pressure_as_of']})",
              file=sys.stderr)
        if r.get("delta"):
            print(f"[lockup-watch]   직전 대비: {json.dumps(r['delta'], ensure_ascii=False)}",
                  file=sys.stderr)
        if r["missing"]:
            print(f"[lockup-watch]   🚨 결손 소스: {r['missing']}", file=sys.stderr)
        if a.dry_run:
            continue
        with open(OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if not a.dry_run:
        print(f"[lockup-watch] -> {os.path.relpath(OUT, _ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
