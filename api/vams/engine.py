"""
VAMS (Virtual Asset Management System) - 가상 투자 엔진

프로필 기반 운용:
  - config.py의 VAMS_PROFILES 중 활성 프로필(VAMS_ACTIVE_PROFILE)이
    매수 조건 · 손절 기준 · 종목당 한도를 모두 결정한다.
  - run_vams_cycle에 profile dict를 넘기면 해당 기준으로 동작.
"""
import errno
import json
import math
import os
import shutil
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, List, Tuple

try:
    import fcntl  # POSIX only
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False
from api.config import (
    VAMS_INITIAL_CASH,
    VAMS_COMMISSION_RATE,
    VAMS_PROFILES,
    VAMS_ACTIVE_PROFILE,
    VAMS_KELLY_SCALE,
    VAMS_MAX_SECTOR_PCT,
    VAMS_MAX_PORTFOLIO_BETA,
    VAMS_MAX_FACTOR_TILT_PCT,
    VAMS_MAX_SINGLE_THEME_PCT,
    VAMS_SELL_TAX_KR_STOCK,
    VAMS_SELL_TAX_KR_ETF,
    VAMS_SELL_TAX_US,
    VAMS_SPREAD_SLIPPAGE_BPS,
    VAMS_DIVIDEND_TAX_RATE,
    PORTFOLIO_PATH,
    RECOMMENDATIONS_PATH,
    VERITY_MODE,
    HISTORY_PATH,
    DATA_DIR,
    now_kst,
)


_KR_ETF_KEYWORDS = (
    "ETF", "KODEX", "TIGER", "ARIRANG", "KBSTAR", "HANARO",
    "KINDEX", "SOL ", "PLUS ", "ACE ", "TIMEFOLIO",
)


def classify_asset(stock_or_holding: dict) -> str:
    """종목을 세율 분기를 위한 4개 클래스로 분류.
    반환: 'KR_STOCK' | 'KR_ETF' | 'US_STOCK' | 'US_ETF'

    currency 필드가 비어 있으면 ticker 포맷으로 추론:
      - 6자리(이하) 숫자만 → KRW
      - 알파벳 포함       → USD
      - 그 외 애매한 경우 → KRW (보수적)
    """
    if not isinstance(stock_or_holding, dict):
        return "KR_STOCK"

    currency_raw = stock_or_holding.get("currency")
    if currency_raw:
        currency = str(currency_raw).upper()
    else:
        ticker = str(stock_or_holding.get("ticker", "") or "").strip()
        if ticker and ticker.isdigit():
            currency = "KRW"
        elif ticker and any(c.isalpha() for c in ticker):
            currency = "USD"
        else:
            currency = "KRW"

    is_etf_flag = bool(stock_or_holding.get("is_etf")) or bool(stock_or_holding.get("etf"))
    name = str(stock_or_holding.get("name", "") or "").upper()
    is_etf_by_name = any(kw in name for kw in _KR_ETF_KEYWORDS)
    is_etf = is_etf_flag or is_etf_by_name

    if currency == "USD":
        return "US_ETF" if is_etf else "US_STOCK"
    return "KR_ETF" if is_etf else "KR_STOCK"


_SELL_TAX_BY_CLASS = {
    "KR_STOCK": VAMS_SELL_TAX_KR_STOCK,
    "KR_ETF": VAMS_SELL_TAX_KR_ETF,
    "US_STOCK": VAMS_SELL_TAX_US,
    "US_ETF": VAMS_SELL_TAX_US,
}


_LOCK_PATH = os.path.join(DATA_DIR, ".portfolio.lock")


@contextmanager
def portfolio_lock(timeout_sec: int = 60):
    """파일 기반 advisory lock — read-modify-write 사이클 보호.
    POSIX 환경(Linux/macOS, GitHub Actions ubuntu-latest)에서만 실제 lock.
    Windows 등은 no-op이지만 경고 없이 동작 (개발 환경 호환)."""
    if not _HAS_FCNTL:
        yield
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    start = time.time()
    fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EACCES):
                    raise
                if time.time() - start > timeout_sec:
                    raise RuntimeError(
                        f"portfolio lock timeout after {timeout_sec}s (another cycle holding the lock)"
                    )
                time.sleep(0.5)
        try:
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:
                pass
    finally:
        try:
            os.close(fd)
        except Exception:
            pass


