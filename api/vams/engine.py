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
    VAMS_DIVIDEND_TAX_RATE_KR,
    VAMS_DIVIDEND_TAX_RATE_US,
    VAMS_US_CAPITAL_GAINS_RATE,
    VAMS_US_CAPITAL_GAINS_DEDUCTION_KRW,
    VAMS_US_FX_COST_RATE,
    VAMS_KR_MAJORITY_SHAREHOLDER,
    VAMS_KR_MAJORITY_TAX_RATE_BASE,
    VAMS_KR_MAJORITY_TAX_RATE_HIGH,
    VAMS_KR_MAJORITY_TAX_RATE_SHORT,
    VAMS_KR_MAJORITY_HIGH_THRESHOLD_KRW,
    VAMS_ISA_DEDUCTION_KRW,
    VAMS_ISA_EXCESS_TAX_RATE,
    VAMS_DIVIDEND_COMPREHENSIVE_THRESHOLD_KRW,
    VAMS_KR_GEUMTU_RESTORED,
    VAMS_KR_GEUMTU_DEDUCTION_KRW,
    VAMS_KR_GEUMTU_TAX_RATE_BASE,
    VAMS_KR_GEUMTU_TAX_RATE_HIGH,
    VAMS_KR_GEUMTU_HIGH_THRESHOLD_KRW,
    PORTFOLIO_PATH,
    RECOMMENDATIONS_PATH,
    VERITY_MODE,
    HISTORY_PATH,
    DATA_DIR,
    now_kst,
    ATR_METHOD as _ATR_METHOD_RUNTIME,  # Phase 0 P-03 (audit fallback)
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
            # Capital 3-Tier sub-PnL (2026-05-17, project_capital_3tier_mode prep)
            # 보수 60% / 중간 30% / 공격 10% 분리 추적. holdings.mode_tag 정합.
            "tier_pnl": {
                "conservative": 0,
                "moderate": 0,
                "aggressive": 0,
            },
            "tier_capital_allocation": {
                "conservative": round(VAMS_INITIAL_CASH * 0.60, 2),
                "moderate": round(VAMS_INITIAL_CASH * 0.30, 2),
                "aggressive": round(VAMS_INITIAL_CASH * 0.10, 2),
            },
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
    # 2026-05-20 — backtest 는 size(recent_trades 배열) 때문에 _REC_EXCLUDE_FIELDS 로 strip 됐으나,
    # brain _backtest_to_score 가 quick mode 에서 portfolio.json 의 backtest(total_trades/win_rate/
    # sharpe_ratio)를 읽음 → strip 시 전 종목 50 fallback (backtest @50 결함 root cause).
    # scalar 만 보존하고 recent_trades 배열만 drop (size 거의 0, 신호는 quick mode 까지 도달).
    slimmed = []
    for r in recs:
        s = {k: v for k, v in r.items() if k not in _REC_EXCLUDE_FIELDS}
        bt = r.get("backtest")
        if isinstance(bt, dict):
            s["backtest"] = {k: v for k, v in bt.items() if k != "recent_trades"}
        slimmed.append(s)
    return slimmed


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
    # 2026-07-20 감사 P0: dev-mode 사이클이 prod history.json 에 phantom 매도 기록 →
    # mode별 경로 분리(rec 패턴 engine.py:325 정합). prod 매매이력 오염 차단(win_rate 왜곡 근원).
    dest = HISTORY_PATH if VERITY_MODE == "prod" else HISTORY_PATH.replace(".json", ".dev.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2, allow_nan=False)


def _get_profile(profile: Optional[dict] = None) -> dict:
    """프로필 dict를 반환. None이면 활성 프로필 사용."""
    if profile is not None:
        return profile
    return VAMS_PROFILES.get(VAMS_ACTIVE_PROFILE, VAMS_PROFILES["moderate"])


def check_stop_loss(holding: dict, profile: Optional[dict] = None) -> Tuple[bool, str]:
    """프로필 기반 손절/익절 조건 체크.

    Phase 1.1 (2026-05-01) — holding.stop_loss_pct_individual (ATR 동적) 우선.
    프로파일 stop_loss_pct 는 **상한선** (더 보수적) 작동.
      profile=-8%, individual=-10% → max(-8, -10) = -8 (profile 우선, 더 빨리 트리거)
      profile=-8%, individual=-5%  → max(-8, -5)  = -5 (individual 우선, 더 빨리 트리거)
    """
    p = _get_profile(profile)
    profile_stop_pct = p["stop_loss_pct"]
    trailing_stop_pct = p["trailing_stop_pct"]
    max_hold_days = p["max_hold_days"]

    # 개별 산출값이 있으면 보수적인 (덜 음수인 = 더 빨리 트리거되는) 쪽 채택
    individual_stop_pct = holding.get("stop_loss_pct_individual")
    if individual_stop_pct is not None:
        effective_stop_pct = max(profile_stop_pct, individual_stop_pct)
        stop_method = (
            "individual_atr"
            if effective_stop_pct == individual_stop_pct
            else "profile_cap"
        )
    else:
        effective_stop_pct = profile_stop_pct
        stop_method = "profile_default"

    buy_price = holding["buy_price"]
    current_price = holding["current_price"]
    return_pct = ((current_price - buy_price) / buy_price) * 100

    if return_pct <= effective_stop_pct:
        # Phase 0 P-03 — method mismatch audit (정상 동작, 알림 없음).
        entry_method = holding.get("atr_method_at_entry")
        if entry_method and entry_method != _ATR_METHOD_RUNTIME:
            holding.setdefault("audit", {})["method_mismatch_at_exit"] = {
                "entry_method": entry_method,
                "exit_runtime_method": _ATR_METHOD_RUNTIME,
                "exit_date": now_kst().strftime("%Y-%m-%d %H:%M"),
                "stop_price_preserved": holding.get("stop_loss_price"),
            }
        return True, f"고정 손절 ({return_pct:.1f}% ≤ {effective_stop_pct}%) [{stop_method}]"

    highest = holding.get("highest_price", buy_price)
    if current_price > highest:
        highest = current_price

    # Phase 1.2 — exit_targets 있는 holding 은 trailing_active=True 일 때만 트레일링 발동
    # (target_2 +2R 도달 후 남은 20% 에만 적용). exit_targets 없는 legacy holding 은 기존 동작.
    has_exit_targets = bool(holding.get("exit_targets"))
    trailing_eligible = (
        holding.get("trailing_active", False) if has_exit_targets else (highest > buy_price)
    )
    if trailing_eligible and highest > buy_price:
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


# ── β USD ETF FX 헷지 reserve (2026-05-18 PM 결정, 5/22 실행) ──────────────
# holdings 가 아닌 별도 필드 = Brain auto-sell(verdict/stop) 구조적 제외.
# USD SOFR ETF = 현금등가 → USDKRW 로 MtM (ETF KR 가격 피드 불요, 환손익 only).
# 진입 = pending sentinel(data/vams/pending_fx_hedge.json) 을 cron cycle 1회 소비.
_PENDING_FX_HEDGE_PATH = os.path.join(DATA_DIR, "vams", "pending_fx_hedge.json")


def enter_fx_hedge(
    portfolio: dict, *, krw_amount: float, usdkrw: float,
    ticker: str, name: str, reason: str,
) -> dict:
    """cash → fx_hedge_reserve 이동. 단일 β 포지션 (중복 진입 거부)."""
    v = portfolio.setdefault("vams", {})
    if v.get("fx_hedge_reserve"):
        return {"ok": False, "reason": "fx_hedge_reserve 이미 존재 (단일 β)"}
    cash = float(v.get("cash", 0))
    if krw_amount <= 0 or krw_amount > cash:
        return {"ok": False, "reason": f"krw_amount {krw_amount} > cash {cash} 또는 ≤0"}
    if usdkrw <= 0:
        return {"ok": False, "reason": f"usdkrw {usdkrw} 비정상"}
    usd_value = krw_amount / usdkrw  # full precision (MtM 기준, 반올림 X — ×fx 재계산 오차 방지)
    v["cash"] = round(cash - krw_amount, 2)
    v["fx_hedge_reserve"] = {
        "kind": "fx_hedge_beta",
        "ticker": str(ticker),
        "name": name,
        "krw_invested": round(krw_amount, 2),
        "entry_usdkrw": round(usdkrw, 2),
        "usd_value": usd_value,                 # USD 원금 (MtM 기준, full precision)
        "entry_date": now_kst().strftime("%Y-%m-%d"),
        "current_krw": round(krw_amount, 2),    # 진입 시 = 원금
        "pnl_krw": 0.0,
        "return_pct": 0.0,
        "reason": reason,
    }
    return {"ok": True, "usd_value": usd_value, "cash_after": v["cash"]}


def _consume_pending_fx_hedge(portfolio: dict) -> None:
    """pending sentinel → fx_hedge_reserve 진입. idempotent (persist 확정까지 sentinel 유지).

    2026-05-22 재설계 — 옛 버그: 비-영속 run(quick/off-hours)이 sentinel 을 소비(삭제)했으나
    portfolio.json 저장 안 해서 reserve 유실 (sentinel 만 사라짐). fix:
      - portfolio 에 이미 reserve 있으면(= 영속 완료) → sentinel 제거 (job done).
      - reserve 없으면 → enter 시도, **sentinel 보존**. 이 run 이 persist 안 해도
        다음 영속 run 이 재진입. 영속 후 다음 run 이 위 분기로 sentinel 정리.
      - 멱등: 매 run portfolio.json 을 fresh load → reserve 있으면 재진입 안 함 (이중 진입 X).
    silent-fail.
    """
    import sys
    if not os.path.exists(_PENDING_FX_HEDGE_PATH):
        return
    try:
        v = portfolio.setdefault("vams", {})
        if v.get("fx_hedge_reserve"):
            # 이미 진입·영속됨 → sentinel 정리 (job done).
            os.remove(_PENDING_FX_HEDGE_PATH)
            print("[fx_hedge] reserve 이미 존재 — sentinel 정리(완료)", file=sys.stderr, flush=True)
            return
        with open(_PENDING_FX_HEDGE_PATH, "r", encoding="utf-8") as f:
            spec = json.load(f)
        usdkrw = float(spec.get("usdkrw") or _get_fx_rate(portfolio))
        r = enter_fx_hedge(
            portfolio,
            krw_amount=float(spec["krw_amount"]),
            usdkrw=usdkrw,
            ticker=spec["ticker"],
            name=spec.get("name", spec["ticker"]),
            reason=spec.get("reason", "β USD ETF FX 헷지 (PM 결정)"),
        )
        # sentinel 보존 — 이 run 이 portfolio.json 저장하면 다음 run 이 정리.
        # (persist 안 하는 run 이 소비해도 intent 유실 X = 이번 fix 핵심.)
        print(f"[fx_hedge] 진입 시도: {r} (sentinel 보존, persist 후 정리) logged=True",
              file=sys.stderr, flush=True)
    except Exception as e:
        print(f"[fx_hedge] pending 소비 실패 — {type(e).__name__}: {e}", file=sys.stderr, flush=True)


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

    # atr 부재 시 fallback = 실 일간변동성(top-level volatility_20d 분수) → 연환산%(×√252×100).
    # 🚨 2026-06-12: 옛 fallback 은 prediction.top_features.volatility_20d 를 읽었으나 그 값은
    #   xgb 정규화 feature importance(vol 아님)라 percent 임계 비교가 무의미했음. production 은
    #   technical.atr_14d_pct 가 25/25 상존 → 이 fallback 미도달(latent dead) → 실 vol 재배선으로
    #   교정. √252 = mean_reversion canonical(:122) 정합. 임계(15/30) 불변.
    vol_frac = stock.get("volatility_20d")
    if not isinstance(vol_frac, (int, float)) or vol_frac <= 0:
        return invest_amount, {"applied": False, "reason": "no_volatility_data"}
    vol = vol_frac * (252 ** 0.5) * 100.0  # 일간분수 → 연환산%

    if vol <= 15.0:
        scale, tier = 1.0, "low"
    elif vol <= 30.0:
        scale, tier = 0.85, "mid"
    else:
        scale, tier = 0.70, "high"

    return invest_amount * scale, {
        "applied": True,
        "tier": tier,
        "volatility_20d_ann_pct": round(vol, 2),
        "scale": scale,
        "source": "volatility_20d_annualized",
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
    # Regime-aware position sizing (2026-05-23 PM 승인, RULE 7) — macro/regime multiplier 를
    # 점수가 아닌 사이징에 적용. macro 비관(고밸류/CAPE/통화) 시 포지션 0.7~1.0× 축소.
    # 신호(grade) ⊥ 사이징(macro). 근거: project_regime_aware_position_sizing (5/19 학술).
    macro_size_mult = 1.0
    _mm = stock.get("macro_multiplier")
    if isinstance(_mm, dict):
        macro_size_mult = max(0.0, min(1.0, float(_mm.get("multiplier", 1.0) or 1.0)))
    invest_amount = invest_amount * macro_size_mult
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

    # Phase 1.1 (2026-05-01) — trade_plan stop_loss 산출값을 진입 시 holding 에 영속화.
    # check_stop_loss 가 individual 우선 사용 (프로파일은 상한 작동).
    _trade_plan = stock.get("trade_plan") or {}
    _stop_loss_obj = _trade_plan.get("stop_loss") or {}
    individual_stop_pct = _stop_loss_obj.get("stop_loss_pct")  # ATR 또는 fallback 산출값
    stop_loss_method = _stop_loss_obj.get("method")  # atr_dynamic | fixed_fallback | None

    # Phase 0 P-03 (2026-05-01) — ATR 산출법 audit. 진입 시점의 ATR_METHOD 영속화.
    # 마이그레이션 후에도 기존 holding 의 stop_price/risk_per_share/exit_targets 모두 entry method 기반으로 변경 X.
    # check_stop_loss 가 mismatch 감지 시 audit log + holding 이력 (동작 변경 없음).
    _atr_method_at_entry = (stock.get("technical") or {}).get("atr_14d_method") or _ATR_METHOD_RUNTIME

    # P2-2 prep (2026-05-17, Perplexity Q3 학계 자문 적용):
    # Capital 3-Tier mode_tag inferred 산식. docs/PHILOSOPHY_TIER_ROUTING_v0.md 정합.
    #
    # 보수 (60%): Score ≥ 75 AND |VCI| < 15 (시장 동의 확인된 정합형 STRONG_BUY)
    # 중간 (30%): Score ≥ 60 AND CS ≥ 55 (중간 확신 BUY, Druckenmiller conviction 정합)
    # 공격 (10%): 두 분기
    #   - Score ≥ 75 AND Catalyst ✓ (촉매 기반 집중 배팅)
    #   - Score 60~74 AND VCI ≥ 20 AND fact_score ≥ 60 (Cohen-style contrarian)
    # 외 = moderate default (안전).
    #
    # Tier 별 MDD 임계 (Perplexity Q3): 보수 7% / 중간 15% / 공격 33%. 전체 동시 = 12%.
    # routing logic 진짜 (자본 분리 + sub-PnL + tier 별 ATR 차별) = 별 sprint.
    inferred_mode = stock.get("mode_tag")
    if not inferred_mode:
        brain = stock.get("brain", {}) or {}
        brain_score = brain.get("brain_score", 0)
        vci = brain.get("vci")
        if isinstance(vci, dict):
            vci_value = abs(vci.get("score") or vci.get("value") or 0)
        else:
            vci_value = abs(vci or 0)
        fact_score = brain.get("fact_score")
        if isinstance(fact_score, dict):
            fact_value = fact_score.get("score", 0)
        else:
            fact_value = fact_score or 0
        catalyst_active = bool(
            (stock.get("catalysts") or {}).get("active")
            or stock.get("has_catalyst")
        )
        cs = (brain.get("conviction_score")
              or (brain.get("druckenmiller_conviction") or {}).get("cs", 0))

        # 보수: STRONG_BUY + 시장 동의
        if brain_score >= 75 and vci_value < 15:
            inferred_mode = "conservative"
        # 공격 분기 1: STRONG_BUY + 촉매
        elif brain_score >= 75 and catalyst_active:
            inferred_mode = "aggressive"
        # 공격 분기 2: Cohen-style contrarian
        elif 60 <= brain_score < 75 and vci_value >= 20 and fact_value >= 60:
            inferred_mode = "aggressive"
        # 중간: BUY + Conviction
        elif brain_score >= 60 and cs >= 55:
            inferred_mode = "moderate"
        # default
        else:
            inferred_mode = "moderate"

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
        # 2026-05-23 RULE 7 — regime-aware 사이징 적용 multiplier (audit)
        "macro_size_multiplier": round(macro_size_mult, 3),
        # Phase 1.1 — ATR 기반 동적 손절 (개별 산출값)
        "stop_loss_pct_individual": individual_stop_pct,
        "stop_loss_method": stop_loss_method,
        # Phase 0 P-03 — ATR 산출법 audit (마이그레이션 holding 보호)
        "atr_method_at_entry": _atr_method_at_entry,
        # Phase 1.2 — R-multiple 부분 익절
        "exit_targets": _trade_plan.get("exit_targets"),
        "exit_history": [],  # [{target_id, sold_qty, sold_price, r_multiple, at}]
        "trailing_active": False,  # +2R 도달 후 True (남은 20% 만 트레일링)
        "realized_pnl_partial": 0,  # 부분 청산 누적 실현 손익
        # P2-2 prep — Capital 3-Tier mode tag. routing logic 별 sprint.
        "mode_tag": inferred_mode,
    }

    portfolio["vams"]["cash"] -= actual_cost
    portfolio["vams"]["holdings"].append(holding)

    # Capital 3-Tier hard cap (CAPITAL_3TIER_HARD_CAP_ENABLED=true 시 활성, Perplexity Q3).
    # tier 별 자본 초과 매수 차단. False (default) = soft (mode_tag 추적만, sub-PnL 누적).
    try:
        from api.config import CAPITAL_3TIER_HARD_CAP_ENABLED
        if CAPITAL_3TIER_HARD_CAP_ENABLED:
            _alloc = portfolio["vams"].get("tier_capital_allocation", {})
            _tier_alloc = _alloc.get(holding["mode_tag"], float("inf"))
            _tier_used = sum(
                h.get("total_cost", 0) for h in portfolio["vams"]["holdings"]
                if h.get("mode_tag") == holding["mode_tag"]
            )
            if _tier_used + actual_cost > _tier_alloc:
                print(
                    f"[VAMS] tier {holding['mode_tag']} hard cap 초과: "
                    f"used {_tier_used:,.0f} + new {actual_cost:,.0f} > alloc {_tier_alloc:,.0f}"
                )
                return None  # reject
    except (ImportError, KeyError):
        pass  # config 미설정 또는 vams 구조 옛 — silent

    # FOMO Score 산출 정합 (api/quant/fomo_score.py):
    # rule_id 설정되어 있으면 auto (rule-based), 없으면 manual (사용자 override). VAMS engine 호출 =
    # 모두 auto (verdict 기반). 외부 호출 (수동 매매 endpoint) = rule_id 미설정 → manual 분리.
    history.append({
        "type": "BUY",
        "date": now_kst().strftime("%Y-%m-%d %H:%M"),
        "timestamp": now_kst().isoformat(timespec="seconds"),
        "ticker": stock["ticker"],
        "name": stock["name"],
        "asset_class": asset_class,
        "price": base_price,
        "effective_price": round(price, 2),
        "slippage_bps": round(slippage_bps, 2),
        "quantity": quantity,
        "total": actual_cost,
        "reason": holding["buy_reason"],
        "rule_id": f"verdict_{stock.get('recommendation', 'BUY')}",  # FOMO 정합
        "mode_tag": holding.get("mode_tag", "moderate"),  # Capital 3-Tier 정합
    })

    print(f"[VAMS] 매수: {stock['name']} {quantity}주 @ {price:,.0f}원 (슬리피지 {slippage_bps:.1f}bp, 총 {actual_cost:,}원)")
    return holding


def _append_exit_log(record: dict) -> None:
    """VAMS 매도 exit_reason 영속 로그 (append-only jsonl) — Step A 인프라.

    2026-05-17 ATR Phase 1.5.1 게이트 FAIL 원인: VAMS 가 summary stats 만 영속화 →
    exit_reason 분해 불가 → actual_stop_hit_rate 산출 불가. 본 로그가 그 결함 fix.
    silent-skip 금지: 실패 시 stderr 명시 ([[feedback_data_collection_verification_mandatory]]).
    """
    import sys
    path = os.path.join(DATA_DIR, "vams", "exit_log.jsonl")
    # 2026-07-20 감사 P0: dev-mode phantom 매도 prod exit_log 오염 차단 — mode별 경로 분리
    if VERITY_MODE != "prod":
        path = path.replace(".jsonl", ".dev.jsonl")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        print(f"[VAMS] exit_log append 실패: {e}", file=sys.stderr, flush=True)


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
    # Capital 3-Tier sub-PnL update (2026-05-17 prep)
    _tier = holding.get("mode_tag", "moderate")
    _tier_pnl_dict = portfolio["vams"].setdefault("tier_pnl", {"conservative": 0, "moderate": 0, "aggressive": 0})
    _tier_pnl_dict[_tier] = round(_tier_pnl_dict.get(_tier, 0) + pnl, 2)
    portfolio["vams"]["total_realized_pnl"] = (
        portfolio["vams"].get("total_realized_pnl", 0) + pnl
    )

    # FOMO Score 정합 — reason 기반 rule_id 추정.
    # auto: "verdict_to_AVOID" / "stop_loss" / "exit_target_*" 등. manual: "manual" / "user_override"
    _rule_id_inferred = (
        reason if reason and any(k in (reason or "").lower() for k in
                                 ["verdict", "stop", "exit", "trail", "atr", "circuit"])
        else None  # manual = rule_id None
    )
    history.append({
        "type": "SELL",
        "date": now_kst().strftime("%Y-%m-%d %H:%M"),
        "timestamp": now_kst().isoformat(timespec="seconds"),
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
        "rule_id": _rule_id_inferred,  # FOMO Score 정합 (None = manual)
        "mode_tag": holding.get("mode_tag", "moderate"),  # Capital 3-Tier
    })

    # Step A: exit_reason 영속 로그 (actual_stop_hit_rate 산출용). stop_loss trigger 식별.
    _is_stop = bool(_rule_id_inferred and any(
        k in (_rule_id_inferred or "").lower() for k in ["stop", "atr", "circuit"]))
    _total_cost = holding.get("total_cost") or 0
    _append_exit_log({
        "ts": now_kst().isoformat(timespec="seconds"),
        "date": now_kst().strftime("%Y-%m-%d"),
        "ticker": holding["ticker"],
        "name": holding["name"],
        "exit_type": "full",
        "reason": reason,
        "rule_id": _rule_id_inferred,
        "is_stop_loss": _is_stop,
        "pnl": pnl,
        "pnl_pct": round(pnl / _total_cost * 100, 2) if _total_cost else None,
        "stop_loss_method": holding.get("stop_loss_method"),
        "stop_loss_pct_individual": holding.get("stop_loss_pct_individual"),
        "mode_tag": holding.get("mode_tag", "moderate"),
    })

    print(f"[VAMS] 매도: {holding['name']} {quantity}주 @ {price:,.0f}원 (슬리피지 {slippage_bps:.1f}bp, 손익: {pnl:+,}원) | 사유: {reason}")
    return {"ticker": holding["ticker"], "name": holding["name"], "pnl": pnl, "slippage_bps": round(slippage_bps, 2), "reason": reason}


# ───────────────────────────────────────────────────────────────────
# Phase 1.2 — R-multiple 부분 익절 (2026-05-01)
# ───────────────────────────────────────────────────────────────────

def execute_partial_sell(
    portfolio: dict,
    holding: dict,
    target_id: str,
    target: dict,
    history: list,
    profile: Optional[dict] = None,
) -> dict:
    """부분 청산 — holding 은 portfolio 에 유지 (남은 수량). exit_history 에 row append.

    Returns: {target_id, sold_qty, sold_price, r_multiple, partial_pnl}
    """
    p = _get_profile(profile)
    base_price = holding["current_price"]
    total_quantity = holding["quantity"]
    exit_pct = target.get("exit_pct", 0)

    # 청산 수량 계산 (정수 round down)
    shares_to_sell = int(total_quantity * exit_pct / 100)
    if shares_to_sell <= 0:
        # 너무 작아서 청산 불가 — 스킵 처리, exit_history 에 기록
        holding.setdefault("exit_history", []).append({
            "target_id": target_id,
            "status": "skipped_too_small",
            "total_quantity": total_quantity,
            "exit_pct": exit_pct,
            "at": now_kst().strftime("%Y-%m-%d %H:%M"),
        })
        return {
            "target_id": target_id, "sold_qty": 0,
            "status": "skipped_too_small",
        }

    # 슬리피지 + 수수료 (execute_sell 과 동일 패턴)
    order_value = shares_to_sell * base_price
    effective_adv = _DEFAULT_ADV
    slippage_bps = _estimate_slippage(order_value, effective_adv, p)
    sold_price = base_price * (1 - slippage_bps / 10000)
    total_revenue = shares_to_sell * sold_price
    commission = int(total_revenue * VAMS_COMMISSION_RATE)
    actual_revenue = total_revenue - commission

    # 부분 손익 = 매도분 revenue - 매도분 cost (per-share)
    cost_per_share = holding["total_cost"] / total_quantity if total_quantity > 0 else 0
    partial_cost = cost_per_share * shares_to_sell
    partial_pnl = actual_revenue - partial_cost

    # holding 갱신 — 잔여 수량으로 차감
    holding["quantity"] = total_quantity - shares_to_sell
    holding["total_cost"] = round(holding["total_cost"] - partial_cost, 2)
    holding["realized_pnl_partial"] = round(
        holding.get("realized_pnl_partial", 0) + partial_pnl, 2
    )

    # exit_history 기록
    r_multiple = target.get("r_multiple")
    holding.setdefault("exit_history", []).append({
        "target_id": target_id,
        "status": "executed",
        "sold_qty": shares_to_sell,
        "sold_price": round(sold_price, 2),
        "base_price": base_price,
        "slippage_bps": round(slippage_bps, 2),
        "exit_pct": exit_pct,
        "r_multiple": r_multiple,
        "partial_pnl": round(partial_pnl, 2),
        "at": now_kst().strftime("%Y-%m-%d %H:%M"),
    })

    # target_2 (2R) 도달 시 trailing_active=True (남은 20% 트레일링 활성)
    if target_id == "target_2":
        holding["trailing_active"] = True

    portfolio["vams"]["cash"] += actual_revenue
    # Capital 3-Tier sub-PnL update — partial sell (2026-05-17)
    _tier_p = holding.get("mode_tag", "moderate")
    _tier_pnl_p = portfolio["vams"].setdefault("tier_pnl", {"conservative": 0, "moderate": 0, "aggressive": 0})
    _tier_pnl_p[_tier_p] = round(_tier_pnl_p.get(_tier_p, 0) + partial_pnl, 2)
    portfolio["vams"]["total_realized_pnl"] = round(
        portfolio["vams"].get("total_realized_pnl", 0) + partial_pnl, 2
    )

    history.append({
        "type": "PARTIAL_SELL",
        "target_id": target_id,
        "date": now_kst().strftime("%Y-%m-%d %H:%M"),
        "timestamp": now_kst().isoformat(timespec="seconds"),
        "ticker": holding["ticker"],
        "name": holding["name"],
        "price": base_price,
        "effective_price": round(sold_price, 2),
        "slippage_bps": round(slippage_bps, 2),
        "quantity": shares_to_sell,
        "remaining_quantity": holding["quantity"],
        "total": actual_revenue,
        "partial_pnl": round(partial_pnl, 2),
        "r_multiple": r_multiple,
        "reason": target.get("reason", f"{target_id} reached"),
        "rule_id": f"exit_target_{target_id}",  # FOMO Score 정합 (auto)
        "mode_tag": holding.get("mode_tag", "moderate"),
    })

    print(
        f"[VAMS] 부분 익절 {target_id}: {holding['name']} {shares_to_sell}주 @ {sold_price:,.0f}원 "
        f"({exit_pct}%) | R={r_multiple} | 부분 손익 {partial_pnl:+,.0f}원 | 잔여 {holding['quantity']}주"
    )
    return {
        "target_id": target_id,
        "sold_qty": shares_to_sell,
        "sold_price": round(sold_price, 2),
        "r_multiple": r_multiple,
        "partial_pnl": round(partial_pnl, 2),
        "remaining_quantity": holding["quantity"],
        "trailing_active": holding.get("trailing_active", False),
    }


def check_partial_exit(
    portfolio: dict,
    holding: dict,
    history: list,
    profile: Optional[dict] = None,
) -> list[dict]:
    """holding 의 exit_targets 평가. 도달한 미실행 target 부분 청산.

    Returns: 실행된 partial sells 리스트 (없으면 빈 리스트).
    """
    targets = holding.get("exit_targets")
    if not targets:
        return []

    current_price = holding["current_price"]
    executed_target_ids = {
        h["target_id"] for h in holding.get("exit_history", []) if h.get("status") == "executed"
    }
    skipped_target_ids = {
        h["target_id"] for h in holding.get("exit_history", []) if h.get("status") == "skipped_too_small"
    }

    results = []
    # 순서대로 평가 — target_1 → target_2. target_3 (트레일링) 은 check_stop_loss 가 처리.
    for target_id in ("target_1", "target_2"):
        target = targets.get(target_id)
        if not target:
            continue
        if target_id in executed_target_ids or target_id in skipped_target_ids:
            continue
        target_price = target.get("price")
        if target_price is None:
            continue
        if current_price >= target_price:
            r = execute_partial_sell(portfolio, holding, target_id, target, history, profile)
            results.append(r)

    return results


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
    # β FX 헷지 reserve MtM — USD 원금 × 현 USDKRW (환손익 only).
    reserve_krw = 0.0
    reserve = portfolio["vams"].get("fx_hedge_reserve")
    if reserve and reserve.get("usd_value"):
        fx = _get_fx_rate(portfolio)
        reserve["current_krw"] = round(reserve["usd_value"] * fx, 2)
        reserve["pnl_krw"] = round(reserve["current_krw"] - reserve["krw_invested"], 2)
        if reserve["krw_invested"]:
            reserve["return_pct"] = round(reserve["pnl_krw"] / reserve["krw_invested"] * 100, 2)
        reserve_krw = reserve["current_krw"]
    total = portfolio["vams"]["cash"] + holdings_value + reserve_krw
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

    # 배당세 — KR/US 출처 분리. dividend_received_kr / _us 우선, 없으면 통합값에 KR 세율 적용.
    # (현 배당 수집기는 KR 만 — engine.py:1206 — 통합값 = KR 가정 유효).
    dividend_received_kr = float(vams.get("dividend_received_kr", vams.get("dividend_received", 0)) or 0)
    dividend_received_us = float(vams.get("dividend_received_us", 0) or 0)
    dividend_total_gross = dividend_received_kr + dividend_received_us

    # ISA mode_tag 적용 — vams.mode_tag == 'isa' 면 비과세 한도 차감
    is_isa = (vams.get("mode_tag") or "").lower() == "isa"
    isa_excess_tax = 0.0
    if is_isa:
        # 한도 차감 (KR + US 통산) → 초과분만 9.9% 분리과세
        isa_quota = float(VAMS_ISA_DEDUCTION_KRW)
        isa_taxable = max(0.0, dividend_total_gross - isa_quota)
        isa_excess_tax = isa_taxable * VAMS_ISA_EXCESS_TAX_RATE
        dividend_tax = isa_excess_tax  # 일반 KR/US 세율 미적용 (ISA 비과세 우선)
    else:
        dividend_tax = (
            dividend_received_kr * VAMS_DIVIDEND_TAX_RATE_KR
            + dividend_received_us * VAMS_DIVIDEND_TAX_RATE_US
        )

    # 금융소득 종합과세 임계 monitoring — 분리과세 유지하되 사용자 신고 영역 안내
    dividend_comprehensive_alert = dividend_total_gross > VAMS_DIVIDEND_COMPREHENSIVE_THRESHOLD_KRW

    # US 양도세 — realized (SELL + PARTIAL_SELL) + unrealized (holdings) 손익통산.
    # 250만 공제 = realized 우선 적용, 잔여만 unrealized 에 적용. KR 양도세는 0% (비과세) 가정.
    # US 환전 비용 (δ_FX) 도 함께 차감 (매도 시 1회).
    _US_CLASSES = ("US_STOCK", "US_ETF")
    realized_us_pnl = 0.0
    us_fx_cost_realized = 0.0
    for h in history:
        if h.get("type") not in ("SELL", "PARTIAL_SELL"):
            continue
        if h.get("asset_class") not in _US_CLASSES:
            continue
        pnl = h.get("pnl")
        if pnl is None:
            pnl = h.get("partial_pnl")
        realized_us_pnl += float(pnl or 0)
        us_fx_cost_realized += float(h.get("total", 0) or 0) * VAMS_US_FX_COST_RATE

    unrealized_us_pnl = 0.0
    us_fx_cost_unrealized = 0.0
    for h in holdings:
        ac = h.get("asset_class") or classify_asset(h)
        if ac not in _US_CLASSES:
            continue
        qty = float(h.get("quantity", 0) or 0)
        current_value = float(h.get("current_price", 0) or 0) * qty
        total_cost_h = h.get("total_cost")
        if total_cost_h is None:
            total_cost_h = float(h.get("buy_price", 0) or 0) * qty
        unrealized_us_pnl += current_value - float(total_cost_h or 0)
        us_fx_cost_unrealized += current_value * VAMS_US_FX_COST_RATE

    deduction_quota = float(VAMS_US_CAPITAL_GAINS_DEDUCTION_KRW)
    realized_taxable = max(0.0, realized_us_pnl - deduction_quota)
    us_capital_gains_tax = realized_taxable * VAMS_US_CAPITAL_GAINS_RATE
    remaining_deduction = max(0.0, deduction_quota - max(0.0, realized_us_pnl))
    unrealized_taxable = max(0.0, unrealized_us_pnl - remaining_deduction)
    us_capital_gains_tax_unrealized_est = unrealized_taxable * VAMS_US_CAPITAL_GAINS_RATE

    # KR 양도세 — 기본 0% (비대주주 비과세 가정). toggle 활성 시 분기:
    #   1. VAMS_KR_MAJORITY_SHAREHOLDER=True → 대주주 세율 (20%/25%/30%, 보유기간 미수집 시 누진만 적용)
    #   2. VAMS_KR_GEUMTU_RESTORED=True → 금투세 재시행 fallback (5000만 공제 / 22%·27.5% 누진)
    # 두 toggle 동시 활성 시 = 대주주 우선 (현 정책 우선순위, 금투세 시행 시 통합 재정의 큐)
    _KR_CLASSES = ("KR_STOCK", "KR_ETF")
    realized_kr_pnl = 0.0
    for h in history:
        if h.get("type") not in ("SELL", "PARTIAL_SELL"):
            continue
        if h.get("asset_class") not in _KR_CLASSES:
            continue
        pnl_h = h.get("pnl")
        if pnl_h is None:
            pnl_h = h.get("partial_pnl")
        realized_kr_pnl += float(pnl_h or 0)

    kr_capital_gains_tax = 0.0
    kr_tax_mode = "none"  # 표기용: "none" / "majority" / "geumtu"
    if VAMS_KR_MAJORITY_SHAREHOLDER and realized_kr_pnl > 0:
        kr_tax_mode = "majority"
        # 1년 미만 보유 판정 데이터 미수집 — 누진만 (보수적). 사용자 명시 시 short rate 별도.
        if realized_kr_pnl <= VAMS_KR_MAJORITY_HIGH_THRESHOLD_KRW:
            kr_capital_gains_tax = realized_kr_pnl * VAMS_KR_MAJORITY_TAX_RATE_BASE
        else:
            base_part = VAMS_KR_MAJORITY_HIGH_THRESHOLD_KRW * VAMS_KR_MAJORITY_TAX_RATE_BASE
            high_part = (realized_kr_pnl - VAMS_KR_MAJORITY_HIGH_THRESHOLD_KRW) * VAMS_KR_MAJORITY_TAX_RATE_HIGH
            kr_capital_gains_tax = base_part + high_part
    elif VAMS_KR_GEUMTU_RESTORED and realized_kr_pnl > VAMS_KR_GEUMTU_DEDUCTION_KRW:
        kr_tax_mode = "geumtu"
        taxable_kr = realized_kr_pnl - VAMS_KR_GEUMTU_DEDUCTION_KRW
        if taxable_kr <= VAMS_KR_GEUMTU_HIGH_THRESHOLD_KRW:
            kr_capital_gains_tax = taxable_kr * VAMS_KR_GEUMTU_TAX_RATE_BASE
        else:
            base_part = VAMS_KR_GEUMTU_HIGH_THRESHOLD_KRW * VAMS_KR_GEUMTU_TAX_RATE_BASE
            high_part = (taxable_kr - VAMS_KR_GEUMTU_HIGH_THRESHOLD_KRW) * VAMS_KR_GEUMTU_TAX_RATE_HIGH
            kr_capital_gains_tax = base_part + high_part

    total_deduction = (
        sell_tax_realized + spread_realized
        + sell_tax_unrealized + spread_unrealized
        + dividend_tax
        + us_capital_gains_tax + us_capital_gains_tax_unrealized_est
        + us_fx_cost_realized + us_fx_cost_unrealized
        + kr_capital_gains_tax
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
            "dividend_tax_kr": round(dividend_received_kr * VAMS_DIVIDEND_TAX_RATE_KR, 2) if not is_isa else 0,
            "dividend_tax_us": round(dividend_received_us * VAMS_DIVIDEND_TAX_RATE_US, 2) if not is_isa else 0,
            "isa_excess_tax": round(isa_excess_tax, 2),
            "us_capital_gains_tax": round(us_capital_gains_tax, 2),
            "us_capital_gains_tax_unrealized_est": round(us_capital_gains_tax_unrealized_est, 2),
            "us_fx_cost_realized": round(us_fx_cost_realized, 2),
            "us_fx_cost_unrealized_est": round(us_fx_cost_unrealized, 2),
            "kr_capital_gains_tax": round(kr_capital_gains_tax, 2),
            "total": round(total_deduction, 2),
            "sell_tax_by_class": {k: round(v, 2) for k, v in sell_tax_by_class.items()},
        },
        "assumptions": {
            "sell_tax_rate_pct_by_class": {
                k: round(v * 100, 4) for k, v in _SELL_TAX_BY_CLASS.items()
            },
            "spread_slippage_bps_roundtrip": VAMS_SPREAD_SLIPPAGE_BPS,
            "dividend_tax_rate_pct_kr": round(VAMS_DIVIDEND_TAX_RATE_KR * 100, 4),
            "dividend_tax_rate_pct_us": round(VAMS_DIVIDEND_TAX_RATE_US * 100, 4),
            "us_capital_gains_rate_pct": round(VAMS_US_CAPITAL_GAINS_RATE * 100, 4),
            "us_capital_gains_deduction_krw": VAMS_US_CAPITAL_GAINS_DEDUCTION_KRW,
            "us_capital_gains_deduction_label": "양도소득 기본공제 (연 1회, 1인당)",
            "us_capital_gains_realized_pnl_krw": round(realized_us_pnl, 2),
            "us_capital_gains_unrealized_pnl_krw": round(unrealized_us_pnl, 2),
            "us_fx_cost_rate_pct": round(VAMS_US_FX_COST_RATE * 100, 4),
            "kr_capital_gains_realized_pnl_krw": round(realized_kr_pnl, 2),
            "kr_tax_mode": kr_tax_mode,
            "isa_active": is_isa,
            "isa_deduction_krw": VAMS_ISA_DEDUCTION_KRW if is_isa else None,
            "dividend_total_gross_krw": round(dividend_total_gross, 2),
            "dividend_comprehensive_alert": dividend_comprehensive_alert,
            "dividend_comprehensive_threshold_krw": VAMS_DIVIDEND_COMPREHENSIVE_THRESHOLD_KRW,
            "tax_date_basis": "settlement_date (T+2 한국 시간 — 미국 T+1 + 시차)",
            "loss_carryover": "해외주식 종목간 + KR 비상장/대주주 통산 가능 (KR 비대주주 소액주주 비과세, 통산 의미 X)",
            "toggles": {
                "kr_majority_shareholder": VAMS_KR_MAJORITY_SHAREHOLDER,
                "kr_geumtu_restored": VAMS_KR_GEUMTU_RESTORED,
            },
            "note": (
                "VAMS 본체는 수수료·시장충격 슬리피지까지 반영. 본 보정은 증권거래세(종목 "
                "타입별 분기)·호가 스프레드·배당세(KR 15.4% / US 15.0% 한미 조세조약)·US "
                "양도세(250만 공제 후 22% 분리과세)·US 환전 비용(0.3%/년)·KR 양도세(대주주 "
                "toggle 또는 금투세 재시행 fallback)·ISA 비과세 한도(mode_tag) 차감. "
                "기본 KR 비대주주 0% 가정 (horizon ~2029 [[project_geumtu_tax_horizon]]). "
                "금융소득 종합과세(연 2000만 초과) = 분리과세 유지 + alert 노출 (사용자 신고 영역)."
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

    # 0. β FX 헷지 pending 진입 1회 소비 (cash→reserve, holdings 외 = auto-sell 제외)
    _consume_pending_fx_hedge(portfolio)

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

    # 2.5. Phase 1.2 — R-multiple 부분 익절 (살아남은 holding 만)
    for holding in portfolio["vams"]["holdings"]:
        partial_results = check_partial_exit(portfolio, holding, history, profile=p)
        for pr in partial_results:
            if pr.get("sold_qty", 0) > 0:
                alerts.append({
                    "type": "PARTIAL_EXIT",
                    "message": (
                        f"💰 {holding['name']} 부분 익절 {pr['target_id']} | "
                        f"{pr['sold_qty']}주 @ {pr['sold_price']:,}원 "
                        f"(R={pr['r_multiple']}, +{pr['partial_pnl']:+,}원, 잔여 {pr['remaining_quantity']}주)"
                    ),
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
                    "timestamp": now_kst().isoformat(timespec="seconds"),
                    "ticker": tk,
                    "name": hold.get("name", tk),
                    "amount_per_share": amount_per_share,
                    "quantity": hold.get("quantity", 0),
                    "total": round(total_amount, 2),
                    "ex_date": div.get("ex_date"),
                    "is_confirmed": div.get("is_confirmed", False),
                    "source": div.get("source"),
                    "rule_id": "dividend_ex_date",  # FOMO 정합 (auto, non-trade event)
                    "mode_tag": hold.get("mode_tag", "moderate"),
                })
                alerts.append({
                    "type": "DIVIDEND",
                    "message": f"💰 {hold.get('name', tk)} 배당 수령 | {int(total_amount):,}원 (주당 {int(amount_per_share):,}원)",
                })
    except Exception as e:
        print(f"[VAMS] 배당 누적 실패 (무시): {e}")

    # 3.6. US 배당 누적 — dividend_us 수집기 + ex_date 일치 holdings 의 USD 배당 → KRW 환산.
    # fx_rate 우선순위: vams.usd_krw_fx_rate > portfolio.macro.usd_krw.value > 1300 (보수적 fallback).
    try:
        from api.collectors.dividend_us import get_ex_dates_today as get_ex_us
        us_tickers = [
            h["ticker"] for h in portfolio["vams"]["holdings"]
            if (h.get("asset_class") in ("US_STOCK", "US_ETF") or h.get("currency", "").upper() == "USD")
            and h.get("ticker")
        ]
        due_today_us = get_ex_us(us_tickers)
        if due_today_us:
            vams_dict = portfolio.setdefault("vams", {})
            macro = portfolio.get("macro") or {}
            fx_rate = (
                vams_dict.get("usd_krw_fx_rate")
                or macro.get("usd_krw", {}).get("value")
                or 1300.0
            )
            for div in due_today_us:
                tk = div.get("ticker")
                amount_per_share_usd = float(div.get("amount_per_share_usd") or 0)
                if amount_per_share_usd <= 0:
                    continue
                hold = next((h for h in portfolio["vams"]["holdings"] if h.get("ticker") == tk), None)
                if not hold:
                    continue
                qty = float(hold.get("quantity", 0) or 0)
                total_usd = amount_per_share_usd * qty
                total_krw = total_usd * float(fx_rate)
                if total_krw <= 0:
                    continue
                vams_dict["dividend_received_us"] = float(vams_dict.get("dividend_received_us", 0) or 0) + total_krw
                vams_dict["cash"] = float(vams_dict.get("cash", 0) or 0) + total_krw  # 배당 = 현금 증가
                history.append({
                    "type": "DIVIDEND",
                    "date": now_kst().strftime("%Y-%m-%d %H:%M"),
                    "timestamp": now_kst().isoformat(timespec="seconds"),
                    "ticker": tk,
                    "name": hold.get("name", tk),
                    "amount_per_share_usd": amount_per_share_usd,
                    "fx_rate_applied": float(fx_rate),
                    "quantity": qty,
                    "total_usd": round(total_usd, 2),
                    "total": round(total_krw, 2),  # KRW (KR 패턴 정합)
                    "ex_date": div.get("ex_date"),
                    "is_confirmed": div.get("is_confirmed", True),
                    "source": div.get("source"),
                    "market": "US",
                    "rule_id": "dividend_ex_date_us",
                    "mode_tag": hold.get("mode_tag", "moderate"),
                })
                alerts.append({
                    "type": "DIVIDEND",
                    "message": f"💰 {hold.get('name', tk)} US 배당 수령 | {int(total_krw):,}원 (USD {amount_per_share_usd:.4f} × {qty:g}주 × FX {fx_rate:.0f})",
                })
    except Exception as e:
        print(f"[VAMS] US 배당 누적 실패 (무시): {e}")

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
