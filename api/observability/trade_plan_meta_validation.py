"""
trade_plan v0_log 메타-검증 — 진입 후보들의 사후 결과를 분해 통계로 산출.

설계 원칙 (memory: feedback_metavalidation_decompose):
- 종합값 단일 신뢰 금지. 호라이즌별/피처별/섹터별/verdict 강도별 분해.
- 시간차 baseline: 첫 30일 누적 vs 30일 후 vs 60일 후 (drift 측정용).

산출 대상:
  - sample_size                           : 누적 row 수, open/closed 분리
  - horizon_summary[h5/h14/h30]           : hit_rate, median_return, IC
  - feature_decomposition                  : RSI/MACD/거래량/foreign_5d 4분위 → 평균 수익
  - sector_breakdown                       : 섹터별 hit_rate · median return
  - verdict_strength                       : multi_score 4분위 → 평균 수익 (verdict 단독 baseline)
  - timeseries_baseline                    : 첫 30일 / 30~60일 / 60일+ 윈도별 hit_rate (drift)
  - active_vs_inactive                     : entry_active=True (3조건 충족) row vs 단순 BUY 전체 비교

저장: data/metadata/trade_plan_meta.json (atomic write).
portfolio["trade_plan_meta"] 로 부착 → 일일 리포트 / AdminDashboard 가 읽음.

데이터 부족 시 (예: 첫 30일 누적 전):
  status="insufficient_data"  + need_more_rows / need_more_days 표시.
  운영 시작 후 자연스레 채워짐. 임의 placeholder X.
"""
from __future__ import annotations

import json
import logging
import math
import os
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 위치 — DATA_DIR 의 metadata 하위. trust_score.py 와 동일 패턴.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_HERE, "..", ".."))
_LOG_PATH = os.path.join(_REPO_ROOT, "data", "metadata", "trade_plan_v0_log.jsonl")
_META_PATH = os.path.join(_REPO_ROOT, "data", "metadata", "trade_plan_meta.json")

# 의미있는 통계가 시작되는 임계 — 30 row 이전엔 분해 통계 신뢰 X.
MIN_ROWS_FOR_DECOMPOSE = 30
MIN_ROWS_PER_BUCKET = 5
HIT_THRESHOLD_PCT = 0.0   # return_pct > 0 → hit (단순 양수 기준 v0)


def _load_log(path: str = _LOG_PATH) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception as e:  # noqa: BLE001
        logger.warning("trade_plan meta: log read failed: %s", e)
        return []
    return rows


def _safe_pct(num: int, den: int) -> Optional[float]:
    if den <= 0:
        return None
    return round(num / den * 100.0, 2)