def load_portfolio() -> dict:
    """기존 포트폴리오 로드 (NaN 방어 + .bak 폴백).

    ★ 중요: 파싱 실패 시 _empty_portfolio() 반환 금지!
    그렇게 하면 후속 save 가 기존 56 keys 를 빈 7 keys 로 덮어써서
    downstream 파괴 (실측: 2026-04-21 bond·etf 가 전체 데이터 증발).

    안전 정책:
      1. portfolio.json 파싱 성공 → 반환
      2. 실패 → portfolio.json.bak 시도 (save_portfolio 가 매 저장 전 생성)
      3. .bak 도 실패 → RuntimeError (빈 dict 대체 금지)
    """
    import re

    def _try_load(path: str) -> Optional[dict]:
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                txt = f.read()
            txt = re.sub(r'\bNaN\b', 'null', txt)
            txt = re.sub(r'\bInfinity\b', 'null', txt)
            txt = re.sub(r'\b-Infinity\b', 'null', txt)
            return json.loads(txt)
        except Exception as e:
            print(f"[load_portfolio] {path} 파싱 실패: {str(e)[:100]}")
            return None

    data = _try_load(PORTFOLIO_PATH)
    if data is not None:
        return data

    # .bak 폴백
    bak_path = PORTFOLIO_PATH + ".bak"
    data = _try_load(bak_path)
    if data is not None:
        print(f"[load_portfolio] ★ 주 파일 손상 — .bak 에서 복구 ({bak_path})")
        return data

    # 신규 설치 (파일 자체 없음) — empty 허용
    if not os.path.exists(PORTFOLIO_PATH):
        print(f"[load_portfolio] 최초 설치 — 빈 포트폴리오로 시작")
        return _empty_portfolio()

    # 둘 다 손상 → 치명. 후속 save 가 덮어쓰지 못 하게 raise.
    raise RuntimeError(
        f"portfolio.json 과 .bak 모두 파싱 실패. "
        "덮어쓰기 방지를 위해 중단. 수동으로 git checkout 으로 복구 필요."
    )


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
    """JSON 호환을 위해 NaN/Infinity/numpy/pandas 타입을 Python 네이티브로 변환.
    allow_nan=False 저장 시 2차 방어선 역할."""
    import numpy as np
    try:
        import pandas as pd
        _pd_na_types = (pd.Timestamp, type(pd.NaT))
    except ImportError:
        pd = None
        _pd_na_types = ()

    if obj is None:
        return None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if _pd_na_types and isinstance(obj, _pd_na_types):
        try:
            if obj != obj:  # NaT / NaN-like 자가 불일치
                return None
        except Exception:
            pass
        return str(obj)
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
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

    if VERITY_MODE != "prod":
        dest_path = PORTFOLIO_PATH.replace("portfolio.json", "portfolio.dev.json")
        portfolio["_verity_mode"] = VERITY_MODE
    else:
        dest_path = PORTFOLIO_PATH

    public = {k: v for k, v in portfolio.items() if k not in _PRIVATE_KEYS}

    full_recs = public.get("recommendations")
    if isinstance(full_recs, list) and full_recs:
        clean_full = _sanitize_nan(full_recs)
        rec_dest = RECOMMENDATIONS_PATH if VERITY_MODE == "prod" else RECOMMENDATIONS_PATH.replace(".json", ".dev.json")
        rec_tmp = rec_dest + ".tmp"
        with open(rec_tmp, "w", encoding="utf-8") as f:
            json.dump(clean_full, f, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        os.replace(rec_tmp, rec_dest)
        public = {**public, "recommendations": _slim_recommendations(full_recs)}

    clean = _sanitize_nan(public)

    backup_path = dest_path + ".bak"
    tmp_path = dest_path + ".tmp"

    if os.path.exists(dest_path):
        shutil.copy2(dest_path, backup_path)

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2, default=str, allow_nan=False)
        os.replace(tmp_path, dest_path)
    except Exception:
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, dest_path)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def save_history(history: list):
    os.makedirs(DATA_DIR, exist_ok=True)
    clean = _sanitize_nan(history)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2, allow_nan=False)


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


_DEFAULT_ADV = 500_000_000  # 소형주 기본 일평균 거래대금 (5억원)


