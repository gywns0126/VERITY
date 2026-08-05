# -*- coding: utf-8 -*-
"""trade_ledger — VAMS 원장에서 **실제 청산 episode** 만 복원하는 단일 출처.

2026-08-05 신설. 두 가지를 동시에 끝낸다:

① 유령 매도 배제 (측정 오염 제거)
   2026-07-20 전수감사가 잡은 P0 "dev-mode 사이클이 prod history 에 phantom 매도 기록"
   (커밋 ec7a66111 에서 mode별 경로 분리로 **버그는 수정**). 그러나 **이미 적재된 기록은
   원장에 남아** 모든 통계를 오염시킨다. 실측(리셋 2026-05-17 이후):
     SELL 70건 = 실제 12 + **유령 58** · 유령에 붙은 손실 −1,396,639원(존재하지 않는 돈)
     EQT 9주 보유인데 4주씩 13회 매도 · EXE 5주 보유인데 3주씩 21회 매도(시간당 1회)
   원장은 **삭제하지 않는다**(감사 trail 보존). 집계 시점에 재생으로 걸러낸다.

② 정의 단일화
   simulation_stats(api/main.py)와 validation.py 가 같은 원장을 다르게 읽어 4.8배 괴리했던
   사고(#290)의 재발 방지. "거래 1건이 무엇인가"를 이 모듈 하나가 정의한다.

복원 규칙 (시간순 재생):
  BUY          → 보유 += quantity
  PARTIAL_SELL → 보유 −= sold_qty · 부분손익 누적(partial_pnl 우선, pnl 폴백)
  SELL         → 보유 > 0 이면 청산 episode 확정(손익 = SELL pnl + 누적 부분손익), 보유 0 리셋
                 보유 ≤ 0 이면 **유령** — episode 아님, 별도 집계로만 보고
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _key(ev: Dict[str, Any]) -> str:
    return str(ev.get("ticker") or ev.get("name") or "")


def _date(ev: Dict[str, Any]) -> str:
    return str(ev.get("date", ""))[:10]


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def reconstruct(history: List[Dict[str, Any]],
                since: Optional[str] = None) -> Dict[str, Any]:
    """원장 재생 → 실제 청산 episode + 유령 매도 분리.

    Args:
        history: VAMS history (load_history() 결과)
        since:   'YYYY-MM-DD' — 이 날짜 이후 청산분만 episode 로 집계(자본 리셋 경계).
                 None 이면 전체. 보유 재생은 항상 전 기간으로 한다(경계 전 매수분이
                 경계 후 매도의 근거이므로 잘라내면 정상 매도가 유령으로 오판된다).

    Returns:
        {
          "episodes":      [{ticker, date, pnl, raw_pnl, partial_pnl, ...}],  # 창 내 확정 청산
          "phantoms":      [{ticker, date, pnl}],                              # 보유 0 매도
          "phantom_pnl":   float,   # 유령에 붙어 있던 손익 합(창 내)
          "partial_realized": float,# 창 내 부분청산 실현 합(미청산 종목 포함)
          "excluded_pre_window": int,
          "open_positions": {ticker: qty},
        }
    """
    events = sorted(history, key=lambda e: str(e.get("date", "")))
    pos: Dict[str, float] = {}
    pacc: Dict[str, float] = {}

    episodes: List[Dict[str, Any]] = []
    phantoms: List[Dict[str, Any]] = []
    phantom_pnl = 0.0
    partial_realized = 0.0
    excluded_pre = 0

    def _in_window(d: str) -> bool:
        return since is None or d >= since

    for ev in events:
        t = ev.get("type")
        tk = _key(ev)
        d = _date(ev)

        if t == "BUY":
            pos[tk] = pos.get(tk, 0.0) + _f(ev.get("quantity"))
            continue

        if t == "PARTIAL_SELL":
            sold = _f(ev.get("sold_qty"))
            if sold > 0:
                pos[tk] = pos.get(tk, 0.0) - sold
            pp = ev.get("partial_pnl")
            if pp is None:
                pp = ev.get("pnl")
            pv = _f(pp)
            pacc[tk] = pacc.get(tk, 0.0) + pv
            if _in_window(d):
                partial_realized += pv
            continue

        if t != "SELL" or ev.get("pnl") is None:
            continue

        held = pos.get(tk, 0.0)
        if held <= 0:
            # 🚨 보유 0 매도 = 유령. episode 로 세지 않는다.
            if _in_window(d):
                phantoms.append({"ticker": tk, "date": d, "pnl": _f(ev.get("pnl"))})
                phantom_pnl += _f(ev.get("pnl"))
            continue

        acc = pacc.pop(tk, 0.0)
        pos[tk] = 0.0
        if not _in_window(d):
            excluded_pre += 1
            continue
        raw = _f(ev.get("pnl"))
        episodes.append({
            "ticker": tk, "name": ev.get("name") or tk, "date": d,
            "raw_pnl": round(raw, 2), "partial_pnl": round(acc, 2),
            "pnl": round(raw + acc, 2),
        })

    return {
        "episodes": episodes,
        "phantoms": phantoms,
        "phantom_pnl": round(phantom_pnl, 2),
        "partial_realized": round(partial_realized, 2),
        "excluded_pre_window": excluded_pre,
        "open_positions": {k: v for k, v in pos.items() if v > 0},
    }


def episode_pnls(history: List[Dict[str, Any]],
                 since: Optional[str] = None) -> Tuple[List[float], Dict[str, Any]]:
    """(episode 손익 리스트, 진단 dict) — 통계 계산부의 공용 진입점."""
    r = reconstruct(history, since=since)
    return [e["pnl"] for e in r["episodes"]], r
