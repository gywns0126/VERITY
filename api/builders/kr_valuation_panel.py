# -*- coding: utf-8 -*-
"""kr_valuation_panel — 리밸런스 시점 PIT PER/PBR/배당수익률 패널 (L2 관측).

2026-08-10 신설. 왜: 8/9 안심점수 검정이 100점 중 **53점만** 재현했다
([[project_safety_score_backtest_2026_08_09]]). 남은 47점(PER 20·PBR 15·배당 12)의
PIT 소스가 없어서였다. 이 패널이 그 47점의 입력이다.

🚨 **이 모듈은 만들기만 한다. 검정하지 않는다.** 전체 100점 검정은 별도 사전등록 대상이다.
   여기서 부호가 뒤집히는지 확인하고 싶은 유혹이 곧 곡선 맞추기다.

## 🚨 운영과 **같은 산식이 아니다** — 근사다

운영(`api/collectors/stock_data.py`)은 per/pbr/div_yield 를 **yfinance `.info` 스냅샷**에서
받는다(`trailingPE` · `priceToBook` · `dividendRate`). yfinance 는 이 값들의 **과거 이력을
주지 않으므로 PIT 재현이 원리적으로 불가능하다.** 그래서 아래로 재구성한다:

| 항목 | 운영 | 여기 | 알려진 차이 |
|---|---|---|---|
| PER | yfinance trailingPE | **주가 ÷ 지배주주 EPS**(DART alotMatter `(연결)주당순이익`) | 정의는 같다. 운영은 TTM, 여기는 직전 확정 사업연도. EPS 부재 시 시총÷TTM순이익 폴백 |
| PBR | yfinance priceToBook | 시총 ÷ 자본총계 | 자본총계 = 패널 역산(실 DART 대조 중앙오차 0.0%) |
| 배당 | yfinance dividendRate/price | DART 주당현금배당금 ÷ 종가 | 운영은 최근 12개월, 여기는 직전 확정 사업연도 |

**배점 구간은 운영 그대로 쓴다**(`calculate_safety_score` 발췌). 연속값으로 바꾸지 않는다.

## PIT

- 시총·종가 = 그 월말의 KRX 마감 실측(`krx_mktcap_history`). 미래 정보 0.
- 재무 = 분기 **+45일** / 사업보고서 **+90일** 지난 뒤에만 관측 가능(법정 제출기한).
- 배당 = 사업연도 종료 **+90일** 이후에만 관측 가능(주총 확정 시점 근사).

출력 = `data/metadata/kr_valuation_panel.jsonl`
"""
from __future__ import annotations

import argparse
import bisect
import json
import os
import sys
import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.config import DATA_DIR, now_kst  # noqa: E402

PANEL_PATH = os.path.join(DATA_DIR, "metadata", "kr_fundamental_panel.jsonl")
MKTCAP_PATH = os.path.join(DATA_DIR, "metadata", "krx_mktcap_history.jsonl")
DIV_PATH = os.path.join(DATA_DIR, "metadata", "kr_dividend_history.jsonl")
OUT_PATH = os.path.join(DATA_DIR, "metadata", "kr_valuation_panel.jsonl")
HEALTH_PATH = os.path.join(DATA_DIR, "metadata", "kr_valuation_panel_health.json")

LAG_QUARTER_DAYS = 45
LAG_ANNUAL_DAYS = 90
LAG_DIVIDEND_DAYS = 90
# 🚨 "가장 최근 스냅샷에 필드가 없으면 포기" 는 채움율을 과하게 깎는다(실측 PBR 50.8%).
#   운영도 최근 확정치를 쓰므로 **필드가 있는 가장 최근 관측**까지 물러난다.
#   다만 무한정 물러나면 stale 값이 PIT 로 둔갑하므로 상한을 두고 경과일을 행에 남긴다.
MAX_STALE_DAYS = 540


# ── 운영 배점 그대로 (api/analyzers/stock_filter.calculate_safety_score 발췌) ──
def pts_per(per: Optional[float]) -> int:
    """🚨 운영은 `stock.get("per", 0)` 이라 **결측 = 0 = 0점**이다. 그 동작을 그대로 옮긴다."""
    p = per or 0
    if 5 <= p <= 15:
        return 20
    if 15 < p <= 25:
        return 12
    if 0 < p <= 50:
        return 5
    return 0


def pts_pbr(pbr: Optional[float]) -> int:
    """🚨 운영에 `elif pbr == 0: score += 3` 이 있다 — **PBR 결측이 3점을 받는다.**
    의도된 설계인지 불명이나 운영 동작이므로 그대로 재현한다(검정 대상은 운영 산식이다)."""
    b = pbr or 0
    if 0 < b <= 1.0:
        return 15
    if 1.0 < b <= 1.5:
        return 10
    if 1.5 < b <= 3.0:
        return 5
    if b == 0:
        return 3
    return 0


