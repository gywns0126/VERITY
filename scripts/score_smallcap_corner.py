#!/usr/bin/env python3
"""
score_smallcap_corner.py — KR 소형주 코너 forward trail 채점 (Smallcap Corner Trail Spec v0).

2026-06-20 신설. spec docs/PREREG_SMALLCAP_CORNER_TRAIL_2026_06_20.md 정합.
SMALLCAP_PATH(별 trail) 의 eval_date 도달 예측을 채점 → (subgroup, horizon) 집계 →
smallcap_corner_ic_history.jsonl append. 관측 only — 결과 어떤 verdict/VAMS/Brain 학습 피드백 0 (RULE 7).

채점·통계 = prediction_scoring 헬퍼 전부 재사용 (신 산식 0, RULE 10):
  - 실현 수익률 = _realized_stock_return (+ 상폐 종결 _realized_terminal_return). 기존 snapshot 가격 source.
  - 통계 = _spearman_ic / _ic_tstat_pvalue / _binom_pvalue / _bootstrap_ci95 / _is_hit / _label_for.
집계만 subgroup 차원 추가 (전체 / high_conf / neglected_quality) — 메인 (target_type,horizon) 집계와 별 sink.

graceful: trail/snapshot 결손 시 예외 없이 부분 진행.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root

from api.config import DATA_DIR, now_kst
from api.metadata.prediction_trail import SMALLCAP_PATH
from api.workflows.archiver import list_available_dates
from api.intelligence.prediction_scoring import (
    GRACE_DAYS,
    HORIZON_OVERLAP_K,
    _binom_pvalue,
    _bootstrap_ci95,
    _created_date,
    _ic_tstat_pvalue,
    _is_hit,
    _label_for,
    _read_trail,
    _realized_stock_return,
    _realized_terminal_return,
    _rewrite_trail,
    _spearman_ic,
)

IC_HISTORY_PATH = os.path.join(DATA_DIR, "smallcap_corner_ic_history.jsonl")

# 부분군 정의 (spec §5). 멤버십 = 사실(점수 아님) → 자유 선택 surface 0.
# high_conf 제거(2026-06-20 §11): 코너 신호 = quant 팩터 개별, low_confidence 개념 부재.
_SUBGROUPS = ("all", "neglected_quality")


def _in_subgroup(e: Dict[str, Any], subgroup: str) -> bool:
    if subgroup == "all":
        return True
    if subgroup == "neglected_quality":
        return bool((e.get("signals") or {}).get("neglected_quality"))
    return False


def _factor_of(e: Dict[str, Any]) -> str:
    """예측 엔트리의 팩터 라벨 (signals.factor). source fallback."""
    fac = (e.get("signals") or {}).get("factor")
    if fac:
        return str(fac)
    src = str(e.get("source") or "")
    parts = src.split(".")  # smallcap_corner.<factor>.v0
    return parts[1] if len(parts) >= 3 else "unknown"


def _score_trail(entries: List[Dict[str, Any]], available, today) -> Dict[str, int]:
    """eval_date 도달 미채점 예측 채점 (score_predictions 루프 미러 — stock only)."""
    today_str = today.strftime("%Y-%m-%d")
    newly = pending = unscoreable = delisted = 0
    for e in entries:
        if e.get("scored"):
            continue
        eval_date = e.get("eval_date")
        if not eval_date or eval_date > today_str:
            continue  # 아직 미도래 (forward)
        if e.get("target_type") != "stock":
            continue
        ret = _realized_stock_return(str(e.get("target")), _created_date(e), eval_date, available)
        if ret is None:
            try:
                ed = datetime.strptime(eval_date, "%Y-%m-%d").date()
            except ValueError:
                ed = today
            if (today - ed).days > GRACE_DAYS:
                # 상폐/소멸 종결 채점 (survivorship-free, spec §6)
                term = _realized_terminal_return(str(e.get("target")), _created_date(e), eval_date, available)
                if term is not None:
                    e.update({
                        "scored": True, "realized_return": term,
                        "hit": _is_hit(str(e.get("direction")), term),
                        "ic_contrib": e.get("pred_score"),
                        "realized_source": "last_available_delisting", "delisted": True,
                    })
                    newly += 1
                    delisted += 1
                else:
                    e.update({"scored": True, "realized_return": None, "hit": None,
                              "_skip_reason": "no_snapshot_within_grace"})
                    unscoreable += 1
            else:
                pending += 1
            continue
        e.update({
            "scored": True, "realized_return": ret,
            "hit": _is_hit(str(e.get("direction")), ret),
            "ic_contrib": e.get("pred_score"),
        })
        newly += 1
    return {"scored": newly, "delisted_scored": delisted, "pending": pending, "unscoreable": unscoreable}


def _aggregate(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """scored 예측을 (factor, subgroup, horizon) 별 집계 → snapshot 레코드 list.
    prediction_scoring._aggregate 와 동일 stat (factor/subgroup 차원 추가, survivorship_unadjusted 명시).
    팩터별 독립 forward IC (PM 결정 §11) — momentum/quality/vol/mr 각각 별 그룹."""
    scored_at = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    scored = [e for e in entries
              if e.get("scored") and e.get("realized_return") is not None and e.get("target_type") == "stock"]

    factors = sorted({_factor_of(e) for e in scored})
    records: List[Dict[str, Any]] = []
    for factor in factors:
      fac_scored = [e for e in scored if _factor_of(e) == factor]
      for subgroup in _SUBGROUPS:
        by_h: Dict[str, List[Dict[str, Any]]] = {}
        for e in fac_scored:
            if _in_subgroup(e, subgroup):
                by_h.setdefault(str(e.get("horizon")), []).append(e)
        for horizon, preds in by_h.items():
            n = len(preds)
            pred_scores = [float(p.get("pred_score") or 0.0) for p in preds]
            realized = [float(p.get("realized_return")) for p in preds]

            ic = _spearman_ic(pred_scores, realized)
            k = HORIZON_OVERLAP_K.get(horizon, 1)
            effective_n = max(1.0, n / k)
            ic_tstat, ic_pvalue = _ic_tstat_pvalue(ic, effective_n)

            dir_outcomes = [(p, _is_hit(str(p.get("direction")), float(p.get("realized_return")))) for p in preds]
            dir_outcomes = [(p, h) for p, h in dir_outcomes if h is not None]
            n_dir = len(dir_outcomes)
            hits = sum(1 for _, h in dir_outcomes if h)
            hit_rate = round(hits / n_dir, 4) if n_dir else None
            hit_pvalue = _binom_pvalue(hits, n_dir) if n_dir else None

            brier = None
            if n_dir:
                brier = round(sum((float(p.get("confidence") or 0.5) - (1.0 if h else 0.0)) ** 2
                                  for p, h in dir_outcomes) / n_dir, 4)

            expectancy = round(sum(realized) / n, 4) if n else None
            ci95 = _bootstrap_ci95(realized)
            label = _label_for(effective_n, ic_pvalue)

            records.append({
                "scored_at": scored_at,
                "factor": factor,
                "subgroup": subgroup,
                "horizon": horizon,
                "n": n,
                "effective_n": round(effective_n, 2),
                "overlap_k": k,
                "ic": ic,
                "ic_tstat": ic_tstat,
                "ic_pvalue": ic_pvalue,
                "hit_rate": hit_rate,
                "hit_n": n_dir,
                "hit_pvalue": hit_pvalue,
                "brier_score": brier,
                "expectancy": expectancy,
                "ci95": ci95,
                "label": label,
                "spec_version": "smallcap.v0",
                "survivorship_unadjusted": True,  # census = 현 listed only (spec §6 gauntlet 정합)
                "_method": "cross-section Spearman IC, N_eff=T/k(overlap), 비중첩 보수. 코너 별 풀 — 메인 IC 직접 비교 금지.",
            })
    return records


def score_smallcap(trail_path: Optional[str] = None, ic_history_path: Optional[str] = None) -> Dict[str, Any]:
    trail_path = trail_path or SMALLCAP_PATH
    ic_history_path = ic_history_path or IC_HISTORY_PATH

    entries = _read_trail(trail_path)
    if not entries:
        return {"scored": 0, "pending": 0, "groups": 0, "note": "trail 비어있음"}

    today = now_kst().date()
    available = list_available_dates()
    stats = _score_trail(entries, available, today)

    if stats["scored"] or stats["unscoreable"]:
        _rewrite_trail(trail_path, entries)

    groups = _aggregate(entries)
    # 신규 채점 있을 때만 append (byte-identical 재append 방지 — prediction_scoring §fix 정합).
    if groups and stats["scored"]:
        os.makedirs(os.path.dirname(ic_history_path), exist_ok=True)
        with open(ic_history_path, "a", encoding="utf-8") as f:
            for g in groups:
                f.write(json.dumps(g, ensure_ascii=False) + "\n")

    return {**stats, "groups": len(groups)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trail", default=None, help="trail 경로 override (테스트용)")
    ap.add_argument("--ic-history", default=None, help="ic_history 경로 override (테스트용)")
    args = ap.parse_args()
    try:
        res = score_smallcap(trail_path=args.trail, ic_history_path=args.ic_history)
    except Exception as e:  # noqa: BLE001 — 채점 결손이 cron 전체 막지 않게 (graceful)
        sys.stderr.write(f"[score-smallcap] skip (graceful): {type(e).__name__}: {e}\n")
        return 0
    print(
        f"[score-smallcap] scored {res.get('scored', 0)} "
        f"(delisted {res.get('delisted_scored', 0)}, pending {res.get('pending', 0)}, "
        f"unscoreable {res.get('unscoreable', 0)}) → {res.get('groups', 0)} group snapshots"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
