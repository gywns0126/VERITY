"""
VAMS Validation — active behavior window and registered thresholds.

The active window is separate from legacy diagnostics. T/N are reported as
evidence diagnostics; fixed sample counts do not authorize a verdict.

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
  7) expectancy          완료 거래 기대값(R)
  8) sqn                 완료 거래 품질
  9) cost_efficiency     비용 누수가 초과수익을 잠식하는지

overall:
  - INSUFFICIENT_DATA: 필수 시계열 부재
  - MEASUREMENT_INCOMPLETE: 판정 지표 일부 측정 불가
  - FAIL:              샤프 < VAMS_REDESIGN_SHARPE 즉시 실패, 또는 2개 이상 미달
  - WATCH:             1개 미달 (관찰 지속)
  - PASS:              전 지표 통과
"""
import glob
import json
import math
import statistics
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
    VAMS_MIN_EXPECTANCY_R,
    VAMS_MIN_SQN,
    VAMS_REDESIGN_SHARPE,
    VAMS_REGIME_DRAWDOWN_PCT,
    VAMS_VALIDATION_MIN_DAYS,
    VAMS_VALIDATION_MIN_TRADES,
    VAMS_VALIDATION_START_DATE,
    VAMS_VALIDATION_LEGACY_START_DATE,
    VAMS_GATE_RULE_VERSION,
    now_kst,
)

_DEFAULT_SNAPSHOTS_DIR = os.path.join(DATA_DIR, "history")
_TRADING_DAYS_PER_YEAR = 252
_GATE_METRIC_KEYS = (
    "cumulative_return",
    "mdd",
    "win_rate",
    "profit_loss_ratio",
    "expectancy",
    "sqn",
    "sharpe",
    "regime_coverage",
    "cost_efficiency",
)


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


def _daily_simple_returns(series: List[float]) -> List[float]:
    out = []
    for i in range(1, len(series)):
        a, b = series[i - 1], series[i]
        if a > 0 and b > 0:
            out.append((b - a) / a)
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


# 2026-06-03 — 과적합 인지 Sharpe 유의성. raw Sharpe 는 저N 에서 부풀려짐 →
# PSR/DSR(Bailey-López de Prado) 병기로 "이 Sharpe 가 통계적으로 유의한가 /
# 다중검정 착시인가" 노출. 1인 운영자 자기기만 가드 (최강 루프의 validate rigor).
# n_trials = Brain 결합 factor 폭 ≈ 다중검정 횟수 (보수 가정, 출력에 라벨 노출).
_DSR_N_TRIALS_ASSUMED = 10


def _sharpe_significance(series: List[float]) -> dict:
    """per-period Sharpe → PSR(SR>0 유의?) + DSR(다중검정 보정). 관측 only.

    🚨 verdict/pass 게이트엔 미반영 (RULE 7 — 게이트 DSR 반영은 사전등록 후).
    psr.py 재사용 (신규 산식 0). 저N 에선 미달이 정상 (= 엣지 미증명 정직 신호).
    """
    try:
        rets = _daily_log_returns(series)
        if len(rets) < 4:
            return {"psr": None, "dsr": None, "_note": "표본<4 — 유의성 측정 불가"}
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        std = math.sqrt(var)
        if std == 0:
            return {"psr": None, "dsr": None, "_note": "std=0"}
        sr_pp = mean / std  # per-period(비연율) Sharpe — PSR/DSR 표준 입력
        T = len(rets)
        from api.quant.alpha.psr import compute_psr, compute_deflated_sharpe_ratio
        psr = compute_psr(sr_pp, 0.0, T, returns=rets)
        dsr = compute_deflated_sharpe_ratio(sr_pp, T, _DSR_N_TRIALS_ASSUMED, returns=rets)
        # psr.py quirk: compute_deflated_sharpe_ratio 는 deflated benchmark 로
        # compute_psr 위임 → DSR 확률이 "psr" 키로 반환 (n_trials<1 시만 "dsr":None).
        _dsr = dsr.get("psr", dsr.get("dsr"))
        return {
            "psr": psr.get("psr"),
            "dsr": _dsr,
            "T": T,
            "n_trials_assumed": _DSR_N_TRIALS_ASSUMED,
            "significant_95": (_dsr is not None and _dsr >= 0.95),
            "_note": ("관측 only — verdict 미반영. PSR=SR>0 유의확률, "
                      "DSR≥0.95=다중검정 보정 95% 신뢰. 저N 미달=엣지 미증명 정상"),
        }
    except Exception as e:
        return {"psr": None, "dsr": None, "_error": str(e)[:60]}


