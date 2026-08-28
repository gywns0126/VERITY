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
from typing import Any, Dict, Optional, List, Tuple

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


def _assert_exit_state_matches_ledger(portfolio: dict, history: list) -> None:
    """오래된 portfolio 로 이미 청산된 종목을 다시 매도하는 cross-run race 차단.

    GitHub Actions runner 간에는 로컬 파일 lock 을 공유할 수 없다. 한 run 이 SELL 을
    커밋한 뒤 먼저 시작한 다른 run 이 옛 portfolio 를 계속 들고 있으면 같은 잔여수량을
    다시 SELL 로 기록할 수 있다. 원장은 이미 닫혔는데 portfolio 에만 남은 종목은
    저장하면 안 되는 stale snapshot 이므로, 어떤 자금 이동보다 먼저 중단한다.
    """
    holdings = ((portfolio.get("vams") or {}).get("holdings")) or []
    if not holdings or not history:
        return
    from api.vams.trade_ledger import reconstruct
    open_positions = reconstruct(history)["open_positions"]
    stale_closed = []
    for holding in holdings:
        ticker = str(holding.get("ticker") or holding.get("name") or "")
        if not ticker:
            continue
        if float(open_positions.get(ticker, 0) or 0) <= 0:
            stale_closed.append(ticker)
    if stale_closed:
        raise RuntimeError(
            "VAMS stale portfolio 감지 — 원장은 이미 청산됐으나 portfolio 에 남은 종목: "
            + ",".join(sorted(stale_closed))
            + ". 중복 매도와 stale 발행을 막기 위해 사이클 중단"
        )


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


def _num(v, default: float) -> float:
    """None·빈문자·비수치를 default 로 접는다.

    🚨 dict.get(k, default) 를 값 검증으로 쓰지 말 것. 그것은 **키 부재**만 막고
    "키는 있는데 값이 None" 은 통과시킨다 — 산술로 넘어가면 TypeError 다.
    """
    if v is None:
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if f == f else default          # NaN 방어


def _guard_beta(stock: dict) -> Optional[float]:
    """VAMS 가드 전용 beta. 채점에는 연결하지 않는다."""
    raw = stock.get("beta")
    if raw is None:
        raw = (stock.get("backtest") or {}).get("beta")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


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
    beta_missing = 0

    for h in holdings:
        # 🚨 2026-08-17 — dict.get(k, default) 는 **키가 없을 때만** default 를 준다.
        #   키가 있는데 값이 None 이면 None 이 그대로 나온다. cc18f344f(8/11)가
        #   가드 입력을 영속하려고 "beta": stock.get("beta") 를 저장했는데 추천
        #   파이프라인에 beta 키가 없어 전 보유 종목이 beta=None 이 됐고,
        #   h_beta * h_pct 가 TypeError 로 파이프라인을 죽였다
        #   (daily_analysis 5연속 실패, 8/16 16:07Z~). 값 검증을 default 에 맡기지 않는다.
        h_value = _num(h.get("current_price"), 0.0) * _num(h.get("quantity"), 0.0)
        h_pct = h_value / total_asset * 100 if total_asset > 0 else 0
        h_sector = (h.get("sector") or "Unknown").strip()
        sector_exposure[h_sector] = sector_exposure.get(h_sector, 0) + h_pct

        h_beta_raw = _guard_beta(h)
        if h_beta_raw is None:
            beta_missing += 1
        h_beta = _num(h_beta_raw, 1.0)
        portfolio_beta_sum += h_beta * h_pct
        portfolio_weight_sum += h_pct

    # 🚨 베타가 없으면 전부 1.0 으로 대체되어 이 가드는 "통과" 만 돌려준다.
    #   조용히 통과시키면 가드가 살아 있는 것처럼 보인다 — 없는 것보다 나쁘다
    #   ([[feedback_silent_total_failure_guard]]). 대체분을 매 판정에서 신고한다.
    if beta_missing:
        print(f"  [exposure] 베타 결측 {beta_missing}/{len(holdings)}종목 → 1.0 대체. "
              f"이만큼 베타 상한({VAMS_MAX_PORTFOLIO_BETA}) 가드는 판정력이 없다")

    current_sector_pct = sector_exposure.get(cand_sector, 0)
    cand_invest = min(
        _get_profile().get("max_per_stock", 2_000_000),
        _num(portfolio.get("vams", {}).get("cash"), 0.0) * 0.9,
    )
    cand_pct = cand_invest / total_asset * 100 if total_asset > 0 else 0

    if current_sector_pct + cand_pct > VAMS_MAX_SECTOR_PCT:
        return {
            "blocked": True,
            "reason": f"섹터 '{cand_sector}' 노출 {current_sector_pct:.1f}%+{cand_pct:.1f}% > 상한 {VAMS_MAX_SECTOR_PCT}%",
        }

    if portfolio_weight_sum > 0:
        current_beta = portfolio_beta_sum / portfolio_weight_sum
        cand_beta = _num(_guard_beta(candidate_stock), 1.0)   # 후보도 동일 None 함정
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
        h_value = _num(h.get("current_price"), 0.0) * _num(h.get("quantity"), 0.0)   # 위와 동일 None 함정
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