def _estimate_slippage(order_value: float, adv: float, profile: Optional[dict] = None) -> float:
    """Almgren-Chriss 스타일 제곱근 마켓임팩트 모델.
    Returns slippage in basis points.
    """
    p = _get_profile(profile)
    coeff = p.get("impact_coeff_bps", 30)
    if adv <= 0:
        adv = _DEFAULT_ADV
    participation = order_value / adv
    return coeff * math.sqrt(max(participation, 0))


def _check_portfolio_exposure(portfolio: dict, candidate_stock: dict) -> dict:
    """V6: 매수 전 포트폴리오 레벨 노출 상한 체크.
    섹터 집중, 베타, 테마 집중을 확인해 blocked/reason 반환."""
    holdings = portfolio.get("vams", {}).get("holdings", [])
    total_asset = portfolio.get("vams", {}).get("total_asset", VAMS_INITIAL_CASH)
    if total_asset <= 0:
        total_asset = VAMS_INITIAL_CASH

    cand_sector = (candidate_stock.get("sector") or "Unknown").strip()

    sector_exposure: dict = {}
    portfolio_beta_sum = 0.0
    portfolio_weight_sum = 0.0

    for h in holdings:
        h_value = h.get("current_price", 0) * h.get("quantity", 0)
        h_pct = h_value / total_asset * 100 if total_asset > 0 else 0
        h_sector = (h.get("sector") or "Unknown").strip()
        sector_exposure[h_sector] = sector_exposure.get(h_sector, 0) + h_pct

        h_beta = h.get("beta", 1.0)
        portfolio_beta_sum += h_beta * h_pct
        portfolio_weight_sum += h_pct

    current_sector_pct = sector_exposure.get(cand_sector, 0)
    cand_invest = min(
        _get_profile().get("max_per_stock", 2_000_000),
        portfolio.get("vams", {}).get("cash", 0) * 0.9,
    )
    cand_pct = cand_invest / total_asset * 100 if total_asset > 0 else 0

    if current_sector_pct + cand_pct > VAMS_MAX_SECTOR_PCT:
        return {
            "blocked": True,
            "reason": f"섹터 '{cand_sector}' 노출 {current_sector_pct:.1f}%+{cand_pct:.1f}% > 상한 {VAMS_MAX_SECTOR_PCT}%",
        }

    if portfolio_weight_sum > 0:
        current_beta = portfolio_beta_sum / portfolio_weight_sum
        cand_beta = candidate_stock.get("beta", 1.0)
        new_beta = (portfolio_beta_sum + cand_beta * cand_pct) / (portfolio_weight_sum + cand_pct)
        if new_beta > VAMS_MAX_PORTFOLIO_BETA:
            return {
                "blocked": True,
                "reason": f"포트폴리오 베타 {new_beta:.2f} > 상한 {VAMS_MAX_PORTFOLIO_BETA}",
            }

    # Sprint 11 결함 4 (베테랑 due diligence) — factor tilt 검사.
    # multi_factor.quant_factors 의 momentum/quality/volatility/mean_reversion 중
    # 한 factor 에 portfolio 의 N% 이상이 같은 방향 (>=70 high or <=30 low) 으로
    # 쏠리면 매수 차단. 사실상 분산 효과 깨짐 차단.
    FACTOR_KEYS = ("momentum", "quality", "volatility", "mean_reversion")
    factor_high_pct: dict = {k: 0.0 for k in FACTOR_KEYS}
    factor_low_pct: dict = {k: 0.0 for k in FACTOR_KEYS}
    for h in holdings:
        h_value = h.get("current_price", 0) * h.get("quantity", 0)
        h_pct = h_value / total_asset * 100 if total_asset > 0 else 0
        h_qf = (h.get("multi_factor") or {}).get("quant_factors") or {}
        for k in FACTOR_KEYS:
            v = h_qf.get(k)
            if isinstance(v, (int, float)):
                if v >= 70:
                    factor_high_pct[k] += h_pct
                elif v <= 30:
                    factor_low_pct[k] += h_pct
    cand_qf = (candidate_stock.get("multi_factor") or {}).get("quant_factors") or {}
    for k in FACTOR_KEYS:
        v = cand_qf.get(k)
        if not isinstance(v, (int, float)):
            continue
        if v >= 70:
            new_pct = factor_high_pct[k] + cand_pct
            if new_pct > VAMS_MAX_FACTOR_TILT_PCT:
                return {
                    "blocked": True,
                    "reason": f"factor '{k}' high tilt {new_pct:.1f}% > 상한 {VAMS_MAX_FACTOR_TILT_PCT}% (분산 깨짐)",
                }
        elif v <= 30:
            new_pct = factor_low_pct[k] + cand_pct
            if new_pct > VAMS_MAX_FACTOR_TILT_PCT:
                return {
                    "blocked": True,
                    "reason": f"factor '{k}' low tilt {new_pct:.1f}% > 상한 {VAMS_MAX_FACTOR_TILT_PCT}% (분산 깨짐)",
                }

    return {"blocked": False, "reason": ""}