def _trade_stats(history: List[dict], start_date: Optional[str] = None) -> dict:
    """매매 통계. start_date 이전 SELL은 제외. date 필드는 'YYYY-MM-DD HH:MM' 형식 가정 (앞 10자 파싱)."""
    start_dt = _parse_start_date(start_date)
    # 2026-06-17 사전등록 fix (PM 승인): R-multiple 부분익절(PARTIAL_SELL.partial_pnl)을 종목
    # episode 의 종가 SELL 에 합산 = 1 진입 → 1 trade 통합 실현손익. 기존엔 partial_pnl(키 상이)
    # + type!=SELL 로 전량 제외돼 승자 이익이 win_rate/expectancy/SQN 서 invisible(게이트 보수 왜곡).
    # 측정 정의 교정(임계 튜닝 아님). 현 오염 0건(PARTIAL_SELL 0/SELL 13) 상태에서 사전 확정.
    # 🚨 2026-08-05 — 원장 재생 SoT 로 이관 (api/vams/trade_ledger).
    #   ① 보유 0 상태 매도(유령) 배제 — 2026-07-20 감사가 잡은 dev-mode 오염의 **잔존 기록**.
    #      버그는 ec7a66111 로 수정됐으나 이미 적재된 58건이 게이트 통계를 오염시키고 있었다
    #      (리셋 후 SELL 70 = 실제 12 + 유령 58, 유령 손익 −1,396,639원).
    #   ② simulation_stats 와 **같은 정의** 공유 — 같은 원장을 다르게 읽어 4.8배 괴리했던
    #      2026-08-05 사고(#290) 재발 방지. "거래 1건"의 정의는 한 곳에만 있어야 한다.
    from api.vams.trade_ledger import episode_pnls
    _since = start_dt.strftime("%Y-%m-%d") if start_dt is not None else None
    pnls, _led = episode_pnls(history, since=_since)
    if not pnls:
        return {
            "trades": 0, "wins": 0, "losses": 0,
            "win_rate": None, "avg_win": None, "avg_loss": None, "pl_ratio": None,
            "expectancy_r": None, "sqn": None, "r_std": None,
        }
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = len(wins) / len(pnls)
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0  # 음수
    pl_ratio = (avg_win / abs(avg_loss)) if avg_loss < 0 else None
    # Expectancy (R-multiple, 2026-05-16 Perplexity MED-D1 / config VAMS_MIN_EXPECTANCY_R):
    # E[R] = win_rate × (avg_win/|avg_loss|) − loss_rate = win_rate × pl_ratio − (1−win_rate).
    # 1 단위 risk(=|avg_loss|) 당 평균 보상. avg_loss=0(무손실) → R 기준 미정의(None).
    expectancy_r = (round(win_rate * pl_ratio - (1 - win_rate), 3)
                    if pl_ratio is not None else None)
    # SQN (Van Tharp System Quality Number, 2026-06-07 Perplexity) = mean(R)/σ(R) × √min(N,100).
    # expectancy(일관성=σ) + 표본(N) 동시 반영 → raw expectancy 보다 robust. R = pnl/|avg_loss|.
    sqn = None
    r_std = None
    _abs_loss = abs(avg_loss) if avg_loss < 0 else None
    if _abs_loss and len(pnls) >= 2:
        r_mults = [p / _abs_loss for p in pnls]
        sd_r = statistics.pstdev(r_mults)
        r_std = round(sd_r, 6)
        if sd_r > 0:
            sqn = round((statistics.mean(r_mults) / sd_r) * math.sqrt(min(len(pnls), 100)), 3)
    return {
        "trades": len(pnls),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "pl_ratio": round(pl_ratio, 3) if pl_ratio is not None else None,
        "expectancy_r": expectancy_r,
        "sqn": sqn,
        "r_std": r_std,
    }


