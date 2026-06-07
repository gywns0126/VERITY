"""
Hard Floor 룰 — Phase 2-A (2026-05-01) + Stage 1 확장 (2026-06-07)

품질 floor (코어 종목 면제):
  Rule 1 — 페니스톡:
    KR market_cap < 50억원 (2026-06-07 유지 — 소형 비효율 엣지 보존)
    US market_cap < $500M (2026-06-07 spec 정합, 옛 $100M)
  Rule 2 — 관리종목/투자경고/거래정지
  Rule 3 — 일평균 거래대금 부족:
    KR < 1억원
    US < $10M (2026-06-07 spec 정합, 옛 $1M)

구조적(instrument-type) 제외 (코어도 항상 적용 — 보통주 아니면 분석 대상 X):
  Rule 4 — 우선주: KR 6자리 코드 끝자리 != '0'
  Rule 5 — 외국주권: KR 6자리 코드 첫자리 == '9'
  Rule 6 — SPAC: 종목명 '기업인수목적|스팩|SPAC' (ipo_scout 패턴 재사용)

is_core=True = 품질 floor(Rule 1-3) 면제, 단 구조적 제외(Rule 4-6)는 적용
(코어가 구조적 매치 시 curation 오류 경보 로깅).

UNIVERSE_FUNNEL_REFORM_PLAN_v0.2 §2 Stage 1 정합. 잔여(Phase A.2): 금융업
(KRX 업종 collector 필요) / 신규상장<6m(krx_ipo_collector join) / 자본잠식(DART).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# 임계값 (원/USD) — 변경 = RULE 7 자기 임계, PM 결정 trail 의무
HARD_FLOOR_MIN_MARKET_CAP_KR = 5_000_000_000   # 50억원 (2026-06-07 PM: 유지)
HARD_FLOOR_MIN_MARKET_CAP_US = 500_000_000     # $500M (2026-06-07 PM: spec 정합)
HARD_FLOOR_MIN_TRADING_VALUE_KR = 100_000_000  # 1억원
HARD_FLOOR_MIN_TRADING_VALUE_US = 10_000_000   # $10M (2026-06-07 PM: spec 정합)

# 구조적 제외 — SPAC 종목명 패턴 (ipo_scout._SPAC_PAT 재사용, 검증된 패턴)
_SPAC_NAME_PAT = re.compile(r"기업인수목적|스팩|SPAC", re.IGNORECASE)


def _kr_digit_code(ticker: object) -> str:
    """ticker 에서 숫자만 추출 (universe_builder 가 digit-strip 한 6자리 KR 코드)."""
    return "".join(ch for ch in str(ticker or "") if ch.isdigit())


def is_kr_preferred(ticker: object) -> bool:
    """KR 우선주 — 6자리 단축코드 끝자리 != '0'. 보통주=0 / 구형우선주=5·7·9 / 신형=알파벳.

    휴리스틱 한계: universe_builder 가 코드를 digit-strip 하므로 구형(숫자 5/7/9)만 신뢰.
    신형우선주(K 등 알파)는 strip 으로 mangle 가능 → 일부 누락. 드물게 끝자리 비-0 보통주
    false-positive 가능 (Perplexity '제로'는 과장) → 제외 건수 로깅으로 surface.
    """
    code = _kr_digit_code(ticker)
    if len(code) < 6:
        return False
    return code[-1] != "0"


def is_kr_foreign(ticker: object) -> bool:
    """KR 외국주권(외국기업 국내상장) — 6자리 코드 첫자리 == '9' (KRX 컨벤션)."""
    code = _kr_digit_code(ticker)
    if len(code) < 6:
        return False
    return code[0] == "9"


def is_spac(name: object) -> bool:
    """SPAC(기업인수목적회사) — 종목명 패턴. ipo_scout 검증 패턴 재사용.

    Perplexity 의 'ticker 첫자리 3/4' 규칙은 타 증권 충돌로 미채택 (RULE 10).
    """
    return bool(_SPAC_NAME_PAT.search(str(name or "")))


def apply_hard_floor(stock: dict) -> dict:
    """자동 제외 룰 적용. 코어 종목은 면제.

    입력 dict 에 hard_floor_metadata 추가하여 반환 (in-place 변형 + return).

    Returns:
        stock dict + {
          "hard_floor_metadata": {
            "passes": bool,
            "reasons": list[str],
            "applied_rules": list[str],
            "computed_at": ISO,
          }
        }
    """
    is_core = bool(stock.get("is_core"))
    is_us = stock.get("currency") == "USD"
    ticker = stock.get("ticker", "")
    name = stock.get("name", "")

    reasons: list[str] = []
    applied: list[str] = []

    # ── 구조적 제외 (Rule 4-6) — instrument type. 코어 면제 없음 ──
    structural: list[str] = []
    if not is_us:
        # 우선주/외국주권 = KR 6자리 코드 규칙 (US 심볼 미적용)
        applied.append("rule_4_preferred")
        if is_kr_preferred(ticker):
            structural.append(f"preferred_stock: ticker={ticker}")
        applied.append("rule_5_foreign")
        if is_kr_foreign(ticker):
            structural.append(f"foreign_stock: ticker={ticker}")
    applied.append("rule_6_spac")
    if is_spac(name):
        structural.append(f"spac: name={name!r}")

    # ── 품질 floor (Rule 1-3) ──
    # Rule 1 — 페니스톡 (시총)
    market_cap = stock.get("market_cap", 0) or 0
    threshold_cap = HARD_FLOOR_MIN_MARKET_CAP_US if is_us else HARD_FLOOR_MIN_MARKET_CAP_KR
    applied.append("rule_1_penny_stock")
    if market_cap < threshold_cap:
        reasons.append(
            f"penny_stock: market_cap={market_cap:,} < {threshold_cap:,}"
        )

    # Rule 2 — 관리종목/투자경고/거래정지
    applied.append("rule_2_alert_status")
    if stock.get("is_managed"):
        reasons.append(f"managed_stock: sect_tp={stock.get('sect_tp', '')!r}")
    if stock.get("is_suspended"):
        reasons.append("trading_suspended")

    # Rule 3 — 거래대금 부족
    trading_val = stock.get("avg_trading_value_30d", 0) or 0
    threshold_tv = (
        HARD_FLOOR_MIN_TRADING_VALUE_US if is_us else HARD_FLOOR_MIN_TRADING_VALUE_KR
    )
    applied.append("rule_3_low_trading_value")
    if trading_val < threshold_tv:
        reasons.append(
            f"low_trading_value: avg_30d={trading_val:,} < {threshold_tv:,}"
        )

    # ── 판정 ──
    if structural:
        # 구조적 제외 = 코어라도 항상 cut (보통주 아닌 instrument).
        if is_core:
            logger.warning(
                "[hard_floor] core 종목이 구조적 제외 매치 (curation 오류 의심): "
                f"ticker={ticker} name={name!r} → {structural}"
            )
        passes = False
        reasons = structural + reasons
    elif is_core:
        # 품질 floor 코어 면제 — 거래정지만 예외 (정지 종목은 코어라도 cut)
        if stock.get("is_suspended"):
            passes = False
            reasons.append("core_immune_except_suspended")
        else:
            passes = True
            reasons = ["core_immune"]
    else:
        passes = len(reasons) == 0

    stock["hard_floor_metadata"] = {
        "passes": passes,
        "reasons": reasons,
        "applied_rules": applied,
        "computed_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
    }
    return stock


def filter_hard_floor(stocks: list[dict]) -> list[dict]:
    """list 입력 helper — 룰 적용 후 통과 종목만 반환."""
    out = []
    for s in stocks:
        apply_hard_floor(s)
        if s.get("hard_floor_metadata", {}).get("passes", True):
            out.append(s)
    return out
