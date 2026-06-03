"""
한/미 수익률 곡선 통합·역전 경보
  - bonddata(KR) + bondus(US) 오케스트레이션
  - 곡선 형태(curve_shape) 판별
  - 역전(inversion) 경보 생성
  - portfolio.json의 최상위 "bonds" 섹션 전체를 조립
"""
from typing import Any, Dict, List, Optional

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


_US_TENOR_ORDER = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
_KR_TENOR_ORDER = ["1Y", "2Y", "3Y", "5Y", "10Y", "20Y", "30Y"]


def _prev_curve(prev_bonds: Optional[Dict[str, Any]], market: str):
    if not isinstance(prev_bonds, dict):
        return None
    return ((prev_bonds.get("yield_curves") or {}).get(market) or {}).get("curve")


def _forward_fill_curve(fresh, prev, order):
    """정공법 — fetch 실패로 빠진 만기를 직전 커브 값으로 carry-forward (stale 표기).

    국채 수익률은 일변동이 작아 1일 stale 이 '만기 누락 → 스프레드 공백/viz 불안정' 보다 무해.
    fresh/prev 둘 다 없는 만기는 누락 유지. Returns: (merged_curve, carried_tenors).
    """
    fresh = [p for p in (fresh or []) if isinstance(p, dict) and p.get("tenor")]
    have = {p["tenor"] for p in fresh}
    prev_map = {p.get("tenor"): p for p in (prev or []) if isinstance(p, dict)}
    merged = list(fresh)
    carried: List[str] = []
    for t in order:
        if t not in have:
            pv = prev_map.get(t)
            if pv and pv.get("yield") is not None:
                merged.append({"tenor": t, "yield": pv["yield"], "stale": True})
                carried.append(t)
    idx = {t: i for i, t in enumerate(order)}
    merged.sort(key=lambda c: idx.get(c.get("tenor"), 99))
    return merged, carried


def get_full_yield_curve_data(prev_bonds: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    한/미 수익률 곡선 + 신용 스프레드 + 역전 경보 통합.
    portfolio["bonds"]에 들어갈 전체 블록을 반환.

    정공법 (2026-06-03 채권 viz 불안정 fix): prev_bonds(직전 portfolio["bonds"])를 받아
    transient fetch 실패로 빠진 만기를 직전 커브로 carry-forward → 커브가 silent 하게
    불완전해지지 않음. carry-forward 만기는 stale 표기 (freshness 투명성). US/KR 공통.
    """
    from api.collectors.bonddata import get_bond_market_summary
    from api.collectors.bondus import get_us_bond_summary, _classify_us_curve_shape

    ts = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")

    kr_data: Dict[str, Any] = {}
    us_data: Dict[str, Any] = {}
    try:
        kr_data = get_bond_market_summary()
    except Exception as e:
        print(f"  [bonds/kr] 수집 실패: {e}")
    try:
        us_data = get_us_bond_summary()
    except Exception as e:
        print(f"  [bonds/us] 수집 실패: {e}")

    yield_curves: Dict[str, Any] = {}

    # KR — forward-fill (KRX 실패 시에도 직전 커브 유지)
    kr_curve, kr_carried = _forward_fill_curve(
        kr_data.get("curve"), _prev_curve(prev_bonds, "kr"), _KR_TENOR_ORDER)
    if kr_curve:
        kr_block: Dict[str, Any] = {
            "curve": kr_curve,
            "curve_shape": kr_data.get("curve_shape", "unknown"),
        }
        if kr_carried:
            kr_block["stale_tenors"] = kr_carried
        yield_curves["kr"] = kr_block

    # US — forward-fill + 스프레드 재계산 (merged 커브 기준)
    us_curve, us_carried = _forward_fill_curve(
        us_data.get("curve"), _prev_curve(prev_bonds, "us"), _US_TENOR_ORDER)
    if us_curve:
        ym = {c["tenor"]: c["yield"] for c in us_curve}
        us_block: Dict[str, Any] = {
            "curve": us_curve,
            "curve_shape": _classify_us_curve_shape(us_curve),
        }
        if ym.get("2Y") is not None and ym.get("10Y") is not None:
            us_block["spread_2y_10y"] = round(ym["10Y"] - ym["2Y"], 3)
        if ym.get("3M") is not None and ym.get("10Y") is not None:
            us_block["spread_3m_10y"] = round(ym["10Y"] - ym["3M"], 3)
        if us_carried:
            us_block["stale_tenors"] = us_carried
        yield_curves["us"] = us_block
        # 역전 감시가 merged 스프레드를 쓰도록 us_data 갱신
        for k in ("spread_2y_10y", "spread_3m_10y"):
            if k in us_block:
                us_data[k] = us_block[k]

    # 완전성 가드 — carry-forward 후에도 핵심 만기 부재 시 로그 (최초 수집/장기 결손)
    us_have = {c.get("tenor") for c in us_curve}
    missing_critical = [t for t in ("3M", "2Y", "10Y") if t not in us_have]
    if missing_critical:
        print(f"  [bonds/us] 핵심 만기 결손 (carry-forward 후에도): {missing_critical}")

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
