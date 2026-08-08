# -*- coding: utf-8 -*-
"""kr_fundamental — KR 펀더멘털 축 백테스트 (사전등록 docs/PREREG_BACKTEST_KR_2020_2026.md).

🚨 이 모듈은 **관측 산출물만** 만든다. 점수·집행 입력 0.

**왜 이게 필요한가**: forward 관측만으로는 답이 안 나온다. `score_ic_audit`(PR #313) 실측 —
20일 지평의 비겹침 표본이 4개, N=30 도달까지 600 거래일 ≈ 2.4년이다. 과거로 가지 않으면
2028년까지 "우리 산식에 신호가 있는지" 를 모른 채 종목을 고르게 된다.

**생존 편향 처리**: 유니버스는 `kr_universe_pit`(그 시점 실제 상장 목록)를 쓰고, 사라진
415종목의 가격은 `kr_chart_delisted` 로 채운다. 현 상장 종목만으로 돌리면 망한 회사가
표본에서 통째로 빠져 어떤 산식이든 수익률이 부풀고, 그 숫자를 믿고 실전에 가면 정확히
그 차이만큼 잃는다 — **백테스트가 없는 것보다 나쁘다**.

🚨 **재현 가능성 한계 (사전등록 v1.1 보정 사유)**
분기 스냅샷(`dart_quarterly_snapshots.jsonl`)이 보유한 필드는 7종 —
roa · debt_ratio · current_ratio · gross_margin · asset_turnover · operating_cashflow · net_income.
  · F2/F4(영업현금흐름)  = 스냅샷에 operating_cashflow·net_income 이 **95.7% 비영값**으로
                           들어있다(2016~2026 연도별 93~99%) → 재현 **가능**.
  · F7(신주 미발행)      = 운영에서도 전 종목 상수 +1 (관측 39/39). 단면 순위에 영향 0 → 제외.
  · Graham PBR×PER       = 전 계열 sweep 결과 시계열 소스 0 → **재현 불가, 축 폐기**.
  · Altman Z            = 운전자본·유보이익·시가총액 부재 → `compute_quality_score`
                           통짜(35+25+20+10+10) 재현 불가. 그래서 축을 F-Score 와 GP/A
                           **두 개의 개별 팩터**로 두고 복합 점수는 검정하지 않는다.
따라서 검정 대상은 **재현 가능한 부분**으로 좁힌다. 좁혔다는 사실을 산출물에 명시한다.

가격 레이크는 repo 밖(Vercel Blob 사본)이라 `--lake` 로 경로를 받는다.
"""
from __future__ import annotations

import argparse
import bisect
import glob
import json
import math
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from api.config import DATA_DIR
    _DATA = DATA_DIR
except Exception:  # 단독 실행 폴백
    _DATA = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))), "data")

from api.utils.fscore_delta import (  # SSOT — Δ math 단일 출처 (운영과 동일 코드)
    compute_fscore_deltas,
    find_yoy_prior,
    is_real_quarter_end,
)

PIT_PATH = os.path.join(_DATA, "kr_universe_pit.jsonl")
DELIST_PATH = os.path.join(_DATA, "kr_delisting.json")
DELIST_META = os.path.join(_DATA, "kr_chart_delisted_meta.json")
DELIST_CHUNKS = os.path.join(_DATA, "kr_chart_delisted", "chunk_*.json")
LISTED_PATH = os.path.join(_DATA, "kr_listed.json")
SNAP_PATH = os.path.join(_DATA, "dart_quarterly_snapshots.jsonl")
OUT_PATH = os.path.join(_DATA, "backtest_kr_fundamental.json")
TRAIL_PATH = os.path.join(_DATA, "backtest_kr_fundamental_trail.jsonl")

