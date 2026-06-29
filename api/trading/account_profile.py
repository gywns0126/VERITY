"""account_profile — 계좌 유형(일반/ISA) 인지 + 세제·적격성 기반 전략 라벨.

VERITY 전용 (AlphaNest = 공개 정보사이트, 계좌연동 X). 추천을 적합 계좌 유형으로
라우팅하는 표시용 라벨 (자동주문 X). 현 venue = KIS (일반·ISA 모두).

배경: 2026-06-19 Toss Open API 평가 → 매매(2027) 외 기능 우위 없음(실시간은 기존 KIS
WebSocket 이 우위, 캔들 동급) → Toss API 도입 원복, 기존 KIS 유지. 본 모듈의 일반/ISA
세제 라우팅 라벨만 무료 자산으로 존치 (Toss API 불필요). 2027 매매 단계서 Toss 소수점
재검토 ([[project_toss_api_watch_2026_06_08]]).

🔒 ISA = 전 금융기관 1인 1계좌 ([[project_kis_isa_constraint]]), KIS 보유.

세제 사실 (2026, 웹 cross-source 검증):
- 일반(위탁): KR 상장주식 양도세 0% (대주주 제외, 금투세 폐지 2024-12-10) ·
  해외(미국) 양도세 22% (250만 기본공제, 3억 초과분 27.5%) ·
  배당 분리과세 15.4%~ (2026 개정) · 증권거래세 0.20% (KR, 2026).
- ISA (조특법 §91의18): 국내상장 상품만 (주식/국내상장 해외ETF/펀드/ELS; 미국 직접투자 불가) ·
  비과세 한도 초과분 9.9% 저율 분리과세 (지방세 포함) · 3년 주기 손익통산 ·
  납입 연 2000만/총 1억 + 비과세 일반형 200만/서민형 400만 (상향 개정 미통과 = 현행 유지) ·
  의무유지 3년.

✅ 확정 2026-06-19 (Perplexity + KPMG 2025 세법개정 cross-source): ISA 한도 상향 개정은
   미통과 = 현행 유지. 대주주 시총 50억→10억 환원은 통과(2025-12)했으나 시행령 시행일
   이후 양도분부터 — 공포일 국세청 공고 확인 필요. 고배당 선택 분리과세 특례 신설(2026~2028).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Broker(str, Enum):
    KIS = "kis"
    TOSS = "toss"


class AccountType(str, Enum):
    GENERAL = "general"   # 위탁/일반계좌
    ISA = "isa"           # 개인종합자산관리계좌


class Market(str, Enum):
    KR = "kr"
    US = "us"


# ── 세제 상수 (2026 시행값, Perplexity + KPMG 2025 세법개정 cross-source 확정 2026-06-19) ──
# ⚠️ 세무 전문가 조언 대체 아님 — 실제 납세 판단 시 세무사 확인. 관측/표시 보조용.
KR_CAPITAL_GAINS_TAX = 0.0          # 국내 상장주식 양도세 = 비과세 (일반 개인, 금투세 폐지 2024-12-10)
KR_MAJOR_SHAREHOLDER_AMOUNT = 1_000_000_000  # 대주주 종목당 시총 기준 = 10억 (50억서 환원)
#   ⚠️ 시행령 시행일(2026 상반기 예상) 이후 양도분부터. 공포일 = 국세청 공고 확인 필요.
KR_TRANSACTION_TAX = 0.0020         # 증권거래세 KOSPI/KOSDAQ (농특세 포함, 2026 0.15%→0.20% 환원)
US_CAPITAL_GAINS_TAX = 0.22         # 해외주식 양도세 (과표 3억 이하; 소득세20%+지방세2%)
US_CAPITAL_GAINS_TAX_HIGH = 0.275   # 과표 3억 초과분 (소득세25%+지방세2.5%)
US_CAPITAL_GAINS_HIGH_THRESHOLD = 300_000_000
US_CAPITAL_GAINS_DEDUCTION = 2_500_000  # 해외 양도소득 기본공제 (연)
DIVIDEND_TAX_DEFAULT = 0.154        # 배당 분리과세 (2천만 이하; 소득세14%+지방세1.4%)
FINANCIAL_INCOME_AGGREGATE_THRESHOLD = 20_000_000  # 금융소득종합과세 합산 기준 (초과 시 종합과세)

# ISA (조세특례제한법 §91의18) — 2026 시행값. 상향 개정안(연4000만/총2억, 비과세500/1000)은
# 2025-12 세법개정에 끝내 미포함 = 미시행 → 현행 유지 확정 (VERIFIED).
ISA_EXCESS_TAX = 0.099             # 비과세 한도 초과분 저율 분리과세 (지방세 포함)
ISA_CONTRIB_LIMIT_ANNUAL = 20_000_000   # 납입 연 한도 (현행 유지)
ISA_CONTRIB_LIMIT_TOTAL = 100_000_000   # 납입 5년 총 한도 (현행 유지)
ISA_LOCKUP_YEARS = 3
ISA_TAX_FREE_GENERAL = 2_000_000    # 일반형 비과세 한도 (현행 유지)
ISA_TAX_FREE_SERVANT = 4_000_000    # 서민형 비과세 한도 (현행 유지)
ISA_TAX_FREE_VERIFIED = True        # 2026-06-19 Perplexity + KPMG cross-source 확정

# 고배당기업 배당소득 선택적 분리과세 특례 (조특법 §104의27 신설, 2026~2028 한시).
# 요건: 배당성향 40%↑ OR (25%↑ AND 전전 사업연도 대비 배당 10%↑ 증가). 신청 필요(자동 X).
# 펀드/리츠/ETF 제외. 종합과세 회피용 — 고배당소득(>2천만) 구간에서 일반계좌 이점 발생.
HIGH_DIVIDEND_SEPARATE_TAX = {  # 과표 상한: 소득세율 (지방세 별도)
    20_000_000: 0.14,
    300_000_000: 0.20,
    5_000_000_000: 0.25,
    float("inf"): 0.30,
}

# ── 브로커별 지원 계좌 유형 (API 검증) ────────────────────────────────
BROKER_ACCOUNT_SUPPORT = {
    Broker.KIS: {AccountType.GENERAL, AccountType.ISA},
    Broker.TOSS: {AccountType.GENERAL},   # ISA 미지원 (enum 부재)
}


@dataclass(frozen=True)
class AccountRoute:
    account_type: AccountType
    broker: Broker
    rationale: str


def is_eligible(account_type: AccountType, market: Market, is_kr_listed: bool) -> bool:
    """해당 계좌가 이 자산을 담을 수 있는가.

    ISA = 국내상장 상품만 (미국 직접투자 불가 — 국내상장 해외ETF 는 is_kr_listed=True).
    일반 = 제약 없음.
    """
    if account_type == AccountType.ISA:
        return is_kr_listed
    return True


def recommended_account(
    market: Market,
    *,
    is_kr_listed: bool = True,
    is_high_dividend: bool = False,
    isa_capacity_left: bool = True,
    has_isa: bool = True,
) -> AccountRoute:
    """추천 종목을 적합 계좌로 라우팅 + 세제 근거.

    전략 원칙 (검증된 세제 기반, venue = KIS):
    - 미국 직접투자 → 일반. ISA 불가(국내상장만), 일반에서 양도세 22%/250만공제.
    - KR 고배당 + ISA 여력 → ISA. 일반 배당 15.4% vs ISA 비과세/9.9% 이점.
    - KR 차익형 → 일반. KR 양도세 이미 0% 라 ISA 이점 미미 → ISA 여력은 배당용 보존.
    """
    # 미국/해외 직접투자: ISA 불가 → 일반
    if market == Market.US and not is_kr_listed:
        return AccountRoute(
            AccountType.GENERAL, Broker.KIS,
            "미국 직접투자 — ISA 불가(국내상장만), 일반계좌 양도세 22%(250만공제)",
        )

    # 국내상장 자산
    if is_high_dividend and has_isa and isa_capacity_left:
        return AccountRoute(
            AccountType.ISA, Broker.KIS,
            "고배당 — ISA 비과세 한도/초과분 9.9% 가 일반 배당 15.4% 대비 유리",
        )

    # KR 차익형: 일반 양도세 0% 라 ISA 이점 없음 → 일반. ISA 여력은 배당용으로 보존.
    return AccountRoute(
        AccountType.GENERAL, Broker.KIS,
        "KR 차익형 — 일반 양도세 0%(대주주 제외)로 ISA 이점 미미, ISA 여력은 배당용 보존",
    )


# ── 추천 라우팅 부착 (표시용) ─────────────────────────────────────────
HIGH_DIVIDEND_YIELD_THRESHOLD = 3.0   # div_yield(%) ≥ → 고배당 (ISA 배당 절세 라우팅 기준)
HAS_KIS_ISA = True   # 사용자 KIS ISA 보유 (확정 2026-06-19). 해지 시 False → 고배당도 일반.
_US_MARKETS = {"US", "USA", "NASDAQ", "NYSE", "AMEX", "NYSEARCA", "미국"}


def _infer_market(rec: dict) -> Market:
    """추천 dict 에서 시장 추론. currency("USD") 1순위, market 라벨 2순위, 기본 KR."""
    if str(rec.get("currency", "")).upper() == "USD":
        return Market.US
    if str(rec.get("market", "")).upper() in _US_MARKETS:
        return Market.US
    return Market.KR


def annotate_recommendation(rec: dict) -> dict:
    """추천 dict 에 적합 계좌 라우팅을 부착 (관측/표시용, 자동주문 X).

    실 추천 필드에서 파생: currency/market → 시장, div_yield(%) → 고배당.
    ISA 보유 = HAS_KIS_ISA (모듈 상수). 반환: rec 사본 + account_route.
    """
    market = _infer_market(rec)
    try:
        div_yield = float(rec.get("div_yield", 0) or 0)
    except (TypeError, ValueError):
        div_yield = 0.0
    route = recommended_account(
        market,
        is_kr_listed=(market == Market.KR),
        is_high_dividend=div_yield >= HIGH_DIVIDEND_YIELD_THRESHOLD,
        isa_capacity_left=bool(rec.get("isa_capacity_left", True)),
        has_isa=HAS_KIS_ISA,
    )
    out = dict(rec)
    out["account_route"] = {
        "account_type": route.account_type.value,
        "broker": route.broker.value,
        "rationale": route.rationale,
    }
    return out


def annotate_recommendations(recs):
    """추천 리스트 일괄 라우팅 부착. list 아니면 원본 그대로 반환 (안전)."""
    if not isinstance(recs, list):
        return recs
    return [annotate_recommendation(r) if isinstance(r, dict) else r for r in recs]
