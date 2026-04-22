"""
VAMS Validation — 사전 약속 판정 기준을 코드에 고정.

3·6·12개월 체크포인트에서 "실거래로 전환해도 되는가"를 판정하는 6개 지표.
결과 본 후 기준을 조정하지 않도록 임계값은 config.py 환경변수로만 변경 가능.

입력:
  - data/history/YYYY-MM-DD.json 일일 스냅샷
    · vams.total_asset        → VAMS 자산 시계열
    · market_summary.kospi.value → 벤치마크 시계열
  - history.json 매매 이력 (SELL.pnl → 승률·손익비)

지표:
  1) cumulative_return   VAMS vs 벤치마크 누적수익률
  2) mdd                 |VAMS MDD| / |벤치 MDD| 비율
  3) win_rate            승률 (SELL pnl > 0)
  4) profit_loss_ratio   평균수익 / |평균손실|
  5) sharpe              연율 샤프 (rf=0)
  6) regime_coverage     벤치마크가 -X% 조정 도달 여부

overall:
  - INSUFFICIENT_DATA: 최소 샘플(일수·매매수) 미달
  - FAIL:              샤프 < VAMS_REDESIGN_SHARPE 즉시 실패, 또는 2개 이상 미달
  - WATCH:             1개 미달 (관찰 지속)
  - PASS:              전 지표 통과
"""
import glob
import json
import math
import os
from datetime import datetime
from typing import List, Optional, Tuple

from api.config import (
    DATA_DIR,
    VAMS_PASS_EXCESS_RETURN_PP,
    VAMS_PASS_MDD_RATIO,
    VAMS_PASS_PROFIT_LOSS_RATIO,
    VAMS_PASS_SHARPE,
    VAMS_PASS_WIN_RATE,
    VAMS_REDESIGN_SHARPE,
    VAMS_REGIME_DRAWDOWN_PCT,
    VAMS_VALIDATION_MIN_DAYS,
    VAMS_VALIDATION_MIN_TRADES,
    VAMS_VALIDATION_START_DATE,
    now_kst,
)

_DEFAULT_SNAPSHOTS_DIR = os.path.join(DATA_DIR, "history")
_TRADING_DAYS_PER_YEAR = 252


def _parse_start_date(start_date: Optional[str]) -> Optional[datetime]:
    """'YYYY-MM-DD' 문자열을 datetime으로. 파싱 실패 또는 빈값이면 None."""
    if not start_date:
        return None
    try:
        return datetime.strptime(start_date.strip(), "%Y-%m-%d")
    except (ValueError, AttributeError):
        return None


def _load_daily_snapshots(
    snapshots_dir: str,
    start_date: Optional[str] = None,
) -> List[dict]:
    """data/history/YYYY-MM-DD.json 을 날짜순 로드. runs/ 같은 하위 디렉토리는 glob 패턴으로 자동 제외.
    start_date('YYYY-MM-DD')가 주어지면 그 날짜 이전 스냅샷은 제외."""
    if not os.path.isdir(snapshots_dir):
        return []
    paths = sorted(glob.glob(os.path.join(snapshots_dir, "????-??-??.json")))
    start_dt = _parse_start_date(start_date)
    out = []
    for p in paths:
        date_str = os.path.basename(p).replace(".json", "")
        if start_dt is not None:
            try:
                file_dt = datetime.strptime(date_str, "%Y-%m-%d")
                if file_dt < start_dt:
                    continue
            except ValueError:
                continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            out.append({"date": date_str, "data": data})
        except Exception:
            continue
    return out


def _extract_series(
    snapshots: List[dict],
) -> Tuple[List[str], List[float], List[float]]:
    """(dates, vams_adjusted_asset, kospi_value) 시계열.

    보정 자산(adjusted_total_asset)이 있으면 우선 사용, 없으면 total_asset 폴백.
    사용자 정의 "진짜 합격 기준"(adjusted > benchmark) 에 맞추기 위함.
    """
    dates, vams_vals, bench_vals = [], [], []
    for snap in snapshots:
        d = snap["data"]
        try:
            vams = d.get("vams", {}) or {}
            adjusted_asset = (
                vams.get("adjusted_performance", {}) or {}
            ).get("adjusted_total_asset")
            vams_v = float(adjusted_asset if adjusted_asset is not None
                           else vams.get("total_asset", 0) or 0)
            bench_v = float(
                d.get("market_summary", {}).get("kospi", {}).get("value", 0) or 0
            )
            if vams_v > 0 and bench_v > 0:
                dates.append(snap["date"])
                vams_vals.append(vams_v)
                bench_vals.append(bench_v)
        except (TypeError, ValueError):
            continue
    return dates, vams_vals, bench_vals


def _cumulative_return_pct(series: List[float]) -> float:
    if not series or series[0] <= 0:
        return 0.0
    return round(((series[-1] - series[0]) / series[0]) * 100, 2)


