"""
observation_scoring.py — 관측-only 신호 forward trail(OBS_PATH) 채점 엔진 (market-level).

2026-06-13 신설. 사전등록 spec docs/observation_signal_trails_spec_v0_2026_06_13.md 정합 (산식 LOCKED).
"진짜 산출물 = 채점되는 trail" (RULE 7 / win condition). 관측 only — 채점 결과 결정 피드백 0.

prediction_scoring.py(종목 cross-section) 의 짝. 차이 = 채점 단위가 종목이 아닌 **시장 index(sp500)**:
  - 종목 scorer 는 snapshot 의 _get_price_map_from_snapshot(종목별 가격) diff 로 채점.
  - 본 scorer 는 동일 snapshot 의 market_summary[idx]['value'](절대 index level) diff 로 채점.
    ⇒ 같은 snapshot 인프라(_find_nearest_snapshot/load_snapshot) 재사용, 새 가격 source 0 (RULE 10).

순환논리 antidote (prediction_scoring §3 정합): 자기 가정 채점 금지. 반드시 실현 index level 로만.

통계 재사용 (RULE 10 — 신 산식 0):
  - 횡단(소스간 cross-section) IC = prediction_scoring 의 stat 헬퍼 재사용 (단, 소스 1 = N<2 → IC None 빈번).
  - 본 trail 의 1차 검증축 = **소스별 시계열** (소스 1개의 forward 방향 hit / 누적 expectancy / IC).
    시계열 IC machinery 가 필요할 때 api/intelligence/ic_stats.py(Newey-West 등) 를 재사용 — 본 v0 은
    소스별 (source, horizon) hit/expectancy 집계까지(정직 보고). 시계열 rank-IC 활성은 N 충분 후 spec §6.

v0 채점 범위 (정직 보고 — RULE 7):
  - MARKET(sp500): snapshot market_summary 절대 level diff 로 realized_return 정식 채점. 신뢰.
  - 비-market(stock/sector) entry 가 OBS_PATH 에 혼입되면 무시(skip) — 본 trail 은 market 전용.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from api.config import DATA_DIR, now_kst
from api.metadata.prediction_trail import OBS_PATH as TRAIL_PATH  # 모듈 SoT 경로 재사용
from api.workflows.archiver import list_available_dates, load_snapshot
from api.intelligence.backtest_archive import _find_nearest_snapshot
# stat 헬퍼 재사용 (신 산식 0 — RULE 10). prediction_scoring §9.4 LOCKED 산식.
from api.intelligence.prediction_scoring import (
    HORIZON_OVERLAP_K,
    _binom_pvalue,
    _bootstrap_ci95,
    _ic_tstat_pvalue,
    _is_hit,
    _label_for,
    _spearman_ic,
)

IC_HISTORY_PATH = os.path.join(DATA_DIR, "observation_ic_history.jsonl")

# 실현 snapshot 미존재 시 재시도 한계 (prediction_scoring GRACE_DAYS 정합)
GRACE_DAYS = 14

# 채점 대상 시장 index 키 (snapshot market_summary 키). 'sp500' = US 관측 신호 target 정합.
_MARKET_KEYS = ("sp500", "kospi", "kosdaq", "ndx")


# ─── 실현 결과 (실제 시장 index level — 순환 antidote) ──────────────────


def _index_value_from_snapshot(snap: Optional[dict], idx: str) -> Optional[float]:
    """snapshot market_summary[idx]['value'] (절대 index level). 결손 → None."""
    if not isinstance(snap, dict):
        return None
    ms = snap.get("market_summary")
    if not isinstance(ms, dict):
        return None
    node = ms.get(idx)
    if not isinstance(node, dict):
        return None
    v = node.get("value")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _realized_market_return(
    idx: str, base_date: str, eval_date: str, available: List[str]
) -> Optional[float]:
    """base_date → eval_date 시장 index 실현 수익률(%). snapshot 절대 level diff.

    종목 scorer 의 _realized_stock_return 와 동형 — 종목 가격맵 대신 market_summary level 사용.
    어느 한쪽 결손/동일 snapshot → None (채점 불가, 호출부 grace 처리).
    """
    base_snap_date = _find_nearest_snapshot(base_date, available)
    eval_snap_date = _find_nearest_snapshot(eval_date, available)
    if not base_snap_date or not eval_snap_date or base_snap_date == eval_snap_date:
        return None
    base_val = _index_value_from_snapshot(load_snapshot(base_snap_date), idx)
    eval_val = _index_value_from_snapshot(load_snapshot(eval_snap_date), idx)
    if not base_val or not eval_val or base_val <= 0:
        return None
    return round((eval_val - base_val) / base_val * 100.0, 4)


# ─── trail I/O (prediction_scoring 패턴 정합, 독립 파일 — 무오염) ──────────


def _read_trail(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    out: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _rewrite_trail(path: str, entries: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _created_date(entry: Dict[str, Any]) -> str:
    ca = entry.get("created_at", "")
    return ca[:10] if len(ca) >= 10 else ca


# ─── 메인 채점 ──────────────────────────────


def score_observations(
    trail_path: Optional[str] = None,
    ic_history_path: Optional[str] = None,
) -> Dict[str, Any]:
    """OBS_PATH 의 eval_date 도달 market 예측 채점 + (source, horizon) 집계 append. graceful."""
    trail_path = trail_path or TRAIL_PATH
    ic_history_path = ic_history_path or IC_HISTORY_PATH

    entries = _read_trail(trail_path)
    if not entries:
        return {"scored": 0, "pending": 0, "skipped_nonmarket": 0, "groups": 0, "note": "trail 비어있음"}

    today = now_kst().date()
    today_str = today.strftime("%Y-%m-%d")
    available = list_available_dates()

    newly_scored: List[Dict[str, Any]] = []
    pending = 0
    unscoreable = 0
    skipped_nonmarket = 0

    for e in entries:
        if e.get("scored"):
            continue
        eval_date = e.get("eval_date")
        if not eval_date or eval_date > today_str:
            continue  # forward 미도래

        if e.get("target_type") != "market":
            skipped_nonmarket += 1
            continue
        idx = str(e.get("target"))
        if idx not in _MARKET_KEYS:
            skipped_nonmarket += 1
            continue

        ret = _realized_market_return(idx, _created_date(e), eval_date, available)
        if ret is None:
            try:
                ed = datetime.strptime(eval_date, "%Y-%m-%d").date()
            except ValueError:
                ed = today
            if (today - ed).days > GRACE_DAYS:
                e["scored"] = True
                e["realized_return"] = None
                e["hit"] = None
                e["_skip_reason"] = "no_snapshot_within_grace"
                unscoreable += 1
            else:
                pending += 1
            continue

        hit = _is_hit(str(e.get("direction")), ret)
        e["scored"] = True
        e["realized_return"] = ret
        e["hit"] = hit
        e["ic_contrib"] = e.get("pred_score")
        newly_scored.append(e)

    if newly_scored or unscoreable:
        _rewrite_trail(trail_path, entries)

    groups = _aggregate(entries)
    if groups:
        os.makedirs(os.path.dirname(ic_history_path), exist_ok=True)
        with open(ic_history_path, "a", encoding="utf-8") as f:
            for g in groups:
                f.write(json.dumps(g, ensure_ascii=False) + "\n")

    return {
        "scored": len(newly_scored),
        "pending": pending,
        "unscoreable": unscoreable,
        "skipped_nonmarket": skipped_nonmarket,
        "groups": len(groups),
    }


def _aggregate(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """scored market 예측을 (source, horizon) 별 집계 → snapshot 레코드 list.

    종목 scorer 와 달리 (target_type, horizon) 가 아닌 (source, horizon) — 소스별 신호의
    forward 유효성을 따로 보기 위함 (각 source = 잠재 wire 후보, 개별 판정 대상).
    """
    scored_at = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    by_group: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for e in entries:
        if not e.get("scored") or e.get("realized_return") is None:
            continue
        if e.get("target_type") != "market":
            continue
        src = (e.get("signals") or {}).get("obs_source") or e.get("source") or "unknown"
        key = (src, e.get("horizon"))
        by_group.setdefault(key, []).append(e)

    records: List[Dict[str, Any]] = []
    for (src, horizon), preds in by_group.items():
        n = len(preds)
        pred_scores = [float(p.get("pred_score") or 0.0) for p in preds]
        realized = [float(p.get("realized_return")) for p in preds]

        # 횡단 IC = 단일 소스 내 (pred_score, realized) 상관 — N<2 면 None (정직). 시계열 IC 는 N 충분 후 §6.
        ic = _spearman_ic(pred_scores, realized)
        k = HORIZON_OVERLAP_K.get(horizon, 1)
        effective_n = max(1.0, n / k)
        ic_tstat, ic_pvalue = _ic_tstat_pvalue(ic, effective_n)

        dir_outcomes = [(p, _is_hit(str(p.get("direction")), float(p.get("realized_return"))))
                        for p in preds]
        dir_outcomes = [(p, h) for p, h in dir_outcomes if h is not None]
        n_dir = len(dir_outcomes)
        hits = sum(1 for _, h in dir_outcomes if h)
        hit_rate = round(hits / n_dir, 4) if n_dir else None
        hit_pvalue = _binom_pvalue(hits, n_dir) if n_dir else None

        expectancy = round(sum(realized) / n, 4) if n else None
        ci95 = _bootstrap_ci95(realized)
        label = _label_for(effective_n, ic_pvalue)

        records.append({
            "scored_at": scored_at,
            "source": src,
            "horizon": horizon,
            "target_type": "market",
            "n": n,
            "effective_n": round(effective_n, 2),
            "overlap_k": k,
            "ic": ic,
            "ic_tstat": ic_tstat,
            "ic_pvalue": ic_pvalue,
            "hit_rate": hit_rate,
            "hit_n": n_dir,
            "hit_pvalue": hit_pvalue,
            "expectancy": expectancy,
            "ci95": ci95,
            "label": label,
            "spec_version": "obs.v0",
            "_method": "market-level index level diff. (source,horizon) 집계. 시계열 rank-IC 는 N 충분 후(spec §6).",
        })
    return records
