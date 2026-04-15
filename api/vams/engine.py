"""
VAMS (Virtual Asset Management System) - 가상 투자 엔진

프로필 기반 운용:
  - config.py의 VAMS_PROFILES 중 활성 프로필(VAMS_ACTIVE_PROFILE)이
    매수 조건 · 손절 기준 · 종목당 한도를 모두 결정한다.
  - run_vams_cycle에 profile dict를 넘기면 해당 기준으로 동작.
"""
import json
import math
import os
import shutil
from datetime import datetime
from typing import Optional, List, Tuple
from api.config import (
    VAMS_INITIAL_CASH,
    VAMS_COMMISSION_RATE,
    VAMS_PROFILES,
    VAMS_ACTIVE_PROFILE,
    PORTFOLIO_PATH,
    RECOMMENDATIONS_PATH,
    HISTORY_PATH,
    DATA_DIR,
    now_kst,
)


def load_portfolio() -> dict:
    """기존 포트폴리오 로드 (NaN 방어 포함)"""
    if os.path.exists(PORTFOLIO_PATH):
        try:
            with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
                txt = f.read()
            import re
            txt = re.sub(r'\bNaN\b', 'null', txt)
            txt = re.sub(r'\bInfinity\b', 'null', txt)
            txt = re.sub(r'\b-Infinity\b', 'null', txt)
            return json.loads(txt)
        except Exception:
            pass
    return _empty_portfolio()


def _empty_portfolio() -> dict:
    return {
        "updated_at": "",
        "market_summary": {},
        "vams": {
            "total_asset": VAMS_INITIAL_CASH,
            "cash": VAMS_INITIAL_CASH,
            "holdings": [],
            "total_return_pct": 0.0,
            "total_realized_pnl": 0,
        },
        "recommendations": [],
        "alerts": [],
    }


def load_history() -> list:
    """매매 이력 로드"""
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _sanitize_nan(obj):
    """JSON 호환을 위해 NaN/Infinity/numpy 타입을 Python 네이티브로 변환"""
    import numpy as np
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_nan(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_sanitize_nan(v) for v in obj.tolist()]
    return obj


_PRIVATE_KEYS = frozenset({
    "_telegram_realtime_dedupe",
    "_claude_emergency_dedupe",
    "_tail_risk_rt_last_gemini",
})

_REC_EXCLUDE_FIELDS = frozenset({
    "dart_financials",
    "quant_factors",
    "yf_extended",
    "group_structure",
    "backtest",
})


def _slim_recommendations(recs: list) -> list:
    return [{k: v for k, v in r.items() if k not in _REC_EXCLUDE_FIELDS} for r in recs]


def save_portfolio(portfolio: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    public = {k: v for k, v in portfolio.items() if k not in _PRIVATE_KEYS}

    full_recs = public.get("recommendations")
    if isinstance(full_recs, list) and full_recs:
        clean_full = _sanitize_nan(full_recs)
        rec_tmp = RECOMMENDATIONS_PATH + ".tmp"
        with open(rec_tmp, "w", encoding="utf-8") as f:
            json.dump(clean_full, f, ensure_ascii=False, indent=2, default=str)
        os.replace(rec_tmp, RECOMMENDATIONS_PATH)
        public = {**public, "recommendations": _slim_recommendations(full_recs)}

    clean = _sanitize_nan(public)

    backup_path = PORTFOLIO_PATH + ".bak"
    tmp_path = PORTFOLIO_PATH + ".tmp"

    if os.path.exists(PORTFOLIO_PATH):
        shutil.copy2(PORTFOLIO_PATH, backup_path)

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp_path, PORTFOLIO_PATH)
    except Exception:
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, PORTFOLIO_PATH)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def save_history(history: list):
    os.makedirs(DATA_DIR, exist_ok=True)
    clean = _sanitize_nan(history)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)


def _get_profile(profile: Optional[dict] = None) -> dict:
    """프로필 dict를 반환. None이면 활성 프로필 사용."""
    if profile is not None:
        return profile
    return VAMS_PROFILES.get(VAMS_ACTIVE_PROFILE, VAMS_PROFILES["moderate"])