def _quartile_buckets(values: List[float]) -> List[float]:
    """v 의 25/50/75 분위수 boundary."""
    if len(values) < 4:
        return []
    sv = sorted(values)
    n = len(sv)
    return [sv[n // 4], sv[n // 2], sv[(3 * n) // 4]]


def _bucket_index(v: float, boundaries: List[float]) -> int:
    """v 가 몇 번째 4분위 (0~3) 에 속하는지."""
    for i, b in enumerate(boundaries):
        if v <= b:
            return i
    return len(boundaries)


def _horizon_stats(rows: List[Dict[str, Any]], h: int) -> Dict[str, Any]:
    """h5/h14/h30 별 hit rate · median return · IC (snapshot multi_score → return rank corr)."""
    key = f"h{h}"
    completed = [r for r in rows if (r.get("followups") or {}).get(key)]
    if not completed:
        return {"horizon_days": h, "n": 0, "hit_rate_pct": None, "median_return_pct": None, "ic": None}
    returns = [float(r["followups"][key]["return_pct"]) for r in completed]
    hits = sum(1 for x in returns if x > HIT_THRESHOLD_PCT)
    multi_scores = [(r.get("snapshot") or {}).get("multi_score") for r in completed]
    return {
        "horizon_days": h,
        "n": len(completed),
        "hit_rate_pct": _safe_pct(hits, len(completed)),
        "median_return_pct": round(statistics.median(returns), 2),
        "mean_return_pct": round(statistics.mean(returns), 2),
        "ic": _spearman_ic(multi_scores, returns),
    }


def _spearman_ic(xs: List[Optional[float]], ys: List[float]) -> Optional[float]:
    """간이 Spearman rank correlation. NaN/None 페어 제외. n<5 면 None."""
    pairs = [(float(x), float(y)) for x, y in zip(xs, ys) if x is not None and y is not None and not math.isnan(float(x))]
    if len(pairs) < 5:
        return None
    xs_sorted = sorted(pairs, key=lambda p: p[0])
    ys_sorted = sorted(pairs, key=lambda p: p[1])
    rank_x = {id(p): i for i, p in enumerate(xs_sorted)}
    rank_y = {id(p): i for i, p in enumerate(ys_sorted)}
    n = len(pairs)
    d2 = sum((rank_x[id(p)] - rank_y[id(p)]) ** 2 for p in pairs)
    return round(1 - (6 * d2) / (n * (n * n - 1)), 3)


def _feature_decomposition(rows_h: List[Dict[str, Any]], horizon: str) -> Dict[str, Any]:
    """
    피처별 4분위 marginal contribution. row 의 snapshot 에서 RSI/MACD_hist/vol_ratio/foreign_5d 각각
    분위별 평균 수익률 산출. 결정 룰엔 안 들어갔어도 사후 회귀 가능 (memory: 단순 결정 + 풍부 로깅).
    """
    if len(rows_h) < MIN_ROWS_FOR_DECOMPOSE:
        return {"status": "insufficient_data", "n": len(rows_h), "need_more_rows": MIN_ROWS_FOR_DECOMPOSE - len(rows_h)}

    features = ["rsi", "macd_hist", "vol_ratio", "foreign_5d_sum", "technical_score", "safety_score", "flow_score"]
    out: Dict[str, Any] = {}
    for f in features:
        vals = [(r.get("snapshot") or {}).get(f) for r in rows_h]
        rets = [float(r["followups"][horizon]["return_pct"]) for r in rows_h]
        pairs = [(float(v), r) for v, r in zip(vals, rets) if v is not None]
        if len(pairs) < MIN_ROWS_FOR_DECOMPOSE:
            out[f] = {"status": "insufficient_data", "n": len(pairs)}
            continue
        bounds = _quartile_buckets([p[0] for p in pairs])
        if not bounds:
            out[f] = {"status": "insufficient_data", "n": len(pairs)}
            continue
        buckets: List[List[float]] = [[], [], [], []]
        for v, r in pairs:
            buckets[_bucket_index(v, bounds)].append(r)
        out[f] = {
            "n": len(pairs),
            "boundaries": [round(b, 2) for b in bounds],
            "quartile_mean_return_pct": [
                {"q": i, "n": len(b), "mean_return_pct": round(statistics.mean(b), 2) if len(b) >= MIN_ROWS_PER_BUCKET else None}
                for i, b in enumerate(buckets)
            ],
        }
    return out


def _sector_breakdown(rows_h: List[Dict[str, Any]], horizon: str) -> Dict[str, Any]:
    by_sector: Dict[str, List[float]] = {}
    for r in rows_h:
        sec = (r.get("snapshot") or {}).get("sector") or "기타"
        by_sector.setdefault(str(sec), []).append(float(r["followups"][horizon]["return_pct"]))
    out: Dict[str, Any] = {}
    for sec, rets in by_sector.items():
        if len(rets) < MIN_ROWS_PER_BUCKET:
            out[sec] = {"n": len(rets), "status": "insufficient_data"}
            continue
        hits = sum(1 for x in rets if x > HIT_THRESHOLD_PCT)
        out[sec] = {
            "n": len(rets),
            "hit_rate_pct": _safe_pct(hits, len(rets)),
            "median_return_pct": round(statistics.median(rets), 2),
        }
    return out


def _timeseries_baseline(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """첫 30일 누적 / 30~60일 / 60일+ 윈도별 h14 hit rate (drift 측정).

    horizon=14 기준 — h30 까지 기다리면 윈도 너무 좁아져서 baseline 의미 약해짐.
    """
    if len(rows) < 5:
        return {"status": "insufficient_data", "n": len(rows)}

    parsed = []
    for r in rows:
        try:
            t = datetime.fromisoformat(r["suggested_at"].replace("Z", "+00:00"))
            parsed.append((t, r))
        except Exception:
            continue
    if not parsed:
        return {"status": "no_parseable_dates", "n": 0}
    parsed.sort(key=lambda p: p[0])
    earliest = parsed[0][0]

    windows = {"first_30d": (0, 30), "30_60d": (30, 60), "60d_plus": (60, 9999)}
    out: Dict[str, Any] = {"earliest": earliest.isoformat(), "windows": {}}
    for label, (lo, hi) in windows.items():
        bucket: List[float] = []
        for t, r in parsed:
            days_since_earliest = (t - earliest).total_seconds() / 86400.0
            if not (lo <= days_since_earliest < hi):
                continue
            f = (r.get("followups") or {}).get("h14")
            if f and f.get("return_pct") is not None:
                bucket.append(float(f["return_pct"]))
        if not bucket:
            out["windows"][label] = {"n": 0, "hit_rate_pct": None, "median_return_pct": None}
            continue
        hits = sum(1 for x in bucket if x > HIT_THRESHOLD_PCT)
        out["windows"][label] = {
            "n": len(bucket),
            "hit_rate_pct": _safe_pct(hits, len(bucket)),
            "median_return_pct": round(statistics.median(bucket), 2),
        }
    return out


def _verdict_strength_breakdown(rows_h: List[Dict[str, Any]], horizon: str) -> Dict[str, Any]:
    """multi_score 4분위 → return. verdict 단독 baseline (trade_plan 활성화의 incremental value 측정용)."""
    pairs = [
        (float((r.get("snapshot") or {}).get("multi_score") or 0), float(r["followups"][horizon]["return_pct"]))
        for r in rows_h
        if (r.get("snapshot") or {}).get("multi_score") is not None
    ]
    if len(pairs) < MIN_ROWS_FOR_DECOMPOSE:
        return {"status": "insufficient_data", "n": len(pairs)}
    bounds = _quartile_buckets([p[0] for p in pairs])
    if not bounds:
        return {"status": "insufficient_data", "n": len(pairs)}
    buckets: List[List[float]] = [[], [], [], []]
    for v, r in pairs:
        buckets[_bucket_index(v, bounds)].append(r)
    return {
        "n": len(pairs),
        "multi_score_boundaries": [round(b, 1) for b in bounds],
        "quartile_mean_return_pct": [
            {"q": i, "n": len(b), "mean_return_pct": round(statistics.mean(b), 2) if len(b) >= MIN_ROWS_PER_BUCKET else None}
            for i, b in enumerate(buckets)
        ],
    }


def summarize(log_path: str = _LOG_PATH) -> Dict[str, Any]:
    """trade_plan_v0_log.jsonl 전체에서 분해 통계 산출."""
    rows = _load_log(log_path)
    n_total = len(rows)
    n_open = sum(1 for r in rows if not r.get("closed_at"))
    n_closed = n_total - n_open

    if n_total == 0:
        return {
            "version": "v0",
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "status": "empty",
            "sample_size": {"total": 0, "open": 0, "closed": 0},
            "note": "운영 시작 전 — 진입 후보 누적 대기",
        }

    horizons = {f"h{h}": _horizon_stats(rows, h) for h in (5, 14, 30)}

    rows_h14 = [r for r in rows if (r.get("followups") or {}).get("h14")]
    rows_h30 = [r for r in rows if (r.get("followups") or {}).get("h30")]
    primary_rows = rows_h14 if rows_h14 else rows_h30

    decomposition = _feature_decomposition(primary_rows, "h14") if primary_rows else {"status": "insufficient_data", "n": 0}
    sector = _sector_breakdown(primary_rows, "h14") if primary_rows else {}
    verdict_strength = _verdict_strength_breakdown(primary_rows, "h14") if primary_rows else {"status": "insufficient_data", "n": 0}
    timeseries = _timeseries_baseline(rows)

    overall_status = (
        "insufficient_data"
        if n_total < MIN_ROWS_FOR_DECOMPOSE
        else "active"
    )

    return {
        "version": "v0",
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "status": overall_status,
        "sample_size": {
            "total": n_total,
            "open": n_open,
            "closed": n_closed,
            "with_h5": sum(1 for r in rows if (r.get("followups") or {}).get("h5")),
            "with_h14": len(rows_h14),
            "with_h30": len(rows_h30),
            "min_for_decompose": MIN_ROWS_FOR_DECOMPOSE,
        },
        "horizon_summary": horizons,
        "feature_decomposition": decomposition,
        "sector_breakdown": sector,
        "verdict_strength": verdict_strength,
        "timeseries_baseline": timeseries,
        "policy_note": (
            "종합값 단일 신뢰 금지. horizon/feature/sector 분해 + 시간차 baseline 동시 참조. "
            f"{MIN_ROWS_FOR_DECOMPOSE} row 미만은 분해 통계 'insufficient_data'."
        ),
    }


def persist(meta: Dict[str, Any], path: str = _META_PATH) -> str:
    """atomic write — tmp 후 replace."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return path


def summarize_and_attach(portfolio: Dict[str, Any], log_path: str = _LOG_PATH) -> Dict[str, Any]:
    """portfolio["trade_plan_meta"] 부착 + data/metadata/trade_plan_meta.json 영속화."""
    meta = summarize(log_path)
    portfolio["trade_plan_meta"] = meta
    try:
        persist(meta)
    except Exception as e:  # noqa: BLE001
        logger.warning("trade_plan_meta persist failed: %s", e)
    return meta
