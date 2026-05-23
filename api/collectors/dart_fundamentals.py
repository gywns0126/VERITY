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

import functools
import json
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
    """DART fnlttSinglAcntAll.json 응답에서 PL/BS/CF 핵심 항목 추출.

    2026-05-20 확장 (실호출 audit 005930 2024 CFS 213 항목 기준):
      BS 9 + IS 5 + CF 3 (영업/투자/재무 활동 현금흐름) + 매출원가/매출총이익.
      fnlttSinglAcnt (단일계정) 30 항목 → fnlttSinglAcntAll (전체) 213 항목 전환.

    Returns: {
      total_assets, total_liabilities, equity,
      current_assets, current_liabilities, working_capital,
      retained_earnings, capital,
      revenue, cogs, gross_profit, operating_profit, net_income, pretax_income,
      operating_cashflow, investing_cashflow, financing_cashflow, free_cashflow
    }
    """
    out = {
        "total_assets": 0,
        "total_liabilities": 0,
        "equity": 0,
        "current_assets": 0,
        "current_liabilities": 0,
        "working_capital": 0,
        "retained_earnings": 0,
        "capital": 0,
        "revenue": 0,
        "cogs": 0,
        "gross_profit": 0,
        "operating_profit": 0,
        "net_income": 0,
        "pretax_income": 0,
        "operating_cashflow": 0,
        "investing_cashflow": 0,
        "financing_cashflow": 0,
        "free_cashflow": 0,
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
            elif acct == "유동자산":
                out["current_assets"] = amount
            elif acct == "유동부채":
                out["current_liabilities"] = amount
            elif "이익잉여금" in acct:
                out["retained_earnings"] = amount
            elif acct == "자본금":
                out["capital"] = amount
        elif sj in ("IS", "CIS"):
            if acct in ("매출액", "영업수익") or "수익(매출액)" in acct:
                out["revenue"] = max(out["revenue"], amount)
            elif acct == "매출원가":
                out["cogs"] = amount
            elif acct == "매출총이익" or "매출총이익" in acct:
                out["gross_profit"] = amount
            elif acct == "영업이익" or "영업이익(손실)" in acct:
                out["operating_profit"] = amount
            elif "당기순이익" in acct:
                out["net_income"] = max(out["net_income"], amount)
            elif "법인세차감전" in acct or "법인세비용차감전" in acct:
                out["pretax_income"] = amount
        elif sj == "CF":
            if "영업활동현금흐름" in acct or acct == "영업활동으로 인한 현금흐름":
                out["operating_cashflow"] = amount
            elif "투자활동현금흐름" in acct or acct == "투자활동으로 인한 현금흐름":
                out["investing_cashflow"] = amount
            elif "재무활동현금흐름" in acct or acct == "재무활동으로 인한 현금흐름":
                out["financing_cashflow"] = amount
    out["equity"] = out["total_assets"] - out["total_liabilities"]
    out["working_capital"] = out["current_assets"] - out["current_liabilities"]
    out["free_cashflow"] = out["operating_cashflow"] + out["investing_cashflow"]
    # gross_profit fallback — 매출 - 매출원가 (account_nm 직접 매칭 부재 시)
    if out["gross_profit"] == 0 and out["revenue"] > 0 and out["cogs"] > 0:
        out["gross_profit"] = out["revenue"] - out["cogs"]
    return out


def _compute_ratios(pl_bs: dict) -> dict:
    """PL/BS 항목 → 펀더멘털 비율 계산.

    2026-05-20 확장: roa / current_ratio / asset_turnover / gross_margin 추가.
    F-Score 단년 9/9 풀가동 + Δ 활성 (시계열 N 누적 후).
    """
    out = {
        "debt_ratio": None, "roe": None, "roa": None,
        "op_margin": None, "current_ratio": None, "asset_turnover": None,
        "gross_margin": None,
    }
    eq = pl_bs.get("equity", 0)
    ta = pl_bs.get("total_assets", 0)
    ni = pl_bs.get("net_income", 0)
    rev = pl_bs.get("revenue", 0)
    cur_a = pl_bs.get("current_assets", 0)
    cur_l = pl_bs.get("current_liabilities", 0)
    op = pl_bs.get("operating_profit", 0)
    gp = pl_bs.get("gross_profit", 0)

    if eq > 0:
        out["debt_ratio"] = round(pl_bs.get("total_liabilities", 0) / eq * 100, 2)
        if ni:
            out["roe"] = round(ni / eq * 100, 2)
    if ta > 0 and ni:
        out["roa"] = round(ni / ta * 100, 2)
    if ta > 0 and rev > 0:
        out["asset_turnover"] = round(rev / ta, 4)
    if rev > 0:
        out["op_margin"] = round(op / rev * 100, 2)
        if gp > 0:
            out["gross_margin"] = round(gp / rev * 100, 2)
    if cur_l > 0 and cur_a > 0:
        out["current_ratio"] = round(cur_a / cur_l, 4)
    return out


def _yf_fallback_for_ticker(ticker: str) -> dict:
    """yfinance .KS / .KQ — per/pbr/누락 필드 fallback.

    ticker = 6자리 KR 종목코드.
    """
    # 2026-05-18 fix — [[yfinance_safe.yf_ticker]] anti-bot
    from api.collectors.yfinance_safe import yf_ticker
    out = {"per": None, "pbr": None, "roe": None, "debt_ratio": None, "op_margin": None}
    for suffix in (".KS", ".KQ"):
        try:
            info = yf_ticker(f"{ticker}{suffix}").info or {}
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


@functools.lru_cache(maxsize=512)
def _fetch_fnltt_all_cached(corp_code: str, bsns_year: str, fs_div: str) -> str:
    """fnlttSinglAcntAll.json 응답 cache (2026-05-20 신설, fs_div 명시).

    fs_div = "CFS" (연결, 한국 상장사 표준) / "OFS" (개별).
    list_n CFS 213 / OFS 131 (005930 2024 audit). 매출원가/CF 섹션 포함.

    2026-05-23 (W3 4/4): record_dart_call(status) 로 dart_metrics 누적.
    lru_cache hit 은 미집계 — 실호출만 측정 정합.
    """
    from api.config import DART_API_KEY
    from api.observability.dart_metrics import record_dart_call
    import requests
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
    params = {
        "crtfc_key": DART_API_KEY, "corp_code": corp_code,
        "bsns_year": bsns_year, "reprt_code": "11011", "fs_div": fs_div,
    }
    try:
        resp = requests.get(url, params=params, timeout=(10, 30))
        resp.raise_for_status()
        text = resp.text
        try:
            status = json.loads(text).get("status", "")
        except Exception:
            status = ""
        record_dart_call(status)
        return text
    except Exception as e:
        record_dart_call("error")
        return json.dumps({"status": "error", "message": str(e), "list": []})


def _get_fnltt_all_data(corp_code: str, bsns_year: str, fs_div: str = "CFS") -> dict:
    return json.loads(_fetch_fnltt_all_cached(corp_code, bsns_year, fs_div))


def _fetch_one_dart_fundamentals(ticker: str, bsns_year: str) -> dict:
    """한 종목 펀더멘털 — DART 우선 (fnlttSinglAcntAll CFS → OFS fallback), yfinance fallback.

    2026-05-20 정정 (fs_div audit):
      이전 = fnlttSinglAcnt.json (단일계정, fs_div 미명시, DART default OFS).
      삼성 영업이익 12.36조 (OFS) ≠ 32.73조 (CFS, 표준).
      변경 = fnlttSinglAcntAll.json fs_div=CFS 우선, 0건 시 OFS fallback.
    """
    from api.collectors.dart_corp_code import get_corp_code

    base = {
        "per": None, "pbr": None, "roe": None, "roa": None,
        "debt_ratio": None, "op_margin": None,
        "current_ratio": None, "asset_turnover": None, "gross_margin": None,
        "working_capital": 0, "retained_earnings": 0, "total_assets": 0,
        "current_assets": 0, "current_liabilities": 0, "operating_profit": 0,
        "revenue": 0, "cogs": 0, "gross_profit": 0, "net_income": 0,
        "operating_cashflow": 0, "investing_cashflow": 0, "financing_cashflow": 0,
        "free_cashflow": 0,
        "reprt_code": "11011", "fs_div": None,
        "report_date": None, "source": "none",
    }

    corp_code = None
    try:
        corp_code = get_corp_code(ticker)
    except Exception:
        corp_code = None

    if corp_code:
        for fs_div in ("CFS", "OFS"):  # 연결 우선, fallback 개별
            try:
                data = _get_fnltt_all_data(corp_code, bsns_year, fs_div=fs_div)
                if data.get("status") != "000":
                    continue
                pl_bs = _extract_pl_bs_from_dart(data)
                if pl_bs.get("total_assets", 0) <= 0:
                    continue
                ratios = _compute_ratios(pl_bs)
                base.update(ratios)
                for k in ("working_capital", "retained_earnings", "total_assets",
                          "current_assets", "current_liabilities", "operating_profit",
                          "revenue", "cogs", "gross_profit", "net_income",
                          "operating_cashflow", "investing_cashflow",
                          "financing_cashflow", "free_cashflow"):
                    base[k] = pl_bs.get(k, 0)
                base["source"] = "DART"
                base["fs_div"] = fs_div
                base["report_date"] = bsns_year
                break
            except Exception:
                continue

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
