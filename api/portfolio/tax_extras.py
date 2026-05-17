"""
tax_extras — 한국 세제 보강 산식 (Perplexity 2026-05-17 자문 정합).

3 영역:
1. **high_div_special_tax** (2026~2029 한시) — 고배당 분리과세 특례
   조건: 배당성향 ≥40% 또는 (≥25% + 전년 대비 10% 증액)
   임계: 2000만 / 3억 / 50억 → 15.4% / 22% / 27.5% / 33%
   참조: pwc.com/kr issue-brief one-point-tax-11

2. **settlement_date_kst** — 결제일 변환 (T+2 한국 시간 기준)
   - KR: 약정일 + 2 영업일
   - US: 약정일 + 1 영업일 (2024-05-28 T+1 단축) + 시차 → T+2 한국 시간
   - 연말 cut-off: 12월 결제일 ≤ 12월 31일 → 당해 양도세, 익년 결제 = 다음 해 귀속
   참조: 소득세법, 미국 SEC Rule 15c6-1

3. **comprehensive_income_tax_estimate** — 종합과세 누진 추정 (자본 5억+ 진입 시)
   - 금융소득 2000만 초과분 = 종합과세 (6/15/24/35/38/40/42/45%)
   - 누진공제 별도 계산
   - VAMS 자본 + 배당수익률 → 종합과세 진입 임계 시뮬

wiring: 현재 dead code (호출자 없음). Tier 3+ 자본 진입 / Brain v6 sprint 시 호출.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Literal


# ─────────────────────────────────────────────────────────────
# 1. 고배당 분리과세 특례 (2026~2029 한시)
# ─────────────────────────────────────────────────────────────

# 적용 한시 기간 — 2026.1.1 ~ 2029.12.31
HIGH_DIV_SPECIAL_START_YEAR = 2026
HIGH_DIV_SPECIAL_END_YEAR = 2029

# 분리과세 누진 구간 (지방세 포함)
HIGH_DIV_BRACKETS = [
    (20_000_000, 0.154),       # ≤ 2,000만: 15.4%
    (300_000_000, 0.22),       # ≤ 3억: 22%
    (5_000_000_000, 0.275),    # ≤ 50억: 27.5%
    (float("inf"), 0.33),       # > 50억: 33%
]


@dataclass
class HighDivQualification:
    """기업의 고배당 분리과세 자격 판정."""
    payout_ratio: float                # 배당성향 (배당/순익)
    payout_ratio_prev_year: float = 0  # 전년 배당성향
    dividend_growth_pct: float = 0     # 전년 대비 현금배당 증액 (%)


def is_high_div_qualified(q: HighDivQualification) -> bool:
    """고배당 분리과세 자격 — 두 조건 중 하나 충족."""
    # 조건 1: 배당성향 ≥ 40%
    if q.payout_ratio >= 0.40:
        return True
    # 조건 2: 배당성향 ≥ 25% AND 전년 대비 현금배당 ≥ 10% 증액
    if q.payout_ratio >= 0.25 and q.dividend_growth_pct >= 10.0:
        return True
    return False


def high_div_special_tax(dividend_krw: float, year: Optional[int] = None) -> float:
    """누진 분리과세 (지방세 포함). 한시 기간 외에는 단일 15.4% fallback.

    Args:
        dividend_krw: 연간 배당 합산 금액 (KRW)
        year: 적용 연도 (기본 = 현재). 한시 기간 외면 일반 분리과세.
    """
    if year is None:
        year = date.today().year
    if year < HIGH_DIV_SPECIAL_START_YEAR or year > HIGH_DIV_SPECIAL_END_YEAR:
        return dividend_krw * 0.154  # 일반 분리과세 fallback

    tax = 0.0
    remaining = dividend_krw
    prev_cap = 0.0
    for cap, rate in HIGH_DIV_BRACKETS:
        if remaining <= 0:
            break
        bracket_size = cap - prev_cap
        in_bracket = min(remaining, bracket_size)
        tax += in_bracket * rate
        remaining -= in_bracket
        prev_cap = cap
    return tax


# ─────────────────────────────────────────────────────────────
# 2. 결제일 변환 (T+2 한국 시간 기준) — pykrx 영업일 dynamic fetch
# ─────────────────────────────────────────────────────────────

# 한국 공휴일 fallback — pykrx 실패 시만 사용 (network/data 미가용)
_KR_HOLIDAYS_FALLBACK = {
    date(2026, 1, 1), date(2026, 1, 2),
    date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),  # 설날
    date(2026, 3, 1),
    date(2026, 5, 5),
    date(2026, 5, 25),
    date(2026, 6, 6),
    date(2026, 8, 15),
    date(2026, 9, 24), date(2026, 9, 25), date(2026, 9, 26),  # 추석
    date(2026, 10, 3),
    date(2026, 10, 9),
    date(2026, 12, 25),
    date(2026, 12, 31),
}

# 영업일 list cache — pykrx 호출 비용 큼, 프로세스 lifetime cache.
_TRADING_DAYS_CACHE: dict[int, list[date]] = {}


def get_kr_trading_days(year: int) -> list[date]:
    """KR 거래소 영업일 list (pykrx OHLCV 기반 동적 fetch + cache).

    fallback: pykrx 실패 / 미래 연도 데이터 없음 시 → 평일 - _KR_HOLIDAYS_FALLBACK 계산.
    """
    if year in _TRADING_DAYS_CACHE:
        return _TRADING_DAYS_CACHE[year]

    days: list[date] = []
    try:
        from pykrx import stock
        df = stock.get_market_ohlcv_by_date(
            f"{year}0101", f"{year}1231", "005930"
        )
        if len(df) > 0:
            days = [d.date() for d in df.index]
    except Exception:
        days = []

    # fallback: pykrx 실패 또는 미래 연도 → 평일 - fallback holidays
    if not days:
        cur = date(year, 1, 1)
        end = date(year, 12, 31)
        while cur <= end:
            if cur.weekday() < 5 and cur not in _KR_HOLIDAYS_FALLBACK:
                days.append(cur)
            cur = cur + timedelta(days=1)

    _TRADING_DAYS_CACHE[year] = days
    return days


def _add_business_days_from_list(d: date, n: int, trading_days: list[date]) -> Optional[date]:
    """trading_days list 에서 d 이후 n번째 영업일. 데이터 부족 시 None."""
    future = [td for td in trading_days if td > d]
    if len(future) < n:
        return None
    return future[n - 1]


def settlement_date_kst(
    trade_date: date,
    market: Literal["KR", "US"] = "KR",
    trading_days: Optional[list[date]] = None,
) -> date:
    """약정일 → 결제일 (한국 시간 기준).

    KR: 약정일 + 2 영업일 (T+2)
    US: 약정일 + 1 영업일 (2024.5.28 T+1) + 1일 시차 = 한국 시간 T+2 (보수적 근사)

    pykrx 영업일 dynamic fetch. cross-year cut-off 정확 (당해 + 익년 list union).
    """
    if trading_days is None:
        current = get_kr_trading_days(trade_date.year)
        nxt = get_kr_trading_days(trade_date.year + 1)
        trading_days = current + nxt

    settled = _add_business_days_from_list(trade_date, 2, trading_days)
    if settled is None:
        # data 부족 → 평일 기반 fallback (보수적)
        cur = trade_date
        added = 0
        while added < 2:
            cur = cur + timedelta(days=1)
            if cur.weekday() < 5:
                added += 1
        return cur
    return settled


def is_year_end_settled(trade_date: date, year: Optional[int] = None) -> bool:
    """연말 매매가 당해 연도 결제 완료되는지 판정.

    예: 2025.12.29 매매 → 결제일 12.30 → True (당해 양도세 귀속)
        2025.12.30 매매 → 결제일 2026.1.2 → False (익년 귀속)

    한국 거래소 12.31 = 증시 휴장. 12.30 가 마지막 영업일.
    """
    if year is None:
        year = trade_date.year
    settled = settlement_date_kst(trade_date, "KR")
    return settled.year == year


# ─────────────────────────────────────────────────────────────
# 3. 종합과세 누진 추정 (자본 5억+ 진입 시)
# ─────────────────────────────────────────────────────────────

# 2026 종합소득세 누진 구간 (지방세 별도 — 산출 후 ×1.1)
# 출처: 소득세법 §55
COMPREHENSIVE_INCOME_BRACKETS = [
    (14_000_000, 0.06, 0),
    (50_000_000, 0.15, 1_080_000),
    (88_000_000, 0.24, 5_220_000),
    (150_000_000, 0.35, 14_900_000),
    (300_000_000, 0.38, 19_400_000),
    (500_000_000, 0.40, 25_400_000),
    (1_000_000_000, 0.42, 35_400_000),
    (float("inf"), 0.45, 65_400_000),
]

COMPREHENSIVE_THRESHOLD_KRW = 20_000_000  # 연 2000만 초과 시 종합과세
LOCAL_TAX_MULTIPLIER = 1.10               # 지방소득세 10%


def comprehensive_income_tax_estimate(
    total_income_krw: float,
    other_income_krw: float = 0,
) -> dict:
    """종합과세 누진 추정 (배당 + 기타 소득 합산).

    한국 세법: 금융소득 (이자 + 배당) ≤ 2000만 = 분리과세 종결.
    > 2000만 = 종합과세 (전체가 종합과세 산입, 다만 2000만 이하분은 14% 산출 비교 → 큰 값).

    Args:
        total_income_krw: 금융소득 (이자 + 배당) 연 합산
        other_income_krw: 기타 종합과세 소득 (근로/사업/연금 등)

    Returns:
        {
            "is_comprehensive": bool,        # 종합과세 전환 여부
            "separate_tax_only": float,      # 분리과세만 적용 시 (15.4%)
            "comprehensive_tax": float,      # 종합과세 적용 시 (지방세 포함)
            "final_tax": float,              # 둘 중 큰 값 (비교 과세 원칙)
            "marginal_rate_pct": float,      # 한계세율
            "notes": [str],
        }
    """
    is_comprehensive = total_income_krw > COMPREHENSIVE_THRESHOLD_KRW
    separate_tax = total_income_krw * 0.154
    notes = []

    if not is_comprehensive:
        return {
            "is_comprehensive": False,
            "separate_tax_only": round(separate_tax, 0),
            "comprehensive_tax": 0,
            "final_tax": round(separate_tax, 0),
            "marginal_rate_pct": 15.4,
            "notes": ["연 2000만 이하 → 분리과세 종결 (사용자 신고 X)"],
        }

    # 종합과세: 2000만 이하분은 14% 산출, 초과분만 누진
    # 한국 세법: 2000만 이하 = 14% 단순 산출, 초과분만 종합소득에 합산
    base_2000 = COMPREHENSIVE_THRESHOLD_KRW * 0.14
    excess = total_income_krw - COMPREHENSIVE_THRESHOLD_KRW
    comprehensive_base = other_income_krw + excess

    # 누진 산출
    tax_excess = 0.0
    marginal_rate = 0.06
    for cap, rate, deduction in COMPREHENSIVE_INCOME_BRACKETS:
        if comprehensive_base <= cap:
            tax_excess = comprehensive_base * rate - deduction
            marginal_rate = rate
            break

    # 분리과세 산출 (비교 기준)
    separate_compare = base_2000 + excess * 0.14  # 단순 14% 비교용

    # 비교 과세: 둘 중 큰 값
    comprehensive_total = max(base_2000 + tax_excess, separate_compare)
    comprehensive_total *= LOCAL_TAX_MULTIPLIER  # 지방세 포함

    notes.append(f"금융소득 {total_income_krw:,.0f}원 > 2000만 → 종합과세 전환")
    notes.append(f"한계세율 {marginal_rate*100:.0f}% (지방세 별도, 실효 {marginal_rate*110:.1f}%)")
    if other_income_krw > 0:
        notes.append(f"기타 종합소득 {other_income_krw:,.0f}원 합산")

    return {
        "is_comprehensive": True,
        "separate_tax_only": round(separate_tax, 0),
        "comprehensive_tax": round(comprehensive_total, 0),
        "final_tax": round(comprehensive_total, 0),
        "marginal_rate_pct": round(marginal_rate * 100, 1),
        "notes": notes,
    }


def estimate_comprehensive_entry_capital(
    dividend_yield_pct: float = 4.0,
    threshold_krw: float = COMPREHENSIVE_THRESHOLD_KRW,
) -> float:
    """배당수익률 가정 시 종합과세 진입 자본 임계.

    예: 4% 배당 → 5억 진입 / 6% → 3.33억 / 8% (REIT) → 2.5억
    """
    if dividend_yield_pct <= 0:
        return float("inf")
    return threshold_krw / (dividend_yield_pct / 100.0)
