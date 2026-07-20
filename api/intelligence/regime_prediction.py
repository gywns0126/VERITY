"""
regime_prediction.py — 국면(regime) forward 예측 로깅 + 시계열 채점.

2026-06-13 신설. 사전등록 spec docs/regime_validation_spec_v0_2026_06_13.md 정합.

동기 (갭):
  verity_brain.py 의 macro_override(panic cap / contrarian_upgrade / cboe / cycle_stage ~35게이트)와
  market_horizon.cycle_stage 가 종목 grade 를 cap/flip 하나, 그 *국면 신호 자체*의 forward
  시장 예측력이 어느 trail 에서도 채점 0. ML shadow trail(commit b1791fc92) 패턴을 미러:
  관측-only forward trail 신설 + 별도 trail 파일(물리 분리) + source 태그 + 사전등록 spec + 테스트.

관측 only (RULE 7): 채점 결과는 macro_override/cycle_stage 결정에 피드백 0. N 누적 후
  "국면 신호가 forward 시장 수익률을 예측하나" 판정 자료로만. 소급 불가 → 지금 로깅 시작이 핵심.

regime = 시장레벨 단일값/run → cross-section prediction_scoring(prediction_trail.log_prediction,
  종목 횡단면 rank-IC) 미적합. 자체 schema 로 직접 기록하고, 시계열 검증은 ic_stats.py 의
  Newey-West t (중첩 horizon 자기상관 보정) 재사용. 신규 산식 0.

매핑 (사전등록, spec §3 — 전부 *재량* 결정. PM 승인 플래그. discretionary):
  (a) target 지수 = KOSPI (market_summary.kospi.value) primary + S&P500(macro.sp500.value) 동시 로깅
      — 채점은 둘 다 산출하되 primary=KOSPI(시스템 home market). 재량.
  (b) horizon = short/mid/long (prediction_trail.HORIZON_DAYS 재사용: 7/90/365 캘린더일). 재량.
  (c) regime→방향 매핑 (강제값, 곡선맞추기 surface 0 — max_grade 심각도/cycle_stage 자연순서 기반):
      · macro_override.max_grade ∈ {AVOID,CAUTION,WATCH} → 방어 국면 → 시장 하락 예측 'down'
        (단 contrarian_upgrade=True 인 패닉 stage 3/4 = 역발상 매수 → 'up')
      · max_grade ∈ {BUY,STRONG_BUY} (euphoria/과열 cap) → 'down' (과열=평균회귀 하락 가설)
      · macro_override 부재 + cycle_stage ∈ {early_bull,mid_bull} → 'up'
      · cycle_stage == 'euphoria' → 'down' (과열) / 'bear' → 'down' / 'late_bull' → 'neutral'
      · 그 외/unknown → 'neutral'
      재량성: 위 매핑은 *방향 라벨*일 뿐 가중치 자유 파라미터 0. 매핑 자체가 가설 → PM 승인.

graceful: 입력 결손(snapshot/index 가격/regime 필드 없음) 시 예외 없이 skip.
"""
from __future__ import annotations

import json
import os
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from api.config import DATA_DIR, now_kst
from api.metadata import prediction_trail as PT

# regime forward trail (물리 분리). prediction_scoring(production/shadow/ML) 무오염.
REGIME_PATH = PT.REGIME_PATH
# 시계열 채점 산출물 (regime 신호의 forward 시장 IC 시계열 집계)
REGIME_IC_HISTORY_PATH = os.path.join(DATA_DIR, "regime_prediction_ic_history.jsonl")

REGIME_SOURCE = "regime_macro_override.v0"

# horizon → eval 캘린더일 (prediction_trail SoT 재사용 — 신규 산식 0)
HORIZON_DAYS = PT.HORIZON_DAYS  # {"short":7,"mid":90,"long":365}
_HORIZONS = tuple(HORIZON_DAYS)