# ── V7 fractional Kelly (PREREG_KELLY_FIX_2026_08_02 · PM 승인 2026-08-02, RULE 7 1회) ──
KELLY_MULT_MIN = 0.6           # D3 — mult 하한
KELLY_MULT_MAX = 1.2           # D3 — mult 상한
KELLY_B_DEFAULT = 1.2          # D4 — 실현 표본 부족 시 보수 default (옛 임의값 1.5 교체)
# D2 — 검증 연동 스케일. 실적이 쌓일수록 brain 의 사이징 영향을 키운다.
# 🚨 2026-08-18 근거 표기 정정 — 종전 주석은 "검증 게이트 정합" 이었다. 그 게이트(N=252 IC,
#   2027-05)는 §7-1 로 폐기됐다. 다만 여기서 252 는 **게이트가 아니라 스케일 분모**로 쓰인다
#   ("도달하면 통과" 가 아니라 "쌓일수록 점증"). 동작은 폐기 대상이 아니므로 값은 유지하고
#   근거 표기만 고친다. 분모 재설정 = RULE 7 쿼터 소모 → 재등록 대상(§7-3 승인 후).
KELLY_LAMBDA_N_FULL = 252
KELLY_MIN_WINS_LOSSES = 10     # D4 — 실현 b 채택 최소 표본 (승·패 각각)
_KELLY_REF_BRAIN = 60          # 중립 기준점 (mult=1.0)


# 🚨 2026-08-18 — mtime 키 캐시. 정본 원장 전환으로 이 함수가 history.json(106KB) +
#   portfolio.json(**3.5MB**) 를 읽게 됐는데, 호출부가 `execute_buy` 라 **매수 후보마다** 돈다.
#   실측 193.5ms/회 → 후보 5,000이면 **967초**. 캐시 없이 두면 정본 전환이 곧 크론 초과다.
#   무효화 = 입력 파일 mtime (매도로 원장이 바뀌면 자동 재계산).
_KELLY_CACHE: Dict[str, Any] = {"key": None, "val": None}


def _kelly_cache_key() -> tuple:
    """캐시 키 = (DATA_DIR, 입력 3파일 mtime_ns).

    🚨 `DATA_DIR` 이 키에 있어야 한다. 없으면 **파일이 전부 없을 때 키가 (0,0,0) 으로
    수렴해 서로 다른 데이터 디렉터리끼리 충돌**한다 (2026-08-18 재현 — 청산 1건인 dir 과
    2건인 dir 이 같은 답을 냈다). watch 대상 = `load_history()`/`load_portfolio()` 가
    **실제로 읽는** 파일. dev 모드에서 save 는 `*.dev.json` 으로 가지만 load 는 항상
    prod 를 읽으므로(engine.py:237·184) prod 경로를 본다.
    """
    out: List[Any] = [DATA_DIR]
    for rel in ("history.json", "portfolio.json", os.path.join("vams", "exit_log.jsonl")):
        fp = os.path.join(DATA_DIR, rel)
        try:
            out.append(os.stat(fp).st_mtime_ns)
        except OSError:
            out.append(0)
    return tuple(out)


def _kelly_window_start() -> Tuple[bool, Optional[str]]:
    """Kelly 집계 창 = `reset_meta.reset_at` 이후. 반환 = (읽기 성공?, 창 시작일).

    🚨 정의를 `api/main.py:1278` · `api/vams/validation.py` 와 **한 글자까지 맞춘다.**
    같은 원장을 다르게 읽어 4.8배 괴리가 났던 것이 #290 사고였다.

    🚨 **"못 읽음" 과 "리셋 없음(legacy)" 을 구분해서 돌려준다.** 둘 다 None 으로 접으면
    `load_portfolio()` 가 실패할 때 창이 **조용히 전체로 넓어진다** — 2026-08-18 실측으로
    에피소드가 **23 → 31** 로 뛰었다(리셋 이전 8건 유입). 사이징이 커지는 방향이라
    안전하지 않다. 호출부는 실패 시 중립(λ=0)으로 접는다.
    """
    try:
        pf = load_portfolio()
    except Exception:  # noqa: BLE001 — 사이징 경로 보호
        return False, None
    v = (pf or {}).get("vams") or {}
    return True, (str(((v.get("reset_meta") or {}).get("reset_at") or ""))[:10] or None)


