"""
VERITY — KRX 섹터 로테이션 vs 경제 quadrant 정합성 검증.

목적
----
1. KRX(KOSPI) 섹터별 5일 누적 수익률 산출 (history snapshot 기반).
2. 상위 3 섹터(강세) / 하위 3 섹터(약세) 자동 분류.
3. detect_economic_quadrant() 의 favored/unfavored 와 교차 검증.
   "코드 quadrant=스태그플레이션인데 실제 강세는 성장주?" → constitution drift.
4. 드리프트 감지 시 텔레그램 알림 발송 (constitution.json 검토 권장).
5. detect_macro_override 에 secondary_signal 로 첨부.

데이터 소스 우선순위
------------------
1순위: data/history/YYYY-MM-DD.json 5개 snapshot — sectors[*].change_pct 일간 합산
       (5일 누적 수익률 근사. 일간 ±수% 범위에서 단순 합산 ≈ 복리, 오차 무시 가능)
2순위: portfolio["sector_trends"]["1m"].top3/bottom3 (history 부재 시)
3순위: portfolio["sectors"][*].change_pct 당일 단일 (최후)

설계 메모
--------
- KOSPI 만 대상 (KOSDAQ/US sector 는 별도 quadrant 매핑 부재).
- favored/unfavored 매칭은 substring (예: "원자재" ⊂ "원자재 ETF").
- 드리프트 임계: top_in_unfavored + bottom_in_favored ≥ 2 건 → 알림.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from api.config import now_kst
from api.workflows.archiver import HISTORY_DIR

logger = logging.getLogger(__name__)

WINDOW_DAYS = 5
TOP_N = 3
DRIFT_ALERT_THRESHOLD = 2  # top3 unfavored + bottom3 favored 합계 임계


# ─── 데이터 수집 ─────────────────────────────────────────────


def _load_recent_sector_returns(window_days: int = WINDOW_DAYS) -> Tuple[Dict[str, float], int]:
    """history 스냅샷에서 KOSPI 섹터별 일간 change_pct 누적.

    주말/공휴일 보정 위해 window_days*2 일까지 거슬러 올라가며 가용 snapshot 수집.
    Returns: ({sector_name: cum_return_pct}, snapshots_used).
    """
    today = now_kst().date()
    sector_sum: Dict[str, float] = {}
    used = 0
    for i in range(window_days * 2):
        d = today - timedelta(days=i)
        path = os.path.join(HISTORY_DIR, f"{d.strftime('%Y-%m-%d')}.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                snap = json.loads(f.read().replace("NaN", "null"))
        except (OSError, json.JSONDecodeError):
            continue
        for s in snap.get("sectors") or []:
            if s.get("market") != "KOSPI":
                continue
            name = s.get("name")
            if not name:
                continue
            try:
                cp = float(s.get("change_pct") or 0)
            except (TypeError, ValueError):
                continue
            sector_sum[name] = sector_sum.get(name, 0.0) + cp
        used += 1
        if used >= window_days:
            break
    return sector_sum, used


def _fallback_from_sector_trends(portfolio: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """sector_trends.1m.top3/bottom3 → {name: avg_change_pct}."""
    one_m = (portfolio.get("sector_trends") or {}).get("1m") or {}
    top = one_m.get("top3_sectors") or []
    bot = one_m.get("bottom3_sectors") or []
    out: Dict[str, float] = {}
    for item in list(top) + list(bot):
        name = item.get("name")
        chg = item.get("avg_change_pct")
        if not name or chg is None:
            continue
        try:
            out[name] = float(chg)
        except (TypeError, ValueError):
            continue
    return out or None


def _fallback_from_today_sectors(portfolio: Dict[str, Any]) -> Dict[str, float]:
    """portfolio.sectors 당일 KOSPI change_pct."""
    out: Dict[str, float] = {}
    for s in portfolio.get("sectors") or []:
        if s.get("market") != "KOSPI":
            continue
        name = s.get("name")
        if not name:
            continue
        try:
            cp = float(s.get("change_pct") or 0)
        except (TypeError, ValueError):
            continue
        out[name] = cp
    return out


def collect_sector_returns(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """우선순위 적용 후 sector returns + source 메타 반환."""
    returns, used = _load_recent_sector_returns()
    if used >= 3:
        return {"returns": returns, "source": "history",
                "snapshots_used": used, "window_days": used}
    alt = _fallback_from_sector_trends(portfolio)
    if alt:
        return {"returns": alt, "source": "sector_trends_1m",
                "snapshots_used": 0, "window_days": 30}
    today_only = _fallback_from_today_sectors(portfolio)
    return {"returns": today_only, "source": "today_only",
            "snapshots_used": 1 if today_only else 0, "window_days": 1}


# ─── 분류 + 정합성 검증 ─────────────────────────────────────


def _classify_top_bottom(
    returns: Dict[str, float], top_n: int = TOP_N,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    items = sorted(returns.items(), key=lambda kv: kv[1], reverse=True)
    top = [{"name": n, "return_pct": round(r, 2)} for n, r in items[:top_n]]
    bot = [{"name": n, "return_pct": round(r, 2)} for n, r in items[-top_n:][::-1]]
    return top, bot


def _matches_keyword(sector_name: str, keywords: List[str]) -> Optional[str]:
    for kw in keywords:
        if kw and kw in sector_name:
            return kw
    return None


def _check_quadrant_consistency(
    top_sectors: List[Dict[str, Any]],
    bottom_sectors: List[Dict[str, Any]],
    quadrant_info: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """quadrant constitution 의 favored/unfavored 와 실제 top/bottom 비교.

    드리프트 = (top3 ∩ unfavored) ∪ (bottom3 ∩ favored) ≥ DRIFT_ALERT_THRESHOLD
    """
    if not quadrant_info:
        return {"drift": False, "drift_count": 0, "reason": "quadrant_unavailable"}

    favored = list(quadrant_info.get("favored") or [])
    unfavored = list(quadrant_info.get("unfavored") or [])

    top_in_unfavored = []
    for s in top_sectors:
        kw = _matches_keyword(s["name"], unfavored)
        if kw:
            top_in_unfavored.append({
                "sector": s["name"], "matched_keyword": kw,
                "return_pct": s["return_pct"],
            })

    bottom_in_favored = []
    for s in bottom_sectors:
        kw = _matches_keyword(s["name"], favored)
        if kw:
            bottom_in_favored.append({
                "sector": s["name"], "matched_keyword": kw,
                "return_pct": s["return_pct"],
            })

    drift_count = len(top_in_unfavored) + len(bottom_in_favored)
    return {
        "drift": drift_count >= DRIFT_ALERT_THRESHOLD,
        "drift_count": drift_count,
        "top_in_unfavored": top_in_unfavored,
        "bottom_in_favored": bottom_in_favored,
        "quadrant": quadrant_info.get("quadrant"),
        "quadrant_label": quadrant_info.get("label"),
        "favored": favored,
        "unfavored": unfavored,
    }


# ─── 알림 + 시그널 ──────────────────────────────────────────


def _build_telegram_message(detection: Dict[str, Any]) -> str:
    cons = detection["consistency"]
    src = detection["source"]
    lines = [
        "<b>⚠️ 섹터 로테이션 vs Quadrant 정합성 경고</b>",
        f"현재 quadrant: <code>{cons.get('quadrant_label') or cons.get('quadrant') or '미지정'}</code>",
        f"검출 소스: {src['source']} ({src['window_days']}일 누적, snap={src['snapshots_used']})",
        "",
        "<b>상위 3 섹터 (실제 강세):</b>",
    ]
    unfav_set = {t["sector"] for t in cons.get("top_in_unfavored", [])}
    fav_set = {b["sector"] for b in cons.get("bottom_in_favored", [])}
    for s in detection["top_sectors"]:
        marker = " ⚠️unfavored" if s["name"] in unfav_set else ""
        lines.append(f"  • {s['name']}: {s['return_pct']:+.2f}%{marker}")
    lines.append("")
    lines.append("<b>하위 3 섹터 (실제 약세):</b>")
    for s in detection["bottom_sectors"]:
        marker = " ⚠️favored" if s["name"] in fav_set else ""
        lines.append(f"  • {s['name']}: {s['return_pct']:+.2f}%{marker}")
    lines.append("")
    lines.append(f"<b>드리프트:</b> {cons['drift_count']}건 (임계 {DRIFT_ALERT_THRESHOLD})")
    if cons.get("top_in_unfavored"):
        names = ", ".join(t["sector"] for t in cons["top_in_unfavored"])
        lines.append(f"  unfavored 인데 강세: {names}")
    if cons.get("bottom_in_favored"):
        names = ", ".join(b["sector"] for b in cons["bottom_in_favored"])
        lines.append(f"  favored 인데 약세: {names}")
    lines.append("")
    lines.append("→ <code>verity_constitution.json</code> 의 economic_quadrant.quadrants 검토 권장")
    return "\n".join(lines)


def detect_sector_rotation(
    portfolio: Dict[str, Any],
    quadrant_info: Optional[Dict[str, Any]] = None,
    notify: bool = True,
) -> Dict[str, Any]:
    """메인 진입점.

    Args:
        portfolio: 분석 portfolio dict
        quadrant_info: detect_economic_quadrant 결과. None이면 portfolio에서 추출.
        notify: True면 드리프트 시 텔레그램 발송.

    Returns:
        {available, source{}, top_sectors[], bottom_sectors[],
         consistency{drift, drift_count, top_in_unfavored, bottom_in_favored},
         alert_sent}
    """
    src = collect_sector_returns(portfolio)
    if not src["returns"]:
        return {"available": False, "reason": "no_sector_data", "source": src}

    top, bot = _classify_top_bottom(src["returns"])

    if quadrant_info is None:
        macro_ov = (portfolio.get("verity_brain") or {}).get("macro_override") or {}
        quadrant_info = macro_ov.get("quadrant")

    consistency = _check_quadrant_consistency(top, bot, quadrant_info)

    result = {
        "available": True,
        "source": src,
        "top_sectors": top,
        "bottom_sectors": bot,
        "consistency": consistency,
        "alert_sent": False,
    }

    if notify and consistency.get("drift"):
        try:
            from api.notifications.telegram import send_message
            sent = send_message(_build_telegram_message(result))
            result["alert_sent"] = bool(sent)
        except Exception as e:
            logger.warning("sector rotation drift alert failed: %s", e)

    return result


def to_macro_signal(detection: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """detect_macro_override.signals 추가용 dict. 드리프트 미감지 시 None.

    secondary_signal 로 사용 — 정보성, 등급 cap 영향 최소화 (max_grade=BUY).
    """
    if not detection.get("available"):
        return None
    cons = detection.get("consistency") or {}
    if not cons.get("drift"):
        return None
    quad_label = cons.get("quadrant_label") or cons.get("quadrant") or "현 quadrant"
    return {
        "mode": "sector_quadrant_drift",
        "label": f"섹터 로테이션 vs {quad_label} 불일치",
        "message": (
            f"top3 unfavored {len(cons.get('top_in_unfavored', []))}건 "
            f"+ bottom3 favored {len(cons.get('bottom_in_favored', []))}건"
        ),
        "reason": "constitution_drift",
        "max_grade": "BUY",
        "drift_detail": {
            "top_in_unfavored": cons.get("top_in_unfavored", []),
            "bottom_in_favored": cons.get("bottom_in_favored", []),
        },
    }