def _apply_half_kelly(invest_amount: float, brain_score: int) -> float:
    """V6: Half-Kelly (또는 설정된 비율) 적용."""
    if VAMS_KELLY_SCALE >= 1.0:
        return invest_amount
    p = brain_score / 100.0
    b = 1.5
    q = 1.0 - p
    kelly_raw = max(0, (b * p - q) / b)
    scaled_kelly = kelly_raw * VAMS_KELLY_SCALE
    return invest_amount * min(scaled_kelly / max(kelly_raw, 0.01), 1.0) if kelly_raw > 0 else invest_amount * 0.5


def _apply_volatility_adj(invest_amount: float, stock: dict) -> tuple:
    """Sprint 11 결함 3: ATR/변동성 기반 sizing 보정.

    근거: 같은 -5% 손절이면 일변동성 1.2% 종목은 정상 노이즈에 손절당하고
    일변동성 4.5% 종목은 손절선 도달 전 -15% 박살. 변동성 정규화 필요.

    우선순위 (2026-05-01 결함 3 후속):
      1. technical.atr_14d_pct (ATR/price%, 직접 수집 — 정확)
         임계: ≤ 1.5% 저 / ≤ 3.0% 중 / > 3.0% 고
      2. prediction.top_features.volatility_20d (20일 수익률 표준편차 %, proxy)
         임계: ≤ 15% 저 / ≤ 30% 중 / > 30% 고
      3. 둘 다 없으면 1.0× (데이터 없음 — 기존 동작)

    Scale 동일: 1.0× / 0.85× / 0.70×.
    """
    tech = stock.get("technical") or {}
    atr_pct = tech.get("atr_14d_pct")
    if isinstance(atr_pct, (int, float)) and atr_pct > 0:
        if atr_pct <= 1.5:
            scale, tier = 1.0, "low"
        elif atr_pct <= 3.0:
            scale, tier = 0.85, "mid"
        else:
            scale, tier = 0.70, "high"
        return invest_amount * scale, {
            "applied": True,
            "tier": tier,
            "atr_14d_pct": round(float(atr_pct), 2),
            "scale": scale,
            "source": "atr_14d",
        }

    pred = stock.get("prediction") or {}
    top_features = pred.get("top_features") or {}
    vol = top_features.get("volatility_20d")
    if not isinstance(vol, (int, float)) or vol <= 0:
        return invest_amount, {"applied": False, "reason": "no_volatility_data"}

    if vol <= 15.0:
        scale, tier = 1.0, "low"
    elif vol <= 30.0:
        scale, tier = 0.85, "mid"
    else:
        scale, tier = 0.70, "high"

    return invest_amount * scale, {
        "applied": True,
        "tier": tier,
        "volatility_20d_pct": round(vol, 2),
        "scale": scale,
        "source": "volatility_20d_proxy",
    }


