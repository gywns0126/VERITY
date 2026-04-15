"""
한/미 수익률 곡선 통합·역전 경보
  - bonddata(KR) + bondus(US) 오케스트레이션
  - 곡선 형태(curve_shape) 판별
  - 역전(inversion) 경보 생성
  - portfolio.json의 최상위 "bonds" 섹션 전체를 조립
"""
from typing import Any, Dict, List

from api.config import now_kst


def _detect_inversions(
    us_data: Dict[str, Any],
    kr_data: Dict[str, Any],
) -> List[Dict[str, str]]:
    """수익률 곡선 역전 경보 생성."""
    alerts: List[Dict[str, str]] = []

    spread_2s10s = us_data.get("spread_2y_10y")
    spread_3m10y = us_data.get("spread_3m_10y")

    if spread_2s10s is not None and spread_2s10s < 0:
        alerts.append({
            "market": "US",
            "type": "2s10s_inversion",
            "spread": spread_2s10s,
            "message": f"미국 2Y-10Y 역전 ({spread_2s10s:+.3f}%p) — 경기침체 선행 신호",
            "severity": "HIGH" if spread_2s10s < -0.5 else "MODERATE",
        })

    if spread_3m10y is not None and spread_3m10y < 0:
        alerts.append({
            "market": "US",
            "type": "3m10y_inversion",
            "spread": spread_3m10y,
            "message": f"미국 3M-10Y 역전 ({spread_3m10y:+.3f}%p) — 강한 침체 경고",
            "severity": "HIGH" if spread_3m10y < -0.5 else "MODERATE",
        })

    kr_curve = kr_data.get("curve", [])
    if len(kr_curve) >= 2:
        kr_yields = {c["tenor"]: c["yield"] for c in kr_curve}
        kr_short = kr_yields.get("1Y") or kr_yields.get("3Y")
        kr_long = kr_yields.get("10Y") or kr_yields.get("30Y")
        if kr_short is not None and kr_long is not None and kr_long < kr_short:
            spread_kr = round(kr_long - kr_short, 3)
            alerts.append({
                "market": "KR",
                "type": "kr_curve_inversion",
                "spread": spread_kr,
                "message": f"한국 장단기 역전 ({spread_kr:+.3f}%p)",
                "severity": "MODERATE",
            })

    us_credit = us_data.get("credit_spreads", {})
    hy_oas = us_credit.get("us_hy_oas")
    if hy_oas is not None and hy_oas > 5.0:
        alerts.append({
            "market": "US",
            "type": "hy_spread_widening",
            "spread": hy_oas,
            "message": f"미국 HY 스프레드 급등 ({hy_oas:.2f}%p) — 신용 경색 경고",
            "severity": "HIGH" if hy_oas > 7.0 else "MODERATE",
        })

    return alerts


def get_full_yield_curve_data() -> Dict[str, Any]:
    """
    한/미 수익률 곡선 + 신용 스프레드 + 역전 경보 통합.
    portfolio["bonds"]에 들어갈 전체 블록을 반환.
    """
    from api.collectors.bonddata import get_bond_market_summary
    from api.collectors.bondus import get_us_bond_summary

    ts = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")

    kr_data = {}
    us_data = {}
    try:
        kr_data = get_bond_market_summary()
    except Exception as e:
        print(f"  [bonds/kr] 수집 실패: {e}")
    try:
        us_data = get_us_bond_summary()
    except Exception as e:
        print(f"  [bonds/us] 수집 실패: {e}")

    yield_curves: Dict[str, Any] = {}

    if kr_data.get("curve"):
        yield_curves["kr"] = {
            "curve": kr_data["curve"],
            "curve_shape": kr_data.get("curve_shape", "unknown"),
        }

    if us_data.get("curve"):
        us_block: Dict[str, Any] = {
            "curve": us_data["curve"],
            "curve_shape": us_data.get("curve_shape", "unknown"),
        }
        if us_data.get("spread_2y_10y") is not None:
            us_block["spread_2y_10y"] = us_data["spread_2y_10y"]
        if us_data.get("spread_3m_10y") is not None:
            us_block["spread_3m_10y"] = us_data["spread_3m_10y"]
        yield_curves["us"] = us_block

    inversion_alerts = _detect_inversions(us_data, kr_data)

    result: Dict[str, Any] = {
        "yield_curves": yield_curves,
        "inversion_alerts": inversion_alerts,
        "has_alert": len(inversion_alerts) > 0,
        "updated_at": ts,
    }

    credit = us_data.get("credit_spreads")
    if credit:
        result["credit_spreads"] = credit

    kr_corp = kr_data.get("kr_corp_spreads")
    if kr_corp:
        result["kr_corp_spreads"] = kr_corp

    return result


if __name__ == "__main__":
    import json
    data = get_full_yield_curve_data()
    print(json.dumps(data, ensure_ascii=False, indent=2))
