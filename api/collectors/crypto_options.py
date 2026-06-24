"""BTC/ETH 옵션 시장 지표 — IV(내재변동성)·실현변동성·옵션 OI 기반 put/call·max pain.

주식의 옵션 시장 지표(VIX·put/call·max pain)에 대응하는 코인 쪽 갭을 메우는 collector.
무료 옵션 데이터는 희소해 개인이 매일 산출하기 어렵다 = 강한 차별 자산.
BTC/ETH 옵션 유동성 대부분이 Deribit 에 집중되어 단일 소스로 대표성을 가진다.

소스: Deribit public API (무인증, US-IP OK) — https://www.deribit.com/api/v2/
  (모두 실호출 schema 검증 완료, 2026-06-24)
  - DVOL(IV 인덱스): public/get_volatility_index_data
      → result.data = [[ts_ms, open, high, low, close], ...]  (close = 최신 DVOL)
      resolution=43200(12h) 로 최근 며칠치 캔들을 받아 마지막 close 사용
  - 실현변동성: public/get_historical_volatility?currency=BTC
      → result = [[ts_ms, vol_pct], ...]  (마지막 entry = 최신, 단위 = 연율화 %)
  - 옵션 OI 전체: public/get_book_summary_by_currency?currency=BTC&kind=option
      → result = [{instrument_name, open_interest, underlying_price, ...}, ...]
      instrument_name 형식 = "BTC-24JUN26-63500-C" (통화-만기-행사가-C|P)
      open_interest = 계약 수(코인 단위). 여기서 put/call·max pain 을 자체 산출.

🚨 RULE 7 (자기 산식 = 가설): DVOL·실현변동성은 Deribit 1차 수치 그대로.
   put/call ratio·max pain 은 본 모듈이 자체 산출하는 파생 지표 = 가설.
   - put_call_ratio_oi = (전 만기 put OI 합) / (전 만기 call OI 합).
       1 초과 = put 수요 우위(헤지/약세 포지션 우세), 1 미만 = call 우위.
       단순 OI 비율이며 델타·만기 가중 없음(1차 근사) = 가설.
   - max_pain_strike = "최근접 미래 만기" 한 군(群)에서 옵션 매수자 총 내재가치
       payout 합이 최소가 되는 행사가. 옵션 매도자(딜러) 손실 최소 = 가격 인력 가설.
       payout(K) = Σ_call max(K - strike, 0) * OI_call
                 + Σ_put  max(strike - K, 0) * OI_put,  K ∈ {관측된 행사가}.
       단일 만기군·OI 가중·순수 내재가치 모델 = 고전적 max pain 정의, 검증 안 됨 = 가설.
   주의: OI 는 스냅샷(실시간 변동), 만기 임박 시 max pain 신뢰도 ↓(시간가치 무시).
         소형 만기군(총 OI 적음)은 노이즈 큼. 점수·매수신호로 직접 wire 금지.

기존 crypto_macro.py / crypto_defillama.py collector 계약 정합:
  표준 라이브러리 + requests 만, 외부 의존 추가 없음. 항상 dict 반환, 절대 raise 안 함.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

# Deribit 무료 공개 API (무인증). 출처 표기.
_BASE = "https://www.deribit.com/api/v2"
_TIMEOUT = 15
_HEADERS = {"User-Agent": "Verity-Terminal/1.0"}
_SOURCE = "Deribit (deribit.com), 무료 공개 API"

_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}
# instrument_name 형식: BTC-24JUN26-63500-C  (통화-DDMMMYY-strike-C|P)
_INSTR_RE = re.compile(r"^[A-Z]+-(\d{1,2})([A-Z]{3})(\d{2})-(\d+(?:\.\d+)?)-([CP])$")


def _num(v: Any) -> float:
    """None / 비숫자 → 0.0 안전 변환."""
    try:
        if v is None:
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _get(path: str, params: Dict[str, Any]) -> Optional[Any]:
    """Deribit JSON-RPC GET → result. 실패 시 None (graceful)."""
    try:
        r = requests.get(f"{_BASE}/{path}", params=params, headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        return r.json().get("result")
    except Exception:  # noqa: BLE001
        return None


def _fetch_dvol(currency: str) -> Optional[float]:
    """DVOL(내재변동성 인덱스) 최신 close. result.data = [[ts,o,h,l,c], ...]."""
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - 3 * 86_400_000  # 최근 3일치 12h 캔들이면 충분
    res = _get(
        "public/get_volatility_index_data",
        {"currency": currency, "start_timestamp": start_ms, "end_timestamp": now_ms, "resolution": 43200},
    )
    rows = (res or {}).get("data") if isinstance(res, dict) else None
    if not rows:
        return None
    # 각 row = [ts_ms, open, high, low, close]. 마지막 캔들의 close = 최신 DVOL.
    last = rows[-1]
    if isinstance(last, (list, tuple)) and len(last) >= 5:
        return round(_num(last[4]), 2)
    return None


def _fetch_hist_vol(currency: str) -> Optional[float]:
    """실현변동성(연율화 %) 최신값. result = [[ts, vol_pct], ...]."""
    res = _get("public/get_historical_volatility", {"currency": currency})
    if not isinstance(res, list) or not res:
        return None
    last = res[-1]  # 마지막 entry = 최신
    if isinstance(last, (list, tuple)) and len(last) >= 2:
        return round(_num(last[1]), 2)
    return None


def _expiry_dt(exp: str) -> Optional[datetime]:
    """'24JUN26' → tz-aware datetime (UTC). 파싱 실패 시 None."""
    m = re.match(r"(\d{2})([A-Z]{3})(\d{2})$", exp)
    if not m:
        return None
    d, mon, yy = m.groups()
    month = _MONTHS.get(mon)
    if not month:
        return None
    try:
        return datetime(2000 + int(yy), month, int(d), tzinfo=timezone.utc)
    except ValueError:
        return None


def _max_pain(calls: Dict[float, float], puts: Dict[float, float]) -> Optional[float]:
    """단일 만기군 max pain = 옵션 매수자 총 내재가치 payout 최소 행사가.

    payout(K) = Σ_call max(K-strike,0)*OI + Σ_put max(strike-K,0)*OI.
    K 후보 = 관측된 모든 행사가. 동률 시 최소 K. = 가설(고전적 정의, 검증 안 됨).
    """
    strikes = sorted(set(calls) | set(puts))
    if not strikes:
        return None

    def payout(k: float) -> float:
        s = 0.0
        for strike, oi in calls.items():
            if k > strike:
                s += (k - strike) * oi
        for strike, oi in puts.items():
            if k < strike:
                s += (strike - k) * oi
        return s

    return min(strikes, key=payout)


def _fetch_option_metrics(currency: str) -> Dict[str, Any]:
    """옵션 OI 스냅샷에서 put/call ratio·max pain·total OI 자체 산출.

    실패/데이터 없음 시 빈 dict. 호출부가 흡수.
    """
    res = _get("public/get_book_summary_by_currency", {"currency": currency, "kind": "option"})
    if not isinstance(res, list) or not res:
        return {}

    call_oi_total = 0.0
    put_oi_total = 0.0
    underlying = 0.0
    # 만기군 → {'C': {strike: OI}, 'P': {strike: OI}}
    by_exp: Dict[str, Dict[str, Dict[float, float]]] = defaultdict(
        lambda: {"C": defaultdict(float), "P": defaultdict(float)}
    )

    for row in res:
        if not isinstance(row, dict):
            continue
        m = _INSTR_RE.match(row.get("instrument_name", "") or "")
        if not m:
            continue
        d, mon, yy, strike_s, cp = m.groups()
        exp = f"{int(d):02d}{mon}{yy}"
        strike = _num(strike_s)
        oi = _num(row.get("open_interest"))
        by_exp[exp][cp][strike] += oi
        if cp == "C":
            call_oi_total += oi
        else:
            put_oi_total += oi
        up = _num(row.get("underlying_price"))
        if up > 0:
            underlying = up  # 마지막 유효값 사용(만기별 약간 상이, 근사용)

    if not by_exp or call_oi_total <= 0:
        return {}

    # 최근접 미래 만기군 선정 (오늘 00:00 UTC 이후, 총 OI 의미 있는 첫 군)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    future: List[Tuple[datetime, str]] = []
    for exp in by_exp:
        dt = _expiry_dt(exp)
        if dt is not None and dt >= today:
            future.append((dt, exp))
    future.sort(key=lambda t: t[0])

    max_pain_strike: Optional[float] = None
    max_pain_expiry: Optional[str] = None
    for dt, exp in future:
        legs = by_exp[exp]
        tot = sum(legs["C"].values()) + sum(legs["P"].values())
        if tot > 10:  # 소형 만기군(노이즈) 회피
            max_pain_strike = _max_pain(legs["C"], legs["P"])
            max_pain_expiry = exp
            break

    return {
        "put_call_ratio_oi": round(put_oi_total / call_oi_total, 3),
        "call_oi": round(call_oi_total, 1),
        "put_oi": round(put_oi_total, 1),
        "total_oi": round(call_oi_total + put_oi_total, 1),
        "max_pain_strike": max_pain_strike,
        "max_pain_expiry": max_pain_expiry,
        "underlying_price": round(underlying, 2) if underlying else None,
        "num_instruments": len(res),
        "num_expiries": len(by_exp),
    }


def _collect_one(currency: str) -> Dict[str, Any]:
    """단일 통화(BTC|ETH) 옵션 지표. 부분 실패 graceful — 있는 것만 채움."""
    dvol = _fetch_dvol(currency)
    hist_vol = _fetch_hist_vol(currency)
    opt = _fetch_option_metrics(currency)

    out: Dict[str, Any] = {
        "dvol": dvol,
        "hist_vol_pct": hist_vol,
        "put_call_ratio_oi": opt.get("put_call_ratio_oi"),
        "max_pain_strike": opt.get("max_pain_strike"),
        "max_pain_expiry": opt.get("max_pain_expiry"),
        "total_oi": opt.get("total_oi"),
        "call_oi": opt.get("call_oi"),
        "put_oi": opt.get("put_oi"),
        "underlying_price": opt.get("underlying_price"),
        "num_instruments": opt.get("num_instruments"),
        "num_expiries": opt.get("num_expiries"),
    }
    # IV-RV 스프레드(변동성 위험 프리미엄 근사) = 가설. 둘 다 있을 때만.
    if dvol is not None and hist_vol is not None:
        out["iv_rv_spread"] = round(dvol - hist_vol, 2)

    has_data = any(v is not None for v in (dvol, hist_vol, opt.get("put_call_ratio_oi")))
    out["ok"] = has_data
    return out


def collect_crypto_options() -> Dict[str, Any]:
    """BTC/ETH 옵션 시장 지표 수집 (Deribit 무인증 공개 API).

    항상 dict 반환, 절대 raise 안 함. 부분 실패는 graceful.

    반환:
      ok        : bool — 통화 한쪽이라도 데이터 1개 있으면 True
      ok_count  : int  — 데이터 있는 통화 수(0~2)
      source    : str  — Deribit attribution
      btc / eth : dict — {dvol, hist_vol_pct, iv_rv_spread, put_call_ratio_oi,
                          max_pain_strike, max_pain_expiry, total_oi, call_oi,
                          put_oi, underlying_price, num_instruments, num_expiries, ok}
      실패 시    : {"ok": False, "ok_count": 0, "error": "<짧은 사유>"}
    """
    try:
        btc = _collect_one("BTC")
        eth = _collect_one("ETH")

        ok_count = sum(1 for c in (btc, eth) if c.get("ok"))
        if ok_count == 0:
            return {"ok": False, "ok_count": 0, "error": "no_data_from_deribit"}

        return {
            "ok": True,
            "ok_count": ok_count,
            "source": _SOURCE,
            "btc": btc,
            "eth": eth,
        }
    except Exception as e:  # noqa: BLE001 — 최종 안전망: 절대 raise 안 함
        return {"ok": False, "ok_count": 0, "error": str(e)[:120]}
