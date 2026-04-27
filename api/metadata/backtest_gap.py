"""
백테스트 vs 실거래(시뮬레이션) 갭 측정 — Monthly~Annual 리포트.

백테스트는 정확한 진입가/청산가 가정. 실제 운영은:
  - 슬리피지 (시장가 매수 시 호가 갭)
  - 타이밍 지연 (신호 발생 → 실거래 사이 lag)
  - 부분 체결 (대량 주문 분할)
  - 호가 단위 반올림

검증 정책 살아있어 실거래 없지만, **시뮬레이션 갭**이라도 추적해야 검증 종료 후 신뢰성 확보.

저장: data/metadata/backtest_gap.jsonl
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

_PATH = os.path.join(DATA_DIR, "metadata", "backtest_gap.jsonl")


def log_gap(
    ticker: str,
    backtest_entry_price: float,
    sim_entry_price: float,
    backtest_exit_price: Optional[float] = None,
    sim_exit_price: Optional[float] = None,
    backtest_return_pct: Optional[float] = None,
    sim_return_pct: Optional[float] = None,
    note: str = "",
) -> Dict[str, Any]:
    """1건 갭 로깅."""
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    entry_slippage_pct = round((sim_entry_price - backtest_entry_price) / backtest_entry_price * 100, 4) if backtest_entry_price else None
    exit_slippage_pct = None
    if backtest_exit_price and sim_exit_price:
        exit_slippage_pct = round((sim_exit_price - backtest_exit_price) / backtest_exit_price * 100, 4)
    return_gap = None
    if backtest_return_pct is not None and sim_return_pct is not None:
        return_gap = round(sim_return_pct - backtest_return_pct, 2)

    entry = {
        "date": now_kst().strftime("%Y-%m-%d"),
        "timestamp": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "ticker": ticker,
        "backtest_entry": backtest_entry_price,
        "sim_entry": sim_entry_price,
        "entry_slippage_pct": entry_slippage_pct,
        "backtest_exit": backtest_exit_price,
        "sim_exit": sim_exit_price,
        "exit_slippage_pct": exit_slippage_pct,
        "backtest_return_pct": backtest_return_pct,
        "sim_return_pct": sim_return_pct,
        "return_gap_pct": return_gap,
        "note": note,
    }
    with open(_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def summarize_gap(days: int = 30) -> Dict[str, Any]:
    """기간 요약 — 평균 슬리피지 + 누적 갭."""
    if not os.path.exists(_PATH):
        return {"days": days, "samples": 0}

    cutoff = (now_kst().date() - __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")
    entry_slips: List[float] = []
    exit_slips: List[float] = []
    return_gaps: List[float] = []

    with open(_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
                if e.get("date", "") < cutoff:
                    continue
                if e.get("entry_slippage_pct") is not None:
                    entry_slips.append(e["entry_slippage_pct"])
                if e.get("exit_slippage_pct") is not None:
                    exit_slips.append(e["exit_slippage_pct"])
                if e.get("return_gap_pct") is not None:
                    return_gaps.append(e["return_gap_pct"])
            except json.JSONDecodeError:
                continue

    def _avg(xs):
        return round(sum(xs) / len(xs), 4) if xs else None

    return {
        "days": days,
        "samples": len(entry_slips),
        "avg_entry_slippage_pct": _avg(entry_slips),
        "avg_exit_slippage_pct": _avg(exit_slips),
        "avg_return_gap_pct": _avg(return_gaps),
        "total_return_gap_pct_sum": round(sum(return_gaps), 2) if return_gaps else 0,
    }
