# -*- coding: utf-8 -*-
"""excursion_trail — 청산 episode 별 MAE/MFE 상시 계측 (관측 전용, 점수 입력 0).

2026-08-06 신설. 2026-08-05 집행 감사에서 KR 청산 12건의 MAE/MFE 를 **손으로** 계산해
사슬을 규명했는데(평균 MFE +5.8% / MAE −9.6% / 손절 −5% = 노이즈 안), 그 계산이 일회성
이라 표본이 쌓이지 않았다. 손절·익절 임계 재등록의 판정 근거가 전부 이 지표에서 나오므로
매 청산마다 자동 기록한다.

지표 정의 (Sweeney *Campaign Trading* 1996 · 2026-08-05 Perplexity 자문 Q1/Q5 정합):
  MAE (Maximum Adverse Excursion)   = 보유 중 최저가 대비 진입가 낙폭
  MFE (Maximum Favorable Excursion) = 보유 중 최고가 대비 진입가 상승폭
  MFE Capture Rate = 실현수익 / MFE — **50% 미만이면 조기 청산** 신호
  MAE-to-Stop Ratio = |MAE| / |손절거리| — **0.85 이상이면 손절이 적정**, 낮으면 스톱이 넓음
  손절 도달률 = 손절 거리에 실제로 닿은 비율 — 높으면 스톱이 노이즈 안

산출: data/excursion_trail.jsonl (episode append) + data/excursion_summary.json (집계)
🚨 **점수·집행에 입력되지 않는다.** 순수 관측 (RULE 7 산식 무변경).
데이터 원천: trade_ledger 청산 episode + 금융위 일봉 OHLC(data/kr_chart_daily).
KR 전용 — US 는 일봉 레이크가 로컬(us_prices.duckdb)이라 CI 에서 못 읽는다(Task#12).
"""
from __future__ import annotations

import glob
import json
import os
import statistics
from typing import Any, Dict, List, Optional, Tuple

from api.config import DATA_DIR, now_kst

TRAIL_PATH = os.path.join(DATA_DIR, "excursion_trail.jsonl")
SUMMARY_PATH = os.path.join(DATA_DIR, "excursion_summary.json")
CHART_DIR = os.path.join(DATA_DIR, "kr_chart_daily")

# 판정 임계 (외부 자문 인용값 — 자체 산식 아님, 라벨링 전용)
CAPTURE_EARLY_EXIT = 50.0   # MFE Capture < 50% = 조기 청산 의심
MAE_STOP_TIGHT = 0.85       # MAE/Stop ≥ 0.85 = 손절 적정 (미만이면 스톱이 넓음)


def _load_bars() -> Dict[str, List[List[int]]]:
    """금융위 일봉 청크 → {ticker: [[yyyymmdd,o,h,l,c,v], ...]}."""
    out: Dict[str, List[List[int]]] = {}
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


def _entry_of(history: List[Dict[str, Any]], ticker: str, exit_date: str
              ) -> Optional[Tuple[str, float]]:
    """해당 청산 직전의 진입(BUY) — (date, price). 없으면 None."""
    best = None
    for ev in history:
        if ev.get("type") != "BUY":
            continue
        if str(ev.get("ticker") or ev.get("name")) != ticker:
            continue
        d = str(ev.get("date", ""))[:10]
        if d <= exit_date and (best is None or d >= best[0]):
            px = ev.get("price")
            if isinstance(px, (int, float)) and px > 0:
                best = (d, float(px))
    return best


def _excursion(bars: List[List[int]], d0: str, d1: str, entry: float
               ) -> Optional[Dict[str, float]]:
    """[d0, d1] 구간 OHLC 로 MAE/MFE(%) 산출. 봉 2개 미만이면 None."""
    try:
        a, b = int(d0.replace("-", "")), int(d1.replace("-", ""))
    except ValueError:
        return None
    win = [x for x in bars if isinstance(x, list) and len(x) >= 5 and a <= x[0] <= b]
    if len(win) < 2 or entry <= 0:
        return None
    hi = max(x[2] for x in win)
    lo = min(x[3] for x in win)
    return {
        "mfe_pct": round((hi - entry) / entry * 100, 2),
        "mae_pct": round((lo - entry) / entry * 100, 2),
        "bars": len(win),
    }