def execute_buy(
    portfolio: dict,
    stock: dict,
    history: list,
    profile: Optional[dict] = None,
) -> Optional[dict]:
    """프로필 기반 가상 매수 (USD 종목은 원화 환산 후 동일 로직). 슬리피지 반영.
    V6: Half-Kelly 스케일링 적용."""
    p = _get_profile(profile)
    max_per_stock = p["max_per_stock"]

    cash = portfolio["vams"]["cash"]
    is_us = stock.get("currency") == "USD"
    fx_rate = _get_fx_rate(portfolio) if is_us else 1.0
    base_price = stock["price"] * fx_rate

    if base_price <= 0:
        return None

    held_tickers = [h["ticker"] for h in portfolio["vams"]["holdings"]]
    if stock["ticker"] in held_tickers:
        return None

    invest_amount = min(max_per_stock, cash * 0.9)
    brain_score = stock.get("brain_score", 0) or stock.get("verity_brain", {}).get("brain_score", 50)
    invest_amount = _apply_half_kelly(invest_amount, brain_score)
    # Sprint 11 결함 3 — 변동성 기반 sizing 보정 (ATR proxy)
    invest_amount, vol_meta = _apply_volatility_adj(invest_amount, stock)
    if invest_amount < base_price:
        return None

    adv = stock.get("trading_value", stock.get("avg_daily_volume", 0))
    if is_us and adv > 0:
        adv *= fx_rate
    slippage_bps = _estimate_slippage(invest_amount, adv if adv > 0 else _DEFAULT_ADV, p)
    price = base_price * (1 + slippage_bps / 10000)

    quantity = int(invest_amount // price)
    if quantity <= 0:
        return None

    total_cost = quantity * price
    commission = int(total_cost * VAMS_COMMISSION_RATE)
    actual_cost = total_cost + commission

    if actual_cost > cash:
        return None

    asset_class = classify_asset(stock)
    holding = {
        "ticker": stock["ticker"],
        "ticker_yf": stock.get("ticker_yf", f"{stock['ticker']}.KS"),
        "name": stock["name"],
        "currency": stock.get("currency", "KRW"),
        "asset_class": asset_class,
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
        "buy_slippage_bps": round(slippage_bps, 2),
        # Sprint 11 결함 3 — sizing audit
        "volatility_adj": vol_meta,
    }

    portfolio["vams"]["cash"] -= actual_cost
    portfolio["vams"]["holdings"].append(holding)

    history.append({
        "type": "BUY",
        "date": now_kst().strftime("%Y-%m-%d %H:%M"),
        "ticker": stock["ticker"],
        "name": stock["name"],
        "asset_class": asset_class,
        "price": base_price,
        "effective_price": round(price, 2),
        "slippage_bps": round(slippage_bps, 2),
        "quantity": quantity,
        "total": actual_cost,
        "reason": holding["buy_reason"],
    })

    print(f"[VAMS] 매수: {stock['name']} {quantity}주 @ {price:,.0f}원 (슬리피지 {slippage_bps:.1f}bp, 총 {actual_cost:,}원)")
    return holding


def execute_sell(portfolio: dict, holding: dict, reason: str, history: list,
                  profile: Optional[dict] = None, adv: float = 0) -> dict:
    """가상 매도 실행 (슬리피지 반영)"""
    p = _get_profile(profile)
    base_price = holding["current_price"]
    quantity = holding["quantity"]

    order_value = quantity * base_price
    effective_adv = adv if adv > 0 else _DEFAULT_ADV
    slippage_bps = _estimate_slippage(order_value, effective_adv, p)
    price = base_price * (1 - slippage_bps / 10000)

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
        "asset_class": holding.get("asset_class") or classify_asset(holding),
        "price": base_price,
        "effective_price": round(price, 2),
        "slippage_bps": round(slippage_bps, 2),
        "quantity": quantity,
        "total": actual_revenue,
        "pnl": pnl,
        "reason": reason,
    })

    print(f"[VAMS] 매도: {holding['name']} {quantity}주 @ {price:,.0f}원 (슬리피지 {slippage_bps:.1f}bp, 손익: {pnl:+,}원) | 사유: {reason}")
    return {"ticker": holding["ticker"], "name": holding["name"], "pnl": pnl, "slippage_bps": round(slippage_bps, 2), "reason": reason}


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
    # VAMS_INITIAL_CASH 가 0/음수로 잘못 설정돼도 ZeroDivisionError 방지
    initial = VAMS_INITIAL_CASH if VAMS_INITIAL_CASH and VAMS_INITIAL_CASH > 0 else 1
    portfolio["vams"]["total_return_pct"] = round(
        ((total - initial) / initial) * 100, 2
    )