def _kelly_realized_stats() -> Tuple[int, float]:
    """VAMS 실현 통계 → (n_closed, b=avg_win/avg_loss). **정본 원장 기준.**

    🚨 2026-08-18 정정 — 종전은 `exit_log.jsonl` 을 **그대로 세었다.** 그 파일은 dev-mode
    사이클이 남긴 **유령 매도**를 포함한다(7/20 감사 P0). 실측: 82행 중 **59행이 유령**이고
    정본 청산은 **23건**이다. 같은 종목·같은 날 같은 고점으로 8행이 연달아 찍힌 경우까지 있었다
    (EQT 2026-07-07). 🚨 EXE 는 **16주를 사고 120주를 팔았다**(SELL 계열 합계).

    그 결과 λ = n/252 가 **0.091 이어야 할 것이 0.325** 로 부풀었다. 🚨 사이징 효과는
    λ 비율(3.57배)이 아니라 **12.7배**다 — mult 식에 λ 가 두 번 들어가(p_eff 안 + 곱셈 인자)
    효과가 대략 λ² 이기 때문이다. 실측 brain 40~90 사이징 폭 **2.426% → 0.191%**.
    즉 미검증 점수에 실제 실적의 12.7배 사이징 권한을 주고 있었고, 방향이 안전한 쪽이 아니라
    위험한 쪽이다. (최초 커밋문의 '3.5배' 는 **틀렸다** — λ 비율을 효과 비율로 옮겨 적었다.)

    `api/main.py` 는 2026-08-05 에 이미 `trade_ledger.reconstruct` 를 단일 출처로 전환했는데
    (#290 의 4.8배 괴리 재발 방지) **이 함수만 따라오지 않았다.** 여기서 맞춘다.

    산식·임계 불변 — 오염 제거일 뿐이라 RULE 7 쿼터를 소모하지 않는다.

    n = 정본 에피소드 수. b 는 pct 가 원장에 없으므로 **에피소드당 exit_log 1행**만
    골라 계산한다(같은 종목·날짜 후보 중 `raw_pnl` 에 가장 가까운 행). 승·패 각
    `KELLY_MIN_WINS_LOSSES` 미만이면 종전대로 `KELLY_B_DEFAULT`.
    read-only, 예외 삼킴(사이징 경로 보호 — 여기서 죽으면 매수가 통째로 멈춘다).

    🚨 **같은 사이클의 매도는 반영되지 않는다** (의도. 2026-08-18 확인).
    `_append_exit_log` 는 매도마다 **즉시** 쓰지만(engine.py:1221) `save_history` 는
    사이클 **끝**에 한 번 쓴다(engine.py:1982). 정본 전환으로 이 함수가 원장(history)을
    보게 되면서, 같은 사이클 매도는 **다음 사이클부터** n 에 들어온다. 종전(exit_log 직독)은
    즉시 반영됐으므로 **동작 변경이다.** 방향은 λ 가 작아지는 쪽 = 미검증 점수의 사이징
    권한이 줄어드는 쪽이라 그대로 둔다. 되돌리려면 in-memory history 를 인자로 받아야 하고
    그건 호출부 시그니처 변경이라 별건이다.
    """
    ck = _kelly_cache_key()
    if _KELLY_CACHE["key"] == ck and _KELLY_CACHE["val"] is not None:
        return _KELLY_CACHE["val"]

    def _ret(v: Tuple[int, float]) -> Tuple[int, float]:
        _KELLY_CACHE["key"], _KELLY_CACHE["val"] = ck, v
        return v

    try:
        from api.vams.trade_ledger import reconstruct
        ok, since = _kelly_window_start()
        if not ok:
            # 창을 모르면 세지 않는다 — 넓혀서 세면 리셋 이전분이 섞여 λ 가 커진다
            return _ret((0, KELLY_B_DEFAULT))
        episodes = reconstruct(load_history(), since=since)["episodes"]
    except Exception:  # noqa: BLE001 — 사이징 경로 보호
        # 🚨 실패도 캐시한다. 안 하면 원장이 깨진 동안 **매수 후보마다** 3.5MB 를 다시
        #   읽고 다시 실패한다 — 성능 회귀를 막으려 캐시를 넣고 정작 최악의 경로를
        #   열어두는 셈이다. mtime 이 바뀌면(=복구되면) 자동 재시도된다.
        return _ret((0, KELLY_B_DEFAULT))

    n = len(episodes)
    if not n:
        return _ret((0, KELLY_B_DEFAULT))

    # pct 조인 — 유령이 같은 (종목,날짜) 에 섞여 있으므로 에피소드당 1행만 고른다
    by_key: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    try:
        path = os.path.join(DATA_DIR, "vams", "exit_log.jsonl")
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("pnl_pct") is None:
                    continue
                key = (str(row.get("ticker")), str(row.get("date") or row.get("ts"))[:10])
                by_key.setdefault(key, []).append(row)
    except OSError:
        return _ret((n, KELLY_B_DEFAULT))

    wins: List[float] = []
    losses: List[float] = []
    for ep in episodes:
        cand = by_key.get((str(ep.get("ticker")), str(ep.get("date"))[:10]))
        if not cand:
            continue
        target = _num(ep.get("raw_pnl") if ep.get("raw_pnl") is not None else ep.get("pnl"), 0.0)
        row = min(cand, key=lambda r: abs(_num(r.get("pnl"), 0.0) - target))
        try:
            pct = float(row["pnl_pct"])
        except (TypeError, ValueError):
            continue
        if pct > 0:
            wins.append(pct)
        elif pct < 0:
            losses.append(-pct)

    if len(wins) >= KELLY_MIN_WINS_LOSSES and len(losses) >= KELLY_MIN_WINS_LOSSES:
        avg_loss = sum(losses) / len(losses)
        if avg_loss > 0:
            return _ret((n, (sum(wins) / len(wins)) / avg_loss))
    return _ret((n, KELLY_B_DEFAULT))


def _apply_fractional_kelly(invest_amount: float, brain_score: int,
                            stats: Optional[Tuple[int, float]] = None) -> float:
    """V7 (PREREG_KELLY_FIX_2026_08_02, PM 승인 2026-08-02) — 검증연동 fractional Kelly.

    옛 V6 half-Kelly 결함(실측 2026-08-02): scaled_kelly/kelly_raw = VAMS_KELLY_SCALE 상쇄로
    brain 50~90 전 구간 0.5× 동일(edge 무차별) + brain 40 은 float epsilon 경로로 ≈0 절벽.

    사전등록 공식 그대로:
      λ = min(1, n_closed/252)                  # 검증 신뢰(D2). 미검증 → 0 → 중립(mult=1)
      p = 0.5 + (brain/100 − 0.5)·λ             # 미검증 점수의 확률 사용 축소 (RULE 7 #2)
      b = 실현 avg_win/avg_loss (D4, 부족 시 1.2)
      f(p) = max(0, (b·p − (1−p)) / b)          # full Kelly 분수
      mult = clip(1 + φ·(f(p) − f(p_ref))·λ, 0.6, 1.2)   # φ=VAMS_KELLY_SCALE(quarter 0.25, D1)

    🚨 λ≈0(미검증) 동안 brain 효과 ≈0 — 미검증 산식이 사이징을 지배하지 못함.
    실자본 사이징 = 중용(brain 배제)이 지배. 본 함수 = VAMS 페이퍼 전용(캘리브레이션 축적).
    """
    try:
        bs = float(brain_score)
    except (TypeError, ValueError):
        return invest_amount
    n, b = stats if stats is not None else _kelly_realized_stats()
    lam = max(0.0, min(1.0, n / float(KELLY_LAMBDA_N_FULL)))
    if lam <= 0.0 or b <= 0.0:
        return invest_amount

    def _f(p: float) -> float:
        p = max(0.0, min(1.0, p))
        return max(0.0, (b * p - (1.0 - p)) / b)

    p_eff = 0.5 + (bs / 100.0 - 0.5) * lam
    p_ref = 0.5 + (_KELLY_REF_BRAIN / 100.0 - 0.5) * lam
    mult = 1.0 + VAMS_KELLY_SCALE * (_f(p_eff) - _f(p_ref)) * lam
    mult = max(KELLY_MULT_MIN, min(KELLY_MULT_MAX, mult))
    return invest_amount * mult


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


