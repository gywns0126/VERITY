"""Phase 1.3 표본 가능성 검증 — 한국 시장 5R 도달 종목 카운트.

목적
----
ATR(14, Wilder EMA) × 2.5 손절 + 252 영업일 max holding 가정 하에 한국
KOSPI+KOSDAQ 2015-2025 10년간 5R 이상 도달한 unique 종목이 통계적으로
의미 있는 표본 (n ≥ 30) 으로 존재하는지 사전 검증한다. Phase 1.3
(Chandelier exit + Thesis Break) 명세 진입 전 데이터 가용성 게이트.

운영 코드 / 운영 데이터 변경 X. 신규 환경변수 X. 신규 파일은 분석 산출물 한정:
  - data/analysis/5r_feasibility_<YYYY-MM-DD>.json
  - data/cache/5r_analysis_ohlcv/<ticker>_<start>_<end>.pkl  (pykrx OHLCV 캐시)
  - 콘솔 markdown 요약

Verdict 매트릭스 (사전 결정 — 변경 시 본 모듈 상수 수정)
----------------------------------------------------------
  n_5r_unique_tickers >= 30  → ok          (Phase 1.3 진입 가능)
  15 ~ 29                   → monitoring  (보강 필요)
  < 15                      → insufficient (룰 재설계 권고)

사용법
------
  # dry-run (100종목 무작위 샘플)
  python scripts/analyze_5r_sample_feasibility.py --limit 100

  # full run
  python scripts/analyze_5r_sample_feasibility.py

  # 시장 한정
  python scripts/analyze_5r_sample_feasibility.py --market KOSPI --limit 50

참조
----
  api/analyzers/technical.py:compute_atr_14d  (Phase 0 Wilder EMA)
  api/intelligence/backtest_archive.py        (survivorship bias 패턴)
  api/config.py:ATR_STOP_MULTIPLIER=2.5       (Phase 1.1)
  api/collectors/parallel_fetcher.py          (KR pykrx workers ≤ 30 한계)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Optional

# repo root sys.path 추가 (api.* import 위해)
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from api.analyzers.technical import compute_atr_14d  # noqa: E402  Phase 0 표준 헬퍼


# ─────────────────────────────────────────────────────────────────────
# 사전 결정 (코드 레벨 상수)
# ─────────────────────────────────────────────────────────────────────
ATR_MULTIPLIER = 2.5              # Phase 1.1 ATR_STOP_MULTIPLIER 와 동일값
MAX_HOLD_DAYS = 252               # 1 trading year
MIN_BARS_BEFORE_ENTRY = 60        # ATR 산출 + 안정화 안전 마진
DELISTED_R_MULTIPLE = -1.0        # 데이터 끝남 = 보수적 -1R 처리 (survivorship)

VERDICT_OK_THRESHOLD = 30
VERDICT_MONITORING_THRESHOLD = 15

# D5 — 결정 23 ("한국 30년 텐버거 약 114개") 검증 임계
DECISION_23_ASSUMED_COUNT = 114      # 한국 KOSPI+KOSDAQ 30년 누적 (Perplexity 인용, 미검증)
DECISION_23_CONSISTENT_LO = 80       # 본 풀스캔 (10년) → 80~150 = 정합 (lookback 짧으니 80~ ok)
DECISION_23_CONSISTENT_HI = 150
DECISION_23_INCONSISTENT_HARD_LO = 50  # < 50 → inconsistent (수치 차이 너무 큼)

TENBAGGER_RETURN_PCT = 900.0   # 10x = +900% buy-and-hold return
TWENTYBAGGER_RETURN_PCT = 1900.0

# Bessembinder 2018 미국 벤치마크 (Do Stocks Outperform Treasury Bills?)
BESSEMBINDER_US_TOP_4PCT_WEALTH_SHARE = 100.0   # 미국 top 4% = 전체 wealth 100% (대략)
BESSEMBINDER_US_MEDIAN_RETURN_PCT = -2.0        # 미국 단일 종목 lifetime median 음수

# parallel_fetcher 결정 8 호환 — KR pykrx 워커 절대 한계
MAX_KR_WORKERS = 30

CACHE_DIR = _REPO_ROOT / "data" / "cache" / "5r_analysis_ohlcv"
OUTPUT_DIR = _REPO_ROOT / "data" / "analysis"
OUTLIER_AUDIT_PATH = OUTPUT_DIR / "r_multiple_outliers.jsonl"

# Phase 1.1 적정성 분석 — 시총 tier (KRW)
TIER_LARGE_MIN_KRW = 1_000_000_000_000   # 1조원
TIER_MID_MIN_KRW = 100_000_000_000       # 1천억원


# ─────────────────────────────────────────────────────────────────────
# Universe / OHLCV
# ─────────────────────────────────────────────────────────────────────
def load_universe_via_system(
    target_size: int = 2000,
    apply_hard_floor_filter: bool = False,
) -> tuple[list[dict], str, Optional[dict]]:
    """build_kr_universe (KRX OpenAPI K1) 활용 — pykrx ticker_list 대안.

    apply_hard_floor_filter=True 시 페니/관리/거래정지/저거래대금 자동 제외 + diagnostics.

    Returns:
        (entries, source_label, universe_diagnostics) — diagnostics 는 hard_floor
        미적용 시 None.
    """
    from api.collectors.universe_builder import build_kr_universe
    bas_dd, entries = build_kr_universe(target_size=target_size)

    diagnostics: Optional[dict] = None

    if apply_hard_floor_filter:
        from api.analyzers.hard_floor import apply_hard_floor as _apply
        before = len(entries)
        for e in entries:
            _apply(e)  # in-place + adds hard_floor_metadata

        passed = [e for e in entries if e.get("hard_floor_metadata", {}).get("passes")]
        excluded = [e for e in entries if not e.get("hard_floor_metadata", {}).get("passes")]

        # 사유 분류 — reasons 첫 키워드 prefix 매칭
        reason_keys = ("penny_stock", "managed_stock", "trading_suspended", "low_trading_value")
        reason_counts = {k: 0 for k in reason_keys}
        reason_counts["other"] = 0
        for e in excluded:
            reasons = e.get("hard_floor_metadata", {}).get("reasons", [])
            matched = False
            for r in reasons:
                for key in reason_keys:
                    if r.startswith(key):
                        reason_counts[key] += 1
                        matched = True
                        break
                if matched:
                    break
            if not matched:
                reason_counts["other"] += 1

        ex_caps = sorted((e.get("market_cap") or 0) for e in excluded)
        ex_dist = {}
        if ex_caps:
            n = len(ex_caps)

            def _p(p: float) -> int:
                return int(ex_caps[min(int(n * p), n - 1)])

            ex_dist = {"p25": _p(0.25), "p50": _p(0.50), "p75": _p(0.75)}

        diagnostics = {
            "before_hard_floor": before,
            "after_hard_floor": len(passed),
            "excluded_count": len(excluded),
            "exclusion_reasons": reason_counts,
            "excluded_tickers_market_cap_distribution": ex_dist,
        }
        entries = passed

    src = f"system_universe_{bas_dd}"
    if apply_hard_floor_filter:
        src += "_hard_floor"
    return entries, src, diagnostics


def stratified_sample_100(entries: list[dict]) -> list[str]:
    """KOSPI 상위30 + KOSPI 중위30 + KOSDAQ 상위20 + KOSDAQ 중위20 = 100.

    cherry-picking 회피용. entries 는 시총 내림차순 정렬 가정
    (build_kr_universe 출력 형태).
    """
    kospi = [e for e in entries if "KOSPI" in (e.get("market") or "").upper()]
    kosdaq = [e for e in entries if "KOSDAQ" in (e.get("market") or "").upper()]

    selected: list[str] = []

    def _take(pool: list[dict], top_n: int, mid_n: int, label: str) -> None:
        if not pool:
            print(f"[warn] stratified: pool {label} 비어있음")
            return
        # 상위
        selected.extend(e["ticker"] for e in pool[:top_n])
        # 중위 (시총 정렬 = 큰→작음, mid 는 전체 중간 부근)
        if mid_n and len(pool) > top_n + mid_n:
            mid_center = len(pool) // 2
            mid_start = max(top_n, mid_center - mid_n // 2)
            mid_end = mid_start + mid_n
            selected.extend(e["ticker"] for e in pool[mid_start:mid_end])
        elif mid_n:
            # 풀 부족 — 가능한 만큼만 mid 채움
            selected.extend(e["ticker"] for e in pool[top_n:top_n + mid_n])

    _take(kospi, 30, 30, "KOSPI")
    _take(kosdaq, 20, 20, "KOSDAQ")
    return sorted(set(selected))


def load_universe_kr(
    date_ymd: str,
    markets: tuple[str, ...],
    ticker_file: Optional[Path] = None,
) -> tuple[list[str], str]:
    """Universe 로딩 — pykrx 우선, 빈 결과 시 fallback.

    Fallback 순서:
      1. ticker_file 옵션 (사용자 제공 텍스트 파일, 한 줄에 ticker 1개)
      2. api.collectors.stock_data 의 KOSPI_MAJOR + KOSDAQ_MAJOR 화이트리스트
         (45 종목 — dry-run smoke test 만. 광범위 verdict 부적합)

    NOTE: end_date 시점 universe 만 사용 — survivorship 일부 잔존.
    delisted 종목은 OHLCV 데이터 짧음 → simulate_position 의
    `delisted_or_insufficient` 보수 처리로 차단.

    Returns:
        (tickers, source) — source ∈ {ticker_file, pykrx, fallback_whitelist}
    """
    if ticker_file and ticker_file.exists():
        tickers = [
            line.strip().split(".")[0] for line in ticker_file.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        print(f"[info] universe from file {ticker_file}: {len(tickers)}")
        return sorted(set(tickers)), "ticker_file"

    from pykrx import stock
    out: set[str] = set()
    for m in markets:
        try:
            tickers = stock.get_market_ticker_list(date_ymd, market=m)
            if tickers:
                out.update(tickers)
        except Exception as e:
            print(f"[warn] pykrx universe fetch failed market={m} date={date_ymd}: {e}")

    if out:
        return sorted(out), "pykrx"

    # Fallback — pykrx ticker_list endpoint 깨짐 (KRX 응답 파싱 실패 등)
    print(
        "[warn] pykrx universe 0건 — stock_data 화이트리스트 fallback (45종목). "
        "이 표본은 시총 상위 = survivorship bias 100% — verdict 일반화 불가. "
        "광범위 분석은 --ticker-file 옵션 사용 (KRX 사이트에서 종목 리스트 다운로드)."
    )
    from api.collectors.stock_data import KOSPI_MAJOR, KOSDAQ_MAJOR
    fb: set[str] = set()
    if "KOSPI" in markets:
        fb.update(t.split(".")[0] for t in KOSPI_MAJOR.keys())
    if "KOSDAQ" in markets:
        fb.update(t.split(".")[0] for t in KOSDAQ_MAJOR.keys())
    return sorted(fb), "fallback_whitelist"


def fetch_ohlcv_cached(ticker: str, start_ymd: str, end_ymd: str):
    """pykrx OHLCV + disk pickle 캐시. parallel_fetcher 패턴 준용."""
    import pandas as pd

    cache_path = CACHE_DIR / f"{ticker}_{start_ymd}_{end_ymd}.pkl"
    if cache_path.exists():
        try:
            return pd.read_pickle(cache_path)
        except Exception:
            try:
                cache_path.unlink()
            except Exception:
                pass

    from pykrx import stock
    try:
        df = stock.get_market_ohlcv(start_ymd, end_ymd, ticker)
    except Exception as e:
        print(f"[warn] OHLCV fetch failed {ticker}: {e}")
        return None

    if df is None or len(df) < MIN_BARS_BEFORE_ENTRY:
        return None

    df = df.rename(columns={
        "시가": "open", "고가": "high", "저가": "low", "종가": "close", "거래량": "volume",
    })

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_pickle(cache_path)
    except Exception:
        pass
    return df


# ─────────────────────────────────────────────────────────────────────
# 시뮬레이션 (단위 테스트 대상 — pure function, 외부 의존성 X)
# ─────────────────────────────────────────────────────────────────────
def compute_atr_at_idx(df, idx: int) -> Optional[float]:
    """idx 시점까지의 데이터로 Wilder EMA(14) ATR 산출 (look-ahead 차단)."""
    if idx < MIN_BARS_BEFORE_ENTRY:
        return None
    sub = df.iloc[:idx + 1]
    atr_val, _, _ = compute_atr_14d(
        sub["high"], sub["low"], sub["close"], method="wilder_ema_14"
    )
    return atr_val


def simulate_position(
    df,
    entry_idx: int,
    atr_value: float,
    multiplier: float = ATR_MULTIPLIER,
    max_days: int = MAX_HOLD_DAYS,
) -> dict[str, Any]:
    """단일 진입 시뮬레이션.

    보수적 가정:
      - 같은 봉에 stop_low + 5R high 동시 발생 시 stop 우선 (실거래 슬리피지 회피)
      - 데이터 부족 (max_days 미충족) = delisted_or_insufficient = -1R

    Returns:
        {exit_reason, exit_idx, days_held, r_multiple, max_excursion_r, hit_5r}
    """
    entry_close = float(df.iloc[entry_idx]["close"])
    R = atr_value * multiplier
    if R <= 0 or entry_close <= 0:
        return {
            "exit_reason": "invalid_R", "exit_idx": entry_idx,
            "days_held": 0, "r_multiple": 0.0,
            "max_excursion_r": 0.0, "hit_5r": False,
        }

    stop_price = entry_close - R
    target_5r_price = entry_close + 5 * R

    max_high = entry_close
    max_excursion_r = 0.0
    last_idx = min(entry_idx + max_days, len(df) - 1)

    for i in range(entry_idx + 1, last_idx + 1):
        row = df.iloc[i]
        h = float(row["high"])
        l = float(row["low"])
        if h > max_high:
            max_high = h
            max_excursion_r = (max_high - entry_close) / R
        if l <= stop_price:
            return {
                "exit_reason": "stop_loss",
                "exit_idx": i,
                "days_held": i - entry_idx,
                "r_multiple": -1.0,
                "max_excursion_r": round(max_excursion_r, 3),
                "hit_5r": max_excursion_r >= 5.0,
            }
        if h >= target_5r_price:
            return {
                "exit_reason": "5r_hit",
                "exit_idx": i,
                "days_held": i - entry_idx,
                "r_multiple": 5.0,
                "max_excursion_r": round(max_excursion_r, 3),
                "hit_5r": True,
            }

    final_close = float(df.iloc[last_idx]["close"])
    final_r = (final_close - entry_close) / R
    days_held = last_idx - entry_idx

    if days_held < max_days:
        return {
            "exit_reason": "delisted_or_insufficient",
            "exit_idx": last_idx,
            "days_held": days_held,
            "r_multiple": DELISTED_R_MULTIPLE,
            "max_excursion_r": round(max_excursion_r, 3),
            "hit_5r": max_excursion_r >= 5.0,
        }

    return {
        "exit_reason": "max_days",
        "exit_idx": last_idx,
        "days_held": max_days,
        "r_multiple": round(final_r, 3),
        "max_excursion_r": round(max_excursion_r, 3),
        "hit_5r": max_excursion_r >= 5.0,
    }


def weekly_entry_indices(
    df, start_date_str: str, end_date_str: str,
    max_hold_days: int = MAX_HOLD_DAYS,
) -> list[int]:
    """매주 첫 영업일 entry indices (ISO 주차 기준 = 월~일).

    cutoff 적용: 진입 idx + max_hold_days 가 데이터 끝을 초과하지 않도록
    제한 → end_of_period 인공 라벨 제거. 진입 자체를 막으면 데이터 끝
    문제는 자연 해결.
    """
    start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    last_valid_entry_idx = len(df) - max_hold_days - 1  # forward 252봉 보장

    indices: list[int] = []
    seen_weeks: set[tuple[int, int]] = set()
    for i, ts in enumerate(df.index):
        if i > last_valid_entry_idx:
            break
        if i < MIN_BARS_BEFORE_ENTRY:
            continue
        if hasattr(ts, "date"):
            d = ts.date()
        else:
            d = datetime.strptime(str(ts)[:10], "%Y-%m-%d").date()
        if d < start or d > end:
            continue
        year, week, _ = d.isocalendar()
        wk_key = (year, week)
        if wk_key in seen_weeks:
            continue
        seen_weeks.add(wk_key)
        indices.append(i)
    return indices


# 호환 alias (이전 quarterly 명세 호출자 보호)
def quarterly_entry_indices(df, start_date_str, end_date_str):  # pragma: no cover
    """Deprecated — weekly_entry_indices 사용."""
    return weekly_entry_indices(df, start_date_str, end_date_str)


def analyze_ticker(
    ticker: str, df, start_date: str, end_date: str,
    r_multiple_cap: Optional[float] = None,
    audit_path: Optional[Path] = None,
) -> dict[str, Any]:
    """단일 종목 weekly Monday 진입 합산.

    weekly_entry_indices 가 cutoff (end - 252봉) 적용 → 진입 후보 단계에서
    end_of_period 자연 차단. simulate_position 의 delisted_or_insufficient
    카운트는 *ticker 데이터 자체 종료* (상장폐지/거래정지) 의미만 남음.

    추가:
      - r_multiple_cap: 지정 시 max_excursion_r 가 cap 초과한 entry 는
        audit jsonl 에 raw 값 기록 + cap 으로 strip → outlier 가 분포 통계 왜곡 방지
      - hit_years (Step 2 연도별 분포)
      - atr_pcts / days_to_5r (Phase 1.1 적정성 분석 입력)
    """
    entries = weekly_entry_indices(df, start_date, end_date)
    sim_results: list[dict[str, Any]] = []
    hit_years: list[int] = []
    atr_pcts: list[float] = []
    days_to_5r: list[int] = []

    for ei in entries:
        atr = compute_atr_at_idx(df, ei)
        if atr is None or atr <= 0:
            continue
        entry_close = float(df.iloc[ei]["close"])
        if entry_close > 0:
            atr_pcts.append(atr / entry_close * 100)

        result = simulate_position(df, ei, atr)

        # R-multiple cap (audit + strip)
        if r_multiple_cap is not None and result["max_excursion_r"] > r_multiple_cap:
            if audit_path is not None:
                _append_outlier_audit(audit_path, {
                    "ticker": ticker,
                    "entry_date": str(df.index[ei])[:10],
                    "raw_max_excursion_r": result["max_excursion_r"],
                    "capped_to": r_multiple_cap,
                    "atr_value": float(atr),
                    "entry_price": entry_close,
                    "exit_reason": result["exit_reason"],
                    "days_held": result["days_held"],
                })
            result["max_excursion_r"] = r_multiple_cap
            result["max_excursion_capped"] = True

        sim_results.append(result)
        if result["hit_5r"]:
            ts = df.index[ei]
            yr = ts.year if hasattr(ts, "year") else int(str(ts)[:4])
            hit_years.append(yr)
        if result["exit_reason"] == "5r_hit":
            days_to_5r.append(result["days_held"])

    n_total = len(sim_results)
    n_5r_hits = sum(1 for r in sim_results if r["hit_5r"])
    n_stop = sum(1 for r in sim_results if r["exit_reason"] == "stop_loss")
    n_max_days = sum(1 for r in sim_results if r["exit_reason"] == "max_days")
    n_delisted = sum(1 for r in sim_results if r["exit_reason"] == "delisted_or_insufficient")
    max_r_overall = max((r["max_excursion_r"] for r in sim_results), default=0.0)
    n_capped = sum(1 for r in sim_results if r.get("max_excursion_capped"))

    avg_atr_pct = sum(atr_pcts) / len(atr_pcts) if atr_pcts else None
    avg_days_to_5r_t = sum(days_to_5r) / len(days_to_5r) if days_to_5r else None

    # ── D5 buy-and-hold (lifetime, Bessembinder/텐버거 검증용) ──
    bh = _compute_buy_and_hold(df)

    return {
        "ticker": ticker,
        "n_entries": n_total,
        "n_5r_hits": n_5r_hits,
        "n_stop_loss": n_stop,
        "n_max_days": n_max_days,
        "n_delisted": n_delisted,
        "n_capped": n_capped,
        "max_excursion_r_overall": round(max_r_overall, 3),
        "had_5r_hit": n_5r_hits > 0,
        "hit_years": hit_years,
        "avg_atr_pct": round(avg_atr_pct, 4) if avg_atr_pct is not None else None,
        "median_days_to_5r": int(avg_days_to_5r_t) if avg_days_to_5r_t else None,
        "buy_and_hold": bh,
    }


def _append_outlier_audit(path: Path, record: dict) -> None:
    """R-multiple cap 초과 entry → jsonl append (thread-safe append-only).

    실패 시 silent (분석 계속 진행).
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _compute_buy_and_hold(df) -> dict[str, Any]:
    """Lifetime buy-and-hold — Bessembinder/텐버거 검증 입력.

    entry = MIN_BARS_BEFORE_ENTRY 시점 close (ATR 안정화 후 첫 가용일)
    exit  = 마지막 데이터 close (정상 = end_date / 짧으면 = 상장폐지/거래정지)
    max_high_pct = entry 후 최고가 / entry - 1 (lifetime 최대 미실현)
    """
    if len(df) <= MIN_BARS_BEFORE_ENTRY:
        return {"return_pct": None, "max_high_pct": None,
                "entry_close": None, "exit_close": None, "last_data_date": None}

    entry_close = float(df.iloc[MIN_BARS_BEFORE_ENTRY]["close"])
    exit_close = float(df.iloc[-1]["close"])
    max_high = float(df["high"].iloc[MIN_BARS_BEFORE_ENTRY:].max())

    if entry_close <= 0:
        return {"return_pct": None, "max_high_pct": None,
                "entry_close": entry_close, "exit_close": exit_close, "last_data_date": None}

    ret_pct = round((exit_close - entry_close) / entry_close * 100, 2)
    max_pct = round((max_high - entry_close) / entry_close * 100, 2)

    last_ts = df.index[-1]
    last_date = last_ts.date().isoformat() if hasattr(last_ts, "date") else str(last_ts)[:10]

    return {
        "return_pct": ret_pct,
        "max_high_pct": max_pct,
        "entry_close": entry_close,
        "exit_close": exit_close,
        "last_data_date": last_date,
    }