def check_stop_loss(holding: dict, profile: Optional[dict] = None) -> Tuple[bool, str]:
    """프로필 기반 손절/익절 조건 체크."""
    p = _get_profile(profile)
    stop_loss_pct = p["stop_loss_pct"]
    trailing_stop_pct = p["trailing_stop_pct"]
    max_hold_days = p["max_hold_days"]

    buy_price = holding["buy_price"]
    current_price = holding["current_price"]
    return_pct = ((current_price - buy_price) / buy_price) * 100

    if return_pct <= stop_loss_pct:
        return True, f"고정 손절 ({return_pct:.1f}% ≤ {stop_loss_pct}%)"

    highest = holding.get("highest_price", buy_price)
    if current_price > highest:
        highest = current_price

    if highest > buy_price:
        drop_from_high = ((current_price - highest) / highest) * 100
        if drop_from_high <= -trailing_stop_pct:
            return True, f"트레일링 스톱 (고점 {highest:,}원 대비 {drop_from_high:.1f}%)"

    buy_date = datetime.strptime(holding["buy_date"], "%Y-%m-%d")
    hold_days = (now_kst().replace(tzinfo=None) - buy_date).days
    if hold_days >= max_hold_days and return_pct <= 0:
        return True, f"기간 손절 ({hold_days}일 보유, 수익 없음)"

    return False, ""


def _get_fx_rate(portfolio: dict) -> float:
    """portfolio.macro.usd_krw에서 환율 추출. 없으면 1350 기본값."""
    try:
        return float(portfolio.get("macro", {}).get("usd_krw", {}).get("value", 1350))
    except (TypeError, ValueError):
        return 1350.0