def pts_div(dy: Optional[float]) -> int:
    d = dy or 0
    if d >= 3:
        return 12
    if d >= 1:
        return 7
    return 0


def _ymd(s: str) -> int:
    return int(s[:4] + s[5:7] + s[8:10])


def _plus(day: int, n: int) -> int:
    d = date(day // 10000, (day // 100) % 100, day % 100) + timedelta(days=n)
    return d.year * 10000 + d.month * 100 + d.day


def load_panel() -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    with open(PANEL_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            qe = str(r.get("quarter_end") or "")
            if len(qe) != 10:
                continue
            q = _ymd(qe)
            r["_as_of"] = _plus(q, LAG_ANNUAL_DAYS if qe[5:7] == "12" else LAG_QUARTER_DAYS)
            out.setdefault(str(r.get("ticker") or ""), []).append(r)
    for v in out.values():
        v.sort(key=lambda x: x["_as_of"])
    return out


def load_mktcap() -> Dict[int, Dict[str, Dict[str, Any]]]:
    out: Dict[int, Dict[str, Dict[str, Any]]] = {}
    with open(MKTCAP_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            out.setdefault(int(r["req"]), {})[str(r["t"])] = r
    return out


def load_dividends() -> Dict[str, List[Dict[str, Any]]]:
    """DART 주당현금배당금 이력. 없으면 빈 dict — 배당 12점은 '미수집' 으로 신고한다."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    try:
        f = open(DIV_PATH, encoding="utf-8")
    except OSError:
        return out
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            y = r.get("year")
            if y is None:
                continue
            # 🚨 당기(thstrm)는 `rcept_date` = **실제 접수일**이 진짜 관측 시점이다
            #    (005930 2024: 결산 12-31, 접수 2025-03-11 = +70일 — +90일 근사보다 이르다).
            #    전기·전전기는 자기 사업연도 보고서로 더 일찍 공개됐으므로 그 해 +90일로 근사.
            rd = str(r.get("rcept_date") or "")
            if r.get("basis") == "thstrm" and len(rd) == 8 and rd.isdigit():
                r["_as_of"] = int(rd)
            else:
                r["_as_of"] = _plus(int(y) * 10000 + 1231, LAG_DIVIDEND_DAYS)
            out.setdefault(str(r.get("ticker") or ""), []).append(r)
    for v in out.values():
        v.sort(key=lambda x: x["_as_of"])
    return out


def _pit(snaps: List[Dict[str, Any]], day: int) -> Optional[Dict[str, Any]]:
    i = bisect.bisect_right([s["_as_of"] for s in snaps], day) - 1
    return snaps[i] if i >= 0 else None


def _days_between(a: int, b: int) -> int:
    da = date(a // 10000, (a // 100) % 100, a % 100)
    db = date(b // 10000, (b // 100) % 100, b % 100)
    return (db - da).days


def _pit_field(snaps: List[Dict[str, Any]], day: int,
               field: str) -> Tuple[Optional[float], Optional[int], Optional[str]]:
    """day 시점에 관측 가능한 것 중 **field 가 실제로 있는** 가장 최근 값.
    반환 = (값, 경과일, 출처분기). 상한 초과면 (None, None, None)."""
    i = bisect.bisect_right([s["_as_of"] for s in snaps], day) - 1
    while i >= 0:
        v = snaps[i].get(field)
        if v is not None:
            age = _days_between(snaps[i]["_as_of"], day)
            if age > MAX_STALE_DAYS:
                return None, None, None
            return float(v), age, snaps[i].get("quarter_end")
        i -= 1
    return None, None, None


def build() -> Dict[str, Any]:
    t0 = time.time()
    panel, mkt, divs = load_panel(), load_mktcap(), load_dividends()
    dates = sorted(mkt)
    rows: List[Dict[str, Any]] = []
    miss: Dict[str, int] = {}

    def bump(k: str) -> None:
        miss[k] = miss.get(k, 0) + 1

    for d in dates:
        for t, m in mkt[d].items():
            mc = m.get("mc")
            if not mc or mc <= 0:
                bump("mktcap_none")          # 거래정지·관리종목 등
                continue
            snaps = panel.get(t)
            p = _pit(snaps, d) if snaps else None
            if p is None:
                bump("no_pit_financials")

            ni = eq = None
            ni_age = eq_age = None
            ni_src = eq_src = None
            ni_basis = None
            if snaps:
                ni, ni_age, ni_src = _pit_field(snaps, d, "net_income_ttm")
                ni_basis = "ttm" if ni is not None else None
                if ni is None:
                    # 폴백 — 직전 확정 사업연도 순이익(운영의 trailing 개념과 같은 자리)
                    for s2 in reversed([x for x in snaps
                                        if x["_as_of"] <= d and x.get("period") == "FY"]):
                        if s2.get("net_income") is not None:
                            age = _days_between(s2["_as_of"], d)
                            if age <= MAX_STALE_DAYS:
                                ni, ni_age, ni_src, ni_basis = (float(s2["net_income"]), age,
                                                                s2.get("quarter_end"), "annual")
                            break
                eq, eq_age, eq_src = _pit_field(snaps, d, "equity")
            if p is not None and ni is None:
                bump("no_net_income")
            if p is not None and eq is None:
                bump("no_equity")

            close = m.get("c")
            dsnaps = divs.get(t)
            dv = _pit(dsnaps, d) if dsnaps else None

            # 🚨 PER 은 **주가 ÷ 지배주주 EPS** 가 정본이다 — 운영 yfinance trailingPE 와 같은 정의.
            #    시총÷전체순이익은 비지배지분 큰 지주사에서 벌어지므로 폴백으로만 쓴다.
            per = per_basis = None
            eps_own = dv.get("eps_owner") if dv else None
            if eps_own and eps_own > 0 and close and close > 0:
                per, per_basis = float(close) / float(eps_own), "eps_owner"
            elif ni and ni > 0:
                per, per_basis = mc / ni, "mktcap_over_ni"
            pbr = (mc / eq) if (eq and eq > 0) else None

            dy = None
            if dv is not None and close and close > 0:
                dps = dv.get("dps")
                if dps is not None:
                    dy = float(dps) / float(close) * 100.0

            rows.append({
                "d": d, "t": t, "mktcap": mc, "close": close,
                "per": (round(per, 4) if per is not None else None),
                "pbr": (round(pbr, 4) if pbr is not None else None),
                "div_yield": (round(dy, 4) if dy is not None else None),
                "src_quarter": (p.get("quarter_end") if p else None),
                "src_period": (p.get("period") if p else None),
                "per_basis": per_basis, "div_src_year": (dv.get("year") if dv else None),
                "ni_basis": ni_basis, "ni_src_quarter": ni_src, "ni_stale_days": ni_age,
                "eq_src_quarter": eq_src, "eq_stale_days": eq_age,
                "pts_per": pts_per(per), "pts_pbr": pts_pbr(pbr), "pts_div": pts_div(dy),
            })

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp, OUT_PATH)

    n = len(rows)
    fill = {k: sum(1 for r in rows if r.get(k) is not None) for k in ("per", "pbr", "div_yield")}
    health = {
        "generated_at": now_kst().isoformat(timespec="seconds"),
        "rows": n, "dates": len(dates), "tickers": len({r["t"] for r in rows}),
        "window": [dates[0], dates[-1]] if dates else None,
        "fill_rate": {k: (round(v / n * 100, 1) if n else 0.0) for k, v in fill.items()},
        "filled": fill,
        "excluded": miss,
        "pit_lag_days": {"quarter": LAG_QUARTER_DAYS, "annual": LAG_ANNUAL_DAYS,
                         "dividend": LAG_DIVIDEND_DAYS},
        "max_stale_days": MAX_STALE_DAYS,
        "ni_basis": {b: sum(1 for r in rows if r.get("ni_basis") == b)
                     for b in ("ttm", "annual")},
        "per_basis": {b: sum(1 for r in rows if r.get("per_basis") == b)
                      for b in ("eps_owner", "mktcap_over_ni")},
        "stale_days_median": {
            k: (sorted(v)[len(v) // 2] if v else None)
            for k, v in (("ni", [r["ni_stale_days"] for r in rows
                                 if r.get("ni_stale_days") is not None]),
                         ("eq", [r["eq_stale_days"] for r in rows
                                 if r.get("eq_stale_days") is not None]))},
        "🚨": ("운영은 yfinance .info 스냅샷이라 PIT 이력이 없다. 이 패널은 **근사**이며 "
               "PER 은 지배주주가 아닌 전체 순이익 기준이다. 배점 구간은 운영 그대로."),
        "elapsed_sec": round(time.time() - t0, 1),
    }
    with open(HEALTH_PATH, "w", encoding="utf-8") as f:
        json.dump(health, f, ensure_ascii=False, indent=1)
    return health


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.parse_args()
    h = build()
    if not h["rows"]:
        print("[kr_valuation_panel] 🚨 0행 — 입력 확인", file=sys.stderr)
        return 1
    print(f"[kr_valuation_panel] {h['rows']:,}행 · {h['dates']}개월 · 종목 {h['tickers']:,} "
          f"· {h['window'][0]}~{h['window'][1]} · {h['elapsed_sec']}s")
    print(f"[kr_valuation_panel] 채움율 PER {h['fill_rate']['per']}% · "
          f"PBR {h['fill_rate']['pbr']}% · 배당 {h['fill_rate']['div_yield']}%")
    print(f"[kr_valuation_panel] 제외 {h['excluded']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
