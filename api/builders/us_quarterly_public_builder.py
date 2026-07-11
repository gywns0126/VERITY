"""us_quarterly_public_builder — 미장 분기 재무 비율 추이 public 빌더 (PublicQuarterlyTrend 재사용).

입력: data/us_financials/{TICKER}.json series_quarterly (SEC EDGAR XBRL).
출력: data/us_quarterly_public.json — KR dart_quarterly_public.json 과 동일 스키마
  {stocks: {ticker: {quarters: [{q, debt_ratio, roa, current_ratio, gross_margin, asset_turnover}]}}}
  → PublicQuarterlyTrend 컴포넌트 무변환 재사용(quarterlyUrl 만 US 로).

🚨 RULE 7 — 계산된 사실 비율만(점수·등급 0). 순수 변환 — 외부호출 0.
publish: data/us_quarterly_public.json (action.yml 등재).
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIN_DIR = os.path.join(_ROOT, "data", "us_financials")
OUTPUT_PATH = os.path.join(_ROOT, "data", "us_quarterly_public.json")
MIN_QUARTERS = 4   # 컴포넌트 게이트(series<4 = 미표시) 정합


def _now_kst() -> datetime:
    return datetime.now(KST)


def _by_end(series: Any) -> Dict[str, float]:
    """series_quarterly[key] (list of {end, val, is_annual}) → {end: val} (분기만, is_annual=False)."""
    out: Dict[str, float] = {}
    if not isinstance(series, list):
        return out
    for e in series:
        if not isinstance(e, dict) or e.get("is_annual") or e.get("val") is None:
            continue
        end = str(e.get("end") or "")
        if not end:
            continue
        try:
            out[end] = float(e.get("val"))
        except (TypeError, ValueError):
            continue
    return out


def _ratio(num: Optional[float], den: Optional[float], scale: float = 100.0,
           lo: float = -1e9, hi: float = 1e9) -> Optional[float]:
    if num is None or den in (None, 0):
        return None
    try:
        v = (num / den) * scale
    except ZeroDivisionError:
        return None
    if v != v or v < lo or v > hi:
        return None
    return round(v, 2)


def _quarters_for(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    sq = doc.get("series_quarterly") or {}
    rev = _by_end(sq.get("revenue"))
    ni = _by_end(sq.get("net_income"))
    oi = _by_end(sq.get("operating_income"))
    ta = _by_end(sq.get("total_assets"))
    ca = _by_end(sq.get("current_assets"))
    cl = _by_end(sq.get("current_liabilities"))
    tl = _by_end(sq.get("total_liabilities"))
    eq = _by_end(sq.get("stockholders_equity"))
    gp = _by_end(sq.get("gross_profit"))
    ends = sorted(set(ta) | set(rev) | set(eq))
    quarters: List[Dict[str, Any]] = []
    for end in ends:
        q: Dict[str, Any] = {"q": end}
        # 부채비율 = 총부채÷자기자본 ×100 / ROA = 순이익÷총자산 ×100 / 유동비율 = 유동자산÷유동부채 ×100
        # 매출총이익률 = 매출총이익÷매출 ×100 / 자산회전율 = 매출÷총자산 (회)
        # 영업이익률 = 영업이익÷매출 ×100 / 순이익률 = 순이익÷매출 ×100 / ROE = 순이익÷자기자본 ×100 (분기, 사실)
        dr = _ratio(tl.get(end), eq.get(end), 100.0, 0, 100000)
        roa = _ratio(ni.get(end), ta.get(end), 100.0, -500, 500)
        cr = _ratio(ca.get(end), cl.get(end), 100.0, 0, 100000)
        gm = _ratio(gp.get(end), rev.get(end), 100.0, -1000, 100)
        at = _ratio(rev.get(end), ta.get(end), 1.0, 0, 100)
        om = _ratio(oi.get(end), rev.get(end), 100.0, -1000, 100)
        nm = _ratio(ni.get(end), rev.get(end), 100.0, -1000, 100)
        roe = _ratio(ni.get(end), eq.get(end), 100.0, -500, 500)
        for k, v in (("debt_ratio", dr), ("roa", roa), ("current_ratio", cr),
                     ("gross_margin", gm), ("asset_turnover", at),
                     ("operating_margin", om), ("net_margin", nm), ("roe", roe)):
            if v is not None:
                q[k] = v
        # 적어도 1개 비율이 있어야 분기 수록
        if len(q) > 1:
            quarters.append(q)
    return quarters


def build() -> Dict[str, Any]:
    stocks: Dict[str, Any] = {}
    for path in glob.glob(os.path.join(FIN_DIR, "*.json")):
        base = os.path.basename(path)
        if base.startswith("_"):   # _summary.json 등 제외
            continue
        ticker = base[:-5]
        try:
            with open(path, "r", encoding="utf-8") as f:
                doc = json.load(f) or {}
        except (OSError, json.JSONDecodeError):
            continue
        qs = _quarters_for(doc)
        if len(qs) >= MIN_QUARTERS:
            stocks[ticker] = {"quarters": qs}
    return {
        "_meta": {
            "generated_at": _now_kst().isoformat(),
            "source": "SEC EDGAR XBRL (us_financials series_quarterly)",
            "count": len(stocks),
            "note": "분기 재무 비율 사실(부채비율/ROA/유동비율/매출총이익률/자산회전율/영업이익률/순이익률/ROE) — 점수·등급 0 (RULE 7).",
        },
        "stocks": stocks,
    }


def main() -> int:
    ok = False
    try:
        if not os.path.isdir(FIN_DIR):
            print(f"[us_quarterly_public] {FIN_DIR} 부재 — skip", file=sys.stderr)
            return 0
        out = build()
        if not out["stocks"] and os.path.isfile(OUTPUT_PATH):
            print("[us_quarterly_public] 0 stocks — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0
        # sticky merge — CI per-ticker 캐시는 그 run 재수집분만 존재. 부분 재빌드가 전량본을
        # 덮어쓴 실사고(2026-07-11 incremental: 1,494→10종, 분기추이 카드 전멸). 기존 유지 + 신규만 갱신.
        if os.path.isfile(OUTPUT_PATH):
            try:
                with open(OUTPUT_PATH, encoding="utf-8") as _f:
                    prev = (json.load(_f) or {}).get("stocks") or {}
            except (OSError, ValueError):
                prev = {}
            fresh = out["stocks"]
            kept = sum(1 for t in prev if t not in fresh)
            out["stocks"] = {**prev, **fresh}
            out["_meta"]["count"] = len(out["stocks"])
            out["_meta"]["fresh_this_run"] = len(fresh)
            if kept:
                print(f"[us_quarterly_public] sticky merge — 기존 {kept} 유지 + 신규 {len(fresh)}", file=sys.stderr)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        print(f"[us_quarterly_public] logged=True · {len(out['stocks'])} 종목 -> "
              f"{os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[us_quarterly_public] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[us_quarterly_public] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