# 채점 시 horizon 중첩 길이(거래일) — prediction_scoring 의 N_eff=T/k lock 정합 (시계열 NW maxlags 입력)
HORIZON_OVERLAP_K = {"short": 5, "mid": 63, "long": 252}

# 실현 가격 snapshot 미존재 시 재시도 한계 (prediction_scoring.GRACE_DAYS 정합)
GRACE_DAYS = 14

# target 지수 → snapshot 내 절대 레벨(value) 경로 (PIT 가격). primary=kospi (spec §3a 재량).
_INDEX_PATHS = {
    "kospi": ("market_summary", "kospi"),
    "sp500": ("macro", "sp500"),
}
_PRIMARY_INDEX = "kospi"

GRADE_SEVERITY = {"AVOID": 5, "CAUTION": 4, "WATCH": 3, "BUY": 2, "STRONG_BUY": 1}
_DEFENSIVE = {"AVOID", "CAUTION", "WATCH"}
_OVERHEAT_CAP = {"BUY", "STRONG_BUY"}


# ── 1. regime → forward 방향 매핑 (spec §3c 강제값) ────────────────────────


def regime_direction(macro_override: Optional[Dict[str, Any]], cycle_stage: Optional[str]) -> str:
    """국면 신호 → forward 시장 방향 라벨 (강제값, 자유 파라미터 0).

    우선순위: macro_override(있으면) → cycle_stage. spec §3c.
    """
    if isinstance(macro_override, dict) and macro_override.get("mode"):
        # 패닉 역발상(contrarian_upgrade) = 바닥 매수 가설 → 시장 반등 'up'
        if macro_override.get("contrarian_upgrade"):
            return "up"
        max_grade = str(macro_override.get("max_grade", "")).upper()
        if max_grade in _DEFENSIVE:
            return "down"   # 방어 cap = 하락 위험 국면
        if max_grade in _OVERHEAT_CAP:
            return "down"   # 과열(euphoria/greed) cap = 평균회귀 하락 가설
        return "neutral"
    cs = str(cycle_stage or "").lower()
    if cs in ("early_bull", "mid_bull"):
        return "up"
    if cs in ("euphoria", "bear"):
        return "down"
    if cs == "late_bull":
        return "neutral"
    return "neutral"


def _confidence(macro_override: Optional[Dict[str, Any]], cycle_stage: Optional[str]) -> float:
    """방향 콜 신뢰(Brier 입력). max_grade 심각도/cycle 강도 기반 강제값 (0.5~0.7)."""
    if isinstance(macro_override, dict) and macro_override.get("mode"):
        sev = GRADE_SEVERITY.get(str(macro_override.get("max_grade", "")).upper(), 2)
        # 심각도 1~5 → 0.5~0.7 선형 (자유 파라미터 0, 단조)
        return round(0.5 + (sev - 1) / 4.0 * 0.2, 4)
    cs = str(cycle_stage or "").lower()
    if cs in ("euphoria", "bear"):
        return 0.6
    if cs in ("early_bull", "mid_bull"):
        return 0.55
    return 0.5


# ── 2. 신호 강도 점수 (시계열 IC 입력 연속값, spec §4) ──────────────────────


def regime_signal_score(macro_override: Optional[Dict[str, Any]], cycle_stage: Optional[str]) -> float:
    """국면 신호 → 연속 강도 점수 (signed). 시계열 IC: corr(score, forward_return).

    방어 신호 = 음(하락 예측), 강세 = 양. 부호는 regime_direction 과 정합 (강제값).
    macro_override 우선(심각도 부호화) → cycle_stage. 자유 파라미터 0.
    """
    if isinstance(macro_override, dict) and macro_override.get("mode"):
        if macro_override.get("contrarian_upgrade"):
            return 1.0   # 역발상 = 강세
        max_grade = str(macro_override.get("max_grade", "")).upper()
        sev = GRADE_SEVERITY.get(max_grade, 2)
        if max_grade in _DEFENSIVE:
            return -float(sev)            # 심각도 클수록 강한 하락 예측 (-3 ~ -5)
        if max_grade in _OVERHEAT_CAP:
            return -float(6 - sev)        # 과열 cap = 약한 하락 예측 (-1=STRONG_BUY ~ -2=BUY 절대값 작게)
        return 0.0
    cs = str(cycle_stage or "").lower()
    return {"early_bull": 2.0, "mid_bull": 1.0, "late_bull": 0.0,
            "euphoria": -2.0, "bear": -3.0}.get(cs, 0.0)


