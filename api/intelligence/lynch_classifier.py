"""
Lynch 6분류 — 한국 KOSPI/KOSDAQ 기준 (2026).

근거:
  - 한국 GDP 2026 전망 1.9% (KDI/IMF/OECD)
  - KOSPI 상장사 평균 매출 성장 2024 +5.4%
  - Lynch 원전 Fast Grower = GDP 대비 10× 수준
  - Value-Up 프로그램 효과 (자사주 매입 + 소각 2.5배 / 4.5배 폭증)

데이터 한계 (한국 KIS):
  - revenue_growth: 단년 YoY (CAGR 3년 미수집 — 추후 DART 확장 시 보강)
  - operating_profit_volatility_3y: 미수집 → sector 매핑으로 proxy
  - years_consecutive_loss: 미수집 → roe<0 + recent margin>0 proxy
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# ── 한국 임계 (2026 기준) ──
FAST_GROWER_REV_MIN = 15.0       # YoY % (Lynch 원전 GDP 10× → 한국 GDP 1.9% × 8 = 15%)
FAST_GROWER_MCAP_MAX = 5e12      # 5조 KRW (소·중형 선호)
STALWART_REV_MIN = 5.0
STALWART_REV_MAX = 15.0
STALWART_MCAP_MIN = 1e12         # 1조 KRW (대형)
SLOW_GROWER_DIV_MIN = 2.5        # % (Slow Grower 배당 특성)
ASSET_PLAY_PBR_MAX = 0.8         # 한국 저PBR 구조 반영
TURNAROUND_DEBT_MAX = 300.0      # 부채비율 % (생존 가능)

# Cyclical 업종 키워드 (한국 시장)
CYCLICAL_KEYWORDS = (
    "철강", "화학", "조선", "건설", "해운", "항공",
    "반도체장비", "정유", "비철금속", "시멘트",
    "자동차부품",  # 완성차는 별도 — 사이클 약함
)

CLASSES = (
    "FAST_GROWER", "STALWART", "SLOW_GROWER",
    "CYCLICAL", "TURNAROUND", "ASSET_PLAY",
)

# AdminDashboard 배지 색 (디자인 토큰 호환 키)
CLASS_BADGE: Dict[str, Dict[str, str]] = {
    "FAST_GROWER":  {"color": "success", "label": "Fast Grower",  "summary": "매출 15%+ 고성장"},
    "STALWART":     {"color": "info",    "label": "Stalwart",     "summary": "안정 성장 5~15%"},
    "TURNAROUND":   {"color": "warn",    "label": "Turnaround",   "summary": "적자→흑자 전환"},
    "CYCLICAL":     {"color": "watch",   "label": "Cyclical",     "summary": "업황 민감"},
    "ASSET_PLAY":   {"color": "purple",  "label": "Asset Play",   "summary": "저PBR 자산 할인"},
    "SLOW_GROWER":  {"color": "muted",   "label": "Slow Grower",  "summary": "저성장 배당주"},
}


def _is_cyclical_sector(stock: Dict[str, Any]) -> bool:
    fields = (
        (stock.get("sector") or "") + " "
        + (stock.get("company_type") or "") + " "
        + (stock.get("industry") or "")
    ).lower()
    return any(kw.lower() in fields for kw in CYCLICAL_KEYWORDS)


def _is_turnaround(stock: Dict[str, Any]) -> bool:
    """proxy: ROE 음수 (적자 흔적) + 최근 영업이익률 양수 (반등 신호) + 매출 성장 (회복 모멘텀) + 부채 생존선.

    Lynch 본인 정의 = "2년+ 적자 → 흑자 전환". 한국 KIS 다년 데이터 미수집이라
    revenue_growth > 0 조건 추가로 false positive 완화 (일회성 손실 vs 진짜 회복).
    """
    kfr = stock.get("kis_financial_ratio") or {}
    roe = (kfr.get("roe") if kfr.get("source") == "kis" else None) or stock.get("roe", 0)
    op_margin = (kfr.get("operating_margin") if kfr.get("source") == "kis" else None) or stock.get("operating_margin", 0)
    debt = (kfr.get("debt_ratio") if kfr.get("source") == "kis" else None) or stock.get("debt_ratio", 0)
    rev_g = stock.get("revenue_growth")
    try:
        roe_v = float(roe) if roe is not None else 0
        op_v = float(op_margin) if op_margin is not None else 0
        debt_v = float(debt) if debt is not None else 0
        rev_v = float(rev_g) if rev_g is not None else 0
    except (TypeError, ValueError):
        return False
    return (roe_v < 0
            and op_v > 0
            and rev_v > 0
            and debt_v < TURNAROUND_DEBT_MAX)


def _is_fast_grower(stock: Dict[str, Any]) -> bool:
    rg = stock.get("revenue_growth")
    mcap = stock.get("market_cap", 0)
    op_margin = stock.get("operating_margin", 0)
    if rg is None:
        return False
    try:
        return (
            float(rg) >= FAST_GROWER_REV_MIN
            and float(mcap) <= FAST_GROWER_MCAP_MAX
            and float(op_margin or 0) > 0
        )
    except (TypeError, ValueError):
        return False


def _is_stalwart(stock: Dict[str, Any]) -> bool:
    rg = stock.get("revenue_growth")
    mcap = stock.get("market_cap", 0)
    if rg is None:
        return False
    try:
        rg_v = float(rg)
        return (
            STALWART_REV_MIN <= rg_v < STALWART_REV_MAX
            and float(mcap) >= STALWART_MCAP_MIN
        )
    except (TypeError, ValueError):
        return False


def _is_asset_play(stock: Dict[str, Any]) -> bool:
    pbr = stock.get("pbr") or stock.get("price_to_book")
    if pbr is None:
        return False
    try:
        pbr_v = float(pbr)
        return 0 < pbr_v < ASSET_PLAY_PBR_MAX
    except (TypeError, ValueError):
        return False


def classify_lynch_kr(stock: Dict[str, Any]) -> Dict[str, Any]:
    """Lynch 6분류 — 한국 기준.

    우선순위 (특수 상황 우선): Turnaround → Cyclical → Fast → Stalwart → Asset → Slow.
    이유:
      - Turnaround/Cyclical 의 반등기 매출 급증 → Fast Grower 오분류 방지
      - Asset Play 의 저성장 → Slow Grower 오분류 방지

    Data Quality:
      revenue_growth / market_cap / op_margin 중 핵심 데이터 누락 시 data_quality="low".
      AdminDashboard 가 별도 표시. 분류 자체는 default(SLOW_GROWER) 로 떨어지지만
      통계 왜곡 방지 위해 외부에서 분리 카운트.

    Returns:
      {
        "class": "FAST_GROWER",
        "label": "Fast Grower",
        "summary": "매출 15%+ 고성장",
        "color": "success",
        "reasons": ["revenue_growth 18.5% ≥ 15.0", ...],
        "data_quality": "ok" | "low",       # low = 핵심 데이터 누락
      }
    """
    reasons = []
    cls = "SLOW_GROWER"  # default
    # data_quality 평가 — 핵심 분류 데이터 가용성
    has_rev = stock.get("revenue_growth") is not None
    has_mcap = bool(stock.get("market_cap"))
    has_op = stock.get("operating_margin") is not None
    data_quality = "ok" if (has_rev and has_mcap and has_op) else "low"

    if _is_turnaround(stock):
        cls = "TURNAROUND"
        reasons.append("ROE 음수 + 영업이익률 양수 (반등 신호)")
    elif _is_cyclical_sector(stock):
        cls = "CYCLICAL"
        reasons.append(f"sector keyword match: {stock.get('sector') or stock.get('company_type')}")
    elif _is_fast_grower(stock):
        cls = "FAST_GROWER"
        reasons.append(f"revenue_growth {stock.get('revenue_growth'):.1f}% ≥ {FAST_GROWER_REV_MIN}%")
        reasons.append(f"market_cap {(stock.get('market_cap', 0)/1e12):.1f}조 ≤ 5조")
    elif _is_stalwart(stock):
        cls = "STALWART"
        reasons.append(f"revenue_growth {stock.get('revenue_growth'):.1f}% in [{STALWART_REV_MIN}, {STALWART_REV_MAX})")
    elif _is_asset_play(stock):
        cls = "ASSET_PLAY"
        reasons.append(f"PBR {float(stock.get('pbr') or stock.get('price_to_book')):.2f} < {ASSET_PLAY_PBR_MAX}")
    else:
        # Slow Grower default
        div = stock.get("div_yield", 0)
        try:
            if float(div or 0) >= SLOW_GROWER_DIV_MIN:
                reasons.append(f"div_yield {float(div):.2f}% ≥ {SLOW_GROWER_DIV_MIN}% (전형 배당주)")
            else:
                reasons.append("나머지 분류 미충족 (default)")
        except (TypeError, ValueError):
            reasons.append("분류 데이터 부족 (default)")

    badge = CLASS_BADGE[cls]
    return {
        "class": cls,
        "label": badge["label"],
        "summary": badge["summary"],
        "color": badge["color"],
        "reasons": reasons,
        "data_quality": data_quality,
    }


def attach_classifications(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """portfolio.recommendations 각 종목에 lynch_kr 키 부착 + 분포 요약.

    Returns: portfolio (in-place)
    """
    recs = portfolio.get("recommendations") or []
    counter: Dict[str, int] = {c: 0 for c in CLASSES}
    low_quality = 0   # data_quality=low 카운트 — 분류 통계 왜곡 방지
    for stock in recs:
        try:
            res = classify_lynch_kr(stock)
            stock["lynch_kr"] = res
            counter[res["class"]] += 1
            if res.get("data_quality") == "low":
                low_quality += 1
        except Exception:  # noqa: BLE001
            stock.setdefault("lynch_kr", {"class": "SLOW_GROWER", "label": "Unknown",
                                         "summary": "분류 실패", "color": "muted",
                                         "reasons": [], "data_quality": "low"})
            low_quality += 1

    total = sum(counter.values()) or 1
    portfolio["lynch_kr_distribution"] = {
        "total": sum(counter.values()),
        "counts": counter,
        "pct": {c: round(counter[c] / total * 100, 1) for c in CLASSES},
        "low_quality_count": low_quality,
        "low_quality_pct": round(low_quality / total * 100, 1) if total > 0 else 0,
    }
    return portfolio