# ─────────────────────────────────────────────────────────────────────
# D5 — decision_23 + Bessembinder helpers
# ─────────────────────────────────────────────────────────────────────
def _skewness(values: list[float]) -> Optional[float]:
    """Sample skewness (scipy 의존성 회피, Pearson moment ratio)."""
    n = len(values)
    if n < 3:
        return None
    m = sum(values) / n
    m2 = sum((x - m) ** 2 for x in values) / n
    if m2 == 0:
        return 0.0
    m3 = sum((x - m) ** 3 for x in values) / n
    return round(m3 / (m2 ** 1.5), 4)


def _compute_decision_23_verification(ticker_results: dict) -> dict[str, Any]:
    """D5 — 결정 23 ("한국 30년 텐버거 약 114개") 검증.

    두 단위 모두 산출:
      - R-multiple (사용자 명세 "10R") = ATR×2.5 의 10배 거리 도달 (max_excursion_r ≥ 10)
      - Price multiple (결정 23 텐버거) = lifetime buy-and-hold 1000% 이상 (10x)
    comparison_to_decision_23 = price multiple (텐버거) 기준.
    """
    n_5r = sum(1 for r in ticker_results.values() if r["had_5r_hit"])
    n_10r_excursion = sum(
        1 for r in ticker_results.values() if r.get("max_excursion_r_overall", 0) >= 10
    )
    n_20r_excursion = sum(
        1 for r in ticker_results.values() if r.get("max_excursion_r_overall", 0) >= 20
    )

    # 텐버거 (price multiple) — buy_and_hold.max_high_pct 기준
    tenbaggers: list[str] = []
    twentybaggers: list[str] = []
    for tk, r in ticker_results.items():
        bh = r.get("buy_and_hold") or {}
        mp = bh.get("max_high_pct")
        if mp is None:
            continue
        if mp >= TENBAGGER_RETURN_PCT:
            tenbaggers.append(tk)
        if mp >= TWENTYBAGGER_RETURN_PCT:
            twentybaggers.append(tk)

    n_universe_eff = len(ticker_results)
    actual_count = len(tenbaggers)
    delta_pct = (
        round((actual_count - DECISION_23_ASSUMED_COUNT) / DECISION_23_ASSUMED_COUNT * 100, 1)
        if DECISION_23_ASSUMED_COUNT else None
    )

    if actual_count < DECISION_23_INCONSISTENT_HARD_LO:
        v_label = "inconsistent"
        v_msg = (
            f"{actual_count} < {DECISION_23_INCONSISTENT_HARD_LO} — 결정 23 의 114개 가정과 격차 큼. "
            "lookback 짧음(10년 vs 30년) + survivorship 잔존 고려해도 underestimate. "
            "결정 23 수치 자체 출처 (Perplexity 인용) 재검증 필요."
        )
    elif actual_count < DECISION_23_CONSISTENT_LO:
        v_label = "over_estimate"
        v_msg = (
            f"{actual_count} < {DECISION_23_CONSISTENT_LO} — 결정 23 의 114개가 "
            "30년 lookback 기준이라면 본 10년 풀스캔으로는 underestimate 가 자연. "
            "단 50% 미만이면 결정 23 수치 자체 over_estimate 의심."
        )
    elif actual_count <= DECISION_23_CONSISTENT_HI:
        v_label = "consistent"
        v_msg = (
            f"{actual_count} ∈ [{DECISION_23_CONSISTENT_LO}, {DECISION_23_CONSISTENT_HI}] — "
            "결정 23 의 114개 수치와 정합 (10년 lookback 으로 30년 추정치 근접)."
        )
    else:
        v_label = "under_estimate"
        v_msg = (
            f"{actual_count} > {DECISION_23_CONSISTENT_HI} — 결정 23 의 114개가 "
            "30년 기준이면 본 10년 풀스캔 수치가 더 큰 것은 모순. "
            "Perplexity 인용 출처 재검증 + survivorship bias 영향 정량화 필요."
        )

    return {
        "reached_5r_unique_tickers": n_5r,
        "reached_10r_unique_tickers": n_10r_excursion,
        "reached_10r_pct_of_5r_reached": (
            round(n_10r_excursion / n_5r * 100, 2) if n_5r > 0 else None
        ),
        "reached_10r_pct_of_universe": (
            round(n_10r_excursion / n_universe_eff * 100, 2) if n_universe_eff > 0 else None
        ),
        "reached_20r_unique_tickers": n_20r_excursion,
        "tenbagger_unique_tickers_price_10x": actual_count,
        "tenbagger_sample": tenbaggers[:20],
        "twentybagger_unique_tickers_price_20x": len(twentybaggers),
        "comparison_to_decision_23": {
            "decision_23_assumed_count": DECISION_23_ASSUMED_COUNT,
            "actual_count": actual_count,
            "delta_pct": delta_pct,
            "lookback_years_assumed": 30,
            "lookback_years_actual": 10,
            "verdict": v_label,
            "verdict_message": v_msg,
        },
    }


