"""
DART 펀더멘털 batch wrapper — Phase 2-A (2026-05-01)

Phase 0.5 결정 2 / 결정 14 적용:
  1순위: DART 분기 보고서 (debt_ratio, op_margin, roe — PL/BS 항목)
  2순위: yfinance .KS suffix (per/pbr 가격 의존 + DART 누락 종목 fallback)
  제외:  pykrx (환경 부적합), KIS (rate limit)

기존 인프라 재활용:
  - api/collectors/dart_corp_code.py — ticker → corp_code 매핑
  - api/collectors/DartScout.py:_get_fnltt_data — 분기 보고서 캐시

설계:
  - 주 1회 (월요일) 갱신 권고 (FUND-CHANGE 측정 결과 — PBR/ROE/op_margin 분기 의존)
  - max_workers=10 (DART rate limit 일 1만건 고려)
  - 모든 외부 호출 timeout 명시 (결정 16 wrapper 의무)
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout, as_completed
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

# DART rate limit 안전 마진 — 일 1만건 / 주 1회 갱신 시 5,000 종목 OK
DART_BATCH_MAX_WORKERS_DEFAULT = 10
DART_PER_TICKER_TIMEOUT_S = 15.0


def _parse_int(value) -> int:
    if value is None:
        return 0
    s = str(value).strip().replace(",", "")
    if not s or s == "-":
        return 0
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _extract_pl_bs_from_dart(data: dict) -> dict:
    """DART fnlttSinglAcnt.json 응답에서 PL/BS 핵심 항목 추출.

    Returns: {total_assets, total_liabilities, equity, revenue, operating_profit, net_income}
    """
    out = {
        "total_assets": 0,
        "total_liabilities": 0,
        "equity": 0,
        "revenue": 0,
        "operating_profit": 0,
        "net_income": 0,
    }
    for item in data.get("list", []):
        sj = item.get("sj_div", "")
        acct = item.get("account_nm", "")
        amount = _parse_int(item.get("thstrm_amount"))
        if sj == "BS":
            if "자산총계" in acct:
                out["total_assets"] = amount
            elif "부채총계" in acct:
                out["total_liabilities"] = amount
        elif sj in ("IS", "CIS"):
            if acct in ("매출액", "영업수익") or "수익(매출액)" in acct:
                out["revenue"] = max(out["revenue"], amount)
            elif acct == "영업이익" or "영업이익(손실)" in acct:
                out["operating_profit"] = amount
            elif "당기순이익" in acct:
                out["net_income"] = max(out["net_income"], amount)
    out["equity"] = out["total_assets"] - out["total_liabilities"]
    return out


def _compute_ratios(pl_bs: dict) -> dict:
    """PL/BS 항목 → 펀더멘털 비율 계산."""
    out = {"debt_ratio": None, "roe": None, "op_margin": None}
    eq = pl_bs.get("equity", 0)
    if eq > 0:
        out["debt_ratio"] = round(pl_bs.get("total_liabilities", 0) / eq * 100, 2)
        ni = pl_bs.get("net_income", 0)
        if ni:
            out["roe"] = round(ni / eq * 100, 2)
    rev = pl_bs.get("revenue", 0)
    if rev > 0:
        op = pl_bs.get("operating_profit", 0)
        out["op_margin"] = round(op / rev * 100, 2)
    return out


def _yf_fallback_for_ticker(ticker: str) -> dict:
    """yfinance .KS / .KQ — per/pbr/누락 필드 fallback.

    ticker = 6자리 KR 종목코드.
    """
    import yfinance as yf
    out = {"per": None, "pbr": None, "roe": None, "debt_ratio": None, "op_margin": None}
    for suffix in (".KS", ".KQ"):
        try:
            info = yf.Ticker(f"{ticker}{suffix}").info or {}
            if not info:
                continue
            per = info.get("trailingPE") or info.get("forwardPE")
            if per:
                out["per"] = round(float(per), 2)
            pbr = info.get("priceToBook")
            if pbr:
                out["pbr"] = round(float(pbr), 2)
            roe = info.get("returnOnEquity")
            if roe is not None:
                out["roe"] = round(float(roe) * 100, 2)
            debt = info.get("debtToEquity")
            if debt is not None:
                out["debt_ratio"] = round(float(debt), 2)
            op = info.get("operatingMargins")
            if op is not None:
                out["op_margin"] = round(float(op) * 100, 2)
            return out
        except Exception:
            continue
    return out


def _fetch_one_dart_fundamentals(ticker: str, bsns_year: str) -> dict:
    """한 종목 펀더멘털 — DART 우선, yfinance fallback."""
    from api.collectors.dart_corp_code import get_corp_code
    from api.collectors.DartScout import _get_fnltt_data

    base = {
        "per": None, "pbr": None, "roe": None,
        "debt_ratio": None, "op_margin": None,
        "report_date": None, "source": "none",
    }

    corp_code = None
    try:
        corp_code = get_corp_code(ticker)
    except Exception:
        corp_code = None

    if corp_code:
        try:
            data = _get_fnltt_data(corp_code, bsns_year)
            pl_bs = _extract_pl_bs_from_dart(data)
            ratios = _compute_ratios(pl_bs)
            if any(v is not None for v in ratios.values()):
                base.update(ratios)
                base["source"] = "DART"
                base["report_date"] = bsns_year
        except Exception:
            pass

    # yfinance fallback for any None field (특히 per/pbr — DART 가 가격 의존 비율 안 줌)
    needs_fallback = base["per"] is None or base["pbr"] is None
    needs_fallback = needs_fallback or any(base[k] is None for k in ("roe", "debt_ratio", "op_margin"))
    if needs_fallback:
        yf_data = _yf_fallback_for_ticker(ticker)
        for k, v in yf_data.items():
            if base.get(k) is None and v is not None:
                base[k] = v
        if base["source"] == "none" and any(yf_data[k] is not None for k in yf_data):
            base["source"] = "yfinance_fallback"
        elif base["source"] == "DART" and (base["per"] is not None or base["pbr"] is not None):
            base["source"] = "DART+yfinance"

    return base


def fetch_dart_fundamentals_batch(
    tickers: list[str],
    max_workers: int = DART_BATCH_MAX_WORKERS_DEFAULT,
    timeout_per_ticker: float = DART_PER_TICKER_TIMEOUT_S,
    bsns_year: Optional[str] = None,
) -> dict[str, dict]:
    """KR 종목 리스트의 펀더멘털 일괄 수집.

    Args:
        tickers: 6자리 KR 종목코드 리스트.
        max_workers: ThreadPool 동시성. 기본 10 (DART rate limit 안전 마진).
        bsns_year: 분기 연도. 미지정 시 직전 회계연도 자동 선택.

    Returns:
        {ticker: {per, pbr, roe, debt_ratio, op_margin, report_date, source}}
    """
    if not tickers:
        return {}

    if bsns_year is None:
        # KST 기준 직전 연도 (3월 사업보고서 기준 — 4월 이후엔 작년 보고서 안정)
        now = datetime.now(ZoneInfo("Asia/Seoul"))
        bsns_year = str(now.year - 1) if now.month <= 4 else str(now.year - 1)

    out: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_fetch_one_dart_fundamentals, t, bsns_year): t
            for t in tickers
        }
        for fu in as_completed(futures, timeout=max(timeout_per_ticker * 4, 60)):
            tk = futures[fu]
            try:
                out[tk] = fu.result(timeout=timeout_per_ticker)
            except (FutTimeout, Exception):
                out[tk] = {
                    "per": None, "pbr": None, "roe": None,
                    "debt_ratio": None, "op_margin": None,
                    "report_date": None, "source": "error",
                }
    return out
