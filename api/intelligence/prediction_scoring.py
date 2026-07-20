"""
prediction_scoring.py — Prediction Layer 채점 엔진 (eval_date 도달분 실현 결과 채점).

2026-06-01 신설. 사전등록 spec docs/prediction_layer_spec_v0_2026_06_01.md §9.3/§9.4 정합 (산식 LOCKED).
"진짜 산출물 = 채점되는 trail" (RULE 7 / win condition). 예측 로깅(prediction_layer)의 짝.

순환논리 antidote (spec §3, ARENA GBM 폐기 교훈): 자기 예측을 자기 가정으로 채점 = 순환.
반드시 **실현된 실제 시장 결과**(history snapshot 가격)로만 채점. 시뮬/자기가정 채점 금지.

흐름 (매 daily run):
  1. prediction_trail.jsonl 읽기 → eval_date <= today AND scored==false 예측 추출
  2. 실현 결과 fetch (history snapshot 가격 — backtest_archive 가격맵 재사용, RULE 6 재구현 X)
  3. hit / realized_return 산출 → scored=true 로 trail rewrite
  4. (target_type, horizon) 집계 → IC/hit/Brier/expectancy/CI → prediction_ic_history.jsonl append

v0 채점 범위 (정직 보고 — RULE 7):
  - STOCK: history snapshot 가격 diff 로 realized_return 정식 채점. 신뢰.
  - SECTOR: 채점 DEFERRED. sectors[].change_pct = heat/모멘텀 메트릭(rank/heat 동반)이며 clean
    period return 이 아님. 잘못된 return proxy 채점 = RULE 7 위반. 검증된 섹터 index return
    source 확정 후 활성. 섹터 예측은 trail 에 계속 누적 (활성 시 backfill 아닌 forward 만).

v0 operational lock (spec §9.4 의 N_eff=T/k 를 구체화 — PM 확인 의무):
  - effective_n = T / k_overlap. T = 집계 관측수, k_overlap = horizon 중첩(거래일):
    short=5 / mid=63 / long=252 (daily 생성 → 중첩 윈도우. Bailey-Lopez de Prado 비중첩 정신, 보수적).
  - 자산 cross-section breadth 는 effective_n 에 가산하지 않음 (자산간 상관 → 과대 inflation 회피, 보수적).
  - 결과: mid/long 은 k 가 커 effective_n≈0~1 → 영구 "Trail 누적 초기" (정직, spec §4 비대칭 정합).
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from api.config import DATA_DIR, now_kst
from api.metadata.prediction_trail import _PATH as TRAIL_PATH  # noqa: N811 (모듈 SoT 경로 재사용)
from api.workflows.archiver import list_available_dates, load_snapshot
from api.intelligence.backtest_archive import (
    _find_nearest_snapshot,
    _get_price_map_from_snapshot,
)

IC_HISTORY_PATH = os.path.join(DATA_DIR, "prediction_ic_history.jsonl")

# 실현 가격 snapshot 미존재 시 재시도 한계 (이후 unscoreable 로 종결, 무한 재시도 차단)
GRACE_DAYS = 14

# horizon 중첩 길이 (거래일) — N_eff = T/k 의 k (v0 operational lock, 위 docstring)
HORIZON_OVERLAP_K = {"short": 5, "mid": 63, "long": 252}

# §4 N_eff 라벨 게이트 (spec §9.4 lock)
_LABEL_EARLY = "Trail 누적 초기"
_LABEL_PRELIM = "예비"
_LABEL_SIGNIFICANT = "유의"


# ─── 실현 결과 (실제 시장 — 순환 antidote) ──────────────────────────────


def _realized_stock_return(
    ticker: str, base_date: str, eval_date: str, available: List[str]
) -> Optional[float]:
    """base_date → eval_date 종목 실현 수익률(%). history snapshot 가격 diff.

    base = 예측 생성 시점(created) 가격 (forecast 기준), eval = eval_date 최근접 snapshot 가격.
    어느 한쪽 가격 결손 → None (채점 불가, 호출부가 grace 처리).
    """
    base_snap_date = _find_nearest_snapshot(base_date, available, backward_only=True)  # base=미래금지(look-ahead)
    eval_snap_date = _find_nearest_snapshot(eval_date, available)
    if not base_snap_date or not eval_snap_date or base_snap_date == eval_snap_date:
        return None
    base_snap = load_snapshot(base_snap_date)
    eval_snap = load_snapshot(eval_snap_date)
    if not base_snap or not eval_snap:
        return None
    base_price = _get_price_map_from_snapshot(base_snap).get(ticker)
    eval_price = _get_price_map_from_snapshot(eval_snap).get(ticker)
    if not base_price or not eval_price or base_price <= 0:
        return None
    return round((eval_price - base_price) / base_price * 100.0, 4)


def _realized_terminal_return(
    ticker: str, base_date: str, eval_date: str, available: List[str]
) -> Optional[float]:
    """eval 시점 가격 소멸(상폐/소멸) 케이스 종결 실현수익 — survivorship-free 교정.

    2026-06-15 추가 (PM 승인 "고고", 사전등록 = ic_dead_freeze 후속 / 자가감사 잔여 gap).
    정상 경로(_realized_stock_return)에서 eval 가격 결손 → 드롭(unscoreable)되던 것은 상폐 손실을
    IC 에서 배제 = 생존편향(우리가 +346bp/yr 로 정량화한 그 편향이 IC 로 재진입). 본 fallback 은
    base~eval 사이 *마지막 가용* snapshot 가격으로 종결가를 잡아 *드롭 대신 하락을 포착*한다.
    🚨 LOCKED 정상 산식 무변경 — 기존에 *버려지던* 케이스에만 적용(grace 초과 후). base 결손이면 None.
    """
    base_snap_date = _find_nearest_snapshot(base_date, available, backward_only=True)  # base=미래금지(look-ahead)
    if not base_snap_date:
        return None
    base_snap = load_snapshot(base_snap_date)
    if not base_snap:
        return None
    base_price = _get_price_map_from_snapshot(base_snap).get(ticker)
    if not base_price or base_price <= 0:
        return None
    # base 이후 ~ eval 이하 snapshot 중 ticker 가격이 존재하는 *마지막*(최신) 것 = 종결가
    for d in sorted((x for x in available if base_snap_date < x <= eval_date), reverse=True):
        snap = load_snapshot(d)
        if not snap:
            continue
        p = _get_price_map_from_snapshot(snap).get(ticker)
        if p and p > 0:
            return round((p - base_price) / base_price * 100.0, 4)
    return None


def _is_hit(direction: str, realized_return: float) -> Optional[bool]:
    """방향 적중 여부. neutral = 방향 콜 부재 → hit_rate 모집단 제외(None)."""
    if direction == "up":
        return realized_return > 0
    if direction == "down":
        return realized_return < 0
    return None  # neutral — 이항 hit 모집단 제외 (IC 연속 채점에는 포함)


# ─── 통계 (spec §9.4 LOCKED 산식) ──────────────────────────────


def _spearman_ic(pred: List[float], realized: List[float]) -> Optional[float]:
    if len(pred) < 2:
        return None
    try:
        from scipy.stats import spearmanr
        rho, _ = spearmanr(pred, realized)
        if rho is None or math.isnan(rho):
            return None
        return round(float(rho), 4)
    except Exception:
        return None


def _ic_tstat_pvalue(ic: Optional[float], effective_n: float) -> Tuple[Optional[float], Optional[float]]:
    """ic_tstat = IC×√N_eff (Grinold-Kahn 1999), df=N_eff-2 단측 p."""
    if ic is None or effective_n is None or effective_n <= 2:
        return None, None
    tstat = ic * math.sqrt(effective_n)
    try:
        from scipy.stats import t as _t
        pval = float(_t.sf(abs(tstat), df=effective_n - 2))  # 단측
    except Exception:
        pval = None
    return round(tstat, 4), (round(pval, 4) if pval is not None else None)


def _binom_pvalue(hits: int, n: int) -> Optional[float]:
    """이항검정 H0:p=0.5 단측(우). 중첩 미보정 — N_eff 게이트로 보수 해석."""
    if n <= 0:
        return None
    try:
        from scipy.stats import binomtest
        return round(float(binomtest(hits, n, 0.5, alternative="greater").pvalue), 4)
    except Exception:
        return None


def _bootstrap_ci95(values: List[float], iters: int = 2000) -> Optional[List[float]]:
    """평균의 bootstrap 95% percentile CI. 결정론적(시드 고정) — 재현성."""
    if len(values) < 3:
        return None
    try:
        import numpy as np
        rng = np.random.default_rng(42)  # 시드 고정 (Math.random 회피 정합, 재현성)
        arr = np.asarray(values, dtype=float)
        means = arr[rng.integers(0, len(arr), size=(iters, len(arr)))].mean(axis=1)
        lo, hi = np.percentile(means, [2.5, 97.5])
        return [round(float(lo), 4), round(float(hi), 4)]
    except Exception:
        return None


def _label_for(effective_n: float, ic_pvalue: Optional[float]) -> str:
    """spec §4/§9.4 N_eff 게이트. raw N 아닌 중첩보정 N_eff 기준."""
    if effective_n is None or effective_n < 30:
        return _LABEL_EARLY
    if effective_n < 270:
        return _LABEL_PRELIM
    if ic_pvalue is not None and ic_pvalue < 0.05:
        return _LABEL_SIGNIFICANT
    return _LABEL_PRELIM


# ─── trail I/O ──────────────────────────────


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
    """원자적 rewrite (scored 플래그 갱신 반영). temp → replace."""
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
    """created_at ISO → YYYY-MM-DD (base 가격 snapshot 조회용)."""
    ca = entry.get("created_at", "")
    return ca[:10] if len(ca) >= 10 else ca


# ─── 메인 채점 ──────────────────────────────


def score_predictions(
    trail_path: Optional[str] = None,
    ic_history_path: Optional[str] = None,
) -> Dict[str, Any]:
    """eval_date 도달 예측 채점 + 집계 trail append. graceful (실패해도 부분 진행)."""
    trail_path = trail_path or TRAIL_PATH
    ic_history_path = ic_history_path or IC_HISTORY_PATH

    entries = _read_trail(trail_path)
    if not entries:
        return {"scored": 0, "deferred_sector": 0, "pending": 0, "groups": 0, "note": "trail 비어있음"}

    today = now_kst().date()
    today_str = today.strftime("%Y-%m-%d")
    available = list_available_dates()

    newly_scored: List[Dict[str, Any]] = []
    deferred_sector = 0
    pending = 0
    unscoreable = 0
    delisted_scored = 0   # survivorship-free 종결 채점(상폐/소멸 손실 포착, 2026-06-15)

    for e in entries:
        if e.get("scored"):
            continue
        eval_date = e.get("eval_date")
        if not eval_date or eval_date > today_str:
            continue  # 아직 미도래 (forward)

        target_type = e.get("target_type")
        if target_type == "sector":
            deferred_sector += 1  # v0 채점 보류 (return source 미검증). scored 유지=false
            continue
        if target_type != "stock":
            continue

        ret = _realized_stock_return(
            str(e.get("target")), _created_date(e), eval_date, available
        )
        if ret is None:
            # 실현 가격 결손. grace 내 = 재시도 보류, 초과 = unscoreable 종결.
            try:
                ed = datetime.strptime(eval_date, "%Y-%m-%d").date()
            except ValueError:
                ed = today
            if (today - ed).days > GRACE_DAYS:
                # 드롭 전 survivorship-free 종결 시도 (상폐/소멸 손실 포착)
                term = _realized_terminal_return(
                    str(e.get("target")), _created_date(e), eval_date, available
                )
                if term is not None:
                    e["scored"] = True
                    e["realized_return"] = term
                    e["hit"] = _is_hit(str(e.get("direction")), term)
                    e["ic_contrib"] = e.get("pred_score")
                    e["realized_source"] = "last_available_delisting"
                    e["delisted"] = True
                    newly_scored.append(e)
                    delisted_scored += 1
                else:
                    e["scored"] = True
                    e["realized_return"] = None
                    e["hit"] = None
                    e["_skip_reason"] = "no_snapshot_within_grace"
                    unscoreable += 1
            else:
                pending += 1
            continue

        if ret == 0.0:
            # 2026-07-20 감사 P1: 정확히 0.0 = base==eval 스냅샷 미갱신(주로 미장 stale 가격) 아티팩트.
            # 이를 방향 '미스'로 계상하면 hit_rate 5~9%p 하향 왜곡 → hit/IC 모집단서 제외.
            # grace 내 = 보류(가격 갱신 시 재시도), 초과 = 종결 제외.
            try:
                ed0 = datetime.strptime(eval_date, "%Y-%m-%d").date()
            except ValueError:
                ed0 = today
            if (today - ed0).days > GRACE_DAYS:
                e["scored"] = True
                e["realized_return"] = None
                e["hit"] = None
                e["_skip_reason"] = "stale_price_zero_return"
                unscoreable += 1
            else:
                pending += 1
            continue

        hit = _is_hit(str(e.get("direction")), ret)
        e["scored"] = True
        e["realized_return"] = ret
        e["hit"] = hit
        e["ic_contrib"] = e.get("pred_score")  # 연속 score (cross-section IC 입력)
        newly_scored.append(e)

    if newly_scored or unscoreable:
        _rewrite_trail(trail_path, entries)

    # 집계: (target_type, horizon) 별 — 전체 scored stock 풀 재계산 후 snapshot append.
    # 2026-06-17 fix: 신규 채점 0건이면 aggregate 가 직전과 동일 → byte-identical 재append(무한 bloat).
    # newly_scored 있을 때만 append (값 변동 시에만 새 스냅샷). 소비처는 _latest_per_horizon last-wins.
    groups = _aggregate(entries, today)
    if groups and newly_scored:
        os.makedirs(os.path.dirname(ic_history_path), exist_ok=True)
        with open(ic_history_path, "a", encoding="utf-8") as f:
            for g in groups:
                f.write(json.dumps(g, ensure_ascii=False) + "\n")

    return {
        "scored": len(newly_scored),
        "delisted_scored": delisted_scored,
        "deferred_sector": deferred_sector,
        "pending": pending,
        "unscoreable": unscoreable,
        "groups": len(groups),
    }


def _aggregate(entries: List[Dict[str, Any]], today) -> List[Dict[str, Any]]:
    """전체 scored stock 예측을 (target_type, horizon) 별 집계 → snapshot 레코드 list."""
    scored_at = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    by_group: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    _seen_pred_ids: Dict[Tuple[str, str], set] = {}
    for e in entries:
        if not e.get("scored") or e.get("realized_return") is None:
            continue
        if e.get("target_type") != "stock":
            continue  # 섹터 채점 보류 — 집계 제외
        key = (e.get("target_type"), e.get("horizon"))
        # 2026-07-20 감사 P1: pred_id 중복(일 2~6회 run 재로깅, 최대 6중복) dedup — 동일 pred_id 1회만 집계.
        pid = e.get("pred_id")
        if pid is not None:
            seen = _seen_pred_ids.setdefault(key, set())
            if pid in seen:
                continue
            seen.add(pid)
        by_group.setdefault(key, []).append(e)

    records: List[Dict[str, Any]] = []
    for (target_type, horizon), preds in by_group.items():
        n = len(preds)
        pred_scores = [float(p.get("pred_score") or 0.0) for p in preds]
        realized = [float(p.get("realized_return")) for p in preds]

        ic = _spearman_ic(pred_scores, realized)
        k = HORIZON_OVERLAP_K.get(horizon, 1)
        # 2026-07-20 감사 P1: N_eff = 독립 시간축(distinct created 일수)/k. 기존 n(종목 횡단면×일중 중복 run)은
        # 모듈 docstring lock('breadth 는 N_eff 가산 않음') 위반 → t-stat 74× 과대. IC 점추정엔 pooled n 유지.
        distinct_days = len({str(p.get("created_at", ""))[:10] for p in preds}) or 1
        effective_n = max(1.0, distinct_days / k)  # N_eff = T/k (v0 lock)
        ic_tstat, ic_pvalue = _ic_tstat_pvalue(ic, effective_n)

        # 방향 hit (up/down 만)
        dir_outcomes = [(p, _is_hit(str(p.get("direction")), float(p.get("realized_return"))))
                        for p in preds]
        dir_outcomes = [(p, h) for p, h in dir_outcomes if h is not None]
        n_dir = len(dir_outcomes)
        hits = sum(1 for _, h in dir_outcomes if h)
        hit_rate = round(hits / n_dir, 4) if n_dir else None
        hit_pvalue = _binom_pvalue(hits, n_dir) if n_dir else None

        # Brier — confidence vs 실현 outcome (방향 모집단). (1/N)Σ(conf - o)²
        brier = None
        if n_dir:
            brier = round(
                sum((float(p.get("confidence") or 0.5) - (1.0 if h else 0.0)) ** 2
                    for p, h in dir_outcomes) / n_dir, 4
            )

        expectancy = round(sum(realized) / n, 4) if n else None
        ci95 = _bootstrap_ci95(realized)
        label = _label_for(effective_n, ic_pvalue)

        records.append({
            "scored_at": scored_at,
            "horizon": horizon,
            "target_type": target_type,
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
            "spec_version": "v0",
            "_method": "cross-section Spearman IC, N_eff=T/k(overlap), 비중첩 보수. stock only(sector deferred).",
        })
    return records