def _max_drawdown_pct(series: List[float]) -> float:
    """최대 낙폭 (음수 퍼센트). 빈 시계열은 0."""
    if not series:
        return 0.0
    peak = series[0]
    mdd = 0.0
    for v in series:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (v - peak) / peak * 100
            if dd < mdd:
                mdd = dd
    return round(mdd, 2)


def _daily_log_returns(series: List[float]) -> List[float]:
    out = []
    for i in range(1, len(series)):
        a, b = series[i - 1], series[i]
        if a > 0 and b > 0:
            out.append(math.log(b / a))
    return out


def _annualized_sharpe(series: List[float]) -> Optional[float]:
    """연율 샤프 (risk-free=0). 표본 2개 미만이거나 std=0이면 None."""
    rets = _daily_log_returns(series)
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    std = math.sqrt(var)
    if std == 0:
        return None
    return round((mean / std) * math.sqrt(_TRADING_DAYS_PER_YEAR), 2)


def _trade_stats(history: List[dict], start_date: Optional[str] = None) -> dict:
    """매매 통계. start_date 이전 SELL은 제외. date 필드는 'YYYY-MM-DD HH:MM' 형식 가정 (앞 10자 파싱)."""
    start_dt = _parse_start_date(start_date)
    sells = []
    for h in history:
        if h.get("type") != "SELL" or h.get("pnl") is None:
            continue
        if start_dt is not None:
            date_str = str(h.get("date", ""))[:10]
            try:
                sell_dt = datetime.strptime(date_str, "%Y-%m-%d")
                if sell_dt < start_dt:
                    continue
            except ValueError:
                continue  # 날짜 파싱 실패 시 보수적으로 제외
        sells.append(h)
    if not sells:
        return {
            "trades": 0, "wins": 0, "losses": 0,
            "win_rate": None, "avg_win": None, "avg_loss": None, "pl_ratio": None,
        }
    pnls = [float(h["pnl"]) for h in sells]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = len(wins) / len(pnls)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0  # 음수
    pl_ratio = (avg_win / abs(avg_loss)) if avg_loss < 0 else None
    return {
        "trades": len(pnls),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "pl_ratio": round(pl_ratio, 3) if pl_ratio is not None else None,
    }


