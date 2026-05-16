"""
F-Score 시계열 Δ 산출 helper (2026-05-17 신설, Perplexity Q1 학계 자문).

Piotroski (2000) 원논문 정의 — Δ 4 항목은 직전 연도 (YoY) 비교:
- ΔROA = ROA(t) - ROA(t-1)
- ΔLEVER = Debt/Assets(t) < Debt/Assets(t-1)  (negative = healthier)
- ΔLIQUID = CurrentRatio(t) > CurrentRatio(t-1)
- ΔMARGIN = GrossMargin(t) - GrossMargin(t-1)
- ΔTURN = AssetTurnover(t) - AssetTurnover(t-1)

한국 시장 적용 (Perplexity Q1-1 학계 자문):
- 4분기 YoY 권장 (원논문 충실, 노이즈 최소)
- 사이클성 섹터 (반도체/조선/철강) = 4분기 + 8분기 AND 게이트 (별 sprint)

데이터 source:
- data/dart_quarterly_snapshots.jsonl (분기별 종목 fundamentals 누적, 별 sprint)
- 또는 dart_pre_attach 의 history 필드

본 모듈 = 산출 helper. 데이터 누적 인프라 = dart_batch_builder 보강 별 sprint.
누적 데이터 부재 시 None 반환 (silent skip 차단).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

KST = timezone(timedelta(hours=9))

REPO_ROOT = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
QUARTERLY_SNAPSHOT_PATH = REPO_ROOT / "data" / "dart_quarterly_snapshots.jsonl"


def load_quarterly_snapshots(ticker: str) -> List[Dict[str, Any]]:
    """data/dart_quarterly_snapshots.jsonl 에서 단일 ticker 의 시계열 snapshot 로드.

    schema (별 sprint 박힌 후):
        {ticker, quarter_end (YYYY-MM-DD), roa, debt_ratio, current_ratio,
         gross_margin, asset_turnover, fetched_at}

    Returns: 분기 desc 정렬 (최근부터). 부재 시 빈 list.
    """
    if not QUARTERLY_SNAPSHOT_PATH.exists():
        return []
    try:
        snapshots = []
        with open(QUARTERLY_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    s = json.loads(line)
                    if s.get("ticker", "").upper() == ticker.upper():
                        snapshots.append(s)
                except json.JSONDecodeError:
                    continue
        # 분기 desc (최근부터)
        snapshots.sort(key=lambda x: x.get("quarter_end", ""), reverse=True)
        return snapshots
    except Exception as e:
        print(f"[fscore_delta] {ticker} snapshot load fail: {e}", file=sys.stderr)
        return []


def find_yoy_prior(
    current_quarter_end: str,
    snapshots: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """현재 분기 (e.g. 2026-Q1) 대비 1년 전 분기 (2025-Q1) snapshot 찾기.

    quarter_end format = "YYYY-MM-DD" (분기 마지막 일).
    """
    try:
        cur_dt = datetime.strptime(current_quarter_end, "%Y-%m-%d")
        target_dt = cur_dt - timedelta(days=365)
        # ±30일 마진 (분기 종료일 변동)
        for s in snapshots:
            s_dt_str = s.get("quarter_end", "")
            if not s_dt_str:
                continue
            try:
                s_dt = datetime.strptime(s_dt_str, "%Y-%m-%d")
                if abs((s_dt - target_dt).days) <= 30:
                    return s
            except ValueError:
                continue
    except ValueError:
        pass
    return None


def compute_fscore_deltas(
    current: Dict[str, Any],
    prior: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Δ 4-5 항목 산출.

    Returns:
        {
          "delta_roa": Optional[float],
          "c5_delta_leverage_negative": Optional[bool],
          "c6_delta_current_ratio_positive": Optional[bool],
          "c8_delta_gross_margin_positive": Optional[bool],
          "c9_delta_asset_turnover_positive": Optional[bool],
          "n_delta_computed": int (0-5),
          "data_source": "quarterly_snapshot_yoy" | "no_prior",
        }
    """
    if not prior:
        return {
            "delta_roa": None,
            "c5_delta_leverage_negative": None,
            "c6_delta_current_ratio_positive": None,
            "c8_delta_gross_margin_positive": None,
            "c9_delta_asset_turnover_positive": None,
            "n_delta_computed": 0,
            "data_source": "no_prior",
        }

    def _delta(field: str) -> Optional[float]:
        cur = current.get(field)
        pri = prior.get(field)
        if cur is None or pri is None:
            return None
        try:
            return float(cur) - float(pri)
        except (TypeError, ValueError):
            return None

    delta_roa = _delta("roa")
    delta_lev = _delta("debt_ratio")  # negative = healthier
    delta_cr = _delta("current_ratio")
    delta_gm = _delta("gross_margin")
    delta_at = _delta("asset_turnover")

    result = {
        "delta_roa": round(delta_roa, 4) if delta_roa is not None else None,
        "c5_delta_leverage_negative": delta_lev < 0 if delta_lev is not None else None,
        "c6_delta_current_ratio_positive": delta_cr > 0 if delta_cr is not None else None,
        "c8_delta_gross_margin_positive": delta_gm > 0 if delta_gm is not None else None,
        "c9_delta_asset_turnover_positive": delta_at > 0 if delta_at is not None else None,
        "data_source": "quarterly_snapshot_yoy",
    }
    result["n_delta_computed"] = sum(1 for v in result.values() if v is not None and not isinstance(v, str))
    return result


def attach_fscore_deltas(stock: Dict[str, Any]) -> None:
    """stock dict 에 'fscore_deltas' field 주입 (in-place).

    stock 에 ticker / current_quarter_fundamentals 필요.
    분기 snapshot 부재 시 fscore_deltas = {data_source: "no_prior"} 박힘.
    """
    ticker = stock.get("ticker", "")
    if not ticker:
        return
    snapshots = load_quarterly_snapshots(ticker)
    if not snapshots:
        stock["fscore_deltas"] = {"n_delta_computed": 0, "data_source": "no_snapshots"}
        return

    # 현재 분기 = stock 의 최근 fundamentals (또는 첫 snapshot)
    current = snapshots[0]  # 가장 최근
    current_qend = current.get("quarter_end", "")

    prior = find_yoy_prior(current_qend, snapshots[1:])
    deltas = compute_fscore_deltas(current, prior)
    stock["fscore_deltas"] = deltas


if __name__ == "__main__":
    # CLI dry-run
    if not QUARTERLY_SNAPSHOT_PATH.exists():
        print(f"[fscore_delta] {QUARTERLY_SNAPSHOT_PATH} 없음 — 인프라 prep 만 박힘", file=sys.stderr)
        # synthetic test
        sample_current = {"roa": 0.08, "debt_ratio": 1.2, "current_ratio": 1.5,
                          "gross_margin": 0.35, "asset_turnover": 0.7}
        sample_prior = {"roa": 0.06, "debt_ratio": 1.3, "current_ratio": 1.4,
                        "gross_margin": 0.32, "asset_turnover": 0.65}
        deltas = compute_fscore_deltas(sample_current, sample_prior)
        print(json.dumps(deltas, indent=2, ensure_ascii=False))
    else:
        print(f"[fscore_delta] {QUARTERLY_SNAPSHOT_PATH} 존재 — schema 확인 후 사용")