def _effective_max_per_stock(profile_abs: float, vams: dict) -> tuple:
    """실효 종목당 상한 = min(프로필 절대액, 총자산 × VAMS_MAX_PER_STOCK_PCT).

    🚨 2026-08-25 PREREG_MICRO_PROFILE (PM 승인·RULE 7 쿼터 1) — 스케일 불변화.
      절대액 200만은 1,000만 시뮬에서 20.6% 로 작동했지만 100만 시드에서는 시드보다 커서
      무력화되고 현금×0.9 만 남아 **1종목 50~90% 집중**이 된다(엔진 함수 실측).
      비율 상한이 이를 5~8종목 분산으로 만든다.
    🚨 총자산 < 1,000만이면 시뮬도 비례 축소된다(등록 §2-보정, 현재 −2.7%) — 의도된 동작.
    🚨 총자산 결측/0 이면 절대액 폴백 — 비율을 0 에 곱해 사이징을 죽이는 조용한 실패 방지
      ([[feedback_silent_zero_fallback_looks_plausible]] 계열).
    Returns: (실효 상한, 바인딩 라벨)
    """
    from api.config import VAMS_MAX_PER_STOCK_PCT
    try:
        ta = float(vams.get("total_asset") or 0)
    except (TypeError, ValueError):
        ta = 0.0
    if VAMS_MAX_PER_STOCK_PCT <= 0 or ta <= 0:
        return float(profile_abs), "max_per_stock_abs"
    pct_cap = ta * VAMS_MAX_PER_STOCK_PCT
    if pct_cap < profile_abs:
        return pct_cap, "total_asset_pct"
    return float(profile_abs), "max_per_stock_abs"


