"""account_profile — 계좌 유형 인지 + 세제·적격성 기반 전략 배분 (하이브리드 2026-06-19).

VERITY 전용 (골든구스 = 공개 정보사이트, 계좌연동 X). KIS+Toss 이원화에서
일반(위탁) vs ISA 차이를 VERITY 가 자체 인지하고 추천을 적합 계좌로 라우팅.

🔒 계좌 토폴로지 제약 (검증 2026-06-19, 공식 OpenAPI 스펙):
- ISA = 전 금융기관 1인 1계좌 ([[project_kis_isa_constraint]]).
- Toss Open API accountType enum = BROKERAGE / OVERSEAS_DERIVATIVES /
  PENSION_SAVINGS / RESHORING_INVESTMENT (ISA 부재, 현재 BROKERAGE 만 노출)
  → ISA 는 KIS 전용, Toss 는 일반(위탁) 전용.

세제 사실 (2026, 웹 cross-source 검증):
- 일반(위탁): KR 상장주식 양도세 0% (대주주 제외, 금투세 폐지 2024-12-10) ·
  해외(미국) 양도세 22% (250만 기본공제, 3억 초과분 27.5%) ·
  배당 분리과세 15.4%~ (2026 개정) · 증권거래세 0.20% (KR, 2026).
- ISA: 국내상장 상품만 (주식/ETF/리츠/펀드 + 국내상장 해외ETF; 미국 직접투자 불가) ·
  순이익 비과세 한도 초과분 9.9% 저율 분리과세 (지방세 포함) · 3년 주기 손익통산 ·
  납입 연 4000만/총 2억 (2026 개편) · 의무유지 3년.

⚠️ UNVERIFIED — ISA 비과세 한도 = 일반형 200만/서민형 400만 (현행) vs 500만/1000만
   (개정안). Perplexity/금융위 확정 후 ISA_TAX_FREE_* 갱신 의무
   ([[feedback_perplexity_collaboration]]). 현재 보수적으로 현행값 사용 + verified=False.
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


# ── 세제 상수 (검증된 값) ─────────────────────────────────────────────
KR_CAPITAL_GAINS_TAX = 0.0          # 상장주식 양도세 (대주주 제외, ~금투세 폐지)
US_CAPITAL_GAINS_TAX = 0.22         # 해외주식 양도세 (3억 초과분 0.275)
US_CAPITAL_GAINS_DEDUCTION = 2_500_000  # 해외 양도소득 기본공제 (연)
DIVIDEND_TAX_DEFAULT = 0.154        # 배당 분리과세 (2천만 이하, 2026)
ISA_EXCESS_TAX = 0.099             # ISA 비과세 한도 초과분 저율 분리과세
ISA_CONTRIB_LIMIT_ANNUAL = 40_000_000   # 납입 연 한도 (2026 개편)
ISA_CONTRIB_LIMIT_TOTAL = 200_000_000   # 납입 총 한도
ISA_LOCKUP_YEARS = 3

# ⚠️ UNVERIFIED — 개정안 확정 전까지 현행값. verified=False (라우팅 결정엔 영향 적음).
ISA_TAX_FREE_GENERAL = 2_000_000    # 일반형 비과세 한도 (현행, 개정안 5,000,000?)
ISA_TAX_FREE_SERVANT = 4_000_000    # 서민형 비과세 한도 (현행, 개정안 10,000,000?)
ISA_TAX_FREE_VERIFIED = False

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

    전략 원칙 (검증된 세제 기반):
    - 미국 직접투자 → 일반(Toss). ISA 불가, 일반에서 양도세 22%/250만공제.
    - KR 고배당 + ISA 여력 → ISA(KIS). 일반 배당 15.4% vs ISA 비과세/9.9% 이점.
    - KR 차익형 → 일반. KR 양도세 이미 0% 라 ISA 이점 미미 → ISA 여력은 배당용 보존.
    """
    # 미국/해외 직접투자: ISA 불가 → 무조건 일반(Toss)
    if market == Market.US and not is_kr_listed:
        return AccountRoute(
            AccountType.GENERAL, Broker.TOSS,
            "미국 직접투자 — ISA 불가(국내상장만), 일반계좌 양도세 22%(250만공제)",
        )

    # 국내상장 자산
    if is_high_dividend and has_isa and isa_capacity_left:
        return AccountRoute(
            AccountType.ISA, Broker.KIS,
            "고배당 — ISA 비과세 한도/초과분 9.9% 가 일반 배당 15.4% 대비 유리",
        )

    # KR 차익형: 일반 양도세 0% 라 ISA 이점 없음 → 일반(Toss, 고빈도 거래 = Toss 원칙).
    # ISA 여력은 배당용으로 보존.
    return AccountRoute(
        AccountType.GENERAL, Broker.TOSS,
        "KR 차익형 — 일반 양도세 0%(대주주 제외)로 ISA 이점 미미, 고빈도=Toss·ISA 여력 보존",
    )


def annotate_recommendation(rec: dict) -> dict:
    """추천 dict 에 적합 계좌 라우팅을 부착 (관측/표시용, 자동주문 X).

    rec 기대 키: market("kr"|"us"), is_kr_listed(bool), is_high_dividend(bool).
    반환: rec 사본 + account_route {account_type, broker, rationale}.
    """
    market = Market(rec.get("market", "kr"))
    route = recommended_account(
        market,
        is_kr_listed=bool(rec.get("is_kr_listed", market == Market.KR)),
        is_high_dividend=bool(rec.get("is_high_dividend", False)),
        isa_capacity_left=bool(rec.get("isa_capacity_left", True)),
        has_isa=bool(rec.get("has_isa", True)),
    )
    out = dict(rec)
    out["account_route"] = {
        "account_type": route.account_type.value,
        "broker": route.broker.value,
        "rationale": route.rationale,
    }
    return out