def build(history: Optional[List[Dict[str, Any]]] = None,
          since: Optional[str] = None) -> Dict[str, Any]:
    """청산 episode 전수 재계산 → trail 재작성 + 요약. 멱등(매 run 전체 재계산)."""
    from api.vams.engine import load_history
    from api.vams.trade_ledger import reconstruct

    hist = history if history is not None else load_history()
    if since is None:
        try:
            with open(os.path.join(DATA_DIR, "portfolio.json"), encoding="utf-8") as f:
                since = str((((json.load(f).get("vams") or {}).get("reset_meta") or {})
                             .get("reset_at") or ""))[:10] or None
        except (OSError, json.JSONDecodeError):
            since = None

    eps = reconstruct(hist, since=since)["episodes"]
    bars = _load_bars()

    rows: List[Dict[str, Any]] = []
    for e in eps:
        tk = str(e.get("ticker") or "")
        if not tk.isdigit():
            continue                      # KR 전용 (US 일봉은 로컬 레이크 — CI 미도달)
        b = bars.get(tk)
        ent = _entry_of(hist, tk, str(e.get("date")))
        if not b or not ent:
            continue
        ex = _excursion(b, ent[0], str(e.get("date")), ent[1])
        if not ex:
            continue
        entry_px = ent[1]
        realized_pct = round(e["pnl"] / (entry_px) * 100, 2) if entry_px else None
        # 실현률은 episode 손익(원) 기준이라 수량 미상 — 가격 기반 근사는 별도 필드로 구분
        rows.append({
            "ticker": tk, "name": e.get("name"),
            "entry_date": ent[0], "exit_date": e.get("date"),
            "entry_price": round(entry_px, 2),
            "hold_bars": ex["bars"],
            "mfe_pct": ex["mfe_pct"], "mae_pct": ex["mae_pct"],
            "episode_pnl": e.get("pnl"),
            "_note": "MAE/MFE = 일봉 고저 기준. episode_pnl 은 원화 실현손익(수량 반영).",
        })

    # ── 집계 ────────────────────────────────────────────────────────
    mfes = [r["mfe_pct"] for r in rows]
    maes = [r["mae_pct"] for r in rows]
    wins = [r for r in rows if (r.get("episode_pnl") or 0) > 0]
    losses = [r for r in rows if (r.get("episode_pnl") or 0) < 0]
    n = len(rows)

    def _med(v):
        return round(statistics.median(v), 2) if v else None

    summary = {
        "as_of": now_kst().isoformat(timespec="seconds"),
        "version": "excursion_v0",
        "window_start": since,
        "n_episodes": n,
        "market": "KR",
        "mfe": {"mean": round(statistics.mean(mfes), 2) if mfes else None,
                "median": _med(mfes), "max": max(mfes) if mfes else None},
        "mae": {"mean": round(statistics.mean(maes), 2) if maes else None,
                "median": _med(maes), "min": min(maes) if maes else None,
                # 손절 폭 재등록의 1차 근거 — 자문 권고 = 승자 MAE 75퍼센타일을 스톱으로
                "winner_mae_p75": (round(sorted(r["mae_pct"] for r in wins)[int(len(wins) * 0.25)], 2)
                                   if len(wins) >= 4 else None)},
        "counts": {"wins": len(wins), "losses": len(losses)},
        "labels": [],
        "brain_input": False,
        "note": ("청산 episode MAE/MFE 관측 — 손절·익절 임계 재등록의 판정 근거. "
                 "점수·집행 입력 0. 정의: Sweeney(1996) MAE/MFE 프레임."),
    }
    if n < 30:
        summary["labels"].append(f"통계 무의미 (N={n} < 30)")
    elif n < 100:
        summary["labels"].append(f"예비 결과 (N={n} < 100)")
    if maes and mfes and statistics.mean(maes) < 0 and abs(statistics.mean(maes)) > statistics.mean(mfes):
        summary["labels"].append(
            "MAE 평균이 MFE 평균보다 큼 — 진입 후 하락 폭이 상승 폭을 넘는다(진입 타이밍/신호 축 점검)")

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