def compute_validation_report(
    portfolio: dict,
    history: list,
    snapshots_dir: Optional[str] = None,
    start_date: Optional[str] = None,
) -> dict:
    """VAMS 성과를 사전 약속 기준으로 판정. 샘플 부족 시 각 pass 필드 = None.

    start_date('YYYY-MM-DD')가 주어지면 그 날짜 이전 스냅샷·SELL은 제외.
    None이면 config.VAMS_VALIDATION_START_DATE 폴백 (환경변수 설정 시 자동 적용).
    """
    if start_date is None:
        start_date = VAMS_VALIDATION_START_DATE or None
    snapshots_dir = snapshots_dir or _DEFAULT_SNAPSHOTS_DIR
    snapshots = _load_daily_snapshots(snapshots_dir, start_date=start_date)
    dates, vams_series, bench_series = _extract_series(snapshots)

    window = {
        "validation_start_configured": start_date,  # 사용자 지정 공식 시작일 (없으면 None)
        "start": dates[0] if dates else None,       # 실제 첫 스냅샷 날짜 (기간 카운트 기준)
        "end": dates[-1] if dates else None,
        "days": len(dates),
        "snapshot_count": len(snapshots),
    }

    trade = _trade_stats(history, start_date=start_date)
    days_ok = window["days"] >= VAMS_VALIDATION_MIN_DAYS
    trades_ok = trade["trades"] >= VAMS_VALIDATION_MIN_TRADES
    series_ok = bool(vams_series) and bool(bench_series)

    # ---- 지표 계산 ----
    vams_ret = _cumulative_return_pct(vams_series)
    bench_ret = _cumulative_return_pct(bench_series)
    excess_pp = round(vams_ret - bench_ret, 2)

    vams_mdd = _max_drawdown_pct(vams_series)
    bench_mdd = _max_drawdown_pct(bench_series)
    mdd_ratio = (
        round(abs(vams_mdd) / abs(bench_mdd), 3) if bench_mdd < 0 else None
    )

    sharpe = _annualized_sharpe(vams_series)

    regime_covered = abs(bench_mdd) >= VAMS_REGIME_DRAWDOWN_PCT

    # ---- pass 판정 (샘플 부족 → None) ----
    def _p(cond, insufficient):
        return None if insufficient else bool(cond)

    m_return = {
        "vams_return_pct": vams_ret,
        "benchmark_return_pct": bench_ret,
        "excess_pp": excess_pp,
        "threshold_pp": VAMS_PASS_EXCESS_RETURN_PP,
        "pass": _p(excess_pp >= VAMS_PASS_EXCESS_RETURN_PP, not series_ok or not days_ok),
    }
    m_mdd = {
        "vams_mdd_pct": vams_mdd,
        "benchmark_mdd_pct": bench_mdd,
        "ratio": mdd_ratio,
        "threshold_ratio": VAMS_PASS_MDD_RATIO,
        "pass": _p(
            mdd_ratio is not None and mdd_ratio <= VAMS_PASS_MDD_RATIO,
            not series_ok or mdd_ratio is None or not days_ok,
        ),
    }
    m_win = {
        **trade,
        "threshold": VAMS_PASS_WIN_RATE,
        "pass": _p(
            trade["win_rate"] is not None and trade["win_rate"] >= VAMS_PASS_WIN_RATE,
            not trades_ok,
        ),
    }
    m_pl = {
        "pl_ratio": trade["pl_ratio"],
        "avg_win": trade["avg_win"],
        "avg_loss": trade["avg_loss"],
        "threshold": VAMS_PASS_PROFIT_LOSS_RATIO,
        "pass": _p(
            trade["pl_ratio"] is not None and trade["pl_ratio"] >= VAMS_PASS_PROFIT_LOSS_RATIO,
            trade["pl_ratio"] is None or not trades_ok,
        ),
    }
    if sharpe is None:
        verdict = "INSUFFICIENT"
    elif sharpe < VAMS_REDESIGN_SHARPE:
        verdict = "REDESIGN"
    elif sharpe < VAMS_PASS_SHARPE:
        verdict = "WATCH"
    else:
        verdict = "PASS"
    m_sharpe = {
        "annualized": sharpe,
        "threshold_pass": VAMS_PASS_SHARPE,
        "threshold_redesign_below": VAMS_REDESIGN_SHARPE,
        "verdict": verdict,
        "pass": _p(
            sharpe is not None and sharpe >= VAMS_PASS_SHARPE,
            sharpe is None or not days_ok,
        ),
    }
    m_regime = {
        "covered": regime_covered,
        "peak_drawdown_pct": bench_mdd,
        "threshold_pct": -float(VAMS_REGIME_DRAWDOWN_PCT),
        "pass": _p(regime_covered, not series_ok or not days_ok),
    }

    # cost_efficiency — 비용이 알파를 먹지 않는지.
    # 합격: gap_pp_total < 0.5 × alpha_vs_benchmark  AND  alpha > 0
    # 알파가 0 이하면 애초에 벤치마크 미달이라 의미 없음 → pass=False 직행
    adj_perf = (portfolio.get("vams", {}) or {}).get("adjusted_performance", {}) or {}
    gap_pp_total = adj_perf.get("gap_pp")
    alpha = excess_pp
    cost_ratio = None
    if gap_pp_total is not None and alpha > 0:
        cost_ratio = round(float(gap_pp_total) / alpha, 3)
    m_cost = {
        "gap_pp_total": gap_pp_total,
        "alpha_pp": alpha,
        "cost_to_alpha_ratio": cost_ratio,
        "threshold_ratio_max": 0.5,
        "pass": _p(
            alpha > 0 and gap_pp_total is not None and cost_ratio is not None and cost_ratio < 0.5,
            not series_ok or not days_ok or gap_pp_total is None,
        ),
    }

    metrics = {
        "cumulative_return": m_return,
        "mdd": m_mdd,
        "win_rate": m_win,
        "profit_loss_ratio": m_pl,
        "sharpe": m_sharpe,
        "regime_coverage": m_regime,
        "cost_efficiency": m_cost,
    }

    # ---- overall ----
    insufficient = not (days_ok and trades_ok and series_ok)
    computed = [m["pass"] for m in metrics.values() if m["pass"] is not None]
    failed = sum(1 for p in computed if p is False)

    if insufficient:
        overall = "INSUFFICIENT_DATA"
    elif sharpe is not None and sharpe < VAMS_REDESIGN_SHARPE:
        overall = "FAIL"  # 샤프 재설계 임계는 즉시 실패
    elif not computed:
        overall = "INSUFFICIENT_DATA"
    elif failed == 0:
        overall = "PASS"
    elif failed == 1:
        overall = "WATCH"
    else:
        overall = "FAIL"

    return {
        "overall": overall,
        "window": window,
        "sample_checks": {
            "days_ok": days_ok,
            "days_required": VAMS_VALIDATION_MIN_DAYS,
            "trades_ok": trades_ok,
            "trades_required": VAMS_VALIDATION_MIN_TRADES,
            "series_ok": series_ok,
        },
        "metrics": metrics,
        "thresholds": {
            "excess_return_pp_min": VAMS_PASS_EXCESS_RETURN_PP,
            "mdd_ratio_max": VAMS_PASS_MDD_RATIO,
            "win_rate_min": VAMS_PASS_WIN_RATE,
            "profit_loss_ratio_min": VAMS_PASS_PROFIT_LOSS_RATIO,
            "sharpe_min": VAMS_PASS_SHARPE,
            "sharpe_redesign_below": VAMS_REDESIGN_SHARPE,
            "regime_drawdown_pct": VAMS_REGIME_DRAWDOWN_PCT,
        },
        "computed_at": now_kst().strftime("%Y-%m-%d %H:%M"),
    }