# ── 사전등록 고정 상수 (실행 중 변경 금지) ─────────────────────────────────
HORIZONS: Tuple[int, ...] = (20, 60)
PIT_LAG_DAYS = 45              # 분기보고서 법정 기한 — quarter_end + 45일 이후만 사용
SELL_TAX = 0.0020              # 증권거래세 (매도)
COMMISSION = 0.00015           # 위탁수수료 (편도)
DELIST_HAIRCUT = 0.70          # 보수 시나리오 — 정리매매 할인 가정 (자체 가정, 문헌 근거 없음)
MIN_NAMES = 30                 # 리밸런스당 최소 종목 (단면 상관 최소 표본)
N_QUANTILE = 10                # 분위 스프레드 = 상위 10% − 하위 10%
ENTRY_TOLERANCE = 5            # 진입 시점 가격 허용 지연 (거래일)

# 제외 규칙 — 사전 고정. 실행 중 추가·변경 금지.
_EXCL_SPAC = re.compile(r"스팩|기업인수목적")
_EXCL_REIT = re.compile(r"리츠|리 츠")
_EXCL_ETF = re.compile(
    r"^(KODEX|TIGER|KBSTAR|KINDEX|ARIRANG|HANARO|KOSEF|PLUS|RISE|SOL|ACE|TIMEFOLIO|"
    r"WOORI|히어로즈|마이다스|파워|FOCUS|BNK|WON|1Q|UNICORN|VITA)")