def execute_buy(
    portfolio: dict,
    stock: dict,
    history: list,
    profile: Optional[dict] = None,
) -> Optional[dict]:
    """프로필 기반 가상 매수 (USD 종목은 원화 환산 후 동일 로직). 슬리피지 반영.
    V6: Half-Kelly 스케일링 적용."""
    p = _get_profile(profile)
    max_per_stock, _mps_binding = _effective_max_per_stock(p["max_per_stock"], portfolio["vams"])

    cash = portfolio["vams"]["cash"]
    is_us = stock.get("currency") == "USD"
    fx_rate = _get_fx_rate(portfolio) if is_us else 1.0
    base_price = stock["price"] * fx_rate

    if base_price <= 0:
        return None

    held_tickers = [h["ticker"] for h in portfolio["vams"]["holdings"]]
    if stock["ticker"] in held_tickers:
        return None

    # 🚨 2026-08-25 — 사이징 체인 자기신고. 되돌리지 말 것.
    #   brain 산출물의 `position_guide.recommended_pct`(등급별 % 상한)는 **집행에 쓰이지 않는다.**
    #   실제 집행은 아래 4단이다: min(max_per_stock, 현금×0.9) → Kelly → 변동성 → 매크로.
    #   두 값이 크게 갈린다 — 실측 2026-08-25 쿠쿠홀딩스: position_guide 3%(=29만) vs 실집행 10.7%(=104만).
    #   표시값을 규칙으로 읽어 잘못 답한 사고가 있었다. 체인을 기록에 남겨 다시 갈리지 않게 한다.
    _size_base = min(max_per_stock, cash * 0.9)
    invest_amount = _size_base
    brain_score = stock.get("brain_score", 0) or stock.get("verity_brain", {}).get("brain_score", 50)
    invest_amount = _apply_fractional_kelly(invest_amount, brain_score)
    _size_after_kelly = invest_amount
    # Sprint 11 결함 3 — 변동성 기반 sizing 보정 (ATR proxy)
    invest_amount, vol_meta = _apply_volatility_adj(invest_amount, stock)
    _size_after_vol = invest_amount
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

    # 🚨 2026-08-05 통화 정규화 — trade_plan 의 가격 필드는 **종목 원통화**(US=USD)로 산출되는데
    # holding 의 buy_price/current_price 는 위에서 fx_rate 를 곱해 **KRW** 로 저장된다.
    # 그대로 부착하면 check_partial_exit 의 `current_price >= target_price` 가
    # `131,397 >= 99` 가 되어 **매 run 익절이 무조건 발동**한다(실측: EQT 30회·EXE 20회,
    # 보유 US 5종 전부 비율 1,312~1,340배 = 환율). 손절도 동일 경로라 도달 불가가 된다.
    # 비율(%)·R배수 필드는 통화 무관이므로 건드리지 않는다.
    def _fx_norm(obj):
        """가격 성격 키만 fx_rate 배 (US 전용). dict/중첩 dict 재귀."""
        if fx_rate == 1.0 or not isinstance(obj, dict):
            return obj
        # 2026-08-06 — risk_per_share 추가. 1R = 진입가−손절가라 **주당 통화 금액**이다.
        # trade_planner 가 원통화(US=USD)로 산출하므로 여기서 KRW 로 맞추지 않으면
        # KRW 가격들과 섞인다. (같은 날 trade_planner 가 이 값을 실제로 emit 하도록 수정)
        _PRICE_KEYS = {"price", "stop_price", "target_price", "low", "high",
                       "min", "max", "entry_low", "entry_high", "risk_per_share"}
        out = {}
        for k, v in obj.items():
            if isinstance(v, dict):
                out[k] = _fx_norm(v)
            elif k in _PRICE_KEYS and isinstance(v, (int, float)):
                out[k] = round(v * fx_rate, 2)
            else:
                out[k] = v
        return out

    _stop_loss_obj = _fx_norm(_trade_plan.get("stop_loss") or {})
    _exit_targets_norm = _fx_norm(_trade_plan.get("exit_targets") or {}) or None
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
        "buy_reason": _buy_reason_with_basis(stock),
        # 🚨 2026-08-23 신설 — 체결 근거 자기신고. 되돌리지 말 것.
        "decision_basis": _decision_basis(stock),
        "safety_score": stock.get("safety_score", 0),
        "buy_slippage_bps": round(slippage_bps, 2),
        # Sprint 11 결함 3 — sizing audit
        "volatility_adj": vol_meta,
        # 2026-05-23 RULE 7 — regime-aware 사이징 적용 multiplier (audit)
        "macro_size_multiplier": round(macro_size_mult, 3),
        # 🚨 사이징 자기신고 (2026-08-25) — 어느 값이 크기를 정했는지. 되돌리지 말 것.
        "sizing_chain": {
            "executor": "vams.execute_buy",
            "max_per_stock": max_per_stock,
            "cash_at_entry": round(cash),
            "base": round(_size_base),
            # 2026-08-25 PREREG_MICRO_PROFILE — max_per_stock 자체가 abs/pct 중 어느 쪽인지까지 신고.
            "max_per_stock_binding": _mps_binding,
            "base_binding": ("max_per_stock" if max_per_stock <= cash * 0.9 else "cash*0.9"),
            "after_kelly": round(_size_after_kelly),
            "after_volatility": round(_size_after_vol),
            "after_macro": round(invest_amount),
            "brain_position_guide_pct": (
                (stock.get("verity_brain") or {}).get("position_guide") or {}
            ).get("recommended_pct"),
            "note": "brain_position_guide_pct 는 참고값이며 집행에 쓰이지 않는다",
        },
        # Phase 1.1 — ATR 기반 동적 손절 (개별 산출값)
        "stop_loss_pct_individual": individual_stop_pct,
        "stop_loss_method": stop_loss_method,
        # Phase 0 P-03 — ATR 산출법 audit (마이그레이션 holding 보호)
        "atr_method_at_entry": _atr_method_at_entry,
        # Phase 1.2 — R-multiple 부분 익절 (통화 정규화본)
        "exit_targets": _exit_targets_norm,
        # 2026-08-05 — 손절 파생값 영속화. 이전엔 stop_loss_pct_individual 만 남고
        # stop_price/risk_per_share 는 저장되지 않아 12/12 가 0 이었다(감사 실측).
        # trade_plan.stop_loss 가 없으면(WATCH 이하 = planner 미생성) None 유지 — 조작 금지.
        "stop_price": _stop_loss_obj.get("stop_price") or _stop_loss_obj.get("price"),
        "risk_per_share": _stop_loss_obj.get("risk_per_share"),
        "entry_currency": "USD" if is_us else "KRW",
        "entry_fx_rate": round(fx_rate, 2) if is_us else None,
        "exit_history": [],  # [{target_id, sold_qty, sold_price, r_multiple, at}]
        "trailing_active": False,  # +2R 도달 후 True (남은 20% 만 트레일링)
        "realized_pnl_partial": 0,  # 부분 청산 누적 실현 손익
        # P2-2 prep — Capital 3-Tier mode tag. routing logic 별 sprint.
        "mode_tag": inferred_mode,
        # 2026-08-11 — 포트폴리오 가드 입력 영속. check_position_size 의 섹터 35% 상한·
        # 베타 1.5 상한·팩터쏠림 가드가 h.get("sector")/h.get("beta")/h["multi_factor"]
        # ["quant_factors"] 를 읽는데 **셋 다 저장된 적이 없어** 가드가 한 번도 안 걸렸다
        # (2026-08-11 실측 0/11 — 섹터는 전부 "Unknown" 으로 뭉쳐 후보 섹터 노출이 항상 0).
        # beta 는 full backtest 의 동일 시장지수 대비 값을 가드 전용으로 저장한다.
        "sector": stock.get("sector"),
        "beta": _guard_beta(stock),
        "multi_factor": {"quant_factors": {
            k: v for k, v in (((stock.get("multi_factor") or {}).get("quant_factors")
                               or {}).items())
            if k in ("momentum", "quality", "volatility", "mean_reversion")
            and isinstance(v, (int, float))
        }},
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
        "decision_basis": holding.get("decision_basis"),
        "rule_id": f"verdict_{stock.get('recommendation', 'BUY')}",  # FOMO 정합
        "mode_tag": holding.get("mode_tag", "moderate"),  # Capital 3-Tier 정합
    })

    print(f"[VAMS] 매수: {stock['name']} {quantity}주 @ {price:,.0f}원 (슬리피지 {slippage_bps:.1f}bp, 총 {actual_cost:,}원)")
    return holding



