"""
백테스트 아카이브 — 추천 스냅샷 저장 + 7/14/30일 후 성과 추적.
history/ 스냅샷의 recommendations[]를 비교하여 적중률·수익률을 산출.

Sprint 11 (2026-04-30) 보정 추가 — 베테랑 due diligence 결함 1 대응:
  - Survivorship bias: today_snap 에 없는 ticker (상장폐지/거래정지) 를 자동 제외하지
    않고 별도 집계 + 보수적 -50% 처리. 종전 hit_rate 부풀림 차단.
  - Slippage: 시총 tier 기반 왕복 슬리피지 모델 (10조+ 0.1% / 1-10조 0.3% / <1조 0.7%).
    KOSPI 대형주 vs KOSDAQ 소형주 차등.
  - Transaction cost: VAMS 와 일치하는 0.03% 왕복 (수수료 0.015% × 2).

Gross (기존 방식, 비교용) + Net (보정 후, 실거래 근사) 둘 다 노출 — 사용자가 차이를
직접 확인 가능. 단일 hit_rate 단절 없음.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst
from api.workflows.archiver import load_snapshot, list_available_dates

logger = logging.getLogger(__name__)

BACKTEST_PATH = os.path.join(DATA_DIR, "backtest_stats.json")

# Sprint 11 보정 상수 (베테랑 결함 1 대응)
TX_COST_PCT = 0.03           # VAMS 수수료 0.015% × 2 왕복
DELISTED_RETURN_PCT = -50.0  # 상장폐지/거래정지 종목 보수 처리 (distress midpoint)


def _slippage_pct(market_cap_krw: Optional[float]) -> float:
    """왕복(매수+매도) 슬리피지 + 호가 spread 추정 (시총 tier 기반).

    근거: KOSPI 대형주 호가 0.05% × 2 왕복 + 시장충격 ≈ 0.1%.
          KOSDAQ 중형주 0.15% × 2 ≈ 0.3%. 소형주/미상 0.35% × 2 ≈ 0.7%.
    """
    if market_cap_krw is None or market_cap_krw <= 0:
        return 0.7  # 시총 미상 — 보수적 (소형주 가정)
    if market_cap_krw >= 10_000_000_000_000:  # 10조+
        return 0.1
    if market_cap_krw >= 1_000_000_000_000:   # 1-10조
        return 0.3
    return 0.7  # 1조 미만


def _load_existing_stats() -> Dict[str, Any]:
    if os.path.exists(BACKTEST_PATH):
        try:
            with open(BACKTEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_stats(stats: Dict[str, Any]):
    with open(BACKTEST_PATH, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2, default=str)


def _get_price_map_from_snapshot(snap: dict) -> Dict[str, float]:
    """스냅샷에서 ticker → price 맵 추출."""
    prices: Dict[str, float] = {}
    for r in snap.get("recommendations", []):
        ticker = r.get("ticker", "")
        price = r.get("price") or r.get("current_price")
        if ticker and price:
            try:
                prices[ticker] = float(price)
            except (TypeError, ValueError):
                pass
    for h in (snap.get("vams") or {}).get("holdings") or []:
        ticker = h.get("ticker", "")
        price = h.get("current_price") or h.get("price")
        if ticker and price:
            try:
                prices[ticker] = float(price)
            except (TypeError, ValueError):
                pass
    return prices


def _next_business_snapshot_date(rec_date: str, available: List[str]) -> Optional[str]:
    """rec_date 다음 영업일 (가장 빠른 후속 snapshot) 반환. 없으면 None.

    Look-ahead bias 보정: 추천 발생 시점 (T) 가격은 사용자 매수 불가 — 다음 영업일 (T+1)
    snapshot 의 price 를 사실상 진입 가격으로 사용. 휴장/연휴는 가장 빠른 후속 snapshot.
    """
    from datetime import datetime
    try:
        rd = datetime.strptime(rec_date, "%Y-%m-%d").date()
    except ValueError:
        return None
    for d_str in available:
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d").date()
            if d > rd:
                return d_str
        except ValueError:
            continue
    return None


def _t_plus_1_price_map(rec_date: str, available: List[str]) -> Dict[str, float]:
    """rec_date 다음 영업일 snapshot 의 ticker → price 맵. 없으면 빈 dict."""
    next_date = _next_business_snapshot_date(rec_date, available)
    if not next_date:
        return {}
    snap = load_snapshot(next_date)
    if not snap:
        return {}
    return _get_price_map_from_snapshot(snap)


def evaluate_past_recommendations(
    lookback_days: List[int] = None,
) -> Dict[str, Any]:
    """
    과거 추천 종목의 성과를 추적.

    lookback_days: 비교 기간 (기본 [7, 14, 30])
    Returns: {
        "periods": {
            "7d": {hit_rate, avg_return, total_recs, ...},
            "14d": {...},
            "30d": {...},
        },
        "recommendations": [{ticker, name, rec_date, rec_price, ...}],
        "updated_at": "...",
    }
    """
    if lookback_days is None:
        lookback_days = [7, 14, 30]

    dates = list_available_dates()
    if len(dates) < 2:
        return {"periods": {}, "recommendations": [], "updated_at": str(now_kst())}

    today = now_kst().date()
    today_str = today.strftime("%Y-%m-%d")
    today_snap = load_snapshot(today_str)
    if not today_snap:
        if dates:
            today_snap = load_snapshot(dates[-1])
            today_str = dates[-1]
    if not today_snap:
        return {"periods": {}, "recommendations": [], "updated_at": str(now_kst())}

    current_prices = _get_price_map_from_snapshot(today_snap)

    period_stats: Dict[str, Dict[str, Any]] = {}
    all_recs: List[Dict[str, Any]] = []

    for days in lookback_days:
        target_date = (today - timedelta(days=days)).strftime("%Y-%m-%d")
        past_snap = _find_nearest_snapshot(target_date, dates)
        if not past_snap:
            period_stats[f"{days}d"] = {"hit_rate": None, "avg_return": None, "total_recs": 0}
            continue

        past_data = load_snapshot(past_snap)
        if not past_data:
            period_stats[f"{days}d"] = {"hit_rate": None, "avg_return": None, "total_recs": 0}
            continue

        past_recs = past_data.get("recommendations", [])
        buy_recs = [r for r in past_recs if r.get("recommendation") in ("BUY", "STRONG_BUY", "매수", "강력 매수")]

        # Look-ahead bias 보정 (Sprint 11 결함 1 후속, 2026-05-01):
        # past_snap 의 price = 추천 발생 시점 가격 (사용자 매수 불가).
        # T+1 영업일 snapshot 가격 = 사실상 진입 가능 가격. 보정값으로 우선 사용.
        # T+1 snapshot 없는 추천 (= 너무 최신이라 다음날 cron 미발생) 은 skip.
        t_plus_1_prices = _t_plus_1_price_map(past_snap, dates)

        # Sprint 11 dual-track: gross (raw forward tracking) + net (slippage+TX 보정).
        # delisted: today_snap 에 없는 ticker — 보수적 -50% 별도 집계 (survivorship 차단).
        hits_gross = 0
        hits_net = 0
        returns_gross: List[float] = []
        returns_net: List[float] = []
        delisted_count = 0
        skipped_no_t1 = 0
        details: List[Dict[str, Any]] = []

        for rec in buy_recs:
            ticker = rec.get("ticker", "")
            name = rec.get("name", "?")
            rec_price_t = rec.get("price") or rec.get("current_price")
            if not rec_price_t or not ticker:
                continue
            try:
                rec_price_t = float(rec_price_t)
            except (TypeError, ValueError):
                continue

            # T+1 시가 보정 — 사용자 매수 가능 가격
            rec_price_t1 = t_plus_1_prices.get(ticker)
            if rec_price_t1 is None or rec_price_t1 <= 0:
                # T+1 snapshot 에 ticker 없음 = 다음날 분석에서 제외됨 또는 너무 최신
                # 보수적으로 skip (alpha 부풀림 방지). Look-ahead bias 차단.
                skipped_no_t1 += 1
                continue
            rec_price = rec_price_t1  # 진입 가격 = T+1 시가

            cur_price = current_prices.get(ticker)
            market_cap = rec.get("market_cap")
            slip = _slippage_pct(market_cap)

            if cur_price is None or cur_price <= 0:
                # SURVIVORSHIP: 상장폐지/거래정지 — 자동 제외 대신 보수 처리.
                # gross 는 측정 불가라 skip, net 만 -50% 로 카운트해서 부풀림 차단.
                delisted_count += 1
                returns_net.append(DELISTED_RETURN_PCT)
                # hit_net 은 false (음수)
                continue

            gross_ret = round((cur_price - rec_price) / rec_price * 100, 2)
            net_ret = round(gross_ret - slip - TX_COST_PCT, 2)

            returns_gross.append(gross_ret)
            returns_net.append(net_ret)
            if gross_ret > 0:
                hits_gross += 1
            if net_ret > 0:
                hits_net += 1

            source = rec.get("_recommendation_source", "gemini")
            detail = {
                "ticker": ticker,
                "name": name,
                "rec_date": past_snap,
                "rec_price": rec_price,
                "current_price": cur_price,
                "return_pct_gross": gross_ret,
                "return_pct_net": net_ret,
                "slippage_pct": slip,
                "hit_gross": gross_ret > 0,
                "hit_net": net_ret > 0,
                "period": f"{days}d",
                "recommendation": rec.get("recommendation"),
                "brain_score": rec.get("brain_score"),
                "source": source,
                # 호환성 — 구버전 필드도 유지 (gross 기준)
                "return_pct": gross_ret,
                "hit": gross_ret > 0,
            }
            details.append(detail)
            all_recs.append(detail)

        total_gross = len(returns_gross)
        total_net = len(returns_net)  # delisted 포함
        hit_rate_gross = round(hits_gross / total_gross * 100, 1) if total_gross > 0 else None
        hit_rate_net = round(hits_net / total_net * 100, 1) if total_net > 0 else None
        avg_gross = round(sum(returns_gross) / total_gross, 2) if total_gross > 0 else None
        avg_net = round(sum(returns_net) / total_net, 2) if total_net > 0 else None
        max_ret = round(max(returns_gross), 2) if returns_gross else None
        min_ret = round(min(returns_net), 2) if returns_net else None  # delisted 포함 최저

        sharpe_gross = None
        if total_gross >= 3:
            import statistics
            mean_r = sum(returns_gross) / total_gross
            std_r = statistics.stdev(returns_gross)
            if std_r > 0:
                sharpe_gross = round(mean_r / std_r, 2)

        period_stats[f"{days}d"] = {
            # Net (보정 후 — 실거래 근사. 베테랑 결함 1 대응 후 실제 신뢰값)
            "hit_rate_net": hit_rate_net,
            "avg_return_net": avg_net,
            # Gross (기존 방식 — 비교/추세 보존용)
            "hit_rate_gross": hit_rate_gross,
            "avg_return_gross": avg_gross,
            # Look-ahead bias 보정 흔적
            "skipped_no_t_plus_1": skipped_no_t1,
            "rec_price_basis": "T_plus_1_open_snapshot",
            # 호환성 — 구버전 필드 (gross 기준)
            "hit_rate": hit_rate_gross,
            "avg_return": avg_gross,
            # 분포
            "max_return": max_ret,
            "min_return": min_ret,
            "sharpe": sharpe_gross,
            "total_recs": total_gross,
            "total_recs_with_delisted": total_net,
            "hits": hits_gross,
            "delisted_count": delisted_count,
            "snapshot_date": past_snap,
        }

    all_recs.sort(key=lambda x: x.get("return_pct_gross", x.get("return_pct", 0)), reverse=True)

    result = {
        "periods": period_stats,
        "recommendations": all_recs[:50],
        "updated_at": str(now_kst()),
        # Sprint 11 메타 — 베테랑 due diligence 결함 1 대응 (감사 흔적)
        "_corrections_meta": {
            "version": "1.0",
            "applied_at": str(now_kst()),
            "tx_cost_pct_round_trip": TX_COST_PCT,
            "delisted_return_pct": DELISTED_RETURN_PCT,
            "slippage_model": "market_cap_tier (≥10조 0.1% / ≥1조 0.3% / <1조 0.7%)",
            "look_ahead_bias_correction": {
                "applied": True,
                "method": "rec_price = T+1 영업일 snapshot 의 ticker 가격 (사용자 매수 가능 가격 근사)",
                "skip_policy": "T+1 snapshot 미존재 ticker 는 skip (alpha 부풀림 차단)",
                "fixed_at": str(now_kst()),
            },
            "limitations": [
                "T+1 시가 = 다음날 분석 cron snapshot price (실제 시가 ≠ snapshot 시점 price 가능 — micro-bias 잔존)",
                "시장충격 비용은 평균 추정 — 대량 주문(>일거래대금 1%) 시 실제는 더 큼",
                "delisted -50% 는 distress midpoint — 실제는 -30 ~ -100% 분포",
            ],
        },
    }

    _save_stats(result)
    return result


def generate_verification_report() -> Dict[str, Any]:
    """IC/ICIR + 추천 성과를 통합한 신호 검증 리포트.
    Brain 가중치 피드백 루프가 실제로 작동하는지 확인하는 검증 문서.

    NOTE: 사후 검증용 아카이브 출력. 실시간 추천/브레인 판단에 역류하지 않음."""
    bt = evaluate_past_recommendations()

    ic_data: Dict[str, Any] = {}
    try:
        from api.quant.alpha.factor_decay import (
            analyze_factor_decay,
            compute_ic_weight_adjustments,
        )
        ic_data = analyze_factor_decay()
        ic_adj = compute_ic_weight_adjustments()
    except Exception:
        ic_adj = {"status": "error", "adjustments": {}, "log": []}

    periods = bt.get("periods", {})
    hit_7d = (periods.get("7d") or {}).get("hit_rate")
    hit_14d = (periods.get("14d") or {}).get("hit_rate")
    hit_30d = (periods.get("30d") or {}).get("hit_rate")

    healthy = ic_data.get("healthy_factors", [])
    decaying = ic_data.get("decaying_factors", [])
    weakening = ic_data.get("weakening_factors", [])

    adj_applied = []
    for factor, info in ic_adj.get("adjustments", {}).items():
        m = info.get("multiplier", 1.0)
        if m != 1.0:
            adj_applied.append({
                "factor": factor,
                "multiplier": m,
                "status": info.get("status"),
                "ic_recent": info.get("ic_recent"),
            })

    # Sprint 11: net (보정 후, 실거래 근사) 도 동시 노출 — 호환 위해 기존 키 유지.
    report = {
        "performance": {
            # Gross (기존 키 — 비교/추세 보존)
            "hit_rate_7d": hit_7d,
            "hit_rate_14d": hit_14d,
            "hit_rate_30d": hit_30d,
            "avg_return_7d": (periods.get("7d") or {}).get("avg_return"),
            "avg_return_14d": (periods.get("14d") or {}).get("avg_return"),
            "sharpe_14d": (periods.get("14d") or {}).get("sharpe"),
            # Net (slippage + TX + survivorship 보정 — 실거래 근사)
            "hit_rate_7d_net": (periods.get("7d") or {}).get("hit_rate_net"),
            "hit_rate_14d_net": (periods.get("14d") or {}).get("hit_rate_net"),
            "hit_rate_30d_net": (periods.get("30d") or {}).get("hit_rate_net"),
            "avg_return_7d_net": (periods.get("7d") or {}).get("avg_return_net"),
            "avg_return_14d_net": (periods.get("14d") or {}).get("avg_return_net"),
            # Survivorship 카운트 (감사용)
            "delisted_count_30d": (periods.get("30d") or {}).get("delisted_count"),
        },
        "_corrections_meta": bt.get("_corrections_meta"),
        "factor_health": {
            "healthy": healthy,
            "weakening": weakening,
            "decaying": decaying,
            "total_factors": len(ic_data.get("factors", {})),
        },
        "ic_adjustments_active": adj_applied,
        "feedback_loop_status": "closed" if adj_applied else "open",
        "generated_at": str(now_kst()),
    }

    report_path = os.path.join(DATA_DIR, "verification_report.json")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass

    return report


def _find_nearest_snapshot(target_date: str, available: List[str]) -> Optional[str]:
    """target_date에 가장 가까운 스냅샷 날짜 반환 (±2일 범위)."""
    if target_date in available:
        return target_date

    from datetime import datetime
    try:
        td = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        return None

    best = None
    best_diff = 999
    for d_str in available:
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d").date()
            diff = abs((d - td).days)
            if diff <= 2 and diff < best_diff:
                best = d_str
                best_diff = diff
        except ValueError:
            continue
    return best