# ══════════════════════════════════════════════════════════════════════════
# 로딩
# ══════════════════════════════════════════════════════════════════════════
def load_universe() -> List[Tuple[str, List[str]]]:
    """PIT 유니버스 스냅샷 → [(as_of 'YYYYMMDD', [tickers]), ...] 오름차순."""
    out: List[Tuple[str, List[str]]] = []
    if not os.path.exists(PIT_PATH):
        return out
    with open(PIT_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            tk = d.get("tickers") or []
            if tk:
                out.append((str(d.get("as_of")), [str(t) for t in tk]))
    out.sort(key=lambda x: x[0])
    return out


def load_names() -> Dict[str, str]:
    """종목명 — 현 상장(kr_listed) + 소멸(kr_chart_delisted_meta) 합집합."""
    names: Dict[str, str] = {}
    try:
        with open(LISTED_PATH, encoding="utf-8") as f:
            for t, v in (json.load(f) or {}).items():
                n = (v or {}).get("name") if isinstance(v, dict) else None
                if n:
                    names[str(t)] = str(n)
    except (OSError, json.JSONDecodeError):
        pass
    try:
        with open(DELIST_META, encoding="utf-8") as f:
            for t, n in ((json.load(f) or {}).get("names") or {}).items():
                if n and str(t) not in names:
                    names[str(t)] = str(n)
    except (OSError, json.JSONDecodeError):
        pass
    return names


def exclusion_reason(ticker: str, name: Optional[str]) -> Optional[str]:
    """제외 사유 — 없으면 None. 사전 고정 규칙만 사용한다.

    🚨 우선주는 종목코드 끝자리로 판정한다(보통주=0). 종목명이 없어도 걸러야 하기 때문이다
       — 이름 미확보 종목을 통과시키면 우선주가 유니버스에 남는다.
    """
    if len(ticker) == 6 and ticker[-1] != "0":
        return "preferred"
    if not name:
        return None
    if _EXCL_SPAC.search(name):
        return "spac"
    if _EXCL_REIT.search(name):
        return "reit"
    if _EXCL_ETF.match(name):
        return "etf"
    return None


def load_prices(lake_dir: str) -> Dict[str, Dict[str, List]]:
    """{ticker: {"d": [yyyymmdd...], "c": [close...]}} — 현 상장(레이크) + 소멸(청크).

    두 소스가 같은 종목을 가지면 봉 수가 많은 쪽을 쓴다(레이크가 2020~ 전 기간).
    """
    px: Dict[str, Dict[str, List]] = {}

    def _absorb(t: str, candles: Sequence[Sequence]) -> None:
        if not candles or len(candles) < 2:
            return
        prev = px.get(t)
        if prev and len(prev["d"]) >= len(candles):
            return
        ds, cs = [], []
        for row in candles:
            try:
                d, c = int(row[0]), float(row[4])
            except (TypeError, ValueError, IndexError):
                continue
            if c > 0:
                ds.append(d)
                cs.append(c)
        if len(ds) >= 2:
            px[t] = {"d": ds, "c": cs}

    for p in glob.glob(os.path.join(lake_dir, "*.json")):
        t = os.path.splitext(os.path.basename(p))[0]
        if len(t) != 6 or not t.isdigit():
            continue
        try:
            with open(p, encoding="utf-8") as f:
                _absorb(t, (json.load(f) or {}).get("c") or [])
        except (OSError, json.JSONDecodeError):
            continue

    for p in sorted(glob.glob(DELIST_CHUNKS)):
        try:
            with open(p, encoding="utf-8") as f:
                for t, ent in ((json.load(f) or {}).get("stocks") or {}).items():
                    _absorb(str(t), (ent or {}).get("c") or [])
        except (OSError, json.JSONDecodeError):
            continue
    return px


def load_fundamentals() -> Dict[str, List[Dict[str, Any]]]:
    """{ticker: [분기 스냅샷 ... quarter_end 오름차순]}.

    🚨 `is_real_quarter_end` 로 수집일이 quarter_end 로 적힌 오염 행을 버린다
       (PR #309 학습 — 2,631행. 그 행이 '최신'으로 뽑히면 YoY 조회가 전부 빗나간다).
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    if not os.path.exists(SNAP_PATH):
        return out
    with open(SNAP_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            qe = r.get("quarter_end")
            if not is_real_quarter_end(qe):
                continue
            out.setdefault(str(r.get("ticker")), []).append(r)
    for v in out.values():
        v.sort(key=lambda x: str(x.get("quarter_end")))
    return out


# ══════════════════════════════════════════════════════════════════════════
# PIT · 점수
# ══════════════════════════════════════════════════════════════════════════
def pit_snapshot(snaps: List[Dict[str, Any]], as_of: str) -> Optional[Dict[str, Any]]:
    """T 시점에 **공시돼 있었을** 최신 분기. quarter_end + 45일 ≤ T 만 사용.

    🚨 look-ahead 차단의 핵심. 분기말 당일 재무를 쓰면 실제로는 45일 뒤에나 알 수 있던
       정보로 매수하는 것이 되어 수익률이 통째로 가짜가 된다.
    """
    try:
        t_dt = datetime.strptime(as_of, "%Y%m%d").date()
    except ValueError:
        return None
    best = None
    for s in snaps:
        try:
            qe = datetime.strptime(str(s.get("quarter_end")), "%Y-%m-%d").date()
        except ValueError:
            continue
        if qe + timedelta(days=PIT_LAG_DAYS) <= t_dt:
            best = s
        else:
            break
    return best


def axis_fscore8(cur: Dict[str, Any], snaps: List[Dict[str, Any]]) -> Optional[int]:
    """축 A — Piotroski 재현 가능 8기준 (F1~F6·F8·F9), 0~8. F7 만 제외.

    Δ math 는 `api/utils/fscore_delta.compute_fscore_deltas` — 운영과 **같은 코드**.
    F2/F4 분기 규칙도 `quality.compute_piotroski_f_score` 와 같은 분기를 쓴다.

    🚨 F7(신주 미발행)만 빠진다. 운영에서도 shares_change_pct 관측이 0/39 라 **전 종목
       무조건 +1**(작업 #33) — 모든 종목에 같은 상수를 더하는 항은 단면 순위를 바꾸지
       않는다. 즉 이 8기준은 운영 F-Score 와 **순위 동치**다.
    🚨 5개 Δ + roa + CFO 가 모두 있을 때만 채점한다. 부분 채점은 결측 종목을 자동으로
       낮은 점수로 만들어 결측을 실패로 채점하게 된다.
    """
    roa = cur.get("roa")
    cfo = cur.get("operating_cashflow")
    ni = cur.get("net_income")
    if not isinstance(roa, (int, float)) or not isinstance(cfo, (int, float)):
        return None
    if not isinstance(ni, (int, float)):
        return None
    prior = find_yoy_prior(str(cur.get("quarter_end")), snaps)
    d = compute_fscore_deltas(cur, prior)
    if d.get("n_delta_computed") != 5:
        return None
    s = 1 if roa > 0 else 0                                     # F1
    s += 1 if cfo > 0 else 0                                    # F2
    s += 1 if (d["delta_roa"] or 0) > 0 else 0                  # F3
    if cfo > ni and ni != 0:                                    # F4 (운영 분기 그대로)
        s += 1
    elif cfo > 0 and ni <= 0:
        s += 1
    s += 1 if d["c5_delta_leverage_negative"] else 0            # F5
    s += 1 if d["c6_delta_current_ratio_positive"] else 0       # F6
    s += 1 if d["c8_delta_gross_margin_positive"] else 0        # F8
    s += 1 if d["c9_delta_asset_turnover_positive"] else 0      # F9
    return s


def axis_gpa(cur: Dict[str, Any]) -> Optional[float]:
    """축 B — Novy-Marx(2013) Gross Profitability = 매출총이익/총자산.

    스냅샷 항등식으로 재구성: (매출총이익/매출) × (매출/총자산) = 매출총이익/총자산.
    🚨 운영 `compute_gross_profitability` 는 gross_profit/total_assets 를 읽는다 —
       **같은 양(quantity)이지만 같은 코드 경로는 아니다.** 운영은 두 필드가 없으면
       영업이익률 프록시로 떨어지는데, 여기서는 항등식이 정확값을 준다.
    """
    gm, at = cur.get("gross_margin"), cur.get("asset_turnover")
    if not isinstance(gm, (int, float)) or not isinstance(at, (int, float)):
        return None
    return (float(gm) / 100.0) * float(at)


# ══════════════════════════════════════════════════════════════════════════
# 수익률
# ══════════════════════════════════════════════════════════════════════════
def _close_at_or_before(series: Dict[str, List], day: int) -> Optional[Tuple[int, float]]:
    ds = series["d"]
    i = bisect.bisect_right(ds, day) - 1
    if i < 0:
        return None
    return ds[i], series["c"][i]


def forward_return(series: Dict[str, List], entry_day: int, exit_day: int,
                   delisted: bool, haircut: bool) -> Optional[Tuple[float, str]]:
    """(수익률, 처리모드). 산출 불가면 None.

    🚨 상폐 처리가 결과를 좌우한다. `last_bar` 이후를 0 이나 마지막 가격으로 **채우지 않는다** —
       채우면 상폐 손실이 지워진다. 소멸 확정 종목만 마지막 체결가(또는 ×0.70)로 청산한다.
       소멸 확정이 아닌 데이터 공백은 **관측을 버린다**(결측 ≠ 실패).
    """
    ent = _close_at_or_before(series, entry_day)
    if ent is None:
        return None
    e_day, e_px = ent
    if _daydiff(entry_day, e_day) > ENTRY_TOLERANCE * 2:   # 달력일 여유 (거래일 5일 ≈ 7~10일)
        return None
    last_day = series["d"][-1]
    if last_day >= exit_day:
        ex = _close_at_or_before(series, exit_day)
        if ex is None:
            return None
        return (ex[1] / e_px - 1.0, "normal")
    if not delisted:
        return None                                        # 단순 데이터 공백 — 버린다
    px = series["c"][-1] * (DELIST_HAIRCUT if haircut else 1.0)
    return (px / e_px - 1.0, "delisted")


def _daydiff(a: int, b: int) -> int:
    try:
        da = date(a // 10000, (a // 100) % 100, a % 100)
        db = date(b // 10000, (b // 100) % 100, b % 100)
        return abs((da - db).days)
    except ValueError:
        return 999


# ══════════════════════════════════════════════════════════════════════════
# 통계
# ══════════════════════════════════════════════════════════════════════════
def _rank(v: Sequence[float]) -> List[float]:
    """평균 순위 (동점 처리)."""
    idx = sorted(range(len(v)), key=lambda i: v[i])
    out = [0.0] * len(v)
    i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and v[idx[j + 1]] == v[idx[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[idx[k]] = avg
        i = j + 1
    return out


def spearman(x: Sequence[float], y: Sequence[float]) -> Optional[float]:
    if len(x) < 3 or len(x) != len(y):
        return None
    rx, ry = _rank(x), _rank(y)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx <= 0 or dy <= 0:
        return None
    return num / (dx * dy)


def t_stat(vals: Sequence[float]) -> Dict[str, Any]:
    n = len(vals)
    if n < 2:
        return {"n": n, "mean": (vals[0] if n else None), "t": None}
    m = sum(vals) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1))
    return {"n": n, "mean": round(m, 6),
            "t": (round(m / (sd / math.sqrt(n)), 4) if sd > 0 else None),
            "positive_rate": round(sum(1 for v in vals if v > 0) / n, 4)}


# ══════════════════════════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════════════════════════
AXES = ("fscore8", "gpa")
SCENARIOS = ("optimistic", "conservative")


def _calendar(px: Dict[str, Dict[str, List]]) -> List[int]:
    """시장 거래일 달력 — 전 종목 관측일의 합집합.

    종목별 거래일 수가 다르므로(거래정지·상폐) 공통 달력으로 지평을 센다.
    종목 자기 인덱스로 h 일을 세면 정지 종목의 지평이 실제보다 길어진다.
    """
    days = set()
    for s in px.values():
        days.update(s["d"])
    return sorted(days)


def _select_non_overlapping(entry_idx: List[int], horizon: int) -> List[int]:
    """겹치지 않는 리밸런스 위치만 그리디 선택 (앞에서부터, 간격 ≥ horizon).

    🚨 겹치는 표본으로 t 값을 내면 √h 배 부풀어 없는 유의성이 생긴다
       (score_ic_audit 실측 — 60일 naive t=5.02 가 비겹침에서 판정 불가).
    """
    keep: List[int] = []
    last = -10 ** 9
    for i, e in enumerate(entry_idx):
        if e - last >= horizon:
            keep.append(i)
            last = e
    return keep


def run(lake_dir: str, out_path: str = OUT_PATH,
        trail_path: str = TRAIL_PATH, dry_run: bool = False) -> Dict[str, Any]:
    t0 = time.time()
    universe = load_universe()
    names = load_names()
    px = load_prices(lake_dir)
    funds = load_fundamentals()
    try:
        with open(DELIST_PATH, encoding="utf-8") as f:
            dl = json.load(f) or {}
        latest_snap = str(dl.get("as_of"))
        gone = {t for t, v in (dl.get("last_seen") or {}).items() if str(v) != latest_snap}
    except (OSError, json.JSONDecodeError):
        gone = set()

    if not universe or not px or not funds:
        return {"status": "missing_input",
                "have": {"universe": len(universe), "prices": len(px), "funds": len(funds)}}

    cal = _calendar(px)
    cal_pos = {d: i for i, d in enumerate(cal)}

    rebalances: List[Dict[str, Any]] = []
    excl_tally: Dict[str, int] = {}
    trail: List[Dict[str, Any]] = []

    for as_of, tickers in universe:
        i = bisect.bisect_right(cal, int(as_of)) - 1
        if i < 0:
            continue
        entry_day = cal[i]
        if i + max(HORIZONS) >= len(cal):
            continue                                    # 최대 지평 미래가 없는 시점은 제외
        exits = {h: cal[i + h] for h in HORIZONS}

        rows: List[Dict[str, Any]] = []
        for t in tickers:
            why = exclusion_reason(t, names.get(t))
            if why:
                excl_tally[why] = excl_tally.get(why, 0) + 1
                continue
            series = px.get(t)
            snaps = funds.get(t)
            if not series or not snaps:
                continue
            cur = pit_snapshot(snaps, as_of)
            if not cur:
                continue
            a = axis_fscore8(cur, snaps)
            b = axis_gpa(cur)
            if a is None and b is None:
                continue
            rec: Dict[str, Any] = {"t": t, "fscore8": a, "gpa": b,
                                   "qe": cur.get("quarter_end")}
            ok = False
            for h in HORIZONS:
                for sc in SCENARIOS:
                    r = forward_return(series, entry_day, exits[h],
                                       delisted=(t in gone), haircut=(sc == "conservative"))
                    if r is not None:
                        rec[f"r{h}_{sc}"] = round(r[0], 6)
                        rec[f"m{h}"] = r[1]
                        ok = True
            if ok:
                rows.append(rec)

        if len(rows) < MIN_NAMES:
            continue
        rebalances.append({"as_of": as_of, "entry_day": entry_day,
                           "entry_idx": i, "rows": rows})
        trail.append({
            "as_of": as_of, "entry_day": entry_day, "n_scored": len(rows),
            "n_universe": len(tickers),
            "n_fscore8": sum(1 for r in rows if r["fscore8"] is not None),
            "n_gpa": sum(1 for r in rows if r["gpa"] is not None),
            "n_delisted_exit": sum(1 for r in rows
                                   if any(r.get(f"m{h}") == "delisted" for h in HORIZONS)),
        })

    coverage = {
        "rebalances": len(rebalances),
        "window": ([rebalances[0]["as_of"], rebalances[-1]["as_of"]] if rebalances else None),
        "excluded": excl_tally,
        "median_names": (sorted(len(r["rows"]) for r in rebalances)[len(rebalances) // 2]
                         if rebalances else 0),
        "total_observations": sum(len(r["rows"]) for r in rebalances),
        "delisted_exits": sum(t["n_delisted_exit"] for t in trail),
        "elapsed_sec": round(time.time() - t0, 1),
    }
    if dry_run:
        return {"status": "dry_run", "coverage": coverage, "trail_head": trail[:3]}

    # ── 단면 IC · 분위 스프레드 ────────────────────────────────────────────
    entry_idx = [r["entry_idx"] for r in rebalances]
    results: Dict[str, Any] = {}
    spreads_by_trial: Dict[str, List[Optional[float]]] = {}

    for axis in AXES:
        for h in HORIZONS:
            for sc in SCENARIOS:
                key = f"{axis}_{h}d_{sc}"
                ics: List[Optional[float]] = []
                sprd: List[Optional[float]] = []
                for rb in rebalances:
                    xs, ys = [], []
                    for r in rb["rows"]:
                        v, ret = r.get(axis), r.get(f"r{h}_{sc}")
                        if v is None or ret is None:
                            continue
                        xs.append(float(v))
                        ys.append(float(ret))
                    ics.append(spearman(xs, ys) if len(xs) >= MIN_NAMES else None)
                    if len(xs) >= N_QUANTILE * 3:
                        order = sorted(range(len(xs)), key=lambda i: xs[i])
                        k = max(1, len(order) // N_QUANTILE)
                        lo = sum(ys[i] for i in order[:k]) / k
                        hi = sum(ys[i] for i in order[-k:]) / k
                        cost = 2 * COMMISSION + SELL_TAX          # 롱숏 각 편도 왕복 근사
                        sprd.append((hi - lo) - 2 * cost)
                    else:
                        sprd.append(None)
                spreads_by_trial[key] = sprd
                sel = _select_non_overlapping(entry_idx, h)
                results[key] = {
                    "ic_naive": t_stat([v for v in ics if v is not None]),
                    "ic_non_overlap": t_stat([ics[i] for i in sel if ics[i] is not None]),
                    "spread_naive": t_stat([v for v in sprd if v is not None]),
                    "spread_non_overlap": t_stat([sprd[i] for i in sel if sprd[i] is not None]),
                }

    # ── PBO (CSCV) — 전 trial 포함 의무 (생존 trial 만 넣으면 과소추정) ────
    pbo: Dict[str, Any] = {"status": "skipped"}
    try:
        import numpy as np
        from api.quant.alpha.pbo import cscv_pbo
        keys = sorted(spreads_by_trial)
        rowsel = [i for i in range(len(rebalances))
                  if all(spreads_by_trial[k][i] is not None for k in keys)]
        if len(rowsel) >= 16 and len(keys) >= 2:
            mat = np.array([[spreads_by_trial[k][i] for k in keys] for i in rowsel],
                           dtype=float)
            pbo = cscv_pbo(mat, n_partitions=16)
            pbo["trials"] = keys
            pbo["T"] = len(rowsel)
        else:
            pbo = {"status": "insufficient", "T": len(rowsel), "N": len(keys)}
    except Exception as e:  # noqa: BLE001
        pbo = {"status": "error", "detail": f"{type(e).__name__}: {str(e)[:120]}"}

    doc = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                      time.localtime(time.time() + 9 * 3600)),
        "prereg": "docs/PREREG_BACKTEST_KR_2020_2026.md (v1.1 보정)",
        "axes": {
            "fscore8": "Piotroski 재현 가능 8기준 (F1~F6·F8·F9) — F7 만 제외, 운영에서도 전 종목 상수라 순위 동치",
            "gpa": "Novy-Marx Gross Profitability = (매출총이익률 × 자산회전율). 항등식 재구성",
        },
        "dropped_axis": {
            "graham_pbr_per": "PBR/PER 시계열 소스 0 (전 data/ sweep 확인) — 재현 불가로 폐기",
        },
        "method": {
            "universe": "kr_universe_pit 월말 스냅샷 (생존 편향 0)",
            "exclusions": "우선주(코드 끝자리≠0) · 스팩 · 리츠 · ETF",
            "pit_lag_days": PIT_LAG_DAYS, "horizons": list(HORIZONS),
            "delist_haircut": DELIST_HAIRCUT,
            "cost_roundtrip": 2 * COMMISSION + SELL_TAX,
            "judgment_rule": "비겹침 표본만 · Bonferroni |t| ≥ 2.64 (사전등록 6검정 기준 유지)",
        },
        "coverage": coverage,
        "results": results,
        "pbo": pbo,
        "note": "🚨 관측 산출물. 점수·집행 입력 0. 결과 해석은 사전등록 §4 표대로.",
    }
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out_path)
    with open(trail_path, "w", encoding="utf-8") as f:
        for t in trail:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lake", required=True, help="일봉 히스토리 디렉토리 (종목당 {code}.json)")
    ap.add_argument("--dry-run", action="store_true", help="커버리지만 — 검정 미실행")
    a = ap.parse_args()
    r = run(a.lake, dry_run=a.dry_run)
    if r.get("status") == "missing_input":
        print(f"[kr_fundamental] 입력 부족 {r.get('have')}", file=sys.stderr)
        return 1
    c = r["coverage"]
    print(f"[kr_fundamental] 리밸런스 {c['rebalances']} · 관측 {c['total_observations']:,} · "
          f"중앙 종목수 {c['median_names']} · 상폐청산 {c['delisted_exits']} · {c['elapsed_sec']}s")
    if r.get("status") == "dry_run":
        print("  (dry-run — 검정 미실행)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
