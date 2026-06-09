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

    schema:
        {ticker, quarter_end (YYYY-MM-DD), reprt_code, roa, debt_ratio,
         current_ratio, gross_margin, asset_turnover, fetched_at}

    Dedupe (2026-05-20): 같은 (ticker + quarter_end) 중복 시 fetched_at 최신만 유지.
    매주 cron append 패턴에서 같은 분기 entry 중복 누적 → 가장 최근 수집 신뢰.

    Returns: 분기 desc 정렬 (최근부터). 부재 시 빈 list.
    """
    if not QUARTERLY_SNAPSHOT_PATH.exists():
        return []
    try:
        by_quarter: Dict[str, Dict[str, Any]] = {}
        with open(QUARTERLY_SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    s = json.loads(line)
                    if s.get("ticker", "").upper() != ticker.upper():
                        continue
                    qend = s.get("quarter_end", "")
                    if not qend:
                        continue
                    prev = by_quarter.get(qend)
                    if prev is None or (s.get("fetched_at", "") > prev.get("fetched_at", "")):
                        by_quarter[qend] = s
                except json.JSONDecodeError:
                    continue
        snapshots = sorted(by_quarter.values(), key=lambda x: x.get("quarter_end", ""), reverse=True)
        return snapshots
    except Exception as e:
        print(f"[fscore_delta] {ticker} snapshot load fail: {e}", file=sys.stderr)
        return []


def find_quarter_offset_prior(
    current_quarter_end: str,
    snapshots: List[Dict[str, Any]],
    quarters_back: int,
) -> Optional[Dict[str, Any]]:
    """현재 분기 대비 N 분기 전 (quarters_back=4 → 1년 / =8 → 2년) snapshot 찾기.

    ±30일 마진 (분기 종료일 변동/연간보고서 결산일 차이).
    """
    try:
        cur_dt = datetime.strptime(current_quarter_end, "%Y-%m-%d")
        target_dt = cur_dt - timedelta(days=int(365 * quarters_back / 4))
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


def find_yoy_prior(
    current_quarter_end: str,
    snapshots: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """현재 분기 대비 1년 전 (4 분기 전) snapshot. find_quarter_offset_prior wrapper."""
    return find_quarter_offset_prior(current_quarter_end, snapshots, quarters_back=4)


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


def is_cyclical_for_fscore(stock: Dict[str, Any]) -> bool:
    """사이클 섹터 식별 — lynch_classifier 의 _is_cyclical_sector 재사용.

    Perplexity Q-fin-4 (2026-05-19): 한국 반도체/조선/철강 등 사이클 섹터는 4Q YoY 노이즈 큼.
    """
    try:
        from api.intelligence.lynch_classifier import _is_cyclical_sector
        return _is_cyclical_sector(stock)
    except Exception:
        return False


def compute_fscore_deltas_with_cycle_guard(
    current: Dict[str, Any],
    prior_4q: Optional[Dict[str, Any]],
    prior_8q: Optional[Dict[str, Any]] = None,
    is_cyclical: bool = False,
) -> Dict[str, Any]:
    """4Q + 8Q AND 게이트 (사이클 섹터 Perplexity Q-fin-4 정합).

    - 비사이클: 4Q YoY 만 사용 (Piotroski 원전).
    - 사이클: 4Q + 8Q 둘 다 통과해야 boolean True (AND 게이트, noise 완화).

    Returns: compute_fscore_deltas 와 동일 schema + cycle_guard 메타.
    """
    base = compute_fscore_deltas(current, prior_4q)
    base["cycle_guard"] = "8q_and" if is_cyclical else "4q_only"

    if not is_cyclical or not prior_8q:
        base["8q_available"] = bool(prior_8q)
        return base

    deltas_8q = compute_fscore_deltas(current, prior_8q)
    # 4Q + 8Q AND — boolean field 만 둘 다 True 시 True
    for key in ("c5_delta_leverage_negative", "c6_delta_current_ratio_positive",
                "c8_delta_gross_margin_positive", "c9_delta_asset_turnover_positive"):
        v4 = base.get(key)
        v8 = deltas_8q.get(key)
        if v4 is True and v8 is True:
            base[key] = True
        elif v4 is None or v8 is None:
            base[key] = None
        else:
            base[key] = False
    base["8q_available"] = True
    base["8q_data_source"] = deltas_8q.get("data_source")
    return base


def attach_fscore_deltas(stock: Dict[str, Any]) -> None:
    """stock dict 에 'fscore_deltas' field 주입 (in-place).

    사이클 섹터 (반도체/조선/철강 등, Perplexity Q-fin-4) 자동 식별 후 4Q+8Q AND 게이트 적용.

    stock 에 ticker / current_quarter_fundamentals 필요.
    분기 snapshot 부재 시 fscore_deltas = {data_source: "no_snapshots"} 설정됨.
    """
    ticker = stock.get("ticker", "")
    if not ticker:
        return
    snapshots = load_quarterly_snapshots(ticker)
    if not snapshots:
        stock["fscore_deltas"] = {"n_delta_computed": 0, "data_source": "no_snapshots"}
        return

    current = snapshots[0]
    current_qend = current.get("quarter_end", "")

    prior_4q = find_quarter_offset_prior(current_qend, snapshots[1:], quarters_back=4)
    is_cyc = is_cyclical_for_fscore(stock)
    prior_8q = find_quarter_offset_prior(current_qend, snapshots[1:], quarters_back=8) if is_cyc else None

    deltas = compute_fscore_deltas_with_cycle_guard(current, prior_4q, prior_8q, is_cyclical=is_cyc)
    stock["fscore_deltas"] = deltas


if __name__ == "__main__":
    # CLI dry-run
    if not QUARTERLY_SNAPSHOT_PATH.exists():
        print(f"[fscore_delta] {QUARTERLY_SNAPSHOT_PATH} 없음 — 인프라 prep 만 완료", file=sys.stderr)
        # synthetic test
        sample_current = {"roa": 0.08, "debt_ratio": 1.2, "current_ratio": 1.5,
                          "gross_margin": 0.35, "asset_turnover": 0.7}
        sample_prior = {"roa": 0.06, "debt_ratio": 1.3, "current_ratio": 1.4,
                        "gross_margin": 0.32, "asset_turnover": 0.65}
        deltas = compute_fscore_deltas(sample_current, sample_prior)
        print(json.dumps(deltas, indent=2, ensure_ascii=False))
    else:
        print(f"[fscore_delta] {QUARTERLY_SNAPSHOT_PATH} 존재 — schema 확인 후 사용")
