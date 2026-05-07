"""
estate_backtest_v0.py — ESTATE LANDEX 백테스트 v0 (P1 셸 — schema/평가 동결, 실 fetch X)

memory `project_estate_backtest_methodology` (2026-04-30 합의) 정합:
    - 산식·가중치 v1.2 (D=26주/±2.0%p, balanced)
    - lookback 8년 권장, 현실 = 2020-01 ~ 2026-05 (~6년)
    - multi-horizon 라벨: T+13주 / T+26주 / T+52주
    - 1차 평가: Mean IC + IC IR + Monotonicity (Q1→Q5 단조)
    - 2차: Quintile Spread (5분위, 25구 → 분위당 5구)
    - 3차: Hit Rate (월별 IC > 0 비율)
    - 4차 (8년+): t-통계량 (보류)
    - methodology version filter (1.0/1.1/1.2 섞임 방지)

P1 (셸): mock dry-run / DI / metric 산식 동결
P2 (이 commit): --with-fetch 플래그 — vapi.landex 로더 + 실 fn 주입 박음 (실행은 cron/dispatch)
P3 (다음): 보고서 산출 + 시각화

거짓말 트랩:
    T1·T9   fabricate·silent X — 실 fetch 실패는 명시 로그 + 빈 셀
    T4      산식 임의 상수 X — IC/Monotonicity 산식 docstring 출처 명시
    T16     fixture 출처 명시 — mock data 는 dry_run 라벨로 분리
    T22     단위 테스트 mock 기반 (DI)

# 출처 주석:
#   IC (Spearman)         : Grinold-Kahn "Active Portfolio Management" Ch.6 (factor IC)
#   IC IR                 : Grinold-Kahn (IC mean / IC std)
#   Monotonicity (Q1->Q5) : LANDEX Grading 본질 (memory project_estate_backtest_methodology)
#   Quintile Spread       : Fama-MacBeth 1973 (decile/quintile portfolio sort)
#   Hit Rate              : Asness-Frazzini-Pedersen 2013 (rolling IC sign consistency)
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(_REPO_ROOT, "data", "estate_backtest_v0")

# 서울 25구 — _snapshot.SEOUL_25_GU 동일. 직접 import 시 vercel-api path 의존성 ↑
# → 백테스트는 자체 상수. drift 시 단위 테스트가 catch.
SEOUL_25_GU = (
    "강남구", "강동구", "강북구", "강서구", "관악구",
    "광진구", "구로구", "금천구", "노원구", "도봉구",
    "동대문구", "동작구", "마포구", "서대문구", "서초구",
    "성동구", "성북구", "송파구", "양천구", "영등포구",
    "용산구", "은평구", "종로구", "중구", "중랑구",
)

# v0 백테스트 구간 (memory 합의: 2020 ~ 현실 lookback)
DEFAULT_BACKTEST_START = "2020-01"
DEFAULT_BACKTEST_END = "2026-05"

# multi-horizon 라벨 (memory 정정 2026-05-02: 13주는 ρ≈0.92 환경에서 노이즈)
HORIZON_WEEKS = (13, 26, 52)

# Quintile = 25구 / 5분위 = 분위당 5구 (memory: decile 금지)
QUINTILE_N = 5

METHODOLOGY_VERSION = "1.2"  # baseline 섞임 방지 (memory 정합)


# ─────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────

@dataclass
class SnapshotCell:
    """단일 (gu, month) snapshot — compute_snapshot 의 v0 백테스트 부분집합."""
    gu: str
    month: str  # "YYYY-MM"
    landex: Optional[float]
    v_score: Optional[float]
    d_score: Optional[float]
    s_score: Optional[float]
    c_score: Optional[float]
    r_score: Optional[float]
    methodology_version: str
    as_of_yyyymm: str
    raw_sources: Dict[str, str]  # 각 팩터 source 라벨 (real/mock/missing)


@dataclass
class LabelCell:
    """단일 (gu, month, horizon) 라벨 — R-ONE 매매지수 forward return."""
    gu: str
    month: str
    horizon_weeks: int
    forward_return_pct: Optional[float]  # None = horizon 데이터 부족 (cutoff 후 가용 X)
    base_week: Optional[str]  # base R-ONE week id
    target_week: Optional[str]  # target R-ONE week id


@dataclass
class HorizonMetrics:
    """단일 horizon 의 1~3차 metrics 묶음."""
    horizon_weeks: int
    n_months: int
    n_pairs: int  # (gu, month) 유효 쌍 수
    mean_ic: Optional[float]
    ic_std: Optional[float]
    ic_ir: Optional[float]
    hit_rate: Optional[float]
    monotonicity: Optional[bool]  # Q1<Q2<Q3<Q4<Q5 strict
    quintile_means: Optional[List[float]]  # Q1..Q5 평균 forward return
    quintile_spread: Optional[float]  # Q5 - Q1


# ─────────────────────────────────────────────────
# Snapshot fetch (DI — compute_snapshot 주입 가능)
# ─────────────────────────────────────────────────

def collect_snapshots(
    months: List[str],
    compute_snapshot_fn: Callable[..., List[Dict[str, Any]]],
    preset: str = "balanced",
) -> List[SnapshotCell]:
    """
    각 month 에서 25구 snapshot 수집. as_of_yyyymm = month (look-ahead 차단).

    Returns:
        SnapshotCell 리스트. 단일 month 실패는 skip + 로그 (T9).
    """
    out: List[SnapshotCell] = []
    for month in months:
        as_of = month.replace("-", "")
        try:
            rows = compute_snapshot_fn(month=month, preset=preset, as_of_yyyymm=as_of)
        except Exception as e:
            logger.error("backtest: compute_snapshot failed month=%s: %s", month, e)
            continue
        if not rows:
            logger.warning("backtest: empty rows month=%s", month)
            continue
        for r in rows:
            method_v = r.get("methodology_version", "unknown")
            if method_v != METHODOLOGY_VERSION:
                # baseline 섞임 가드 (memory)
                logger.warning(
                    "backtest: skip row gu=%s month=%s methodology=%s (need %s)",
                    r.get("gu"), month, method_v, METHODOLOGY_VERSION,
                )
                continue
            raw = r.get("raw_payload") or {}
            out.append(SnapshotCell(
                gu=r["gu"], month=r["month"],
                landex=r.get("landex"),
                v_score=r.get("v_score"),
                d_score=r.get("d_score"),
                s_score=r.get("s_score"),
                c_score=r.get("c_score"),
                r_score=r.get("r_score"),
                methodology_version=method_v,
                as_of_yyyymm=raw.get("as_of_yyyymm", as_of),
                raw_sources={
                    "v": raw.get("v_source", "unknown"),
                    "d": raw.get("d_source", "unknown"),
                    "s": raw.get("s_source", "unknown"),
                    "c": raw.get("c_source", "unknown"),
                    "r": raw.get("r_source", "unknown"),
                },
            ))
    return out


# ─────────────────────────────────────────────────
# Labels — R-ONE forward return
# ─────────────────────────────────────────────────

def compute_forward_returns(
    snapshots: List[SnapshotCell],
    fetch_weekly_index_fn: Callable[..., Dict[str, Any]],
    horizons: Tuple[int, ...] = HORIZON_WEEKS,
) -> List[LabelCell]:
    """
    각 (gu, month) → R-ONE 주간 매매지수 base→target 변화율.

    base = month 의 첫 R-ONE 주 (혹은 cutoff 시점 마지막 주).
    target = base 로부터 horizon_weeks 후의 주.

    fetch_weekly_index_fn(gu, weeks, as_of_yyyymmww) → {"series":[{week,value}, ...], "as_of":...}
    백테스트는 라벨 산출 시 as_of=None (라벨은 *미래* 정보 OK).

    실패/horizon 데이터 부족 시 forward_return_pct=None (T1 — fabricate X).
    """
    # gu → (week, value) 정렬 시리즈 캐시 (gu 당 1회 fetch)
    series_cache: Dict[str, List[Dict[str, Any]]] = {}

    out: List[LabelCell] = []
    for cell in snapshots:
        if cell.gu not in series_cache:
            try:
                # weeks 파라미터는 lookback 깊이 — 백테스트는 충분히 deep
                payload = fetch_weekly_index_fn(gu=cell.gu, weeks=520, as_of_yyyymmww=None)
            except Exception as e:
                logger.error("backtest: fetch_weekly_index failed gu=%s: %s", cell.gu, e)
                series_cache[cell.gu] = []
                continue
            series_cache[cell.gu] = sorted(
                (payload or {}).get("series") or [],
                key=lambda x: x.get("week") or "",
            )

        series = series_cache.get(cell.gu) or []
        for horizon in horizons:
            base_week, base_val, target_week, target_val = _find_base_target(
                series, cell.month, horizon,
            )
            forward_return: Optional[float] = None
            if base_val is not None and target_val is not None and base_val != 0:
                forward_return = round(((target_val - base_val) / base_val) * 100, 4)
            out.append(LabelCell(
                gu=cell.gu, month=cell.month, horizon_weeks=horizon,
                forward_return_pct=forward_return,
                base_week=base_week, target_week=target_week,
            ))
    return out


def _find_base_target(
    series: List[Dict[str, Any]], month: str, horizon_weeks: int,
) -> Tuple[Optional[str], Optional[float], Optional[str], Optional[float]]:
    """
    series 에서 base = month 첫 주 (또는 그 직후), target = base + horizon 주.

    series 항목 schema: {"week": "YYYYMMW#", "value": float, "date": "YYYY-MM-DD"}
    (R-ONE _sources/rone.py 기준)
    """
    if not series:
        return None, None, None, None

    # base = month prefix YYYYMM 매칭 첫 항목
    yyyymm = month.replace("-", "")
    base_idx: Optional[int] = None
    for i, s in enumerate(series):
        wk = (s.get("week") or "")
        if wk.startswith(yyyymm):
            base_idx = i
            break
    if base_idx is None:
        return None, None, None, None

    target_idx = base_idx + horizon_weeks
    if target_idx >= len(series):
        return series[base_idx].get("week"), series[base_idx].get("value"), None, None

    return (
        series[base_idx].get("week"), series[base_idx].get("value"),
        series[target_idx].get("week"), series[target_idx].get("value"),
    )


# ─────────────────────────────────────────────────
# Metrics — 1~3차 (memory 합의)
# ─────────────────────────────────────────────────

def compute_metrics(
    snapshots: List[SnapshotCell],
    labels: List[LabelCell],
    horizons: Tuple[int, ...] = HORIZON_WEEKS,
) -> List[HorizonMetrics]:
    """
    snapshots(landex score) ↔ labels(forward return) 매칭 후 horizon 별 metrics 산출.
    """
    snap_by_key: Dict[Tuple[str, str], SnapshotCell] = {(s.gu, s.month): s for s in snapshots}

    out: List[HorizonMetrics] = []
    for h in horizons:
        # (month, gu) → (landex, forward_return) 페어 모음
        by_month: Dict[str, List[Tuple[str, float, float]]] = {}
        for lab in labels:
            if lab.horizon_weeks != h:
                continue
            if lab.forward_return_pct is None:
                continue
            snap = snap_by_key.get((lab.gu, lab.month))
            if snap is None or snap.landex is None:
                continue
            by_month.setdefault(lab.month, []).append((lab.gu, snap.landex, lab.forward_return_pct))

        # month 별 IC + 분위
        ic_series: List[float] = []
        all_pairs: List[Tuple[float, float]] = []  # (landex, forward)
        for month, pairs in by_month.items():
            if len(pairs) < 5:  # 5분위 최소 5구
                continue
            xs = [p[1] for p in pairs]  # landex
            ys = [p[2] for p in pairs]  # forward return
            ic = _spearman(xs, ys)
            if ic is not None:
                ic_series.append(ic)
            all_pairs.extend([(x, y) for _, x, y in pairs])

        # 1차 — mean IC, IC std, IC IR, hit rate
        mean_ic = _safe_mean(ic_series)
        ic_std = _safe_std(ic_series)
        ic_ir = (mean_ic / ic_std) if (mean_ic is not None and ic_std and ic_std > 0) else None
        hit_rate = (
            sum(1 for ic in ic_series if ic > 0) / len(ic_series) if ic_series else None
        )

        # 2차 — Quintile (전체 풀 합쳐서 5분위)
        q_means, q_spread, monotonic = _quintile_metrics(all_pairs, QUINTILE_N)

        out.append(HorizonMetrics(
            horizon_weeks=h,
            n_months=len(by_month),
            n_pairs=len(all_pairs),
            mean_ic=_safe_round(mean_ic, 4),
            ic_std=_safe_round(ic_std, 4),
            ic_ir=_safe_round(ic_ir, 3),
            hit_rate=_safe_round(hit_rate, 3),
            monotonicity=monotonic,
            quintile_means=[round(v, 4) for v in q_means] if q_means else None,
            quintile_spread=_safe_round(q_spread, 4),
        ))
    return out


def _spearman(xs: List[float], ys: List[float]) -> Optional[float]:
    """
    Spearman rank correlation — Grinold-Kahn factor IC 정의.
    동률은 평균 rank (mid-rank) — scipy.stats.spearmanr 와 정합.
    """
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    rx = _rank_avg(xs)
    ry = _rank_avg(ys)
    n = len(rx)
    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n
    num = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    den_x = math.sqrt(sum((rx[i] - mean_rx) ** 2 for i in range(n)))
    den_y = math.sqrt(sum((ry[i] - mean_ry) ** 2 for i in range(n)))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def _rank_avg(values: List[float]) -> List[float]:
    """평균 rank — 동률 처리 (mid-rank)."""
    indexed = sorted(enumerate(values), key=lambda iv: iv[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1  # 1-based, midrank
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def _quintile_metrics(
    pairs: List[Tuple[float, float]], n_quantiles: int,
) -> Tuple[List[float], Optional[float], Optional[bool]]:
    """
    pairs = [(landex, forward_return), ...] → Q1..Q_n means + spread + 단조성.
    """
    if len(pairs) < n_quantiles:
        return [], None, None
    sorted_pairs = sorted(pairs, key=lambda p: p[0])  # ASC by landex
    n = len(sorted_pairs)
    q_size = n // n_quantiles  # remainder 는 마지막 분위로 합산
    q_means: List[float] = []
    for q in range(n_quantiles):
        start = q * q_size
        end = (q + 1) * q_size if q < n_quantiles - 1 else n
        chunk = sorted_pairs[start:end]
        if not chunk:
            return [], None, None
        q_means.append(sum(p[1] for p in chunk) / len(chunk))
    spread = q_means[-1] - q_means[0]
    monotonic = all(q_means[i] <= q_means[i + 1] for i in range(n_quantiles - 1))
    return q_means, spread, monotonic


def _safe_mean(xs: List[float]) -> Optional[float]:
    return (sum(xs) / len(xs)) if xs else None


def _safe_std(xs: List[float]) -> Optional[float]:
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _safe_round(v: Optional[float], digits: int) -> Optional[float]:
    return round(v, digits) if v is not None else None


# ─────────────────────────────────────────────────
# Pipeline + IO
# ─────────────────────────────────────────────────

def month_range(start: str, end: str) -> List[str]:
    """'YYYY-MM' inclusive 범위."""
    s_y, s_m = (int(x) for x in start.split("-"))
    e_y, e_m = (int(x) for x in end.split("-"))
    out: List[str] = []
    y, m = s_y, s_m
    while (y, m) <= (e_y, e_m):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def run(
    start: str = DEFAULT_BACKTEST_START,
    end: str = DEFAULT_BACKTEST_END,
    preset: str = "balanced",
    horizons: Tuple[int, ...] = HORIZON_WEEKS,
    compute_snapshot_fn: Optional[Callable] = None,
    fetch_weekly_index_fn: Optional[Callable] = None,
    output_dir: str = OUTPUT_DIR,
    label_tag: str = "live",
) -> Dict[str, Any]:
    """
    백테스트 v0 entry. DI 패턴 — fn 미주입 시 ImportError 발생 (P1: 의도적, P2 시 default 주입).
    """
    if compute_snapshot_fn is None or fetch_weekly_index_fn is None:
        raise RuntimeError(
            "P1 단계: compute_snapshot_fn + fetch_weekly_index_fn 필수. "
            "P2 시 vercel-api/api/landex import 후 default 주입."
        )

    months = month_range(start, end)
    logger.info("backtest: %d months (%s ~ %s) preset=%s", len(months), start, end, preset)

    snapshots = collect_snapshots(months, compute_snapshot_fn, preset=preset)
    logger.info("backtest: snapshots=%d (expected %d)", len(snapshots), len(months) * 25)

    labels = compute_forward_returns(snapshots, fetch_weekly_index_fn, horizons=horizons)
    logger.info("backtest: labels=%d (expected %d)", len(labels), len(snapshots) * len(horizons))

    metrics = compute_metrics(snapshots, labels, horizons=horizons)

    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "label_tag": label_tag,  # "live" or "dry_run"
        "config": {
            "start": start, "end": end, "preset": preset,
            "horizons_weeks": list(horizons),
            "methodology_version": METHODOLOGY_VERSION,
            "quintile_n": QUINTILE_N,
        },
        "summary": {
            "n_months": len(months),
            "n_snapshots": len(snapshots),
            "n_labels": len(labels),
        },
        "metrics_by_horizon": [asdict(m) for m in metrics],
    }

    _write_outputs(output_dir, snapshots, labels, payload)
    return payload


def _write_outputs(
    output_dir: str,
    snapshots: List[SnapshotCell],
    labels: List[LabelCell],
    metrics_payload: Dict[str, Any],
) -> None:
    os.makedirs(output_dir, exist_ok=True)
    _write_json(os.path.join(output_dir, "snapshots.json"), [asdict(s) for s in snapshots])
    _write_json(os.path.join(output_dir, "labels.json"), [asdict(l) for l in labels])
    _write_json(os.path.join(output_dir, "metrics.json"), metrics_payload)


def _write_json(path: str, data: Any) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ─────────────────────────────────────────────────
# Dry-run mock — 실 fetch 없이 e2e schema 검증 (P1)
# ─────────────────────────────────────────────────

def _mock_compute_snapshot(month: str, preset: str, as_of_yyyymm: str) -> List[Dict[str, Any]]:
    """결정적 mock — landex 가 gu·month 로 deterministic. 실 _snapshot 의 schema 정합."""
    rows = []
    for gu in SEOUL_25_GU:
        seed = sum(ord(c) for c in gu) + sum(ord(c) for c in month)
        landex = round(40 + (seed * 17 % 100) * 0.6, 1)
        rows.append({
            "gu": gu, "month": month, "preset": preset,
            "v_score": round(40 + (seed * 23 % 100) * 0.6, 1),
            "d_score": round(40 + (seed * 41 % 100) * 0.6, 1),
            "s_score": round(40 + (seed * 53 % 100) * 0.6, 1),
            "c_score": round(40 + (seed * 67 % 100) * 0.6, 1),
            "r_score": 50.0,
            "landex": landex,
            "tier10": None,
            "gei": 50.0,
            "gei_stage": 2,
            "raw_payload": {
                "v_source": "mock", "d_source": "mock", "s_source": "mock",
                "c_source": "mock", "r_source": "mock",
                "as_of_yyyymm": as_of_yyyymm,
            },
            "methodology_version": METHODOLOGY_VERSION,
        })
    return rows


def _mock_fetch_weekly_index(
    gu: str, weeks: int, as_of_yyyymmww: Optional[str],
) -> Dict[str, Any]:
    """결정적 mock — 2018-01 ~ 2027-01 주별 시계열 (~470주). 25구 차별 trend."""
    series = []
    seed = sum(ord(c) for c in gu)
    base = 100.0
    # 2018-01-01 ~ 2027-01-01 weekly
    start = datetime(2018, 1, 1)
    n_weeks = 470
    for i in range(n_weeks):
        d = start + timedelta(weeks=i)
        # 주식별자 = YYYYMMW#  (월 1~5주, 단순화: i%5 +1)
        yyyymm = d.strftime("%Y%m")
        wn = (i % 4) + 1
        week_id = f"{yyyymm}W{wn}"
        # gu 별 trend + 작은 sin 변동
        landex_corr = ((seed * 7) % 100) / 1000.0  # gu 별 trend slope
        val = base * (1 + landex_corr * i + 0.005 * math.sin(i * 0.4))
        series.append({"week": week_id, "value": round(val, 4), "date": d.strftime("%Y-%m-%d")})
    return {"series": series, "as_of": series[-1]["week"]}


# ─────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────

# ─────────────────────────────────────────────────
# Real fn loader (P2 — run_landex_snapshot.py 패턴 정합)
# ─────────────────────────────────────────────────

def _load_real_fns() -> Tuple[Callable, Callable]:
    """
    vercel-api/api/landex 의 compute_snapshot + rone.fetch_weekly_index 동적 로드.

    ROOT/api 와 vercel-api/api 가 namespace 충돌이라 importlib + sys.modules
    조작으로 'vapi' 별칭 등록 (run_landex_snapshot.py 패턴 정합).

    Returns:
        (compute_snapshot_fn, fetch_weekly_index_fn)
    """
    import importlib.util
    import sys
    import types
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    vercel_api = root / "vercel-api"

    # .env 로드
    env_path = root / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    # vapi 별칭 패키지 박음
    api_pkg = types.ModuleType("vapi"); api_pkg.__path__ = [str(vercel_api / "api")]
    sys.modules["vapi"] = api_pkg
    landex_pkg = types.ModuleType("vapi.landex"); landex_pkg.__path__ = [str(vercel_api / "api" / "landex")]
    sys.modules["vapi.landex"] = landex_pkg
    sources_pkg = types.ModuleType("vapi.landex._sources")
    sources_pkg.__path__ = [str(vercel_api / "api" / "landex" / "_sources")]
    sys.modules["vapi.landex._sources"] = sources_pkg

    def _load(name: str, path: Path):
        spec = importlib.util.spec_from_file_location(name, str(path))
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load {name} from {path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    SD = vercel_api / "api" / "landex" / "_sources"
    LD = vercel_api / "api" / "landex"

    _load("vapi.landex._sources._lawd",        SD / "_lawd.py")
    _load("vapi.landex._sources.molit",        SD / "molit.py")
    _load("vapi.landex._sources.ecos",         SD / "ecos.py")
    _load("vapi.landex._sources.seoul_subway", SD / "seoul_subway.py")
    rone_mod = _load("vapi.landex._sources.rone", SD / "rone.py")
    _load("vapi.landex._methodology",          LD / "_methodology.py")
    _load("vapi.landex._compute",              LD / "_compute.py")

    # _snapshot 의 relative import 를 절대명으로 패치 (run_landex_snapshot 패턴 동일)
    snapshot_src = (LD / "_snapshot.py").read_text()
    snapshot_src = snapshot_src.replace("from . import _methodology as M", "from vapi.landex import _methodology as M")
    snapshot_src = snapshot_src.replace("from ._compute import", "from vapi.landex._compute import")
    snapshot_src = snapshot_src.replace("from ._sources._lawd import", "from vapi.landex._sources._lawd import")
    snapshot_src = snapshot_src.replace("from ._sources import", "from vapi.landex._sources import")

    snap_module = types.ModuleType("vapi.landex._snapshot")
    snap_module.__file__ = str(LD / "_snapshot.py")
    sys.modules["vapi.landex._snapshot"] = snap_module
    exec(compile(snapshot_src, str(LD / "_snapshot.py"), "exec"), snap_module.__dict__)

    return snap_module.compute_snapshot, rone_mod.fetch_weekly_index


# ─────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="ESTATE LANDEX Backtest v0")
    parser.add_argument("--start", default=DEFAULT_BACKTEST_START)
    parser.add_argument("--end", default=DEFAULT_BACKTEST_END)
    parser.add_argument("--preset", default="balanced")
    parser.add_argument("--dry-run", action="store_true",
                        help="실 fetch 없이 mock 으로 schema/평가 e2e 검증 (P1)")
    parser.add_argument("--with-fetch", action="store_true",
                        help="실 fetch (P2). vercel-api/api/landex 동적 로드 + 6년 합성. "
                             "60+ snapshot fetch — 30~60분 + R-ONE/ECOS rate limit 의존")
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.dry_run and args.with_fetch:
        logger.error("--dry-run 과 --with-fetch 동시 사용 불가")
        return 1

    if not args.dry_run and not args.with_fetch:
        logger.error("--dry-run 또는 --with-fetch 중 하나 필수")
        return 1

    if args.dry_run:
        out_dir = (
            os.path.join(_REPO_ROOT, "data", "estate_backtest_v0_dry_run")
            if args.output_dir == OUTPUT_DIR else args.output_dir
        )
        compute_fn = _mock_compute_snapshot
        fetch_fn = _mock_fetch_weekly_index
        label_tag = "dry_run"
    else:
        # --with-fetch
        logger.info("backtest: vapi.landex 로드 중 (run_landex_snapshot 패턴)...")
        compute_fn, fetch_fn = _load_real_fns()
        out_dir = args.output_dir
        label_tag = "live"
        logger.warning(
            "backtest: 실 fetch 시작 — 6년 × 25구 monthly snapshot. "
            "R-ONE/ECOS rate limit 의존 (~30~60분 추정)"
        )

    payload = run(
        start=args.start, end=args.end, preset=args.preset,
        compute_snapshot_fn=compute_fn,
        fetch_weekly_index_fn=fetch_fn,
        output_dir=out_dir,
        label_tag=label_tag,
    )
    print(json.dumps(payload["summary"], indent=2))
    print("---metrics---")
    for m in payload["metrics_by_horizon"]:
        print(json.dumps(m, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
