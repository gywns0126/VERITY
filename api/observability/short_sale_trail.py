# -*- coding: utf-8 -*-
"""short_sale_trail — 공매도 규칙이 걸러낸 종목의 사후 수익률 관측 (점수 입력 0).

2026-08-06 신설. 사전등록 docs/PREREG_SHORT_SALE_AUTO_AVOID_2026_08_06.md, PM 승인 안 (가).

**왜 필요한가**: 공매도 `auto_avoid` 는 등급 산식에서 가장 강한 조치(즉시 AVOID)인데,
걸러낸 종목의 이후 수익률을 우리는 기록하지 않았다. 즉 **이 규칙이 옳은지 판정할 데이터가
0** 이었다(등록 §3). 임계·강도를 논하기 전에 관측이 먼저다.

**무엇을 재는가**: 매일의 스냅샷에서 종목별 공매도 지표 → tier 분류 → 이후 20/60 거래일
수익률. tier 간 수익률 분포를 비교하면 "잘 걸러냈는가"에 데이터로 답할 수 있다.

  auto_avoid  KR 거래량비중 > 15%     (미장은 이 tier 없음 — 강도 자체가 다르다)
  downgrade   KR > 8% · US 숏인터레스트 > 20%
  clean       임계 미만
  missing     지표 결측 — 🚨 **clean 과 분리한다**. 기존 코드가 결측을 0(무혐의)으로
              통과시킨 것이 본 등록의 출발점이다. 여기서 섞으면 같은 오류를 재생산한다.

🚨 **점수·집행에 입력되지 않는다.** 순수 관측 (RULE 7 산식 무변경).
🚨 **KR·US tier 를 합산하지 않는다.** 측정 대상(흐름 vs 포지션)·임계·강도가 모두 다르다.

데이터 원천: data/history/YYYY-MM-DD.json 의 recommendations[] (원값 `kis_short_sale` /
`short_interest` 가 그대로 남아 있어 소급 재구성 가능 — 0 에서 시작하지 않는다) +
금융위 일봉 OHLC(data/kr_chart_daily). 수익률은 KR 전용 — US 일봉 레이크는 로컬이라
CI 에서 못 읽는다(Task#12). US 는 tier 분류까지만 기록한다.

산출: data/short_sale_trail.jsonl (관측 append) + data/short_sale_summary.json (집계)
"""
from __future__ import annotations

import glob
import json
import os
import re
import statistics
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

TRAIL_PATH = os.path.join(DATA_DIR, "short_sale_trail.jsonl")
SUMMARY_PATH = os.path.join(DATA_DIR, "short_sale_summary.json")
HISTORY_GLOB = os.path.join(DATA_DIR, "history", "20??-??-??.json")
CHART_DIR = os.path.join(DATA_DIR, "kr_chart_daily")

# 현행 임계 — red_flags.py 의 값을 **복제가 아니라 관측 대상으로** 명시한다.
# 본 모듈은 판정하지 않는다. 임계 변경은 재등록 대상(등록 §7-5, N=20 전 조정 금지).
KR_AUTO_AVOID = 15.0
KR_DOWNGRADE = 8.0
US_DOWNGRADE = 20.0

HORIZONS = (20, 60)      # 거래일