# ── 3. forward 로깅 (append-only, forward-only) ─────────────────────────────


def log_regime_prediction(
    macro_override: Optional[Dict[str, Any]],
    cycle_stage: Optional[str],
    index_levels: Dict[str, Optional[float]],
    extra_signals: Optional[Dict[str, Any]] = None,
    path: Optional[str] = None,
    spec_version: str = "regime.v0",
) -> List[Dict[str, Any]]:
    """국면 상태 1벌(=horizon 3개) forward 로깅. macro_override/cycle_stage 부재 시 빈 list.

    index_levels = {"kospi": float|None, "sp500": float|None} — created 시점 동결(PIT).
    horizon 별 1줄 (eval_date 만 상이). 시장레벨 단일 신호 → run 당 3줄(short/mid/long).
    실패해도 caller 진행 (예측 = 부수효과).
    """
    has_override = isinstance(macro_override, dict) and macro_override.get("mode")
    cs = str(cycle_stage or "").lower()
    if not has_override and cs in ("", "unknown", "none"):
        return []  # 국면 신호 전무 = skip (graceful, 의미없는 neutral 누적 방지)

    target_path = path or REGIME_PATH
    direction = regime_direction(macro_override, cycle_stage)
    confidence = _confidence(macro_override, cycle_stage)
    sig_score = regime_signal_score(macro_override, cycle_stage)

    now = now_kst()
    created_iso = now.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    mode = (macro_override or {}).get("mode") if has_override else f"cycle_{cs}"

    signals = {
        "macro_override_mode": (macro_override or {}).get("mode") if has_override else None,
        "max_grade": (macro_override or {}).get("max_grade") if has_override else None,
        "contrarian_upgrade": bool((macro_override or {}).get("contrarian_upgrade")) if has_override else False,
        "secondary_modes": [s.get("mode") for s in ((macro_override or {}).get("secondary_signals") or [])]
        if has_override else [],
        "cycle_stage": cycle_stage,
        "index_levels": {k: (round(float(v), 4) if v is not None else None) for k, v in index_levels.items()},
        "source": REGIME_SOURCE,
    }
    if extra_signals:
        signals.update(extra_signals)

    out: List[Dict[str, Any]] = []
    rows: List[Dict[str, Any]] = []
    for h in _HORIZONS:
        eval_dt = now + timedelta(days=HORIZON_DAYS[h])
        eval_date = eval_dt.strftime("%Y-%m-%d")
        pid = f"{now.strftime('%Y%m%d')}-regime-{h}"
        rows.append({
            "pred_id": pid,
            "created_at": created_iso,
            "spec_version": spec_version,
            "source": REGIME_SOURCE,
            "target_type": "market",          # 시장레벨 (sector/stock 아님 — 별 schema)
            "target": _PRIMARY_INDEX,         # primary 지수 (채점은 index_levels 전부 산출)
            "horizon": h,
            "eval_date": eval_date,           # created < eval = forward-only
            "regime_mode": mode,
            "direction": direction,
            "signal_score": round(float(sig_score), 4),   # 시계열 IC 입력 연속값(signed)
            "confidence": round(float(confidence), 4),
            "signals": signals,
            # 채점 cron 산출 (eval_date 도달 시):
            "scored": False,
            "realized_return": None,          # primary 지수 forward 수익률(%)
            "realized_return_by_index": None,  # {kospi:.., sp500:..}
            "hit": None,
        })

    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    with open(target_path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            out.append(r)
    return out


# ── 4. 채점: 실현 시장 수익률 (실제 — 순환 antidote) ────────────────────────


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
    import tempfile
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


def _index_level_from_snapshot(snap: Dict[str, Any], index: str) -> Optional[float]:
    """snapshot 에서 지수 절대 레벨 추출. _INDEX_PATHS 경로 (graceful None)."""
    pth = _INDEX_PATHS.get(index)
    if not pth:
        return None
    node: Any = snap
    for k in pth:
        if not isinstance(node, dict):
            return None
        node = node.get(k)
    if not isinstance(node, dict):
        return None
    v = node.get("value")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _realized_index_return(
    index: str, base_level: Optional[float], eval_date: str,
    available: List[str], load_snapshot, find_nearest,
) -> Optional[float]:
    """base_level(created 시점 동결) → eval_date 최근접 snapshot 레벨 수익률(%).

    base = trail 에 동결된 PIT 레벨 (look-ahead 차단), eval = 실현 snapshot.
    어느 한쪽 결손 → None (호출부 grace 처리).
    """
    if base_level is None or base_level <= 0:
        return None
    eval_snap_date = find_nearest(eval_date, available)
    if not eval_snap_date:
        return None
    eval_snap = load_snapshot(eval_snap_date)
    if not eval_snap:
        return None
    eval_level = _index_level_from_snapshot(eval_snap, index)
    if eval_level is None or eval_level <= 0:
        return None
    return round((eval_level - base_level) / base_level * 100.0, 4)


def _is_hit(direction: str, realized_return: float) -> Optional[bool]:
    """방향 적중 (neutral = 콜 부재 → hit 모집단 제외 None). prediction_scoring 정합."""
    if direction == "up":
        return realized_return > 0
    if direction == "down":
        return realized_return < 0
    return None


def score_regime_predictions(
    trail_path: Optional[str] = None,
    ic_history_path: Optional[str] = None,
) -> Dict[str, Any]:
    """eval_date 도달 regime 예측 채점 + 시계열 IC 집계. graceful (실패해도 부분 진행).

    시계열 방식 (spec §4): horizon 별로 (signal_score, primary 실현수익률) 시리즈를 모아
    ic_stats.newey_west_tstat 으로 중첩 자기상관 보정 t. cross-section 아님 → prediction_scoring 미사용.
    """
    trail_path = trail_path or REGIME_PATH
    ic_history_path = ic_history_path or REGIME_IC_HISTORY_PATH

    entries = _read_trail(trail_path)
    if not entries:
        return {"scored": 0, "pending": 0, "unscoreable": 0, "groups": 0, "note": "trail 비어있음"}

    # lazy import (라이트 run / 테스트 격리 — archiver 미가용 시 graceful)
    try:
        from api.workflows.archiver import list_available_dates, load_snapshot
        from api.intelligence.backtest_archive import _find_nearest_snapshot as find_nearest
    except Exception as e:  # noqa: BLE001
        return {"scored": 0, "pending": 0, "unscoreable": 0, "groups": 0,
                "note": f"archiver 미가용 (graceful): {type(e).__name__}"}

    from datetime import datetime as _dt
    today = now_kst().date()
    today_str = today.strftime("%Y-%m-%d")
    available = list_available_dates()

    newly_scored = 0
    pending = 0
    unscoreable = 0

    for e in entries:
        if e.get("scored"):
            continue
        eval_date = e.get("eval_date")
        if not eval_date or eval_date > today_str:
            continue  # forward 미도래
        if e.get("target_type") != "market":
            continue

        idx_levels = (e.get("signals") or {}).get("index_levels") or {}
        by_index: Dict[str, Optional[float]] = {}
        for idx in _INDEX_PATHS:
            base = idx_levels.get(idx)
            by_index[idx] = _realized_index_return(
                idx, base, eval_date, available, load_snapshot, find_nearest
            )
        primary_ret = by_index.get(_PRIMARY_INDEX)

        if primary_ret is None:
            # 실현 결손. grace 내 = 재시도, 초과 = unscoreable 종결.
            try:
                ed = _dt.strptime(eval_date, "%Y-%m-%d").date()
            except ValueError:
                ed = today
            if (today - ed).days > GRACE_DAYS:
                e["scored"] = True
                e["realized_return"] = None
                e["realized_return_by_index"] = by_index
                e["hit"] = None
                e["_skip_reason"] = "no_snapshot_within_grace"
                unscoreable += 1
            else:
                pending += 1
            continue

        e["scored"] = True
        e["realized_return"] = primary_ret
        e["realized_return_by_index"] = by_index
        e["hit"] = _is_hit(str(e.get("direction")), primary_ret)
        newly_scored += 1

    if newly_scored or unscoreable:
        _rewrite_trail(trail_path, entries)

    groups = _aggregate_timeseries(entries)
    # 2026-07-20 감사 P1: 신규 채점 0 이어도 매 run 집계 재append 되던 결함(byte-identical 중복) —
    # 형제 scorer 와 동일 가드(newly_scored 있을 때만 append). 6/17 newly_scored 가드 수정서 누락됐던 라인.
    if groups and newly_scored:
        os.makedirs(os.path.dirname(ic_history_path), exist_ok=True)
        with open(ic_history_path, "a", encoding="utf-8") as f:
            for g in groups:
                f.write(json.dumps(g, ensure_ascii=False) + "\n")

    return {
        "scored": newly_scored,
        "pending": pending,
        "unscoreable": unscoreable,
        "groups": len(groups),
    }


def _aggregate_timeseries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """horizon 별 scored 시리즈 → ic_stats Newey-West 시계열 IC 집계 (spec §4).

    시리즈: x=signal_score(국면 신호 강도), y=primary 실현수익률. 각 run = 1 관측.
    per-run IC 가 아닌 *시계열 corr* — Pearson(signal_score, return) + NW-t(중첩 보정).
    N<3 = 무의미 라벨. 신규 산식 0 (ic_stats 재사용).
    """
    from datetime import datetime as _dt
    scored_at = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")

    try:
        import numpy as np
        from scipy import stats as _sp
    except Exception:  # noqa: BLE001
        return []

    from api.intelligence import ic_stats

    by_h: Dict[str, List[Dict[str, Any]]] = {}
    for e in entries:
        if not e.get("scored") or e.get("realized_return") is None:
            continue
        if e.get("target_type") != "market":
            continue
        by_h.setdefault(str(e.get("horizon")), []).append(e)

    records: List[Dict[str, Any]] = []
    for horizon, preds in by_h.items():
        preds = sorted(preds, key=lambda p: str(p.get("created_at", "")))
        scores = [float(p.get("signal_score") or 0.0) for p in preds]
        rets = [float(p.get("realized_return")) for p in preds]
        n = len(preds)

        # 시계열 corr (signal_score ↔ forward return). N<3 또는 분산0 = None.
        ts_ic: Optional[float] = None
        ts_p: Optional[float] = None
        if n >= 3 and np.ptp(scores) > 0 and np.ptp(rets) > 0:
            try:
                rho, pv = _sp.spearmanr(scores, rets)
                if rho is not None and np.isfinite(rho):
                    ts_ic = round(float(rho), 4)
                    ts_p = round(float(pv), 4) if pv is not None and np.isfinite(pv) else None
            except Exception:  # noqa: BLE001
                pass

        # 방향 hit (up/down 만)
        dir_outcomes = [_is_hit(str(p.get("direction")), float(p.get("realized_return"))) for p in preds]
        dir_outcomes = [h for h in dir_outcomes if h is not None]
        n_dir = len(dir_outcomes)
        hits = sum(1 for h in dir_outcomes if h)
        hit_rate = round(hits / n_dir, 4) if n_dir else None

        # Brier (confidence vs outcome, 방향 모집단)
        brier = None
        if n_dir:
            pairs = [(float(p.get("confidence") or 0.5),
                      _is_hit(str(p.get("direction")), float(p.get("realized_return"))))
                     for p in preds]
            pairs = [(c, h) for c, h in pairs if h is not None]
            if pairs:
                brier = round(sum((c - (1.0 if h else 0.0)) ** 2 for c, h in pairs) / len(pairs), 4)

        # Newey-West 시계열 t — IC 시리즈 대신, per-run 기여(signal_score*sign(return)) 시계열로
        # 평균≠0 검정. 중첩 horizon 자기상관 보정 (ic_stats 재사용, 신규 산식 0).
        k = HORIZON_OVERLAP_K.get(horizon, 1)
        # 기여 시리즈 = signal_score 와 return 의 동부호 여부(+1/-1)*|간이 IC contribution|.
        # signed 강도 정합: z = sign(signal_score) * return (국면이 옳으면 +). NW(z) 검정.
        contrib = [
            (1.0 if s > 0 else -1.0 if s < 0 else 0.0) * r
            for s, r in zip(scores, rets)
        ]
        nw = ic_stats.newey_west_tstat(contrib, horizon_days=k)
        expectancy = round(sum(rets) / n, 4) if n else None

        # 라벨 (prediction_scoring N_eff 게이트 정신: 중첩보정). 시계열은 N/k.
        effective_n = max(1.0, n / k)
        if effective_n < 30:
            label = "Trail 누적 초기"
        elif effective_n < 270:
            label = "예비"
        elif nw.get("nw_tstat") is not None and abs(nw["nw_tstat"]) > 1.96:
            label = "유의"
        else:
            label = "예비"

        records.append({
            "scored_at": scored_at,
            "horizon": horizon,
            "target_type": "market",
            "primary_index": _PRIMARY_INDEX,
            "n": n,
            "effective_n": round(effective_n, 2),
            "overlap_k": k,
            "ts_ic_spearman": ts_ic,
            "ts_ic_pvalue": ts_p,
            "nw_tstat": (round(nw["nw_tstat"], 4) if nw.get("nw_tstat") is not None else None),
            "nw_maxlags": nw.get("maxlags"),
            "hit_rate": hit_rate,
            "hit_n": n_dir,
            "brier_score": brier,
            "expectancy": expectancy,
            "label": label,
            "spec_version": "regime.v0",
            "_method": ("시계열 Spearman(signal_score↔fwd_return) + NW-t(sign-contrib, 중첩보정). "
                        "market-level 단일값 → cross-section 미적용. 관측 only(RULE 7)."),
        })
    return records


def run_regime_layer(portfolio: Dict[str, Any], path: Optional[str] = None) -> Dict[str, int]:
    """daily hook 진입점. portfolio(또는 snapshot)에서 regime 상태 추출 → forward 로깅.

    portfolio 필요 필드 (둘 다 결손 가능 — graceful):
      - verity_brain.macro_override (또는 top-level macro_override)
      - market_horizon.cycle_stage
      - market_summary.kospi.value / macro.sp500.value (PIT 동결 레벨)
    """
    vb = portfolio.get("verity_brain") or {}
    macro_override = vb.get("macro_override")
    if macro_override is None:
        macro_override = portfolio.get("macro_override")  # 직접 노출된 경우
    cycle_stage = (portfolio.get("market_horizon") or {}).get("cycle_stage")

    index_levels = {idx: _index_level_from_snapshot(portfolio, idx) for idx in _INDEX_PATHS}

    rows = log_regime_prediction(macro_override, cycle_stage, index_levels, path=path)
    return {"regime_predictions": len(rows)}
