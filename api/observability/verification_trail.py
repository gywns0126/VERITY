"""verification_trail — N counter helper (Phase 1 P1-d).

PM=approved 2026-05-23 (plan §Phase 1-d).
WHY: VAMS reset_meta 시점 = N=0 origin. 매매 이벤트 count → N_today.
     Q11 milestone (50/100/252/365) 까지 잔여 계산. Bailey-Lopez de Prado 2014
     검증 게이트 후 통계 유의 (메모리 [[project_minimum_n_milestones_2026_05_18]]).
DATA: portfolio.vams.simulation_stats.total_trades (5/17 reset 후 누적 trade count) +
      portfolio.validation.cumulative_days (운영 일수).
EXPECTED: cockpit_aggregate.py 가 compute_n_today() + compute_milestones() 호출 추가.

자기 산식 0 (단순 count + 차이). RULE 7 비대상.

별 ledger (verification_trail.jsonl) 기록하지 않음 — Phase 2 후속 (시계열 분석 필요 시).
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# 통계 유의성 milestone (메모리 [[project_minimum_n_milestones_2026_05_18]] 정합)
#
# 🚨 2026-08-18 — `to_252`(IC IR 임계) 와 `to_365`(운영 trail 1년, 목표 2027-05) **제거**.
#    둘 다 `docs/VALIDATION_METHODOLOGY.md` §7-1 로 폐기된 표본수 게이트다. 폐기 사유가
#    정확히 이 계산이었다 — *"실제 출력이 언제나 '더 모아라' 였다. 검정력을 따지지 않은 채
#    표본만 요구하는 것은 무책임하다."* 그런데 콕핏이 매일 "252까지 170일 · 365까지 283일"
#    을 계산해 오퍼레이터 UI 에 띄우고 있었다 (`data/metadata/cockpit_state.json` 실측).
#    `to_365` 는 CLAUDE.md RULE 7 이 **부활 금지**로 명시한 값이기도 하다.
#
#    남긴 둘은 폐기 대상이 아니다 — 표본 크기의 **방법론적 하한**이지 목표 시점이 아니다:
#      to_50  = IC 측정 가능 임계 · to_100 = PSR 적용 가능(Bailey-Lopez 2014)
#    이들은 "언제 도달하나" 가 아니라 "이 아래로는 계산 자체가 무의미" 를 뜻한다.
#
#    🚨 소비처가 프런트 2곳(operator-web `CockpitCard.tsx` · framer `OperatorCockpitCard.tsx`)
#    이라 키를 통째로 지우면 UI 가 빈 값을 렌더한다. 두 키를 없애는 대신 **산출에서 제외**하고,
#    프런트는 옵셔널 체이닝(`ms.to_252` → undefined)으로 자연히 생략된다.
#    framer 는 RULE 11(3소스 동기화) 대상이라 별도 절차 — 잔여로 남긴다.
_MILESTONES = {
    "to_50": 50,    # IC 측정 가능 임계 (5% 신뢰)
    "to_100": 100,  # PSR 적용 가능 (Bailey-Lopez 2014)
}


def compute_n_today(portfolio: Dict[str, Any]) -> Dict[str, int]:
    """portfolio.json → N counter dict 반환.

    Returns:
        {
            "n_trades": int,            # vams.simulation_stats.total_trades
            "n_validation_days": int,   # vams.validation_report.window.days (진짜 검증일수, 5/17 reset 이후 snapshot)
            "n_validation_samples": int # validation.sample_total
        }

    결손 source 부분 = 0 반환 (silent skip 차단 — 0 값이 의도된 미충족).
    """
    vams = portfolio.get("vams") or {}
    sim = vams.get("simulation_stats") or {}
    val = portfolio.get("validation") or {}

    try:
        n_trades = int(sim.get("total_trades") or 0)
    except (TypeError, ValueError):
        n_trades = 0
    # n_validation_days = 진짜 검증일수 = VAMS validation_report.window.days (validation_start 이후 snapshot 수).
    # 🔧 2026-06-11 fix: 기존엔 validation.cumulative_days(=factor_ic 최대 윈도우, 예 126일)를 잘못 읽어
    #   검증 ~5배 과장(N=21을 126으로 표시). RULE 7 직격. 권위 소스(validation_report.window.days)로 교체.
    try:
        _window = (vams.get("validation_report") or {}).get("window") or {}
        n_days = int(_window.get("days") or 0)
    except (TypeError, ValueError):
        n_days = 0
    try:
        n_samples = int(val.get("sample_total") or 0)
    except (TypeError, ValueError):
        n_samples = 0

    return {
        "n_trades": n_trades,
        "n_validation_days": n_days,
        "n_validation_samples": n_samples,
    }


def compute_milestones(n_current: int) -> Dict[str, int]:
    """N_current 기준 milestone 잔여 계산.

    Args:
        n_current: 현 N (trades / days / samples 중 하나).

    Returns:
        {"to_50": 잔여, "to_100": 잔여, "to_252": 잔여, "to_365": 잔여}
        도달 시 = 0 (음수 반환하지 않음).
    """
    return {
        key: max(0, target - n_current)
        for key, target in _MILESTONES.items()
    }


def compute_trail(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """전체 N trail 산출.

    Returns:
        {
            "n_today": {n_trades, n_validation_days, n_validation_samples},
            "trade_milestones": {to_50, to_100, to_252, to_365},
            "day_milestones": {to_50, to_100, to_252, to_365},
            "sample_milestones": {to_50, to_100, to_252, to_365}
        }
    """
    n_today = compute_n_today(portfolio)
    return {
        "n_today": n_today,
        "trade_milestones": compute_milestones(n_today["n_trades"]),
        "day_milestones": compute_milestones(n_today["n_validation_days"]),
        "sample_milestones": compute_milestones(n_today["n_validation_samples"]),
    }
