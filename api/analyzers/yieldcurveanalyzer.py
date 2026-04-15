"""
yieldcurveanalyzer.py — 수익률 곡선 형태 분류 + Verity Brain 연동 레이어
의존: api/analyzers/bondanalyzer.py, api/collectors/yieldcurve.py
역할: 수익률 곡선 분석 결과를 verity_constitution.json의
      bond_regime 판단 로직과 연결하는 브릿지 모듈
      → alert_engine.py에 Telegram 경보 트리거 신호 전달
"""

import logging
import json
from datetime import datetime
from typing import Any, Dict, List

from api.analyzers.bondanalyzer import (
    analyze_yield_curve,
    analyze_credit_spreads,
    curve_list_to_dict,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Verity Brain bond_regime → 주식 판단 조정 매핑
# ──────────────────────────────────────────────
BOND_REGIME_TO_EQUITY_IMPACT: Dict[str, Dict[str, Any]] = {
    "rate_high_restrictive": {
        "equity_bias": "NEGATIVE",
        "sector_favor": ["금융", "에너지", "원자재"],
        "sector_avoid": ["성장주", "기술주", "부동산"],
        "bond_strategy": "단기채·플로팅레이트 선호. 장기채 비중 축소.",
        "duration_target": "SHORT (<3Y)",
    },
    "rate_elevated": {
        "equity_bias": "NEUTRAL",
        "sector_favor": ["가치주", "배당주", "금융"],
        "sector_avoid": ["고밸류 성장주"],
        "bond_strategy": "중단기 국채 유지. 투자등급 회사채 일부.",
        "duration_target": "MID (3~7Y)",
    },
    "rate_normal": {
        "equity_bias": "POSITIVE",
        "sector_favor": ["기술주", "소비재", "헬스케어"],
        "sector_avoid": ["방어주 과도 비중"],
        "bond_strategy": "장기국채 비중 확대 기회. IG 회사채 매력적.",
        "duration_target": "LONG (7Y+)",
    },
    "rate_low_accommodative": {
        "equity_bias": "VERY_POSITIVE",
        "sector_favor": ["성장주", "기술주", "부동산"],
        "sector_avoid": ["현금·단기채 과도 보유"],
        "bond_strategy": "장기채 비중 최대화. 하이일드 고려.",
        "duration_target": "LONG (10Y+)",
    },
}

RECESSION_SIGNAL_OVERRIDE: Dict[str, Any] = {
    "equity_bias": "VERY_NEGATIVE",
    "sector_favor": ["국채", "금", "현금", "필수소비재"],
    "sector_avoid": ["경기민감주", "하이일드채", "이머징"],
    "bond_strategy": "장기국채 최대 비중. 리스크 자산 전면 회피.",
    "duration_target": "LONG (20Y+)",
    "alert_level": "CRITICAL",
}


def get_bond_regime_signal(
    curve_data: Dict[str, Any],
    credit_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    수익률 곡선 + 신용 스프레드 → Verity Brain bond_regime 종합 신호.

    curve_data: Phase 1 yield_curves 블록
        {"us": {"curve": [...], ...}, "kr": {"curve": [...], ...}}
    credit_data: Phase 1 credit_spreads 블록
        {"us_ig_oas": 1.05, "us_hy_oas": 3.52, ...}
    """
    us_curve_list = curve_data.get("us", {}).get("curve", [])
    kr_curve_list = curve_data.get("kr", {}).get("curve", [])

    us_dict = curve_list_to_dict(us_curve_list) if us_curve_list else {}
    kr_dict = curve_list_to_dict(kr_curve_list) if kr_curve_list else {}

    us_analysis = analyze_yield_curve(us_dict, "US") if us_dict else {"shape": "unknown", "regime": "unknown"}
    kr_analysis = analyze_yield_curve(kr_dict, "KR") if kr_dict else {"shape": "unknown"}

    credit_analysis = analyze_credit_spreads(credit_data) if credit_data else {}

    rate_env = us_analysis.get("regime", "rate_normal")
    curve_shape = us_analysis.get("shape", "normal")
    credit_cycle = credit_analysis.get("credit_cycle", "neutral")
    recession = us_analysis.get("recession_signal", False)

    bond_regime: Dict[str, Any] = {
        "rate_environment": rate_env,
        "curve_shape": curve_shape,
        "credit_cycle": credit_cycle,
        "recession_signal": recession,
        "us_spreads": us_analysis.get("key_spreads", {}),
        "kr_shape": kr_analysis.get("shape", "unknown"),
    }

    if recession:
        equity_impact = dict(RECESSION_SIGNAL_OVERRIDE)
    else:
        equity_impact = dict(BOND_REGIME_TO_EQUITY_IMPACT.get(rate_env, {}))

    alert_triggers: List[Dict[str, str]] = []

    if recession:
        alert_triggers.append({
            "type": "RECESSION_SIGNAL",
            "severity": "CRITICAL",
            "message": f"경기침체 선행신호: 미국 수익률 곡선 역전 ({us_analysis.get('key_spreads', {})})",
            "action": "즉시 포트폴리오 방어적 전환 검토",
        })

    hy_oas = credit_data.get("HY_OAS") or credit_data.get("us_hy_oas")
    if hy_oas is not None and hy_oas > 6.5:
        alert_triggers.append({
            "type": "CREDIT_STRESS",
            "severity": "CRITICAL",
            "message": f"HY 크레딧 스트레스: OAS {hy_oas}bp (임계값 650bp 초과)",
            "action": "리스크 자산 비중 즉시 축소",
        })
    elif hy_oas is not None and hy_oas > 5.0:
        alert_triggers.append({
            "type": "CREDIT_WARNING",
            "severity": "WARNING",
            "message": f"HY 스프레드 확대 경고: {hy_oas}bp",
            "action": "하이일드 비중 점검 권고",
        })

    constitution_patch: Dict[str, Any] = {
        "bond_regime": bond_regime,
        "macro_override": recession,
        "updated_at": datetime.now().isoformat(),
    }

    return {
        "bond_regime": bond_regime,
        "equity_impact": equity_impact,
        "macro_override": recession,
        "alert_triggers": alert_triggers,
        "has_critical_alert": any(a["severity"] == "CRITICAL" for a in alert_triggers),
        "verity_constitution_patch": constitution_patch,
        "kr_curve_interpretation": kr_analysis.get("interpretation", ""),
        "us_curve_interpretation": us_analysis.get("interpretation", ""),
        "analyzed_at": datetime.now().isoformat(),
    }


def format_telegram_bond_report(signal: Dict[str, Any]) -> str:
    """Telegram 알림용 채권 시장 요약 텍스트."""
    regime = signal.get("bond_regime", {})
    impact = signal.get("equity_impact", {})
    alerts = signal.get("alert_triggers", [])

    lines = [
        "*VERITY 채권 시장 리포트*",
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')} KST",
        "",
        "*[ 금리 레짐 ]*",
        f"  환경: `{regime.get('rate_environment', 'N/A')}`",
        f"  곡선 형태: `{regime.get('curve_shape', 'N/A')}` (US)",
        f"  크레딧 사이클: `{regime.get('credit_cycle', 'N/A')}`",
        f"  경기침체 신호: {'발동' if regime.get('recession_signal') else '없음'}",
        "",
        "*[ 주식 시장 함의 ]*",
        f"  편향: `{impact.get('equity_bias', 'N/A')}`",
        f"  선호 섹터: {', '.join(impact.get('sector_favor', []))}",
        f"  채권 전략: {impact.get('bond_strategy', 'N/A')}",
    ]

    if alerts:
        lines.append("")
        lines.append("*[ 경보 ]*")
        for alert in alerts:
            icon = "[CRITICAL]" if alert["severity"] == "CRITICAL" else "[WARNING]"
            lines.append(f"  {icon} {alert['message']}")

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_curve = {
        "us": {"curve": [
            {"tenor": "3M", "yield": 5.28}, {"tenor": "2Y", "yield": 4.82},
            {"tenor": "5Y", "yield": 4.62}, {"tenor": "10Y", "yield": 4.55},
            {"tenor": "30Y", "yield": 4.61},
        ]},
        "kr": {"curve": [
            {"tenor": "1Y", "yield": 3.15}, {"tenor": "3Y", "yield": 3.22},
            {"tenor": "10Y", "yield": 3.48},
        ]},
    }
    test_credit = {"us_hy_oas": 3.52, "us_ig_oas": 1.05}

    signal = get_bond_regime_signal(test_curve, test_credit)
    print(json.dumps(signal, ensure_ascii=False, indent=2))
    print("\n--- Telegram ---")
    print(format_telegram_bond_report(signal))