def _is_kr(ticker: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", str(ticker or "")))


def _tier(rec: Dict[str, Any]) -> tuple:
    """(tier, 지표값, 시장). 결측은 clean 과 분리한다."""
    tk = str(rec.get("ticker") or "")
    if _is_kr(tk):
        v = (rec.get("kis_short_sale") or {}).get("avg_short_ratio_5d")
        if not isinstance(v, (int, float)):
            return "missing", None, "KR"
        if v > KR_AUTO_AVOID:
            return "auto_avoid", float(v), "KR"
        if v > KR_DOWNGRADE:
            return "downgrade", float(v), "KR"
        return "clean", float(v), "KR"
    v = (rec.get("short_interest") or {}).get("short_pct")
    if not isinstance(v, (int, float)):
        return "missing", None, "US"
    return ("downgrade" if v > US_DOWNGRADE else "clean"), float(v), "US"


def _load_bars() -> Dict[str, List[List[Any]]]:
    """금융위 일봉 청크 → {ticker: [[yyyymmdd,o,h,l,c,v], ...]} (오름차순 가정)."""
    out: Dict[str, List[List[Any]]] = {}
    for p in sorted(glob.glob(os.path.join(CHART_DIR, "chunk_*.json"))):
        try:
            with open(p, encoding="utf-8") as f:
                stocks = (json.load(f).get("stocks") or {})
        except (OSError, json.JSONDecodeError):
            continue
        for tk, ent in stocks.items():
            c = (ent or {}).get("c")
            if c:
                out[str(tk)] = c
    return out


def _forward(bars: List[List[Any]], d0: str, n: int) -> Optional[float]:
    """d0 이후 n 거래일 수익률(%). 봉이 모자라면 None (외삽 금지)."""
    try:
        a = int(str(d0).replace("-", ""))
    except (ValueError, TypeError):
        return None
    fut = [x for x in bars if isinstance(x, list) and len(x) >= 5 and x[0] >= a]
    if len(fut) <= n:
        return None                      # 아직 안 지난 구간 — 조용히 제외
    base, later = fut[0][4], fut[n][4]
    if not base or base <= 0:
        return None
    return round((later - base) / base * 100, 2)


def build(since: Optional[str] = None) -> Dict[str, Any]:
    """히스토리 스냅샷 전수 재계산 → trail 재작성 + 집계. 멱등."""
    bars = _load_bars()
    rows: List[Dict[str, Any]] = []
    seen: set = set()

    for path in sorted(glob.glob(HISTORY_GLOB)):
        day = os.path.basename(path)[:10]
        if since and day < since:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                recs = json.load(f).get("recommendations") or []
        except (OSError, json.JSONDecodeError):
            continue
        for rec in recs:
            tk = str(rec.get("ticker") or "")
            if not tk or (day, tk) in seen:
                continue
            seen.add((day, tk))
            tier, val, market = _tier(rec)
            row: Dict[str, Any] = {
                "date": day, "ticker": tk, "name": rec.get("name"),
                "market": market, "tier": tier, "short_metric": val,
                "metric_kind": ("거래량 비중(흐름)" if market == "KR" else "숏인터레스트(포지션)"),
                "grade": rec.get("recommendation"),
                "brain_score": rec.get("brain_score_pre_macro"),
            }
            if market == "KR" and tk in bars:
                for h in HORIZONS:
                    row[f"fwd_{h}d_pct"] = _forward(bars[tk], day, h)
            rows.append(row)

    # ── 집계 — 시장별로 분리한다 (합산 금지: 지표·임계·강도가 다르다) ──
    # 🚨 **의사복제(pseudo-replication) 통제**: 같은 종목이 매일 스냅샷에 다시 등장한다.
    #   관측 건수를 N 으로 쓰면 종목 9개가 31로 부풀어 유의성을 지어낸다. 실측에서
    #   종목 단위로 접자 tier 순서가 뒤집혔다(downgrade 관측 −1.97% → 종목 −4.34%).
    #   → **1차 수치는 종목 단위 평균**, 관측 단위는 참고로만 병기. 게이트도 종목 수 기준.
    def _agg(market: str) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for tier in ("auto_avoid", "downgrade", "clean", "missing"):
            sub = [r for r in rows if r["market"] == market and r["tier"] == tier]
            ent: Dict[str, Any] = {
                "n_observations": len(sub),
                "n_tickers": len({r["ticker"] for r in sub}),
            }
            for h in HORIZONS:
                per: Dict[str, List[float]] = {}
                for r in sub:
                    v = r.get(f"fwd_{h}d_pct")
                    if isinstance(v, (int, float)):
                        per.setdefault(r["ticker"], []).append(v)
                by_tk = [statistics.mean(v) for v in per.values()]
                flat = [v for vs in per.values() for v in vs]
                ent[f"fwd_{h}d"] = {
                    "n_tickers": len(by_tk),            # ← 유효 표본
                    "n_observations": len(flat),
                    "mean": round(statistics.mean(by_tk), 2) if by_tk else None,
                    "median": round(statistics.median(by_tk), 2) if by_tk else None,
                    "mean_by_observation": round(statistics.mean(flat), 2) if flat else None,
                    "_note": "mean/median = 종목 단위(의사복제 제거). 관측 단위는 참고값.",
                }
            out[tier] = ent
        return out

    kr, us = _agg("KR"), _agg("US")
    labels: List[str] = []
    h0 = HORIZONS[0]
    aa_ent, cl_ent = kr["auto_avoid"][f"fwd_{h0}d"], kr["clean"][f"fwd_{h0}d"]
    n_aa = aa_ent["n_tickers"]          # 🚨 종목 수 기준 — 관측 수로 게이트하지 않는다
    if n_aa < 20:
        labels.append(f"통계 무의미 — auto_avoid 고유 종목 N={n_aa} < 20 "
                      f"(관측 {aa_ent['n_observations']}건이지만 같은 종목 반복. 등록 §6 게이트)")
    elif n_aa < 100:
        labels.append(f"예비 결과 — auto_avoid 종목 N={n_aa} < 100")

    # 실패 조항(등록 §6): 걸러낸 쪽이 더 잘 갔으면 규칙이 수익을 깎고 있다는 신호.
    # 🚨 게이트를 종목 수로 건다. 관측 수로 걸면 종목 9개짜리 비교에 경보가 뜬다.
    aa, cl = aa_ent["mean"], cl_ent["mean"]
    if aa is not None and cl is not None and aa > cl:
        if n_aa >= 20:
            labels.append(f"🚨 auto_avoid 종목이 clean 보다 높다 ({aa:+.2f}% vs {cl:+.2f}%, "
                          f"종목 N={n_aa}) — 규칙이 수익을 깎고 있을 가능성. "
                          "임계 조정이 아니라 지표 교체(등록 §4-나) 검토")
        else:
            labels.append(f"[관측] auto_avoid {aa:+.2f}% > clean {cl:+.2f}% (종목 N={n_aa}) — "
                          "방향은 규칙과 반대지만 표본 미달로 판정 보류. N≥20 까지 조정 금지")

    n_missing_us = us["missing"]["n_observations"]
    if n_missing_us:
        labels.append(f"US 지표 결측 {n_missing_us}건 — clean 과 분리 집계됨(무혐의 통과 아님)")
    if kr["missing"]["n_observations"]:
        labels.append(f"KR 지표 결측 {kr['missing']['n_observations']}건 — 수집 이전 기간 포함. "
                      "clean 과 분리 집계")

    summary = {
        "as_of": now_kst().isoformat(timespec="seconds"),
        "version": "short_sale_trail_v0",
        "n_observations": len(rows),
        "window_start": since,
        "thresholds_observed": {"kr_auto_avoid": KR_AUTO_AVOID, "kr_downgrade": KR_DOWNGRADE,
                                "us_downgrade": US_DOWNGRADE},
        "KR": kr,
        "US": us,
        "labels": labels,
        "brain_input": False,
        "note": ("공매도 규칙 사후 수익률 관측 — 임계·강도 재판단의 판정 근거. 점수·집행 입력 0. "
                 "KR=거래량 비중(흐름) / US=숏인터레스트(포지션) 로 측정 대상이 다르므로 "
                 "시장 간 수치를 비교하지 말 것. 수익률은 KR 전용(US 일봉 레이크 미도달)."),
    }

    os.makedirs(os.path.dirname(TRAIL_PATH) or ".", exist_ok=True)
    tmp = TRAIL_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, TRAIL_PATH)
    tmp2 = SUMMARY_PATH + ".tmp"
    with open(tmp2, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    os.replace(tmp2, SUMMARY_PATH)
    return summary