def _decision_basis(stock: dict) -> dict:
    """체결이 어느 산식을 따랐는지 기록에 남긴다 (2026-08-23 신설).

    🚨 사고 경위 — AMG(8/21 매수). 한 레코드에 점수가 둘 있다:
      · `verity_brain.grade` = BUY (brain_score 65)  ← `recommendation` 이 따르는 값 = **체결 근거**
      · `multi_factor.grade` = 관망 (multi_score 52) ← `ai_verdict` 문자열이 따르는 값
    buy_reason 이 ai_verdict 를 그대로 썼기 때문에 거래 로그에 "멀티팩터 53점 (관망)" 이 남아
    **체결 근거와 감사 흔적이 어긋났다.** 두 점수 중 어느 쪽이 옳은지는 여기서 판정하지 않는다
    (전향 IC 비교 사안). 여기서 하는 일은 **무엇을 따랐는지 신고**하는 것뿐이다 — 임계 무변경.
    """
    brain = stock.get("verity_brain") or {}
    mf = stock.get("multi_factor") or {}
    basis = {
        "recommendation": stock.get("recommendation"),
        "recommendation_source": stock.get("_recommendation_source") or "verity_brain",
        "brain_score": brain.get("brain_score"),
        "brain_grade": brain.get("grade"),
        "multi_score": mf.get("multi_score"),
        "multi_grade": mf.get("grade"),
        "ai_verdict_source": "multi_factor",
    }
    # 갈림 판정 = **체결된 등급**(recommendation) vs 멀티팩터 등급. 둘 다 알 때만 비교한다.
    exec_rank = _grade_rank(stock.get("recommendation"))
    mf_rank = _grade_rank_ko(mf.get("grade"))
    basis["scores_disagree"] = exec_rank >= 0 and mf_rank >= 0 and exec_rank != mf_rank
    return basis


_GRADE_RANK = {"STRONG_BUY": 4, "BUY": 3, "WATCH": 2, "CAUTION": 1, "AVOID": 0}
_GRADE_RANK_KO = {"매수": 3, "관망": 2, "주의": 1, "회피": 0}


def _grade_rank(g) -> int:
    return _GRADE_RANK.get(str(g or "").upper(), -1)


def _grade_rank_ko(g) -> int:
    return _GRADE_RANK_KO.get(str(g or "").strip(), -1)