def execute_buy(
    portfolio: dict,
    stock: dict,
    history: list,
    profile: Optional[dict] = None,
) -> Optional[dict]:
    """프로필 기반 가상 매수 (USD 종목은 원화 환산 후 동일 로직)."""
    p = _get_profile(profile)
    max_per_stock = p["max_per_stock"]

    cash = portfolio["vams"]["cash"]
    is_us = stock.get("currency") == "USD"
    fx_rate = _get_fx_rate(portfolio) if is_us else 1.0
    price = stock["price"] * fx_rate

    if price <= 0:
        return None

    held_tickers = [h["ticker"] for h in portfolio["vams"]["holdings"]]
    if stock["ticker"] in held_tickers:
        return None

    invest_amount = min(max_per_stock, cash * 0.9)
    if invest_amount < price:
        return None

    quantity = int(invest_amount // price)
    if quantity <= 0:
        return None

    total_cost = quantity * price
    commission = int(total_cost * VAMS_COMMISSION_RATE)
    actual_cost = total_cost + commission

    if actual_cost > cash:
        return None

    holding = {
        "ticker": stock["ticker"],
        "ticker_yf": stock.get("ticker_yf", f"{stock['ticker']}.KS"),
        "name": stock["name"],
        "currency": stock.get("currency", "KRW"),
        "buy_price": price,
        "buy_price_original": stock["price"],
        "current_price": price,
        "highest_price": price,
        "quantity": quantity,
        "total_cost": actual_cost,
        "return_pct": 0.0,
        "buy_date": now_kst().strftime("%Y-%m-%d"),
        "buy_reason": stock.get("ai_verdict", "AI 추천"),
        "safety_score": stock.get("safety_score", 0),
    }

    portfolio["vams"]["cash"] -= actual_cost
    portfolio["vams"]["holdings"].append(holding)

    history.append({
        "type": "BUY",
        "date": now_kst().strftime("%Y-%m-%d %H:%M"),
        "ticker": stock["ticker"],
        "name": stock["name"],
        "price": price,
        "quantity": quantity,
        "total": actual_cost,
        "reason": holding["buy_reason"],
    })

    print(f"[VAMS] 매수: {stock['name']} {quantity}주 @ {price:,}원 (총 {actual_cost:,}원)")
    return holding


def execute_sell(portfolio: dict, holding: dict, reason: str, history: list) -> dict:
    """가상 매도 실행"""
    price = holding["current_price"]
    quantity = holding["quantity"]
    total_revenue = quantity * price
    commission = int(total_revenue * VAMS_COMMISSION_RATE)
    actual_revenue = total_revenue - commission

    pnl = actual_revenue - holding["total_cost"]

    portfolio["vams"]["cash"] += actual_revenue
    portfolio["vams"]["holdings"] = [
        h for h in portfolio["vams"]["holdings"]
        if h["ticker"] != holding["ticker"]
    ]
    portfolio["vams"]["total_realized_pnl"] = (
        portfolio["vams"].get("total_realized_pnl", 0) + pnl
    )

    history.append({
        "type": "SELL",
        "date": now_kst().strftime("%Y-%m-%d %H:%M"),
        "ticker": holding["ticker"],
        "name": holding["name"],
        "price": price,
        "quantity": quantity,
        "total": actual_revenue,
        "pnl": pnl,
        "reason": reason,
    })

    print(f"[VAMS] 매도: {holding['name']} {quantity}주 @ {price:,}원 (손익: {pnl:+,}원) | 사유: {reason}")
    return {"ticker": holding["ticker"], "name": holding["name"], "pnl": pnl, "reason": reason}


def update_holdings_price(portfolio: dict, price_map: dict):
    """보유 종목 현재가 업데이트 (KR: 6자리 코드, US: 티커 그대로)"""
    fx_rate = _get_fx_rate(portfolio)
    for holding in portfolio["vams"]["holdings"]:
        is_us = holding.get("currency") == "USD"
        tk = str(holding["ticker"])
        if not is_us:
            tk = tk.zfill(6)
        if tk in price_map:
            raw_price = price_map[tk]
            new_price = raw_price * fx_rate if is_us else raw_price
            holding["current_price"] = new_price
            if new_price > holding.get("highest_price", 0):
                holding["highest_price"] = new_price
            holding["return_pct"] = round(
                ((new_price - holding["buy_price"]) / holding["buy_price"]) * 100, 2
            )


def recalculate_total(portfolio: dict):
    """총 자산 및 수익률 재계산"""
    holdings_value = sum(
        h["current_price"] * h["quantity"] for h in portfolio["vams"]["holdings"]
    )
    total = portfolio["vams"]["cash"] + holdings_value
    portfolio["vams"]["total_asset"] = total
    portfolio["vams"]["total_return_pct"] = round(
        ((total - VAMS_INITIAL_CASH) / VAMS_INITIAL_CASH) * 100, 2
    )


def run_vams_cycle(
    portfolio: dict,
    analyzed_stocks: List[dict],
    price_map: dict,
    profile: Optional[dict] = None,
) -> Tuple[dict, List[dict]]:
    """
    VAMS 프로필 기반 사이클.
    1. 보유 종목 가격 업데이트
    2. 프로필 기준 손절/익절 체크 → 매도
    3. 프로필 기준 신규 매수 (추천등급 + 안심점수 + 리스크 키워드)
    4. 총 자산 재계산
    """
    p = _get_profile(profile)
    history = load_history()
    alerts = []

    # 1. 가격 업데이트
    update_holdings_price(portfolio, price_map)

    # 2. 손절/익절 체크
    for holding in list(portfolio["vams"]["holdings"]):
        should_sell, reason = check_stop_loss(holding, p)
        if should_sell:
            sell_result = execute_sell(portfolio, holding, reason, history)
            alerts.append({
                "type": "STOP_LOSS",
                "message": f"🚨 {sell_result['name']} 매도 | {reason} | 손익: {sell_result['pnl']:+,}원",
            })

    # 3. 신규 매수 — 프로필 기준 필터링
    allowed_recs = set(p["recommendations"])
    min_safety = p["min_safety"]
    max_risk_kw = p["max_risk_keywords"]
    max_buy = p.get("max_buy_per_cycle", 5)

    held_tickers = {h["ticker"] for h in portfolio["vams"]["holdings"]}

    buy_candidates = [
        s for s in analyzed_stocks
        if s.get("recommendation") in allowed_recs
        and s.get("safety_score", 0) >= min_safety
        and len(s.get("detected_risk_keywords") or []) <= max_risk_kw
        and s.get("ticker") not in held_tickers
        and s.get("price", 0) > 0
    ]

    # 안심점수 높은 순 정렬
    buy_candidates.sort(key=lambda s: s.get("safety_score", 0), reverse=True)

    bought = 0
    for stock in buy_candidates:
        if bought >= max_buy:
            break
        result = execute_buy(portfolio, stock, history, p)
        if result:
            bought += 1
            alerts.append({
                "type": "NEW_BUY",
                "message": f"✅ {result['name']} 매수 | {result['quantity']}주 @ {result['buy_price']:,}원 | 사유: {result['buy_reason']}",
            })

    # 4. 재계산
    recalculate_total(portfolio)

    # 프로필 이름 기록
    portfolio["vams"]["active_profile"] = VAMS_ACTIVE_PROFILE

    save_history(history)
    print(f"[VAMS] 사이클 완료 — 프로필: {p['label']} | 매도: {sum(1 for a in alerts if a['type'] == 'STOP_LOSS')}건 | 매수: {bought}건 | 후보: {len(buy_candidates)}종목")
    return portfolio, alerts