def _compute_bessembinder_check(ticker_results: dict) -> dict[str, Any]:
    """D5 — Bessembinder 2018 (wealth concentration) 검증.

    각 종목 lifetime buy-and-hold = (exit_close - entry_close) 단위 가격 차이.
    동일 자본 1단위 진입 가정 → wealth = max(return_pct, 0) (positive wealth share).
    Bessembinder finding: 미국은 top 4% 가 전체 wealth 100% (median 음수).
    """
    rets: list[float] = []
    wealths: list[tuple[str, float]] = []  # (ticker, positive_wealth_unit)
    for tk, r in ticker_results.items():
        bh = r.get("buy_and_hold") or {}
        ret = bh.get("return_pct")
        if ret is None:
            continue
        rets.append(ret)
        # 1단위 자본 → 양의 wealth = max(ret/100, 0). 음수는 손실 → wealth 미생성
        wealths.append((tk, max(ret / 100.0, 0.0)))

    if not rets:
        return {"status": "insufficient_data"}

    n = len(rets)
    rets_sorted = sorted(rets)

    def _pct(p: float) -> float:
        return round(rets_sorted[min(int(n * p), n - 1)], 2)

    median_ret = round(rets_sorted[n // 2], 2)
    skew = _skewness(rets)

    # wealth share — 양의 wealth 기준 top N%
    pos_wealths = sorted((w for _, w in wealths), reverse=True)
    total_pos_wealth = sum(pos_wealths)
    pct_winners = round(sum(1 for w in pos_wealths if w > 0) / n * 100, 2) if n else None

    def _share(top_pct: float) -> Optional[float]:
        if total_pos_wealth <= 0 or n == 0:
            return None
        k = max(1, int(n * top_pct / 100))
        top_sum = sum(pos_wealths[:k])
        return round(top_sum / total_pos_wealth * 100, 2)

    top_1 = _share(1)
    top_4 = _share(4)
    top_10 = _share(10)

    # interpretation 자동 생성
    if top_4 is None:
        interp = "insufficient_data"
    else:
        # 미국 100% (Bessembinder) 와 비교
        delta_top4 = top_4 - BESSEMBINDER_US_TOP_4PCT_WEALTH_SHARE
        delta_median = median_ret - BESSEMBINDER_US_MEDIAN_RETURN_PCT
        bits = []
        if abs(delta_top4) <= 10:
            bits.append("top4% wealth share = 미국 Bessembinder 와 정합 (100% 부근)")
        elif top_4 >= 110:
            bits.append("top4% wealth share > 110% (음수 wealth 의 양수 보정 결과 ≠ 실제 수익자)")
        elif top_4 >= 80:
            bits.append("top4% wealth share = 미국 대비 약간 낮음 (한국 wealth concentration 약함)")
        else:
            bits.append(f"top4% wealth share = {top_4}% (미국 100% 대비 분산형)")

        if median_ret < 0:
            bits.append(f"한국 median lifetime return {median_ret}% < 0 = 미국 패턴 일치")
        elif median_ret < 20:
            bits.append(f"한국 median {median_ret}% > 0 (미국 -2% 대비 우호 — survivorship 가능)")
        else:
            bits.append(f"한국 median {median_ret}% — survivorship bias 강함 의심")

        if (skew or 0) >= 3:
            bits.append(f"return skewness {skew} >= 3 = 강한 우편향 (Bessembinder 패턴 일치)")
        elif skew is not None:
            bits.append(f"return skewness {skew} (Bessembinder 미국 보통 5+ 대비 약함)")

        interp = " / ".join(bits)

    return {
        "n_tickers": n,
        "median_total_return_pct": median_ret,
        "mean_total_return_pct": round(sum(rets) / n, 2),
        "p25_return_pct": _pct(0.25),
        "p75_return_pct": _pct(0.75),
        "p90_return_pct": _pct(0.90),
        "p95_return_pct": _pct(0.95),
        "max_return_pct": _pct(0.999),
        "pct_positive_winners": pct_winners,
        "return_skewness": skew,
        "top_1pct_wealth_share_pct": top_1,
        "top_4pct_wealth_share_pct": top_4,
        "top_10pct_wealth_share_pct": top_10,
        "us_benchmark": {
            "top_4pct_wealth_share_us": BESSEMBINDER_US_TOP_4PCT_WEALTH_SHARE,
            "median_total_return_us": BESSEMBINDER_US_MEDIAN_RETURN_PCT,
            "source": "Bessembinder 2018 — Do Stocks Outperform Treasury Bills?",
        },
        "interpretation": interp,
    }


def _compute_phase_1_1_atr_review(
    ticker_results: dict, universe_meta: dict
) -> Optional[dict]:
    """Phase 1.1 ATR×2.5 적정성 분석 — 시총 tier 별 stop_loss_rate.

    interpretation 자동 생성:
      large stop_loss > 60% → ATR×2.5 부적합 강한 신호
      40~60%               → borderline. multiplier 상향 검토
      < 40%                → 정상. 5/17 4-cell 백테스트 schedule 대로
    """
    if not universe_meta:
        return None

    tier_stop_rates: dict[str, list[float]] = {"large": [], "mid": [], "small": []}
    all_atr_pcts: list[float] = []
    all_days_to_5r: list[int] = []

    for tk, r in ticker_results.items():
        cap = (universe_meta.get(tk) or {}).get("market_cap") or 0
        if cap >= TIER_LARGE_MIN_KRW:
            tier = "large"
        elif cap >= TIER_MID_MIN_KRW:
            tier = "mid"
        else:
            tier = "small"

        n_total = r.get("n_entries") or 0
        n_stop = r.get("n_stop_loss") or 0
        if n_total > 0:
            tier_stop_rates[tier].append(n_stop / n_total)

        if r.get("avg_atr_pct") is not None:
            all_atr_pcts.append(r["avg_atr_pct"])
        if r.get("median_days_to_5r"):
            all_days_to_5r.append(r["median_days_to_5r"])

    def _mean(lst): return round(sum(lst) / len(lst), 4) if lst else None

    sl_by_tier = {t: _mean(v) for t, v in tier_stop_rates.items()}

    atr_dist: dict = {}
    if all_atr_pcts:
        srt = sorted(all_atr_pcts)
        n = len(srt)

        def _p(p): return round(srt[min(int(n * p), n - 1)], 4)

        atr_dist = {"p25": _p(0.25), "p50": _p(0.50), "p75": _p(0.75), "p90": _p(0.90)}

    avg_days_to_5r = _mean(all_days_to_5r)

    large_sl = sl_by_tier.get("large")
    if large_sl is None:
        interp = "tier=large 표본 부족 — 분석 불가"
    elif large_sl > 0.60:
        interp = (
            f"large tier stop_loss_rate={large_sl * 100:.1f}% > 60%. "
            f"ATR×2.5 한국 시장 부적합 강한 신호. "
            f"Phase 1.1 재검토 의제 큐잉 권고 (project_atr_dynamic_stop 4-cell 백테스트 우선)."
        )
    elif large_sl >= 0.40:
        interp = (
            f"large tier stop_loss_rate={large_sl * 100:.1f}% (40~60% borderline). "
            f"ATR multiplier 상향 (2.5 → 3.0) 비교 백테스트 권고."
        )
    else:
        interp = (
            f"large tier stop_loss_rate={large_sl * 100:.1f}% < 40%. "
            f"ATR×2.5 정상 작동. 5/17 4-cell 백테스트는 schedule 대로 진행 가능."
        )

    return {
        "stop_loss_rate_by_tier": sl_by_tier,
        "tier_thresholds_krw": {
            "large_min": TIER_LARGE_MIN_KRW,
            "mid_min": TIER_MID_MIN_KRW,
        },
        "atr_pct_distribution": atr_dist,
        "avg_days_to_5r": avg_days_to_5r,
        "interpretation": interp,
    }


# ─────────────────────────────────────────────────────────────────────
# Verdict
# ─────────────────────────────────────────────────────────────────────
def decide_verdict(unique_5r_count: int) -> dict[str, str]:
    if unique_5r_count >= VERDICT_OK_THRESHOLD:
        return {
            "verdict": "ok",
            "recommendation": (
                f"5R 도달 unique 종목 {unique_5r_count}개 (≥{VERDICT_OK_THRESHOLD}). "
                f"통계 표본 충분. Phase 1.3 (Chandelier exit + Thesis Break) 명세 진입 가능."
            ),
        }
    if unique_5r_count >= VERDICT_MONITORING_THRESHOLD:
        return {
            "verdict": "monitoring",
            "recommendation": (
                f"5R 도달 {unique_5r_count}개 ({VERDICT_MONITORING_THRESHOLD}~"
                f"{VERDICT_OK_THRESHOLD - 1} 구간). 보강 필요: "
                f"(a) lookback 확장 (b) entry 빈도 상향 (월/주) (c) ATR multiplier 변형 비교."
            ),
        }
    return {
        "verdict": "insufficient",
        "recommendation": (
            f"5R 도달 {unique_5r_count}개 (<{VERDICT_MONITORING_THRESHOLD}). "
            f"통계 표본 부족 — Phase 1.3 룰 자체 재설계 권고. "
            f"대안: (a) ATR multiplier 하향 (2.0/1.5) (b) max_days 단축 (60d) "
            f"(c) Trailing-only 전략."
        ),
    }


# ─────────────────────────────────────────────────────────────────────
# Run analysis
# ─────────────────────────────────────────────────────────────────────
def run_analysis(
    start_date: str = "2015-01-01",
    end_date: str = "2025-12-31",
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ"),
    sample_limit: Optional[int] = None,
    workers: int = MAX_KR_WORKERS,
    seed: int = 42,
    ticker_file: Optional[Path] = None,
    use_system_universe: bool = False,
    stratified_100: bool = False,
    system_target_size: int = 2000,
    apply_hard_floor_filter: bool = False,
    r_multiple_cap: Optional[float] = None,
    audit_path: Optional[Path] = None,
    time_cap_min: Optional[float] = None,
    partial_save_path: Optional[Path] = None,
) -> dict[str, Any]:
    if workers > MAX_KR_WORKERS:
        raise ValueError(
            f"workers={workers} > {MAX_KR_WORKERS} "
            f"(parallel_fetcher 결정 8 — KRX P50 hung 방지)"
        )

    t0 = time.time()
    end_ymd = end_date.replace("-", "")
    start_ymd = start_date.replace("-", "")

    # universe_meta — Step 2 시총 tier 분해용 (build_kr_universe 의 market/market_cap 보존)
    universe_meta: dict[str, dict] = {}
    universe_diagnostics: Optional[dict] = None

    if use_system_universe or stratified_100:
        try:
            entries, src_label, universe_diagnostics = load_universe_via_system(
                target_size=system_target_size,
                apply_hard_floor_filter=apply_hard_floor_filter,
            )
        except Exception as e:
            print(f"[error] system universe failed: {e}")
            print("[info] fallback to load_universe_kr (pykrx + whitelist)")
            universe, universe_source = load_universe_kr(end_ymd, markets, ticker_file=ticker_file)
        else:
            for e in entries:
                universe_meta[e["ticker"]] = {
                    "market": e.get("market"),
                    "market_cap": e.get("market_cap", 0),
                    "name": e.get("name"),
                }
            if stratified_100:
                universe = stratified_sample_100(entries)
                universe_source = f"stratified_dry_run_100__{src_label}"
            else:
                universe = sorted({e["ticker"] for e in entries})
                universe_source = src_label
    else:
        universe, universe_source = load_universe_kr(end_ymd, markets, ticker_file=ticker_file)
    print(f"[info] Universe size = {len(universe)} (markets={markets}, source={universe_source})")

    if sample_limit and sample_limit < len(universe):
        import random
        rng = random.Random(seed)
        universe = sorted(rng.sample(universe, sample_limit))
        print(f"[info] dry-run sample = {len(universe)} (seed={seed})")

    def _process(ticker: str):
        df = fetch_ohlcv_cached(ticker, start_ymd, end_ymd)
        if df is None or len(df) < MIN_BARS_BEFORE_ENTRY * 2:
            return ticker, None
        try:
            return ticker, analyze_ticker(
                ticker, df, start_date, end_date,
                r_multiple_cap=r_multiple_cap,
                audit_path=audit_path,
            )
        except Exception as e:
            print(f"[warn] analyze failed {ticker}: {e}")
            return ticker, None

    ticker_results: dict[str, dict] = {}
    completed = 0
    partial = False
    cap_s = time_cap_min * 60 if time_cap_min else None
    deadline = (t0 + cap_s) if cap_s else None
    last_partial_save_t = t0

    ex = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {ex.submit(_process, t): t for t in universe}
        for fu in as_completed(futures):
            if deadline and time.time() > deadline:
                print(f"[time-cap] {time_cap_min}min reached at "
                      f"{completed}/{len(universe)} — graceful abort")
                partial = True
                break
            try:
                tk, res = fu.result(timeout=30)
            except Exception as ex_:
                print(f"[warn] future error: {ex_}")
                completed += 1
                continue
            if res is not None:
                ticker_results[tk] = res
            completed += 1
            if completed % 50 == 0:
                n_5r = sum(1 for r in ticker_results.values() if r['had_5r_hit'])
                el = time.time() - t0
                print(f"[progress] {completed}/{len(universe)} "
                      f"(5R unique: {n_5r}, elapsed: {el:.0f}s)")
                # 부분 저장 (5분 간격)
                if partial_save_path and (time.time() - last_partial_save_t) > 300:
                    try:
                        partial_save_path.parent.mkdir(parents=True, exist_ok=True)
                        partial_save_path.write_text(json.dumps(
                            {"computed_at": datetime.now().isoformat(),
                             "completed": completed, "total": len(universe),
                             "n_tickers_ok": len(ticker_results),
                             "n_5r_unique_so_far": n_5r}, indent=2))
                        last_partial_save_t = time.time()
                    except Exception:
                        pass
    finally:
        # Python 3.9+ cancel_futures 지원 — in-flight 종료 대기 회피
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            ex.shutdown(wait=False)

    elapsed = time.time() - t0

    # 집계
    n_tickers_ok = len(ticker_results)
    n_5r_unique = sum(1 for r in ticker_results.values() if r["had_5r_hit"])
    total_entries = sum(r["n_entries"] for r in ticker_results.values())
    total_5r_hits = sum(r["n_5r_hits"] for r in ticker_results.values())
    total_stops = sum(r["n_stop_loss"] for r in ticker_results.values())
    total_max_days = sum(r["n_max_days"] for r in ticker_results.values())
    total_delisted = sum(r["n_delisted"] for r in ticker_results.values())

    excursions = sorted(r["max_excursion_r_overall"] for r in ticker_results.values())
    excursion_dist: dict[str, float] = {}
    if excursions:
        n = len(excursions)

        def _pct(p: float) -> float:
            idx = min(int(n * p), n - 1)
            return round(excursions[idx], 3)

        excursion_dist = {
            "min": round(excursions[0], 3),
            "p25": _pct(0.25),
            "median": round(median(excursions), 3),
            "mean": round(mean(excursions), 3),
            "p75": _pct(0.75),
            "p90": _pct(0.90),
            "p95": _pct(0.95),
            "p99": _pct(0.99),
            "max": round(excursions[-1], 3),
        }

    per_ticker_s = elapsed / max(n_tickers_ok, 1)
    full_universe_size_estimate = 2500  # KOSPI+KOSDAQ 대략
    estimated_full_run_min = (
        round(per_ticker_s * full_universe_size_estimate / 60, 1)
        if sample_limit else None
    )

    # ── Step 2 분해 (universe_meta 있을 때만, 없으면 None) ──
    tier_breakdown: Optional[dict] = None
    year_breakdown: Optional[dict] = None
    if universe_meta:
        # 시총 tier — 처리된 ticker 만 집계 (universe_meta 와 ticker_results intersect)
        meta_for_processed = [
            (tk, universe_meta.get(tk, {}))
            for tk in ticker_results.keys() if tk in universe_meta
        ]
        caps = sorted(
            (m.get("market_cap") or 0) for _, m in meta_for_processed if (m.get("market_cap") or 0) > 0
        )
        if caps:
            n_caps = len(caps)
            mid_lo = caps[int(n_caps * 0.33)]
            mid_hi = caps[int(n_caps * 0.67)]

            def _tier(cap: int) -> str:
                if cap >= mid_hi:
                    return "large"
                if cap >= mid_lo:
                    return "mid"
                return "small"

            tier_counts = {"large": {"n_total": 0, "n_5r": 0},
                           "mid": {"n_total": 0, "n_5r": 0},
                           "small": {"n_total": 0, "n_5r": 0}}
            for tk, meta in meta_for_processed:
                cap = meta.get("market_cap") or 0
                if cap <= 0:
                    continue
                tier = _tier(cap)
                tier_counts[tier]["n_total"] += 1
                if ticker_results[tk]["had_5r_hit"]:
                    tier_counts[tier]["n_5r"] += 1
            for t in tier_counts.values():
                t["rate_5r"] = round(t["n_5r"] / t["n_total"], 4) if t["n_total"] else None
            tier_breakdown = {
                "tier_thresholds_krw": {
                    "small_max_exclusive": int(mid_lo),
                    "mid_max_exclusive": int(mid_hi),
                },
                "counts": tier_counts,
            }

        # 연도별 5R hit 분포 (entry 시점 기준)
        year_counts: dict[int, int] = {}
        for r in ticker_results.values():
            for yr in (r.get("hit_years") or []):
                year_counts[yr] = year_counts.get(yr, 0) + 1
        if year_counts:
            year_breakdown = {
                str(y): year_counts[y] for y in sorted(year_counts.keys())
            }

    # ── D5 — decision_23 + Bessembinder ──
    decision_23 = _compute_decision_23_verification(ticker_results)
    bessembinder = _compute_bessembinder_check(ticker_results)

    # ── Phase 1.1 ATR×2.5 적정성 ──
    phase_1_1_review = _compute_phase_1_1_atr_review(ticker_results, universe_meta)

    decision = decide_verdict(n_5r_unique)
    if universe_source == "fallback_whitelist":
        # 표본이 시총 상위 45 종목 = survivorship 100% — verdict 신뢰도 낮음
        decision["recommendation"] = (
            "⚠ universe_source=fallback_whitelist (45 시총 상위) — survivorship bias 100% "
            "이므로 본 verdict 는 *스크립트 작동 검증* 한정. 광범위 verdict 는 "
            "--ticker-file 또는 pykrx ticker_list 복구 후 재실행. "
            + decision["recommendation"]
        )

    top_excursion = sorted(
        ticker_results.values(),
        key=lambda x: x["max_excursion_r_overall"],
        reverse=True,
    )[:20]

    return {
        "computed_at": datetime.now().isoformat(),
        "params": {
            "start_date": start_date,
            "end_date": end_date,
            "markets": list(markets),
            "atr_method": "wilder_ema_14",
            "atr_multiplier": ATR_MULTIPLIER,
            "max_hold_days": MAX_HOLD_DAYS,
            "min_bars_before_entry": MIN_BARS_BEFORE_ENTRY,
            "entry_frequency": "weekly_iso",
            "sample_limit": sample_limit,
            "seed": seed,
            "workers": workers,
            "universe_source": universe_source,
        },
        "execution": {
            "elapsed_s": round(elapsed, 1),
            "per_ticker_s": round(per_ticker_s, 3),
            "estimated_full_run_min": estimated_full_run_min,
            "estimated_full_universe_size": full_universe_size_estimate,
            "partial": partial,
            "n_processed": completed,
            "time_cap_min": time_cap_min,
        },
        "metrics": {
            "n_universe": len(universe),
            "n_tickers_with_data": n_tickers_ok,
            "n_5r_unique_tickers": n_5r_unique,
            "total_entries_simulated": total_entries,
            "total_5r_hits": total_5r_hits,
            "total_stop_loss": total_stops,
            "total_max_days": total_max_days,
            "total_delisted": total_delisted,
            "stop_loss_rate": round(total_stops / max(total_entries, 1), 4),
            "5r_hit_rate": round(total_5r_hits / max(total_entries, 1), 4),
        },
        "max_excursion_distribution_R": excursion_dist,
        "universe_diagnostics": universe_diagnostics,
        "tier_breakdown": tier_breakdown,
        "year_breakdown_5r_hits": year_breakdown,
        "phase_1_1_atr_review": phase_1_1_review,
        "decision_23_verification": decision_23,
        "bessembinder_check": bessembinder,
        "verdict": decision["verdict"],
        "verdict_threshold": {
            "ok_min": VERDICT_OK_THRESHOLD,
            "monitoring_min": VERDICT_MONITORING_THRESHOLD,
        },
        "recommendation": decision["recommendation"],
        "top_excursion_sample": [
            {
                "ticker": t["ticker"],
                "max_excursion_r": t["max_excursion_r_overall"],
                "n_entries": t["n_entries"],
                "n_5r_hits": t["n_5r_hits"],
            }
            for t in top_excursion
        ],
    }


def write_report(report: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))


def render_markdown(report: dict) -> str:
    p = report["params"]
    e = report["execution"]
    m = report["metrics"]
    d = report.get("max_excursion_distribution_R") or {}
    vt = report["verdict_threshold"]

    lines: list[str] = []
    lines.append("# Phase 1.3 표본 가능성 검증 결과")
    lines.append("")
    lines.append(f"**Computed at**: {report['computed_at']}")
    lines.append("")
    lines.append("## 입력")
    lines.append(f"- Period: {p['start_date']} ~ {p['end_date']}")
    lines.append(f"- Markets: {', '.join(p['markets'])}")
    lines.append(f"- ATR: Wilder EMA(14) × {p['atr_multiplier']} 손절")
    lines.append(f"- Max hold: {p['max_hold_days']} 영업일")
    lines.append(f"- Entry: {p['entry_frequency']} 첫 영업일")
    lines.append(f"- Sample limit: {p['sample_limit'] or 'full'} (seed={p['seed']})")
    lines.append(f"- Universe source: **{p.get('universe_source', '?')}**")
    if p.get("universe_source") == "fallback_whitelist":
        lines.append(
            "  - ⚠ pykrx ticker_list 실패 → 시총 상위 45종목 화이트리스트. "
            "survivorship bias 100% — verdict 일반화 불가."
        )
    lines.append("")
    lines.append("## 실행")
    lines.append(f"- elapsed: {e['elapsed_s']}s ({e['elapsed_s'] / 60:.1f} min)")
    lines.append(f"- per ticker: {e['per_ticker_s']}s")
    if e.get("estimated_full_run_min"):
        lines.append(
            f"- full run 추정 (~{e['estimated_full_universe_size']}종목): "
            f"{e['estimated_full_run_min']}분"
        )
    lines.append("")
    lines.append("## 핵심 지표")
    lines.append(f"- universe: {m['n_universe']} → 데이터 OK: {m['n_tickers_with_data']}")
    lines.append(f"- **5R 도달 unique 종목: {m['n_5r_unique_tickers']}**")
    lines.append(f"- 총 시뮬 진입: {m['total_entries_simulated']}")
    lines.append(f"  - 5R hit: {m['total_5r_hits']} ({m['5r_hit_rate'] * 100:.2f}%)")
    lines.append(f"  - stop loss: {m['total_stop_loss']} ({m['stop_loss_rate'] * 100:.2f}%)")
    lines.append(f"  - max days 만기: {m['total_max_days']}")
    lines.append(f"  - delisted/insufficient: {m['total_delisted']}")
    if d:
        lines.append("")
        lines.append("## Max Excursion 분포 (R-multiple 단위)")
        lines.append(
            f"- min: {d.get('min')} / p25: {d.get('p25')} / "
            f"median: {d.get('median')} / mean: {d.get('mean')}"
        )
        lines.append(
            f"- p75: {d.get('p75')} / p90: {d.get('p90')} / "
            f"p95: {d.get('p95')} / p99: {d.get('p99')} / max: {d.get('max')}"
        )
    if e.get("partial"):
        lines.append("")
        lines.append(
            f"## ⚠ 부분 실행 (time-cap {e.get('time_cap_min')}min) — "
            f"{e.get('n_processed')}/{m['n_universe']} 처리. verdict 는 처리분 기준."
        )
    tb = report.get("tier_breakdown")
    if tb:
        lines.append("")
        lines.append("## 시총 tier 별 5R 도달 비율")
        thr = tb["tier_thresholds_krw"]
        lines.append(
            f"- tier 임계 (KRW): small < {thr['small_max_exclusive']:,} ≤ mid < "
            f"{thr['mid_max_exclusive']:,} ≤ large"
        )
        for t in ("large", "mid", "small"):
            c = tb["counts"][t]
            rate = c.get("rate_5r")
            rate_str = f"{rate * 100:.1f}%" if rate is not None else "n/a"
            lines.append(f"- {t}: {c['n_5r']}/{c['n_total']} = {rate_str}")
    yb = report.get("year_breakdown_5r_hits")
    if yb:
        lines.append("")
        lines.append("## 연도별 5R hit 분포 (entry 시점 기준)")
        for yr in sorted(yb.keys()):
            lines.append(f"- {yr}: {yb[yr]}")

    ud = report.get("universe_diagnostics")
    if ud:
        lines.append("")
        lines.append("## Universe diagnostics (Hard Floor)")
        lines.append(
            f"- before: {ud['before_hard_floor']} → after: {ud['after_hard_floor']} "
            f"(excluded: {ud['excluded_count']})"
        )
        lines.append("- exclusion reasons:")
        for k, v in ud["exclusion_reasons"].items():
            if v > 0:
                lines.append(f"  - {k}: {v}")
        ed = ud.get("excluded_tickers_market_cap_distribution") or {}
        if ed:
            lines.append(
                f"- excluded market_cap (KRW): "
                f"p25={ed.get('p25', 0):,} / p50={ed.get('p50', 0):,} / p75={ed.get('p75', 0):,}"
            )

    pr = report.get("phase_1_1_atr_review")
    if pr:
        lines.append("")
        lines.append("## Phase 1.1 ATR×2.5 적정성 분석")
        sl = pr["stop_loss_rate_by_tier"]
        thr = pr["tier_thresholds_krw"]
        lines.append(
            f"- tier 임계 (KRW): large ≥ {thr['large_min']:,} / "
            f"mid ≥ {thr['mid_min']:,} / small < {thr['mid_min']:,}"
        )
        for t in ("large", "mid", "small"):
            v = sl.get(t)
            v_str = f"{v * 100:.1f}%" if v is not None else "n/a"
            lines.append(f"- {t} stop_loss_rate (entry 평균): {v_str}")
        ad = pr.get("atr_pct_distribution") or {}
        if ad:
            lines.append(
                f"- ATR%/price 분포: p25={ad.get('p25')} / p50={ad.get('p50')} / "
                f"p75={ad.get('p75')} / p90={ad.get('p90')}"
            )
        if pr.get("avg_days_to_5r"):
            lines.append(f"- avg days to 5R hit: {pr['avg_days_to_5r']:.0f}")
        lines.append(f"- **interpretation**: {pr['interpretation']}")

    d23 = report.get("decision_23_verification")
    if d23:
        lines.append("")
        lines.append("## D5 — 결정 23 (한국 텐버거 114개) 검증")
        lines.append(f"- 5R 도달: {d23.get('reached_5r_unique_tickers')}")
        lines.append(
            f"- R-multiple 10R 도달: {d23.get('reached_10r_unique_tickers')} "
            f"({d23.get('reached_10r_pct_of_5r_reached')}% of 5R 도달, "
            f"{d23.get('reached_10r_pct_of_universe')}% of universe)"
        )
        lines.append(f"- R-multiple 20R 도달: {d23.get('reached_20r_unique_tickers')}")
        lines.append(
            f"- **텐버거 (price 10x = +900%) 도달: {d23.get('tenbagger_unique_tickers_price_10x')}**"
        )
        lines.append(
            f"- 20-bagger (price 20x = +1900%) 도달: {d23.get('twentybagger_unique_tickers_price_20x')}"
        )
        cmp_ = d23.get("comparison_to_decision_23") or {}
        lines.append(
            f"- 결정 23 비교: 가정 {cmp_.get('decision_23_assumed_count')}개 (30년) vs "
            f"실측 {cmp_.get('actual_count')}개 (10년) → "
            f"Δ {cmp_.get('delta_pct')}% / verdict = **{cmp_.get('verdict')}**"
        )
        lines.append(f"  - {cmp_.get('verdict_message', '')}")
        sample = d23.get("tenbagger_sample") or []
        if sample:
            lines.append(f"  - 텐버거 샘플 (최대 20개): {', '.join(sample[:20])}")

    bess = report.get("bessembinder_check")
    if bess and bess.get("status") != "insufficient_data":
        lines.append("")
        lines.append("## D5 — Bessembinder 2018 wealth concentration 검증")
        lines.append(f"- n_tickers (lifetime return 산출): {bess.get('n_tickers')}")
        lines.append(
            f"- median return: {bess.get('median_total_return_pct')}% "
            f"(미국 Bessembinder = {BESSEMBINDER_US_MEDIAN_RETURN_PCT}%)"
        )
        lines.append(
            f"- mean: {bess.get('mean_total_return_pct')}% / "
            f"p25: {bess.get('p25_return_pct')}% / p75: {bess.get('p75_return_pct')}% / "
            f"p90: {bess.get('p90_return_pct')}% / p95: {bess.get('p95_return_pct')}% / "
            f"max: {bess.get('max_return_pct')}%"
        )
        lines.append(
            f"- positive winners: {bess.get('pct_positive_winners')}% / "
            f"return skewness: {bess.get('return_skewness')}"
        )
        lines.append("- wealth share (positive 만):")
        lines.append(f"  - top 1%: {bess.get('top_1pct_wealth_share_pct')}%")
        lines.append(
            f"  - top 4%: {bess.get('top_4pct_wealth_share_pct')}% "
            f"(미국 ≈ {BESSEMBINDER_US_TOP_4PCT_WEALTH_SHARE}%)"
        )
        lines.append(f"  - top 10%: {bess.get('top_10pct_wealth_share_pct')}%")
        lines.append(f"- **interpretation**: {bess.get('interpretation')}")
    lines.append("")
    lines.append(f"## Verdict: **{report['verdict'].upper()}**")
    lines.append(
        f"- 임계: ok ≥ {vt['ok_min']} / monitoring ≥ {vt['monitoring_min']} "
        f"/ 그 외 = insufficient"
    )
    lines.append(f"- {report['recommendation']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1.3 5R 표본 가능성 검증")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument(
        "--market", default="all", choices=["all", "KOSPI", "KOSDAQ"]
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="dry-run: N 종목 무작위 sampling. None=전체",
    )
    parser.add_argument(
        "--workers", type=int, default=MAX_KR_WORKERS,
        help=f"KR pykrx 병렬 (≤ {MAX_KR_WORKERS})",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--ticker-file", default=None,
        help="ticker 리스트 파일 (한 줄에 1개). pykrx universe 우회용",
    )
    parser.add_argument(
        "--use-system-universe", action="store_true",
        help="api.collectors.universe_builder.build_kr_universe 활용 (KRX OpenAPI K1)",
    )
    parser.add_argument(
        "--stratified-100", action="store_true",
        help="KOSPI 상위30+중위30 + KOSDAQ 상위20+중위20 = 100 (cherry-picking 회피)",
    )
    parser.add_argument(
        "--system-target-size", type=int, default=2000,
        help="--use-system-universe / --stratified-100 의 build_kr_universe target_size",
    )
    parser.add_argument(
        "--apply-hard-floor", action="store_true",
        help="Hard Floor 자동 제외 (페니/관리/거래정지/저거래대금) + universe_diagnostics 산출",
    )
    parser.add_argument(
        "--r-multiple-cap", type=float, default=None,
        help="max_excursion_r cap (예: 50). 초과 entry 는 r_multiple_outliers.jsonl audit 후 strip",
    )
    parser.add_argument(
        "--audit-path", default=None,
        help=f"R-multiple outlier audit jsonl 경로. 기본: {OUTLIER_AUDIT_PATH}",
    )
    parser.add_argument(
        "--time-cap-min", type=float, default=None,
        help="실행 시간 cap (분). 도달 시 graceful abort 후 부분 결과로 verdict 산출",
    )
    parser.add_argument(
        "--partial-save", default=None,
        help="진행 상황 부분 저장 경로 (5분 간격). cron 모니터링용",
    )
    parser.add_argument(
        "--output", default=None,
        help="JSON 출력 경로. None=auto data/analysis/5r_feasibility_<date>.json",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.workers > MAX_KR_WORKERS:
        print(
            f"[error] workers={args.workers} > {MAX_KR_WORKERS} "
            f"(parallel_fetcher 결정 8 — KRX P50 hung 방지)",
            file=sys.stderr,
        )
        return 2

    markets = ("KOSPI", "KOSDAQ") if args.market == "all" else (args.market,)

    report = run_analysis(
        start_date=args.start,
        end_date=args.end,
        markets=markets,
        sample_limit=args.limit,
        workers=args.workers,
        seed=args.seed,
        ticker_file=Path(args.ticker_file) if args.ticker_file else None,
        use_system_universe=args.use_system_universe,
        stratified_100=args.stratified_100,
        system_target_size=args.system_target_size,
        apply_hard_floor_filter=args.apply_hard_floor,
        r_multiple_cap=args.r_multiple_cap,
        audit_path=Path(args.audit_path) if args.audit_path else OUTLIER_AUDIT_PATH,
        time_cap_min=args.time_cap_min,
        partial_save_path=Path(args.partial_save) if args.partial_save else None,
    )

    if args.output:
        out_path = Path(args.output)
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
        if args.stratified_100:
            suffix = "_strat100"
        elif args.limit:
            suffix = f"_dry{args.limit}"
        else:
            suffix = ""
        out_path = OUTPUT_DIR / f"5r_feasibility_{date_str}{suffix}.json"

    write_report(report, out_path)

    if not args.quiet:
        print()
        print(render_markdown(report))
        print()
        print(f"[saved] {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