def _buy_reason_with_basis(stock: dict) -> str:
    """사유 문자열이 **체결 근거**를 말하게 한다. 두 점수가 갈릴 때만 병기한다."""
    verdict = stock.get("ai_verdict") or "AI 추천"
    b = _decision_basis(stock)
    if not b.get("scores_disagree"):
        return verdict
    return (
        f"{b.get('recommendation')} 체결 — 근거 {b.get('recommendation_source')} "
        f"{b.get('brain_grade')}({b.get('brain_score')}) · 참고 멀티팩터 "
        f"{b.get('multi_grade')}({b.get('multi_score')})"
    )


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
        # 너무 작아서 청산 불가 — 감사 기록만 남긴다.
        # 🚨 2026-08-06 — 이 기록은 **차단이 아니다**. "지금 수량이 안 나눠진다"는 일시적
        # 상태이지 "영원히 익절하지 않는다"가 아니다. 이전엔 check_partial_exit 가 이
        # 항목을 executed 와 동급으로 취급해 해당 타깃을 영구 차단했고, 그래서 수량 1주인
        # 보유는 이후 물타기로 수량이 늘어도 익절 평가가 되살아나지 않았다.
        # 매 run 재기록으로 exit_history 가 무한 증식하지 않도록 1회만 남긴다.
        _eh = holding.setdefault("exit_history", [])
        if not any(x.get("target_id") == target_id and x.get("status") == "skipped_too_small"
                   for x in _eh):
            _eh.append({
                "target_id": target_id,
                "status": "skipped_too_small",
                "total_quantity": total_quantity,
                "exit_pct": exit_pct,
                "at": now_kst().strftime("%Y-%m-%d %H:%M"),
                "_note": "감사 기록 — 재평가를 막지 않는다(2026-08-06)",
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

    # trailing_active 설정은 check_partial_exit 의 **가격 도달** 판정으로 이관했다
    # (2026-08-11 PREREG_SMALL_QTY_EXIT §2-1). 체결 여부에 묶으면 소수량 포지션이
    # 영구 미활성이 된다. 단일 출처 유지를 위해 여기서는 설정하지 않는다.

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

    # 🚨 2026-08-05 스케일 가드 — 기존 보유분 구제 + 재발 차단.
    # execute_buy 는 이제 trade_plan 가격을 KRW 로 정규화해 부착하지만, **그 이전에 산
    # holding** 은 타깃이 원통화(USD)로 남아 있다. 실측: 보유 US 5종 전부 매수가/타깃
    # 비율이 1,312~1,340배(=환율) → `current_price >= target` 이 항상 참 → 매 run 익절
    # 발동(EQT 30회·EXE 20회). 통화가 다르면 비교 자체가 무의미하므로 **평가를 건너뛴다**.
    # 자동 환산은 하지 않는다 — 잘못된 배수로 실집행하느니 미실행이 안전하다(fail-closed).
    buy_price = holding.get("buy_price") or 0
    _t1 = (targets.get("target_1") or {}).get("price")
    if buy_price > 0 and isinstance(_t1, (int, float)) and _t1 > 0:
        _ratio = buy_price / _t1
        if _ratio > 10 or _ratio < 0.1:
            if not holding.get("_scale_mismatch_logged"):
                holding["_scale_mismatch_logged"] = True
                print(f"[VAMS] ⚠ 익절 타깃 스케일 불일치 — {holding.get('name')} "
                      f"매수가 {buy_price:,.0f} vs target_1 {_t1:,.0f} (비율 {_ratio:,.0f}x). "
                      f"통화 혼재 의심 — 부분익절 평가 skip (fail-closed)")
            return []
    # 🚨 2026-08-06 — 차단은 **실제 체결(executed)만**. 이전엔 skipped_too_small 도 같이
    # 차단해, 수량이 안 나눠져 한 번 건너뛴 타깃이 영구히 죽었다. 실측: GOOGL(1주)은
    # target_1·2 가 모두 skipped 로 기록돼 **앞으로 어떤 가격에도 익절하지 않는 상태**였다.
    # "지금 못 나눔"은 일시적 상태다 — 수량이 늘거나 비중이 바뀌면 다시 평가돼야 한다.
    # 재평가해도 여전히 작으면 sold_qty 0 으로 끝나므로 자금 이동은 없다(중복 기록은 위에서 차단).
    executed_target_ids = {
        h["target_id"] for h in holding.get("exit_history", []) if h.get("status") == "executed"
    }

    # ── 🚨 멀티배거 active gate B (PREREG_MULTIBAGGER_ACTIVE_GATE_2026_08_22, PM 승인) ──
    # Lynch *One Up*(1989) "꽃을 뽑지 마라" — 오래 들고 크게 오른 포지션의 **첫 익절 한
    # 단계만** 미룬다. 전량 보유 유예가 아니다(되돌릴 수 있는 최소 개입).
    #
    # 🚨 **익절에만 붙는다. 손절(check_stop_loss)에는 절대 붙이지 않는다.**
    #   2026-08-21 전향 검정(US 28년·창 5개)에서 유일하게 유의했던 축이 **하방 회피**다
    #   (상방 10배 선별은 5가설 중 4개가 검출하한 미달). 손절이 그 하방을 잡는 장치이므로
    #   멀티배거 신호로 손절을 유예하면 **유일하게 작동하는 것을 끄는 셈**이 된다.
    #   Lynch 원칙도 "손실을 견뎌라" 가 아니라 "이익을 너무 일찍 실현하지 마라" 다.
    #
    # 🚨 임계(보유 180일 · +50%)는 기존 신호 그대로다. 신설·조정 0.
    #   실측 2026-08-21: 보유 10종목 최장 42일·최고 +25.1% → **발동 0**.
    #   VAMS 리셋(5/17) 때문에 2026-11-13 이전 발동은 구조적으로 불가하다.
    #   그때 급히 정하면 분포를 보고 정하게 되므로(곡선 맞추기) 지금 정해 둔다.
    defer_first = False
    try:
        from api.analyzers.multi_bagger_signals import detect_hold_pnl_threshold
        _flower = detect_hold_pnl_threshold(holding) or {}
        defer_first = bool(_flower.get("triggered"))
        if defer_first:
            holding["multibagger_defer"] = {
                "target_deferred": "target_1",
                "reason": _flower.get("reason"),
                "basis": "PREREG_MULTIBAGGER_ACTIVE_GATE_2026_08_22 (Lynch 꽃을 뽑지 마라)",
                "at": now_kst().strftime("%Y-%m-%d %H:%M"),
            }
    except Exception as _mbe:  # noqa: BLE001 — 신호 실패가 익절을 죽이지 않는다(fail-open)
        import sys as _sys
        print(f"[vams] multibagger defer 평가 skip: {type(_mbe).__name__}: {_mbe}",
              file=_sys.stderr)

    results = []
    # 순서대로 평가 — target_1 → target_2. target_3 (트레일링) 은 check_stop_loss 가 처리.
    for target_id in ("target_1", "target_2"):
        target = targets.get(target_id)
        if not target:
            continue
        if target_id in executed_target_ids:
            continue
        if defer_first and target_id == "target_1":
            continue  # 🚨 한 단계만 유예 — target_2 는 그대로 평가된다
        target_price = target.get("price")
        if target_price is None:
            continue
        if current_price >= target_price:
            # 🚨 2026-08-11 (PREREG_SMALL_QTY_EXIT) — 트레일링 활성은 **가격 도달** 기준이다.
            # 옛 코드는 execute_partial_sell 의 체결 블록 안에서만 켰다. 그래서 수량이
            # 안 나눠져 skipped_too_small 이 되면 그 줄에 도달하지 않아 trailing_active 가
            # 영구 False 였고, check_stop_loss 는 exit_targets 보유에 이 플래그를 요구하므로
            # **1주 포지션은 이익을 확정할 코드 경로가 하나도 없었다**(출구 = −20% 손절뿐).
            # 실측 2026-08-11: 보유 11건 중 6건이 사다리 일부/전부 불능, NEM 은 target_2
            # 가격을 넘겼는데도 미활성. 두 분할 수량이 모두 0인 포지션은 target_1 도달
            # 시점부터 트레일링이 유일한 이익 확정 경로이므로 즉시 활성화한다.
            _qty = float(holding.get("quantity") or 0)
            _all_tranches_zero = all(
                int(_qty * float((targets.get(tid) or {}).get("exit_pct") or 0) / 100) < 1
                for tid in ("target_1", "target_2")
            )
            if target_id == "target_2" or _all_tranches_zero:
                holding["trailing_active"] = True
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

    # cross-run stale snapshot 은 이후 매도·현금 이동 전에 차단해야 한다.
    _assert_exit_state_matches_ledger(portfolio, history)

    # 0. β FX 헷지 pending 진입 1회 소비 (cash→reserve, holdings 외 = auto-sell 제외)
    _consume_pending_fx_hedge(portfolio)

    # 0.5. 🚨 통화 정규화 마이그레이션 (2026-08-06). 손절·익절 판정 **전에** 돌아야 한다.
    # 8/5 에 넣은 _fx_norm 은 신규 매수에만 적용돼 기존 보유의 exit_targets 가 원통화(USD)로
    # 남았고, 스케일 가드가 fail-closed 로 작동해 **미장 보유는 부분익절 평가가 통째로
    # 건너뛰어졌다**(실측 3건). 멱등 — entry_currency 표식이 있으면 즉시 skip 한다.
    try:
        from api.vams.currency_migration import run as _ccy_migrate
        _mig = _ccy_migrate(portfolio)
        if _mig["converted"] or _mig["unresolved"]:
            print(f"[currency_migration] {_mig['summary']}")
    except Exception as _e:  # noqa: BLE001 — 마이그레이션 실패가 사이클을 죽이지 않는다
        print(f"[currency_migration] skipped: {type(_e).__name__}: {_e}")

    # 0.6. 가드 입력 백필 (2026-08-11). 기존 보유 11건이 sector/quant_factors 없이 저장돼
    # 사이징 가드 3종이 전부 무발동이었다. 멱등 — 채워진 보유는 즉시 skip.
    try:
        from api.vams.holding_metadata_backfill import run as _meta_backfill
        _mb = _meta_backfill(portfolio)
        if _mb["filled"]:
            print(f"[meta_backfill] {_mb['summary']}")
    except Exception as _e:  # noqa: BLE001 — 백필 실패가 사이클을 죽이지 않는다
        print(f"[meta_backfill] skipped: {type(_e).__name__}: {_e}")

    # 1. 가격 업데이트
    update_holdings_price(portfolio, price_map)

    # 1.5. FX 헤지 레짐 게이트 (2026-08-11 PM 승인, PREREG_FX_HEDGE_REGIME_2026_08_11).
    # 가격 갱신 **후** 평가해야 목표(0.30×총자산 − USD 주식)가 신선하다. recalc 선행.
    try:
        from api.vams.fx_hedge_regime import run as _fx_regime
        recalculate_total(portfolio)
        _fxr = _fx_regime(portfolio, _get_fx_rate(portfolio))
        if _fxr.get("status") == "adjusted":
            _op = _fxr["op"]
            recalculate_total(portfolio)
            print(f"[fx_hedge_regime] {_op['kind']} {_op.get('moved', 0):,.0f}원 "
                  f"({','.join(_op['triggers'])}) → 목표 {_op['target']:,}원 · 상태 {_op['state']}")
    except Exception as _e:  # noqa: BLE001 — 레짐 평가 실패가 사이클을 죽이지 않는다
        print(f"[fx_hedge_regime] skipped: {type(_e).__name__}: {_e}")

    # 2. 손절/익절 체크
    for holding in list(portfolio["vams"]["holdings"]):
        should_sell, reason = check_stop_loss(holding, p)
        if should_sell:
            sell_result = execute_sell(portfolio, holding, reason, history, profile=p)
            alerts.append({
                "type": "STOP_LOSS",
                "level": "CRITICAL",
                "message": f"🚨 {sell_result['name']} 매도 | {reason} | 손익: {sell_result['pnl']:+,}원",
            })

    # 2.5. Phase 1.2 — R-multiple 부분 익절 (살아남은 holding 만)
    for holding in portfolio["vams"]["holdings"]:
        partial_results = check_partial_exit(portfolio, holding, history, profile=p)
        for pr in partial_results:
            if pr.get("sold_qty", 0) > 0:
                alerts.append({
                    "type": "PARTIAL_EXIT",
                    "level": "WARNING",
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

    # ── 게이트 컷오버 (2026-08-12, PREREG_GATE_STRENGTH_REDESIGN §4 · PR #357 채택 B) ──
    # 정본 게이트 = safety_pct ≥ GATE_BOTTOM_PCT (하위 배제 — 측정된 신호 구간).
    # 🚨 전환 폴백: safety_pct 미부착이면 구 게이트(min_safety)로 — 조용한 매수 정지 방지.
    from api.config import GATE_BOTTOM_PCT

    def _gate_pass(s: dict) -> bool:
        pct = s.get("safety_pct")
        if pct is not None:
            return pct >= GATE_BOTTOM_PCT
        return s.get("safety_score", 0) >= min_safety

    buy_candidates = [
        s for s in analyzed_stocks
        if s.get("recommendation") in allowed_recs
        and _gate_pass(s)
        and len(s.get("detected_risk_keywords") or []) <= max_risk_kw
        and s.get("ticker") not in held_tickers
        and s.get("price", 0) > 0
    ]

    # 🚨 정렬 = brain_score (safety 내림차순 폐지 — 측정: safety 상위 구간 승자보존
    #   0.746 = 무작위(1.0) 이하. 그 구간을 선호해서 사는 키였다). brain 정렬은 미검증
    #   (등록 §4-2 정직 신고) — G2/G3 전방 감시 대상. 결측 brain = 0 (뒤로).
    def _brain_key(s: dict) -> float:
        v = s.get("brain_score", 0) or (s.get("verity_brain") or {}).get("brain_score", 0)
        return float(v) if isinstance(v, (int, float)) else 0.0

    _old_order = sorted(buy_candidates,
                        key=lambda s: s.get("safety_score", 0), reverse=True)[:3]
    buy_candidates.sort(key=_brain_key, reverse=True)
    if buy_candidates and _old_order:
        print(f"[gate_cutover] 매수 정렬 섀도 — 구(safety) 상위3: "
              f"{[s.get('ticker') for s in _old_order]} · 신(brain) 상위3: "
              f"{[s.get('ticker') for s in buy_candidates[:3]]}")

    bought = 0
    for stock in buy_candidates:
        if bought >= max_buy:
            break

        exposure = _check_portfolio_exposure(portfolio, stock)
        if exposure.get("blocked"):
            alerts.append({
                "type": "EXPOSURE_BLOCK",
                "level": "WARNING",
                "message": f"⛔ {stock.get('name', '?')} 매수 차단: {exposure['reason']}",
            })
            continue

        result = execute_buy(portfolio, stock, history, p)
        if result:
            bought += 1
            alerts.append({
                "type": "NEW_BUY",
                "level": "WARNING",
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