def compute_adjusted_return(portfolio: dict, history: list) -> dict:
    """VAMS 수익률을 실매매 기준으로 보정.

    공식:
      보정 = VAMS 수익률 − (매도 시 거래세) − (왕복 슬리피지) − (배당 × 배당세)

    구현 원칙:
      - VAMS 본체는 이미 수수료(VAMS_COMMISSION_RATE)·시장충격 슬리피지(Almgren-Chriss)를 반영.
        따라서 중복 차감하지 않고, 누락된 3항목만 추가로 차감한다.
      - **세율은 종목 타입별 분기** (KR 일반주 / KR ETF / US 주식·ETF)
      - 실현 매도: history.SELL 각 엔트리의 asset_class로 세율 선택 (누락 시 'KR_STOCK' 기본)
      - 미실현 보유: holdings 각 종목의 asset_class로 세율 선택 (매도 가정)
      - 매수 시 거래세는 0 — 집계 자체에 BUY를 포함하지 않음
      - 배당: portfolio.vams.dividend_received 필드가 있을 때만 과세. 배당 수집기 미구현 시 0.
        6개월 판정 시 코스피 평균 배당 2~3% 누락 가능 → 수집기 백필 계획 세워둘 것.
    """
    vams = portfolio.get("vams", {}) or {}
    total_asset = float(vams.get("total_asset", VAMS_INITIAL_CASH) or VAMS_INITIAL_CASH)
    holdings = vams.get("holdings", []) or []

    spread_rate = float(VAMS_SPREAD_SLIPPAGE_BPS) / 10000.0

    # 실현 매도: 종목 타입별 거래세 + 스프레드
    sell_tax_realized = 0.0
    spread_realized = 0.0
    sell_tax_by_class: dict = {}
    for h in history:
        if h.get("type") != "SELL":
            continue
        total = float(h.get("total", 0) or 0)
        ac = h.get("asset_class") or "KR_STOCK"
        tax_rate = _SELL_TAX_BY_CLASS.get(ac, VAMS_SELL_TAX_KR_STOCK)
        tax = total * tax_rate
        sell_tax_realized += tax
        spread_realized += total * spread_rate
        sell_tax_by_class[ac] = sell_tax_by_class.get(ac, 0.0) + tax

    # 미실현 보유: 매도 가정 → 종목 타입별 거래세 + 스프레드
    sell_tax_unrealized = 0.0
    spread_unrealized = 0.0
    unrealized_value = 0.0
    for h in holdings:
        value = float(h.get("current_price", 0) or 0) * float(h.get("quantity", 0) or 0)
        if value <= 0:
            continue
        ac = h.get("asset_class") or classify_asset(h)
        tax_rate = _SELL_TAX_BY_CLASS.get(ac, VAMS_SELL_TAX_KR_STOCK)
        sell_tax_unrealized += value * tax_rate
        spread_unrealized += value * spread_rate
        unrealized_value += value

    dividend_received = float(vams.get("dividend_received", 0) or 0)
    dividend_tax = dividend_received * VAMS_DIVIDEND_TAX_RATE

    total_deduction = (
        sell_tax_realized + spread_realized
        + sell_tax_unrealized + spread_unrealized
        + dividend_tax
    )

    adjusted_asset = total_asset - total_deduction
    initial = VAMS_INITIAL_CASH if VAMS_INITIAL_CASH and VAMS_INITIAL_CASH > 0 else 1
    adjusted_return_pct = round(((adjusted_asset - initial) / initial) * 100, 2)

    raw_return_pct = float(vams.get("total_return_pct", 0.0) or 0.0)
    gap_pp = round(raw_return_pct - adjusted_return_pct, 2)

    return {
        "adjusted_total_asset": round(adjusted_asset, 2),
        "adjusted_return_pct": adjusted_return_pct,
        "raw_return_pct": raw_return_pct,
        "gap_pp": gap_pp,
        "deductions": {
            "sell_tax_realized": round(sell_tax_realized, 2),
            "sell_tax_unrealized_est": round(sell_tax_unrealized, 2),
            "spread_slippage_realized": round(spread_realized, 2),
            "spread_slippage_unrealized_est": round(spread_unrealized, 2),
            "dividend_tax": round(dividend_tax, 2),
            "total": round(total_deduction, 2),
            "sell_tax_by_class": {k: round(v, 2) for k, v in sell_tax_by_class.items()},
        },
        "assumptions": {
            "sell_tax_rate_pct_by_class": {
                k: round(v * 100, 4) for k, v in _SELL_TAX_BY_CLASS.items()
            },
            "spread_slippage_bps_roundtrip": VAMS_SPREAD_SLIPPAGE_BPS,
            "dividend_tax_rate_pct": round(VAMS_DIVIDEND_TAX_RATE * 100, 4),
            "note": (
                "VAMS 본체는 수수료·시장충격 슬리피지까지 반영. 본 보정은 증권거래세(종목 "
                "타입별 분기)·호가 스프레드·배당세만 추가 차감."
            ),
        },
        "computed_at": now_kst().strftime("%Y-%m-%d %H:%M"),
    }


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
            sell_result = execute_sell(portfolio, holding, reason, history, profile=p)
            alerts.append({
                "type": "STOP_LOSS",
                "message": f"🚨 {sell_result['name']} 매도 | {reason} | 손익: {sell_result['pnl']:+,}원",
            })

    # 3. 신규 매수 — 프로필 기준 필터링 + V6 포트폴리오 노출 제어
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

    buy_candidates.sort(key=lambda s: s.get("safety_score", 0), reverse=True)

    bought = 0
    for stock in buy_candidates:
        if bought >= max_buy:
            break

        exposure = _check_portfolio_exposure(portfolio, stock)
        if exposure.get("blocked"):
            alerts.append({
                "type": "EXPOSURE_BLOCK",
                "message": f"⛔ {stock.get('name', '?')} 매수 차단: {exposure['reason']}",
            })
            continue

        result = execute_buy(portfolio, stock, history, p)
        if result:
            bought += 1
            alerts.append({
                "type": "NEW_BUY",
                "message": f"✅ {result['name']} 매수 | {result['quantity']}주 @ {result['buy_price']:,}원 | 사유: {result['buy_reason']}",
            })

    # 3.5. 배당 수령 처리 (KR) — 오늘이 ex_date 인 보유 종목의 배당을 누적.
    # 데이터는 data/dividends_kr.json (별도 cron 으로 수집). DB 없으면 no-op.
    try:
        from api.collectors.dividend_kr import get_ex_dates_today
        kr_tickers = [
            h["ticker"] for h in portfolio["vams"]["holdings"]
            if h.get("currency", "KRW") == "KRW" and h.get("ticker")
        ]
        due_today = get_ex_dates_today(kr_tickers)
        if due_today:
            vams_dict = portfolio.setdefault("vams", {})
            for div in due_today:
                tk = div.get("ticker")
                amount_per_share = float(div.get("announced_amount_per_share") or 0)
                if amount_per_share <= 0:
                    continue
                hold = next((h for h in portfolio["vams"]["holdings"] if h.get("ticker") == tk), None)
                if not hold:
                    continue
                total_amount = amount_per_share * float(hold.get("quantity", 0) or 0)
                if total_amount <= 0:
                    continue
                vams_dict["dividend_received"] = float(vams_dict.get("dividend_received", 0) or 0) + total_amount
                vams_dict["cash"] = float(vams_dict.get("cash", 0) or 0) + total_amount  # 배당 수령 = 현금 증가
                history.append({
                    "type": "DIVIDEND",
                    "date": now_kst().strftime("%Y-%m-%d %H:%M"),
                    "ticker": tk,
                    "name": hold.get("name", tk),
                    "amount_per_share": amount_per_share,
                    "quantity": hold.get("quantity", 0),
                    "total": round(total_amount, 2),
                    "ex_date": div.get("ex_date"),
                    "is_confirmed": div.get("is_confirmed", False),
                    "source": div.get("source"),
                })
                alerts.append({
                    "type": "DIVIDEND",
                    "message": f"💰 {hold.get('name', tk)} 배당 수령 | {int(total_amount):,}원 (주당 {int(amount_per_share):,}원)",
                })
    except Exception as e:
        print(f"[VAMS] 배당 누적 실패 (무시): {e}")

    # 4. 재계산
    recalculate_total(portfolio)

    # 4.1. 실매매 보정 수익률 — 거래세·스프레드·배당세 추가 차감
    portfolio["vams"]["adjusted_performance"] = compute_adjusted_return(portfolio, history)

    # 4.2. 사전 약속 판정 보고 (3·6·12개월 체크포인트용).
    # 스냅샷 I/O 실패해도 VAMS 사이클 자체는 성공해야 하므로 감싸둠.
    try:
        from api.vams.validation import compute_validation_report
        portfolio["vams"]["validation_report"] = compute_validation_report(portfolio, history)
    except Exception as e:
        print(f"[VAMS] validation_report 계산 실패 (무시): {e}")

    # 프로필 이름 기록
    portfolio["vams"]["active_profile"] = VAMS_ACTIVE_PROFILE

    save_history(history)
    print(f"[VAMS] 사이클 완료 — 프로필: {p['label']} | 매도: {sum(1 for a in alerts if a['type'] == 'STOP_LOSS')}건 | 매수: {bought}건 | 후보: {len(buy_candidates)}종목")
    return portfolio, alerts