def _regime_context_safe() -> dict:
    """국면 맥락 조회 — 실패해도 게이트 산출을 죽이지 않는다.

    🚨 advisory only. 이 값은 어떤 pass/verdict 에도 반영되지 않는다.
    """
    try:
        from api.vams.regime_context import describe
        return describe()
    except Exception as e:
        return {"advisory_only": True, "error": f"국면 맥락 산출 실패: {str(e)[:120]}"}


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
        "rule_version": VAMS_GATE_RULE_VERSION,
        "used_by_gate": True,
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
        "pass": _p(excess_pp >= VAMS_PASS_EXCESS_RETURN_PP, not series_ok),
    }
    m_mdd = {
        "vams_mdd_pct": vams_mdd,
        "benchmark_mdd_pct": bench_mdd,
        "ratio": mdd_ratio,
        "threshold_ratio": VAMS_PASS_MDD_RATIO,
        "pass": _p(
            mdd_ratio is not None and mdd_ratio <= VAMS_PASS_MDD_RATIO,
            not series_ok or mdd_ratio is None,
        ),
    }
    m_win = {
        **trade,
        "threshold": VAMS_PASS_WIN_RATE,
        "pass": _p(
            trade["win_rate"] is not None and trade["win_rate"] >= VAMS_PASS_WIN_RATE,
            trade["win_rate"] is None,
        ),
    }
    m_pl = {
        "pl_ratio": trade["pl_ratio"],
        "avg_win": trade["avg_win"],
        "avg_loss": trade["avg_loss"],
        "threshold": VAMS_PASS_PROFIT_LOSS_RATIO,
        "pass": _p(
            trade["pl_ratio"] is not None and trade["pl_ratio"] >= VAMS_PASS_PROFIT_LOSS_RATIO,
            trade["pl_ratio"] is None,
        ),
    }
    # Expectancy AND-gate (2026-05-16 Perplexity MED-D1 승인, config 정의 → 본 구현 88b40aa2).
    # 승률 55% 단독 불충분 → Expectancy 동반 의무(이중 임계). RULE 7: hit rate + expectancy 병기.
    # 임계 0.25R (2026-06-07 재보정 6ecf2c59, Perplexity 승인). 실제 게이트 = VAMS_MIN_EXPECTANCY_R.
    # ⚠️ 게이트는 N 충분(trades_ok) 시에만 활성 — VAMS 5/17 리셋, 65거래일 게이트 ~8월까지 pass=None.
    m_expectancy = {
        "expectancy_r": trade["expectancy_r"],
        "threshold": VAMS_MIN_EXPECTANCY_R,
        "pass": _p(
            trade["expectancy_r"] is not None and trade["expectancy_r"] >= VAMS_MIN_EXPECTANCY_R,
            trade["expectancy_r"] is None,
        ),
    }
    # SQN gate (Van Tharp System Quality Number ≥ 1.7 "Average", 2026-06-07 Perplexity).
    # expectancy 일관성(σ)+표본(N) 동시 반영 — raw expectancy 보다 robust한 품질 게이트.
    m_sqn = {
        "sqn": trade["sqn"],
        "threshold": VAMS_MIN_SQN,
        "pass": _p(
            trade["sqn"] is not None and trade["sqn"] >= VAMS_MIN_SQN,
            trade["sqn"] is None,
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
        # 2026-06-03 과적합 인지 Sharpe 유의성 (관측 only, pass/verdict 미반영 = RULE 7)
        "significance": _sharpe_significance(vams_series),
        "pass": _p(
            sharpe is not None and sharpe >= VAMS_PASS_SHARPE,
            sharpe is None,
        ),
    }
    m_regime = {
        "covered": regime_covered,
        "peak_drawdown_pct": bench_mdd,
        "threshold_pct": -float(VAMS_REGIME_DRAWDOWN_PCT),
        "pass": _p(regime_covered, not series_ok),
    }

    # 2026-05-29 — risk_metrics.py wrapper (5/17 dead code) wire.
    # informational only, pass=None → overall verdict 영향 0.
    # Phase 2 Stress (9월) sortino/calmar pass / Attribution (12-1월) alpha/beta/capture pass — 별 sprint.
    extra_risk: dict = {}
    if vams_series and bench_series:
        try:
            from api.quant.risk_metrics import compute_risk_metrics
            vams_simple = _daily_simple_returns(vams_series)
            bench_simple = _daily_simple_returns(bench_series)
            if len(vams_simple) >= 2 and len(bench_simple) == len(vams_simple):
                extra_risk = compute_risk_metrics(
                    vams_simple, bench_simple, periods=_TRADING_DAYS_PER_YEAR
                )
        except Exception:
            extra_risk = {"available": False}

    _info_note = "informational only — Phase 2 sprint 진행할 때 pass 판정 wire"
    m_sortino = {
        "annualized": extra_risk.get("sortino"),
        "pass": None,
        "note": _info_note,
    }
    m_calmar = {
        "annualized": extra_risk.get("calmar"),
        "pass": None,
        "note": _info_note,
    }
    m_alpha_beta = {
        "alpha": extra_risk.get("alpha"),
        "beta": extra_risk.get("beta"),
        "pass": None,
        "note": _info_note,
    }
    m_capture = {
        "up_capture": extra_risk.get("up_capture"),
        "down_capture": extra_risk.get("down_capture"),
        "pass": None,
        "note": _info_note,
    }
    # 자체 Sharpe (log returns) vs empyrical Sharpe (simple returns) cross-validation
    # [[feedback_metavalidation_decompose]] 정합 — 요소별 분해
    m_sharpe["empyrical_cross_simple"] = extra_risk.get("sharpe")

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
            not series_ok or gap_pp_total is None,
        ),
    }

    metrics = {
        "cumulative_return": m_return,
        "mdd": m_mdd,
        "win_rate": m_win,
        "profit_loss_ratio": m_pl,
        "expectancy": m_expectancy,
        "sqn": m_sqn,
        "sharpe": m_sharpe,
        "regime_coverage": m_regime,
        "cost_efficiency": m_cost,
        # 2026-05-29 informational — Phase 2 sprint 진행할 때 pass wire
        "sortino": m_sortino,
        "calmar": m_calmar,
        "alpha_beta": m_alpha_beta,
        "capture_ratios": m_capture,
    }

    # ---- overall ----
    measured_gate_keys = [
        key for key in _GATE_METRIC_KEYS if metrics[key]["pass"] is not None
    ]
    missing_gate_keys = [
        key for key in _GATE_METRIC_KEYS if metrics[key]["pass"] is None
    ]
    computed = [metrics[key]["pass"] for key in measured_gate_keys]
    failed = sum(1 for p in computed if p is False)

    if not series_ok:
        overall = "INSUFFICIENT_DATA"
    elif missing_gate_keys:
        overall = "MEASUREMENT_INCOMPLETE"
    elif sharpe is not None and sharpe < VAMS_REDESIGN_SHARPE:
        overall = "FAIL"  # 샤프 재설계 임계는 즉시 실패
    elif not computed:
        overall = "MEASUREMENT_INCOMPLETE"
    elif failed == 0:
        overall = "PASS"
    elif failed == 1:
        overall = "WATCH"
    else:
        overall = "FAIL"

    n_trades = trade["trades"]
    if n_trades < 30:
        evidence_status = "STATISTICALLY_UNINFORMATIVE"
    elif n_trades < 100:
        evidence_status = "PRELIMINARY"
    else:
        evidence_status = "MATURE"
    detection_floor = None
    if n_trades >= 2 and trade.get("r_std") is not None:
        detection_floor = round(3.0 * float(trade["r_std"]) / math.sqrt(n_trades), 3)

    return {
        "_meta": {
            "score_system": {
                "name": "VAMS realized trade ledger",
                "is_operational": True,
                "rule_version": VAMS_GATE_RULE_VERSION,
            },
            "min_detectable": {
                "method": "abs_t_3",
                "unit": "R",
                "n": n_trades,
                "sigma_r": trade.get("r_std"),
                "effect_r": detection_floor,
            },
            "evidence_status": evidence_status,
            "gate_metrics": {
                "required": list(_GATE_METRIC_KEYS),
                "required_count": len(_GATE_METRIC_KEYS),
                "measured": measured_gate_keys,
                "measured_count": len(measured_gate_keys),
                "missing": missing_gate_keys,
            },
        },
        "overall": overall,
        "window": window,
        "sample_checks": {
            "days_ok": days_ok,
            "days_required": VAMS_VALIDATION_MIN_DAYS,
            "trades_ok": trades_ok,
            "trades_required": VAMS_VALIDATION_MIN_TRADES,
            "series_ok": series_ok,
            "diagnostic_only": True,
            "gate_binding": False,
        },
        "legacy_diagnostic": {
            "window_start": VAMS_VALIDATION_LEGACY_START_DATE,
            "used_by_gate": False,
            "note": "legacy boundary retained for comparison only",
        },
        "metrics": metrics,
        "thresholds": {
            "excess_return_pp_min": VAMS_PASS_EXCESS_RETURN_PP,
            "mdd_ratio_max": VAMS_PASS_MDD_RATIO,
            "win_rate_min": VAMS_PASS_WIN_RATE,
            "profit_loss_ratio_min": VAMS_PASS_PROFIT_LOSS_RATIO,
            "expectancy_r_min": VAMS_MIN_EXPECTANCY_R,
            "sqn_min": VAMS_MIN_SQN,
            "sharpe_min": VAMS_PASS_SHARPE,
            "sharpe_redesign_below": VAMS_REDESIGN_SHARPE,
            "regime_drawdown_pct": VAMS_REGIME_DRAWDOWN_PCT,
        },
        # 🚨 국면 맥락 (PM 승인 2026-08-18) — **판정에 쓰지 않는다. 기록 의무다.**
        #    VAMS 게이트는 절대 기준이라 국면을 통제하지 않는데, 주식도 국면 의존이
        #    실측된다(200d MA 위 Sharpe 1.83 vs 아래 −1.03, t=+2.58).
        #    게이트를 국면 조건부로 바꾸는 것은 지표 선택이 사전등록 대상이라 보류했고,
        #    대신 판정문에 국면을 병기해 "국면 탓" 과 "실력 탓" 을 사후 분리 가능하게 한다.
        #    소급 불가한 정보이므로 지금 기록을 시작하는 것이 핵심.
        #    상세 = docs/KR_REGIME_WATCH_ASSESSMENT_2026_08_18.md
        "regime_context": _regime_context_safe(),
        "computed_at": now_kst().strftime("%Y-%m-%d %H:%M"),
    }
