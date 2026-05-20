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
    # v0.4 (5/20) — Altman Z 입력 (대차대조표). 비금융 전 종목 실호출 확인.
    "total_assets": ["Assets"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "total_liabilities": ["Liabilities"],
    "retained_earnings": ["RetainedEarningsAccumulatedDeficit"],
    # v0.4 — F-Score F7 (신주 발행). 희석 가중평균 주식수 (shares unit).
    "diluted_shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}

# v0.3 (5/20) — 금융 sector revenue alias 우선순위 override.
# 결함: 기본 alias 순서는 RevenueFromContractWithCustomer(비이자 계약수익 일부) 가
#   RevenuesNetOfInterestExpense(은행/핀테크 총수익) 보다 앞 → SOFI revenue 0.62B 과소계상
#   (실제 총수익 3.61B) → net_margin 77.7% 왜곡 (DTA 아님, revenue 분모 결함).
# 금융은 RevenuesNetOfInterestExpense 를 최우선. 부재 시 Revenues→contract 순 fallback.
# 실측: SOFI 3.61B (정정), JPM/BAC(revNI 부재→Revenues)/BRK 불변.
FINANCIAL_REVENUE_ALIASES: List[str] = [
    "RevenuesNetOfInterestExpense",
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
]

# Flow-type vs instant-type metric 구분 — instant 는 balance sheet (start == end).
INSTANT_METRICS = {"cash", "stockholders_equity", "long_term_debt",
                   "total_assets", "current_assets", "current_liabilities",
                   "total_liabilities", "retained_earnings"}


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
        elif "shares" in units:
            unit_rows = units["shares"]  # v0.4 — diluted_shares (F-Score F7 신주 발행)
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
    # v0.1 — SIC fetch (FCF financial gating + v0.3 revenue alias). 실패해도 graceful.
    sic, sic_desc = fetch_sic(cik)
    time.sleep(0.15)
    is_fin = is_financial_sic(sic)
    # v0.3 — 금융은 revenue 만 FINANCIAL_REVENUE_ALIASES (총수익 우선) 로 추출.
    out_metrics: Dict[str, List[Dict[str, Any]]] = {}
    for k in TAG_ALIASES.keys():
        if k == "revenue" and is_fin:
            out_metrics[k] = extract_metric_series(facts, k, aliases=FINANCIAL_REVENUE_ALIASES)
        else:
            out_metrics[k] = extract_metric_series(facts, k)
    meta = get_entity_meta(facts)
    meta["sic"] = sic
    meta["sic_description"] = sic_desc
    meta["is_financial"] = is_fin
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


def compute_altman_z_us(latest: Dict[str, Any], is_financial: bool = False,
                        market_cap: Optional[float] = None,
                        sic: Optional[int] = None) -> Dict[str, Any]:
    """Altman Z — US calibration. SIC + market_cap 가용 여부로 모델 dispatch.

    제조업(SIC 2000-3999) + market_cap → **원본 1968 Z** (X4 시가):
      Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4(시가/총부채) + 1.0·X5(매출/총자산)
      cut: Safe ≥ 2.99 / Grey 1.81-2.99 / Distress < 1.81.
    그 외 비금융 → **Z'' (non-mfg, 장부가 4-variable)**:
      Z'' = 3.25 + 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4(장부가/총부채)
      cut: Safe ≥ 2.6 / Grey 1.1-2.6 / Distress < 1.1.
    공통 X1=(유동자산-유동부채)/총자산, X2=이익잉여금/총자산, X3=EBIT/총자산.

    학술 원전 ≥2 (2026-05-20): wallstreetprep + Wikipedia + quality.py Q-fin (RISS/SSRN).
    금융(SIC 6000-6499) = not_applicable. market_cap = portfolio.json wire.
    """
    if is_financial:
        return {"z_score": None, "zone": "not_applicable",
                "model_variant": "excluded_financial", "applicable": False}
    ta = latest.get("total_assets")
    if not ta or ta <= 0:
        return {"z_score": None, "zone": "unknown", "applicable": False}
    ca = latest.get("current_assets")
    cl = latest.get("current_liabilities")
    re = latest.get("retained_earnings")
    ebit = latest.get("operating_income")
    eq = latest.get("stockholders_equity")
    tl = latest.get("total_liabilities")
    if None in (ca, cl, re, ebit, eq, tl) or tl <= 0:
        return {"z_score": None, "zone": "unknown", "applicable": False, "missing": True}
    x1 = (ca - cl) / ta
    x2 = re / ta
    x3 = ebit / ta

    is_mfg = sic is not None and 2000 <= sic <= 3999
    if is_mfg and market_cap and market_cap > 0:
        x4 = market_cap / tl
        x5 = (latest.get("revenue") or 0) / ta
        z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
        model_variant, safe_cut, distress_cut = "altman_z_original_mfg", 2.99, 1.81
        components = {"x1_wc": round(x1, 4), "x2_re": round(x2, 4), "x3_ebit": round(x3, 4),
                      "x4_market_equity": round(x4, 4), "x5_turnover": round(x5, 4)}
    else:
        x4 = eq / tl
        z = 3.25 + 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
        model_variant, safe_cut, distress_cut = "altman_zpp_book", 2.6, 1.1
        components = {"x1_wc": round(x1, 4), "x2_re": round(x2, 4),
                      "x3_ebit": round(x3, 4), "x4_book_equity": round(x4, 4)}
    zone = "safe" if z >= safe_cut else ("grey" if z >= distress_cut else "distress")
    return {
        "z_score": round(z, 2), "zone": zone, "model_variant": model_variant,
        "applicable": True, "safe_cut": safe_cut, "distress_cut": distress_cut,
        "components": components,
    }


def compute_fscore_us(metrics: Dict[str, List[Dict[str, Any]]],
                      is_financial: bool = False) -> Dict[str, Any]:
    """Piotroski F-Score (0~9) — US-GAAP, 연간 시계열 2년 직접 비교.

    수익성 4: F1 ROA>0 / F2 OCF>0 / F3 ΔROA>0 / F4 OCF>순이익(발생주의 품질)
    레버리지·유동성 3: F5 Δ레버리지<0 / F6 Δ유동비율>0 / F7 신주 미발행
    효율성 2: F8 Δ매출총이익률>0 / F9 Δ자산회전율>0

    학술 원전: Piotroski (2000) — project_perplexity_q1_q6_batch Q1 검증.
    데이터 부재 기준 = 미가점 (0). 금융(SIC 6000-6499) = not_applicable.
    """
    if is_financial:
        return {"f_score": None, "applicable": False, "label": "금융 — F-Score 미적용 (CAMELS 별도)"}

    def two(key: str) -> Tuple[Optional[float], Optional[float]]:
        s = [r for r in (metrics.get(key) or [])
             if r.get("is_annual") and r.get("val") is not None]
        if len(s) >= 2:
            return s[-1]["val"], s[-2]["val"]
        return (s[-1]["val"] if s else None), None

    ni_t, ni_p = two("net_income")
    ta_t, ta_p = two("total_assets")
    ocf_t, _ = two("operating_cash_flow")
    ltd_t, ltd_p = two("long_term_debt")
    ca_t, ca_p = two("current_assets")
    cl_t, cl_p = two("current_liabilities")
    gp_t, gp_p = two("gross_profit")
    rev_t, rev_p = two("revenue")
    sh_t, sh_p = two("diluted_shares")

    def _ratio(a, b):
        return (a / b) if (a is not None and b not in (None, 0)) else None

    score = 0
    passed: List[str] = []
    roa_t, roa_p = _ratio(ni_t, ta_t), _ratio(ni_p, ta_p)
    if roa_t is not None and roa_t > 0:
        score += 1; passed.append("F1_roa_pos")
    if ocf_t is not None and ocf_t > 0:
        score += 1; passed.append("F2_ocf_pos")
    if roa_t is not None and roa_p is not None and roa_t > roa_p:
        score += 1; passed.append("F3_droa_pos")
    if ocf_t is not None and ni_t is not None and ocf_t > ni_t:
        score += 1; passed.append("F4_accrual")
    lev_t, lev_p = _ratio(ltd_t, ta_t), _ratio(ltd_p, ta_p)
    if lev_t is not None and lev_p is not None and lev_t < lev_p:
        score += 1; passed.append("F5_dleverage_neg")
    cr_t, cr_p = _ratio(ca_t, cl_t), _ratio(ca_p, cl_p)
    if cr_t is not None and cr_p is not None and cr_t > cr_p:
        score += 1; passed.append("F6_dcurrent_pos")
    if sh_t is not None and sh_p is not None and sh_t <= sh_p:
        score += 1; passed.append("F7_no_dilution")
    gm_t, gm_p = _ratio(gp_t, rev_t), _ratio(gp_p, rev_p)
    if gm_t is not None and gm_p is not None and gm_t > gm_p:
        score += 1; passed.append("F8_dgross_pos")
    at_t, at_p = _ratio(rev_t, ta_t), _ratio(rev_p, ta_p)
    if at_t is not None and at_p is not None and at_t > at_p:
        score += 1; passed.append("F9_dturnover_pos")

    grade = "strong" if score >= 7 else ("weak" if score <= 3 else "mid")
    return {"f_score": score, "applicable": True, "grade": grade, "passed": passed}


# Lynch cyclical SIC (US) — 업황 민감 산업 (석유/광물/철강/자동차/항공/반도체/화학/건설).
# Lynch One Up On Wall Street 정성 정의 정합. 보수적 targeted set (명백 cyclical 만).
_CYCLICAL_SIC_RANGES = [
    (1000, 1099), (1200, 1499),   # 금속/광물 채굴
    (1300, 1399), (2900, 2999),   # 석유/가스 추출·정제
    (1500, 1799),                 # 건설
    (2400, 2499), (2600, 2699),   # 목재/제지
    (2800, 2829), (2850, 2899),   # 산업 화학·플라스틱 (제약 2830-2836 / 소비재 2840-2849 제외 — 방어주)
    (3300, 3399),                 # 1차 금속 (철강)
    (3500, 3599),                 # 산업 기계
    (3670, 3679),                 # 반도체
    (3710, 3799),                 # 자동차/항공/운송장비
    (4400, 4700),                 # 운송 (항공/해운)
]


def _is_cyclical_sic(sic: Optional[int]) -> bool:
    if sic is None:
        return False
    return any(lo <= sic <= hi for lo, hi in _CYCLICAL_SIC_RANGES)


def compute_lynch_us(revenue_growth_pct: Optional[float], market_cap: Optional[float] = None,
                     div_yield_pct: Optional[float] = None,
                     sic: Optional[int] = None) -> Dict[str, Any]:
    """Peter Lynch 6-category classifier — US calibration (USD 임계 + SIC cyclical).

    Lynch *One Up On Wall Street* 정성 정의:
      Fast Grower  = 20~25% 고성장 (소·중형 선호)  → rg ≥ 20%
      Stalwart     = 10~12% 안정 성장 대형주        → 8 ≤ rg < 20% & 대형(≥ $10B)
      Slow Grower  = 저성장 + 배당                  → rg < 8%
      Cyclical     = 업황 민감 (SIC 우선 판별)
    threshold = Lynch 원전 range 기반 자체 운영 선택 (한국판 lynch_classifier.py 와 동일 철학,
    USD/SIC calibration). market_cap/div_yield/sic = portfolio.json wire (SEC 스냅샷 부재분).
    """
    rg = revenue_growth_pct
    if rg is None:
        return {"lynch_class": None, "label": "데이터 부족", "applicable": False}

    if _is_cyclical_sic(sic):
        cls, label, summary = "CYCLICAL", "Cyclical", "업황 민감 (SIC)"
    elif rg >= 20:
        cls, label, summary = "FAST_GROWER", "Fast Grower", "매출 20%+ 고성장"
    elif rg >= 8:
        if market_cap and market_cap >= 10e9:
            cls, label, summary = "STALWART", "Stalwart", "안정 성장 8~20% 대형주"
        else:
            cls, label, summary = "FAST_GROWER", "Fast Grower", "중간 성장 소·중형"
    else:  # rg < 8
        if div_yield_pct and div_yield_pct >= 2.0:
            cls, label, summary = "SLOW_GROWER", "Slow Grower", "저성장 배당주"
        else:
            cls, label, summary = "SLOW_GROWER", "Slow Grower", "저성장"
    return {"lynch_class": cls, "label": label, "summary": summary, "applicable": True,
            "inputs": {"revenue_growth_pct": rg, "market_cap": market_cap,
                       "div_yield_pct": div_yield_pct, "sic": sic}}


def compute_derived(
    metrics: Dict[str, List[Dict[str, Any]]],
    is_financial: bool = False,
    external: Optional[Dict[str, Any]] = None,
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

    # v0.4 — Altman Z (US). 제조업+market_cap → 원본 Z, 그 외 → Z'' 장부가.
    ext = external or {}
    _ta = _latest_annual_val("total_assets")
    _tl = _latest_annual_val("total_liabilities")
    # 총부채 fallback = 총자산 - 자기자본 (회계 항등식 — Liabilities tag 미보고 TMO/DIS 등).
    if _tl is None and _ta is not None and eq is not None:
        _tl = _ta - eq
    out["altman_z"] = compute_altman_z_us({
        "total_assets": _ta,
        "current_assets": _latest_annual_val("current_assets"),
        "current_liabilities": _latest_annual_val("current_liabilities"),
        "retained_earnings": _latest_annual_val("retained_earnings"),
        # EBIT proxy: 영업이익 우선, 부재(OperatingIncomeLoss 미보고 — XOM/에너지) 시 세전이익 fallback.
        "operating_income": op_v if op_v is not None else ptx_v,
        "stockholders_equity": eq,
        "total_liabilities": _tl,
        "revenue": rev_v,
    }, is_financial=is_financial, market_cap=ext.get("market_cap"), sic=ext.get("sic"))

    # v0.4 — Piotroski F-Score (US-GAAP, 시계열 2년).
    out["fscore"] = compute_fscore_us(metrics, is_financial=is_financial)

    # v0.4 — Lynch 6-category (market_cap/div/sic = portfolio wire).
    out["lynch"] = compute_lynch_us(
        out.get("revenue_yoy_pct_annual"),
        market_cap=ext.get("market_cap"), div_yield_pct=ext.get("div_yield"), sic=ext.get("sic"))

    return out


def build_ticker_snapshot(
    ticker: str, cik: int, history_quarters: int = 8, history_years: int = 5,
    market_cap: Optional[float] = None, div_yield: Optional[float] = None,
) -> Dict[str, Any]:
    """단일 ticker 의 표준화 + 시계열 + 파생 snapshot.

    market_cap / div_yield = portfolio.json wire (SEC 스냅샷 부재분, Lynch/원본 Altman 입력).

    Returns: {ticker, meta, series_annual, series_quarterly, derived, fetched_at, _errors}.
    """
    raw = fetch_all_metrics(cik)
    if "_error" in raw:
        return {"ticker": ticker, "_error": raw["_error"], "fetched_at": raw.get("fetched_at")}

    metrics = raw["metrics"]
    meta = raw["meta"]
    external = {"market_cap": market_cap, "div_yield": div_yield, "sic": meta.get("sic")}
    out: Dict[str, Any] = {
        "ticker": ticker,
        "meta": meta,
        "fetched_at": raw["fetched_at"],
        "series_annual": {},
        "series_quarterly": {},
        "derived": compute_derived(metrics, is_financial=bool(meta.get("is_financial")),
                                   external=external),
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
