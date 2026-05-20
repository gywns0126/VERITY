"""us_financials — SEC EDGAR XBRL 시계열 표준화 (8Q + 5Y).

기존 api/collectors/sec_edgar.py.get_financial_facts() 는 latest annual single value only.
본 모듈 = 시계열 + 파생 metrics + cumulative quarterly 필터.

PM 직관 (사용자, 5/20): 미장 재무제표 분석 — bottom-up fundamentals layer.
[[project_us_financials_sec_edgar]] 정합. RULE 6 정합 (LLM call 0건).

데이터 source: SEC EDGAR XBRL companyfacts (무료, official).
XBRL 데이터 특성:
  - 한 row 당 start/end/val/fy/fp/form/accn 필드.
  - 10-K (annual, ~365 days span), 10-Q (quarterly, ~90 days standalone OR 6/9-month cumulative).
  - 필터 = end-start span 으로 period 분류. cumulative 제외.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

_logger = logging.getLogger(__name__)

SEC_USER_AGENT = "VERITY gywns0126@gmail.com"
TICKER_INDEX_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
# v0.1 (5/20) — SIC 는 companyfacts 에 없음 → submissions endpoint 별도 fetch.
SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# Period 분류 — span days
QUARTER_MIN_DAYS, QUARTER_MAX_DAYS = 80, 100
ANNUAL_MIN_DAYS, ANNUAL_MAX_DAYS = 350, 380

# Tag alias 매핑 (5/20 실측 검증 — MSFT 정합).
# 산업별 (특히 금융/REIT) 별도 tag 가능 — v0.1 별도 sprint.
TAG_ALIASES: Dict[str, List[str]] = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        # v0.1 (5/20 실측) — 은행/핀테크 총수익 정식 라인 (JPM/SOFI 는 plain Revenues 부재).
        "RevenuesNetOfInterestExpense",
    ],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    # v0.1 (5/20 실측) — 은행(BAC/JPM)·에너지(XOM)·보험(BRK) 은 OperatingIncomeLoss 미보고.
    # 세전이익 = sector-agnostic 수익성 지표 (op_income 으로 conflate 금지 — 비영업 항목 포함).
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "stockholders_equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquirePropertyPlantAndEquipmentExcludingNet",
    ],
}

# Flow-type vs instant-type metric 구분 — instant 는 balance sheet (start == end).
INSTANT_METRICS = {"cash", "stockholders_equity", "long_term_debt"}


@dataclass(frozen=True)
class Period:
    fiscal_year: int
    fiscal_period: str  # FY / Q1 / Q2 / Q3 / Q4
    end_date: str
    form: str
    is_annual: bool


def _http_get(url: str, timeout: int = 15) -> Optional[Any]:
    try:
        r = requests.get(
            url,
            headers={"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"},
            timeout=timeout,
        )
    except requests.RequestException as e:
        _logger.warning("SEC fetch failed %s: %s", url, e)
        return None
    if r.status_code != 200:
        _logger.warning("SEC %s HTTP %d", url, r.status_code)
        return None
    try:
        return r.json()
    except (ValueError, json.JSONDecodeError) as e:
        _logger.warning("SEC %s JSON decode failed: %s", url, e)
        return None


def build_ticker_cik_cache() -> Dict[str, int]:
    """US 전체 ticker→CIK 1회 fetch."""
    data = _http_get(TICKER_INDEX_URL)
    if not data:
        return {}
    return {
        row["ticker"].upper(): int(row["cik_str"])
        for row in data.values()
        if row.get("ticker") and row.get("cik_str")
    }


def ticker_to_cik(ticker: str, cache: Optional[Dict[str, int]] = None) -> Optional[int]:
    if cache is not None:
        return cache.get(ticker.upper())
    cache = build_ticker_cik_cache()
    return cache.get(ticker.upper())


def fetch_companyfacts(cik: int) -> Optional[Dict[str, Any]]:
    return _http_get(COMPANYFACTS_URL_TEMPLATE.format(cik=cik))


def fetch_sic(cik: int) -> Tuple[Optional[int], Optional[str]]:
    """submissions endpoint 에서 SIC 코드 + 설명. companyfacts 에는 SIC 부재 (5/20 실측)."""
    data = _http_get(SUBMISSIONS_URL_TEMPLATE.format(cik=cik))
    if not data:
        return (None, None)
    sic_raw = data.get("sic")
    try:
        sic = int(sic_raw) if sic_raw not in (None, "") else None
    except (TypeError, ValueError):
        sic = None
    return (sic, data.get("sicDescription"))


def is_financial_sic(sic: Optional[int]) -> bool:
    """SEC SIC 은행(6000-6199)·증권(6200-6299)·보험(6300-6499) — FCF=OCF-CapEx 구조적 무의미.
    부동산/REIT (6500+) 는 capex 유의미 → 제외. 5/20 실측: BAC/JPM 6021, SOFI 6199, BRK 6331.
    """
    if sic is None:
        return False
    return 6000 <= sic <= 6499


def _parse_iso(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _classify_period(
    start: str, end: str, form: str, fp: str, fy_hint: Optional[int],
    is_instant: bool,
) -> Optional[Period]:
    """row span → Period. cumulative quarterly 제외.

    is_instant: balance-sheet (start == end). span 분류 우회.
    """
    s = _parse_iso(start) if start else None
    e = _parse_iso(end)
    if not e:
        return None
    fy = fy_hint or e.year

    if is_instant or (s and s == e):
        if form in ("10-K", "10-K/A"):
            is_annual = True
            fp_out = "FY"
        elif form in ("10-Q", "10-Q/A"):
            is_annual = False
            fp_out = fp if fp in ("Q1", "Q2", "Q3", "Q4") else "Q?"
        else:
            return None
        return Period(fy, fp_out, end, form, is_annual)

    if not s:
        return None
    span = (e - s).days
    if form in ("10-K", "10-K/A") and ANNUAL_MIN_DAYS <= span <= ANNUAL_MAX_DAYS:
        return Period(fy, "FY", end, form, True)
    if form in ("10-Q", "10-Q/A") and QUARTER_MIN_DAYS <= span <= QUARTER_MAX_DAYS:
        return Period(fy, fp if fp in ("Q1", "Q2", "Q3", "Q4") else "Q?", end, form, False)
    return None


def extract_metric_series(
    facts: Dict[str, Any],
    metric_key: str,
    aliases: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """단일 metric 의 표준화 시계열 — **모든 alias tag 의 rows 를 merge**.

    이유: 회사가 시기별 다른 tag 사용 (예: MSFT 2010 이전 Revenues, 2018+
    RevenueFromContractWithCustomerExcludingAssessedTax — ASC 606 도입).
    First-match 만 사용 시 시계열 잘림 (5/20 박힘 — MSFT revenue 2010 종결 결함).

    dedupe key: (end, fp, form). 충돌 시 accn (restatement) 최신 우선.
    """
    us_gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    tag_aliases = aliases or TAG_ALIASES.get(metric_key) or []
    is_instant = metric_key in INSTANT_METRICS

    seen: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    matched_tags: List[str] = []
    for tag in tag_aliases:
        if tag not in us_gaap:
            continue
        matched_tags.append(tag)
        units = us_gaap[tag].get("units") or {}
        if "USD" in units:
            unit_rows = units["USD"]
        elif "USD/shares" in units:
            unit_rows = units["USD/shares"]
        else:
            continue
        for r in unit_rows:
            end = r.get("end")
            if not end:
                continue
            start = r.get("start") or end
            form = r.get("form", "")
            fp = r.get("fp", "")
            fy = r.get("fy")
            period = _classify_period(start, end, form, fp, fy, is_instant)
            if period is None:
                continue
            key = (period.end_date, period.fiscal_period, period.form)
            accn_new = r.get("accn", "")
            existing = seen.get(key)
            # 충돌: accn 최신 우선. 같은 accn 이면 alias 우선순위 (앞쪽 tag 우선).
            if existing is None:
                pick = True
            elif accn_new > existing.get("accn", ""):
                pick = True
            elif accn_new == existing.get("accn", ""):
                # 첫 tag 우선 — existing 유지
                pick = False
            else:
                pick = False
            if pick:
                seen[key] = {
                    "end": period.end_date,
                    "fy": int(period.fiscal_year),
                    "fp": period.fiscal_period,
                    "form": period.form,
                    "is_annual": period.is_annual,
                    "val": r.get("val"),
                    "accn": accn_new,
                    "tag": tag,
                }
    return sorted(seen.values(), key=lambda x: x["end"])


def get_entity_meta(facts: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "cik": facts.get("cik"),
        "entity_name": facts.get("entityName"),
    }


def fetch_all_metrics(cik: int) -> Dict[str, Any]:
    """단일 ticker 전체 표준 metrics fetch + alias 해소.

    Returns: {meta, metrics: {revenue: [...], ...}, fetched_at}
    """
    facts = fetch_companyfacts(cik)
    if not facts:
        return {"_error": f"companyfacts fetch failed for CIK {cik}"}
    time.sleep(0.15)  # SEC rate limit 안전
    out_metrics: Dict[str, List[Dict[str, Any]]] = {
        k: extract_metric_series(facts, k) for k in TAG_ALIASES.keys()
    }
    # v0.1 — SIC fetch (FCF financial gating). 별도 endpoint, 실패해도 graceful (is_financial=False).
    sic, sic_desc = fetch_sic(cik)
    time.sleep(0.15)
    meta = get_entity_meta(facts)
    meta["sic"] = sic
    meta["sic_description"] = sic_desc
    meta["is_financial"] = is_financial_sic(sic)
    return {
        "meta": meta,
        "metrics": out_metrics,
        "fetched_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


# ──────────────────────────────────────────────────────────────────────
# Derived metrics (시계열 → 파생)
# ──────────────────────────────────────────────────────────────────────


def _by_end(series: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {row["end"]: row for row in series if row.get("val") is not None}


def _latest_n(series: List[Dict[str, Any]], n: int, annual: bool) -> List[Dict[str, Any]]:
    filtered = [r for r in series if r.get("is_annual") == annual]
    return filtered[-n:]


def _yoy_growth(current: float, prior: float) -> Optional[float]:
    if prior is None or prior == 0:
        return None
    if current is None:
        return None
    return round((current - prior) / abs(prior) * 100, 2)


def compute_derived(
    metrics: Dict[str, List[Dict[str, Any]]],
    is_financial: bool = False,
) -> Dict[str, Any]:
    """8Q + 5Y 시계열 → 파생 metrics (latest period 기준).

    파생:
      - revenue_yoy_pct (annual + quarterly)
      - gross_margin / operating_margin / net_margin / pretax_margin (latest annual)
      - fcf (latest annual) = OCF - CapEx — 금융 sector 는 무의미 → null + reason (v0.1)
      - debt_to_equity (latest annual)
      - roe (latest annual)

    is_financial: SIC 6000-6499 (은행/증권/보험). FCF gating 용.
    """
    out: Dict[str, Any] = {}

    # Latest annual
    rev_a = _latest_n(metrics.get("revenue", []), 2, annual=True)
    if len(rev_a) >= 2:
        out["revenue_yoy_pct_annual"] = _yoy_growth(rev_a[-1]["val"], rev_a[-2]["val"])
    # v0.2 (5/20) — quarterly YoY 는 prior-year same quarter 를 **end-date 근접(~365d)** 으로 매칭.
    # 옛 (fp + fy==latest.fy-1) 매칭 = SEC fy 필드가 restated comparative 에서 filing 연도로 오염
    #   (실측: MSFT end=2025-03-31 이 fy=2026 오라벨) → 0/15 universe 전부 null 결함.
    # end-date 는 dedup key 라 오염 없음. ±20d tolerance (분기말 변동/53주 회계 흡수).
    rev_q = _latest_n(metrics.get("revenue", []), 8, annual=False)
    if len(rev_q) >= 2:
        latest_q = rev_q[-1]
        le = _parse_iso(latest_q.get("end", ""))
        if le and latest_q.get("val") is not None:
            best, best_gap = None, None
            for r in rev_q[:-1]:
                re = _parse_iso(r.get("end", ""))
                if not re or r.get("val") is None:
                    continue
                gap = abs((le - re).days - 365)
                if gap <= 20 and (best_gap is None or gap < best_gap):
                    best, best_gap = r, gap
            if best:
                out["revenue_yoy_pct_quarterly"] = _yoy_growth(latest_q["val"], best["val"])

    # Margins (latest annual)
    def _latest_annual_val(key: str) -> Optional[float]:
        series = _latest_n(metrics.get(key, []), 1, annual=True)
        return series[0]["val"] if series and series[0].get("val") is not None else None

    rev_v = _latest_annual_val("revenue")
    gp_v = _latest_annual_val("gross_profit")
    op_v = _latest_annual_val("operating_income")
    ptx_v = _latest_annual_val("pretax_income")
    ni_v = _latest_annual_val("net_income")
    if rev_v and rev_v > 0:
        if gp_v is not None:
            out["gross_margin_pct"] = round(gp_v / rev_v * 100, 2)
        if op_v is not None:
            out["operating_margin_pct"] = round(op_v / rev_v * 100, 2)
        # v0.1 — 세전이익률: op_income 미보고 (은행/에너지/보험) 종목의 sector-agnostic 수익성.
        if ptx_v is not None:
            out["pretax_margin_pct"] = round(ptx_v / rev_v * 100, 2)
        if ni_v is not None:
            out["net_margin_pct"] = round(ni_v / rev_v * 100, 2)

    # FCF (latest annual). v0.1 — 금융 sector 는 FCF=OCF-CapEx 구조적 무의미 (대출/트레이딩
    # 현금흐름, capex trivial). null + reason 으로 명시 (5/20 JPM -$147.8B / SOFI -$3.7B 왜곡 해소).
    ocf = _latest_annual_val("operating_cash_flow")
    capex = _latest_annual_val("capex")
    if is_financial:
        out["fcf_usd"] = None
        out["fcf_na_reason"] = "financial_sector"
    elif ocf is not None:
        out["fcf_usd"] = ocf - (capex or 0)

    # Debt-to-Equity
    ltd = _latest_annual_val("long_term_debt")
    eq = _latest_annual_val("stockholders_equity")
    if eq and eq > 0 and ltd is not None:
        out["debt_to_equity"] = round(ltd / eq, 3)

    # ROE
    if ni_v is not None and eq and eq > 0:
        out["roe_pct"] = round(ni_v / eq * 100, 2)

    return out


def build_ticker_snapshot(
    ticker: str, cik: int, history_quarters: int = 8, history_years: int = 5,
) -> Dict[str, Any]:
    """단일 ticker 의 표준화 + 시계열 + 파생 snapshot.

    Returns: {ticker, meta, metrics_latest_annual, metrics_latest_quarterly,
              series_annual, series_quarterly, derived, fetched_at, _errors}.
    """
    raw = fetch_all_metrics(cik)
    if "_error" in raw:
        return {"ticker": ticker, "_error": raw["_error"], "fetched_at": raw.get("fetched_at")}

    metrics = raw["metrics"]
    out: Dict[str, Any] = {
        "ticker": ticker,
        "meta": raw["meta"],
        "fetched_at": raw["fetched_at"],
        "series_annual": {},
        "series_quarterly": {},
        "derived": compute_derived(metrics, is_financial=bool(raw["meta"].get("is_financial"))),
        "_errors": [],
    }
    for key, series in metrics.items():
        annual = _latest_n(series, history_years, annual=True)
        quarterly = _latest_n(series, history_quarters, annual=False)
        out["series_annual"][key] = annual
        out["series_quarterly"][key] = quarterly
        if not series:
            out["_errors"].append(f"{key}: no tag matched")
    return out
