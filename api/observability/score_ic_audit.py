# -*- coding: utf-8 -*-
"""score_ic_audit — 우리 점수가 실제로 수익률을 가르는가 (2026-08-07, 관측 전용).

**왜 지금 가능한가**: "미래에 검증"이 아니라 **이미 쌓인 데이터로 지금** 잴 수 있다.
  · 일 단면 스냅샷 108일(2026-04-05~)에 `brain_score` 4,090 종목-일
  · 일봉이 2025-05-22 부터라 **전 구간 겹침**
  · 108일 창이라 생존 편향이 사실상 없다(10년 백테스트와 다른 점)

**세 질문을 중요도 순으로 답한다**:
  ① 총점 IC   — brain_score 가 forward return 을 가르는가. 0 이면 나머지는 무의미하다
  ② 축 분해   — fact vs sentiment 중 어느 쪽이 그 IC 를 만드는가.
                 7:3 가중치는 **한 번도 검정된 적이 없다**
  ③ 등급 단조 — STRONG_BUY > BUY > WATCH > CAUTION > AVOID 순서로 수익이 나는가.
                 안 나면 등급 임계(75-60-45-25)는 장식이다

🚨 **관측 전용. 이 산출로 임계·가중치를 조정하지 않는다** — 조정은 RULE 7 사전등록 대상.
   결과를 보고 만지기 시작하면 오늘 종일 고친 것과 같은 곡선 맞추기가 된다.

방법론 (오늘 배운 함정 반영):
  · **단면 IC** — 매일 그 날 종목들 안에서 Spearman 순위상관을 구하고, 날짜별 IC 를 평균.
    관측 단위(4,090)로 세면 같은 종목 반복이 N 을 부풀린다(공매도 trail 실측 9종목→31건).
    단면 IC 는 날짜가 관측 단위라 그 함정이 정의상 없다.
  · **유효 N = 날짜 수**(T+h 가 지난 날), 종목-일 수가 아니다.
  · look-ahead 차단 — T 시점 점수 vs T→T+h 수익률. 같은 날 종가로 진입 가정.
  · 다중검정 — 3질문 × 지평 3개 = 9검정. Bonferroni 기준을 함께 보고한다.
"""
from __future__ import annotations

import glob
import json
import math
import os
import statistics
from typing import Any, Dict, List, Optional, Tuple

from api.config import DATA_DIR, now_kst

OUT_PATH = os.path.join(DATA_DIR, "score_ic_audit.json")
HORIZONS = (5, 20, 60)
_MIN_NAMES = 8      # 단면 IC 최소 종목 수 (이보다 적으면 순위상관이 무의미)
_GRADE_ORDER = ("STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID")


def _spearman(xs: List[float], ys: List[float]) -> Optional[float]:
    """순위상관. 동점은 평균 순위. n<3 이면 None."""
    n = len(xs)
    if n < 3 or n != len(ys):
        return None

    def _rank(v: List[float]) -> List[float]:
        idx = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[idx[j + 1]] == v[idx[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[idx[k]] = avg
            i = j + 1
        return r

    rx, ry = _rank(xs), _rank(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _load_bars() -> Dict[str, List[List[Any]]]:
    out: Dict[str, List[List[Any]]] = {}
    for p in sorted(glob.glob(os.path.join(DATA_DIR, "kr_chart_daily", "chunk_*.json"))):
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


def _fwd(bars: List[List[Any]], day: str, h: int) -> Optional[float]:
    """day 이후 h 거래일 수익률(%). 봉이 모자라면 None — 외삽 금지."""
    try:
        a = int(day.replace("-", ""))
    except (TypeError, ValueError):
        return None
    fut = [x for x in bars if isinstance(x, list) and len(x) >= 5 and x[0] >= a]
    if len(fut) <= h:
        return None
    base, later = fut[0][4], fut[h][4]
    if not base or base <= 0:
        return None
    return (later - base) / base * 100.0


def _snapshots() -> List[Tuple[str, List[Dict[str, Any]]]]:
    out: List[Tuple[str, List[Dict[str, Any]]]] = []
    for p in sorted(glob.glob(os.path.join(DATA_DIR, "history", "20??-??-??.json"))):
        day = os.path.basename(p)[:10]
        try:
            with open(p, encoding="utf-8") as f:
                recs = json.load(f).get("recommendations") or []
        except (OSError, json.JSONDecodeError):
            continue
        if recs:
            out.append((day, recs))
    return out


def _score_of(r: Dict[str, Any]) -> Optional[float]:
    v = ((r.get("verity_brain") or {}).get("brain_score"))
    if v is None:
        v = r.get("brain_score_pre_macro")
    return float(v) if isinstance(v, (int, float)) else None


def _axis_of(r: Dict[str, Any], axis: str) -> Optional[float]:
    v = (r.get("score_breakdown") or {}).get(axis)
    return float(v) if isinstance(v, (int, float)) else None


def _summ(vals: List[float], horizon: int = 1) -> Dict[str, Any]:
    """평균 IC + t통계 (겹침 보정 포함).

    🚨 **겹침(overlapping window) 함정**: 매일 스냅샷을 찍고 h일 forward 수익률을 재면
    연속된 날의 수익률 구간이 거의 완전히 겹친다. 관측이 독립이 아닌데 독립처럼 t 를
    계산하면 t 가 √h 배 가까이 부풀어 없는 유의성이 생긴다.
    실측(2026-08-07): 60일 지평 t=5.02 로 매우 강해 보였지만 N=28일이고 60일 겹침이라
    독립 구간은 사실상 0~1개다.

    두 값을 함께 낸다:
      · naive  — 전 날짜 사용(겹침 무시). 참고용이며 **유의 판정에 쓰지 않는다**
      · nonoverlap — h일 간격으로 솎아낸 비겹침 표본. 이쪽이 판정 기준
    """
    n = len(vals)
    if n < 3:
        return {"n_days": n, "mean": None, "t_stat": None, "verdict": "표본 부족"}

    def _t(v: List[float]) -> Tuple[Optional[float], Optional[float]]:
        if len(v) < 3:
            return (round(statistics.mean(v), 4) if v else None), None
        m_ = statistics.mean(v)
        sd_ = statistics.stdev(v)
        return round(m_, 4), (round(m_ / (sd_ / math.sqrt(len(v))), 2) if sd_ > 0 else None)

    m, t = _t(vals)
    step = max(1, int(horizon))
    nov = vals[::step]
    m_no, t_no = _t(nov)
    return {
        "n_days": n,
        "mean": m,
        "std": round(statistics.stdev(vals), 4),
        "t_stat_naive": t,
        "positive_days_pct": round(sum(1 for v in vals if v > 0) / n * 100, 1),
        "nonoverlap": {"n": len(nov), "mean": m_no, "t_stat": t_no},
        "_note": "판정은 nonoverlap.t_stat 로 한다 — naive 는 겹침으로 부풀려져 있다",
    }


def build() -> Dict[str, Any]:
    bars = _load_bars()
    snaps = _snapshots()
    ic: Dict[int, List[float]] = {h: [] for h in HORIZONS}
    ic_fact: Dict[int, List[float]] = {h: [] for h in HORIZONS}
    ic_sent: Dict[int, List[float]] = {h: [] for h in HORIZONS}
    grade_ret: Dict[int, Dict[str, List[float]]] = {
        h: {g: [] for g in _GRADE_ORDER} for h in HORIZONS}
    n_obs = 0

    for day, recs in snaps:
        rows = []
        for r in recs:
            tk = str(r.get("ticker") or "")
            if not tk.isdigit() or tk not in bars:
                continue            # KR 전용 (일봉 레이크가 KR)
            sc = _score_of(r)
            if sc is None:
                continue
            rows.append((tk, sc, r))
        if len(rows) < _MIN_NAMES:
            continue
        for h in HORIZONS:
            xs, ys, fx, sx = [], [], [], []
            for tk, sc, r in rows:
                fr = _fwd(bars[tk], day, h)
                if fr is None:
                    continue
                xs.append(sc); ys.append(fr)
                f, s = _axis_of(r, "fact_contribution"), _axis_of(r, "sentiment_contribution")
                if f is not None and s is not None:
                    fx.append((f, fr)); sx.append((s, fr))
                g = str(r.get("recommendation") or "")
                if g in grade_ret[h]:
                    grade_ret[h][g].append(fr)
            if h == HORIZONS[0]:
                n_obs += len(xs)
            if len(xs) >= _MIN_NAMES:
                v = _spearman(xs, ys)
                if v is not None:
                    ic[h].append(v)
            if len(fx) >= _MIN_NAMES:
                a = _spearman([p[0] for p in fx], [p[1] for p in fx])
                b = _spearman([p[0] for p in sx], [p[1] for p in sx])
                if a is not None:
                    ic_fact[h].append(a)
                if b is not None:
                    ic_sent[h].append(b)

    doc: Dict[str, Any] = {
        "as_of": now_kst().isoformat(timespec="seconds"),
        "version": "score_ic_audit_v0",
        "snapshots": len(snaps),
        "stock_days_used": n_obs,
        "method": ("단면 Spearman IC — 매일 그 날 종목 안에서 순위상관 → 날짜별 IC 평균. "
                   "유효 N = 날짜 수(종목-일 아님). 같은 종목 반복이 N 을 부풀리는 함정 회피."),
        "brain_input": False,
        "q1_total_ic": {str(h): _summ(ic[h], h) for h in HORIZONS},
        "q2_axis_ic": {str(h): {"fact": _summ(ic_fact[h], h), "sentiment": _summ(ic_sent[h], h)}
                       for h in HORIZONS},
        "q3_grade_monotonicity": {},
        "overlap_warning": ("매일 스냅샷 × h일 수익률 = 구간 겹침. naive t 는 √h 배 부풀 수 있다. "
                            "판정은 nonoverlap 기준."),
        "multiple_testing": ("3질문 × 지평 3 = 9검정. Bonferroni α=0.05 → |t| ≳ 2.77 "
                             "(단일 검정 1.96 아님). 이 문턱 아래는 '유의'라고 말하지 않는다."),
        "note": ("🚨 관측 전용 — 이 산출로 임계·가중치를 조정하지 않는다(RULE 7 사전등록 대상). "
                 "결과를 보고 만지면 곡선 맞추기다."),
    }
    for h in HORIZONS:
        ent: Dict[str, Any] = {}
        for g in _GRADE_ORDER:
            v = grade_ret[h][g]
            ent[g] = {"n": len(v),
                      "mean": round(statistics.mean(v), 2) if v else None,
                      "median": round(statistics.median(v), 2) if v else None}
        means = [(g, ent[g]["mean"]) for g in _GRADE_ORDER if ent[g]["mean"] is not None]
        mono = all(means[i][1] >= means[i + 1][1] for i in range(len(means) - 1)) if len(means) > 1 else None
        ent["_monotonic"] = mono
        ent["_order_observed"] = [g for g, _ in sorted(means, key=lambda x: -x[1])]
        doc["q3_grade_monotonicity"][str(h)] = ent

    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, OUT_PATH)
    return doc


def main() -> None:
    d = build()
    print(f"[score_ic] 스냅샷 {d['snapshots']}일 · 종목-일 {d['stock_days_used']:,}\n")
    print("① 총점 IC")
    for h in HORIZONS:
        s = d["q1_total_ic"][str(h)]
        no = s.get("nonoverlap") or {}
        print(f"   {h:>2}일: IC {s.get('mean')} · 양(+) {s.get('positive_days_pct')}% · "
              f"naive t {s.get('t_stat_naive')} (N {s.get('n_days')}) → "
              f"비겹침 t {no.get('t_stat')} (N {no.get('n')})")
    print("\n② 축 분해 (7:3 가중치 검정)")
    for h in HORIZONS:
        a = d["q2_axis_ic"][str(h)]
        fo = a["fact"].get("nonoverlap") or {}; so = a["sentiment"].get("nonoverlap") or {}
        print(f"   {h:>2}일: fact IC {a['fact'].get('mean')} (비겹침 t {fo.get('t_stat')}, N {fo.get('n')}) · "
              f"sentiment IC {a['sentiment'].get('mean')} (비겹침 t {so.get('t_stat')}, N {so.get('n')})")
    print("\n③ 등급 단조성")
    for h in HORIZONS:
        g = d["q3_grade_monotonicity"][str(h)]
        row = " · ".join(f"{k} {g[k]['mean']}({g[k]['n']})" for k in _GRADE_ORDER
                         if g[k]["mean"] is not None)
        print(f"   {h:>2}일: 단조={g['_monotonic']} | {row}")
    print(f"\n{d['multiple_testing']}")


if __name__ == "__main__":
    main()
