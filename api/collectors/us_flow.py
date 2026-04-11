"""
US 종목 수급(Flow) 점수 합성기
Finnhub(내부자/기관/컨센서스) + Polygon(옵션/공매도) → flow dict (KR 호환)

KR의 get_investor_flow가 외국인/기관 순매수로 flow_score를 만들듯이,
US는 이미 수집된 데이터를 기반으로 동등한 flow_score + flow_signals를 생성.
"""
from typing import Any, Dict, List


def compute_us_flow(stock: Dict[str, Any]) -> Dict[str, Any]:
    """
    stock 객체에 이미 붙어있는 US 전용 수집 데이터로 flow 점수 산출.
    full_us에서 Finnhub/Polygon 수집 후 호출. 데이터가 없으면 중립(50).

    Returns: KR flow dict 호환 구조
        flow_score (0~100), flow_signals[], 기타 호환 키
    """
    score = 50.0
    signals: List[str] = []

    # ── 1) 내부자 심리 (MSPR) — KR 외국인 순매수 대용 ──
    insider = stock.get("insider_sentiment") or {}
    mspr = insider.get("mspr", 0)
    net_shares = insider.get("net_shares", 0)

    if mspr > 5:
        score += 10
        signals.append(f"내부자 대량 매수 (MSPR {mspr:.1f})")
    elif mspr > 0:
        score += 5
        signals.append(f"내부자 순매수 (MSPR {mspr:.1f})")
    elif mspr < -5:
        score -= 10
        signals.append(f"내부자 대량 매도 (MSPR {mspr:.1f})")
    elif mspr < 0:
        score -= 5
        signals.append(f"내부자 순매도 (MSPR {mspr:.1f})")

    # ── 2) 기관 보유 변동 — KR 기관 순매수 대용 ──
    inst = stock.get("institutional_ownership") or {}
    inst_chg = inst.get("change_pct", 0)

    if inst_chg > 5:
        score += 8
        signals.append(f"기관 보유 증가 ({inst_chg:+.1f}%)")
    elif inst_chg > 0:
        score += 3
    elif inst_chg < -5:
        score -= 8
        signals.append(f"기관 보유 감소 ({inst_chg:+.1f}%)")
    elif inst_chg < 0:
        score -= 3

    # ── 3) 애널리스트 컨센서스 — 방향성 시그널 ──
    consensus = stock.get("analyst_consensus") or {}
    buy = consensus.get("buy", 0)
    hold = consensus.get("hold", 0)
    sell = consensus.get("sell", 0)
    total_analysts = buy + hold + sell

    if total_analysts > 0:
        buy_pct = buy / total_analysts
        if buy_pct > 0.7:
            score += 8
            signals.append(f"애널리스트 강력 매수 ({buy}/{total_analysts})")
        elif buy_pct > 0.5:
            score += 4
            signals.append(f"애널리스트 매수 우세 ({buy}/{total_analysts})")
        elif buy_pct < 0.2:
            score -= 8
            signals.append(f"애널리스트 매도 우세 ({sell}/{total_analysts})")

    upside = consensus.get("upside_pct", 0)
    if upside > 30:
        score += 5
        signals.append(f"목표가 업사이드 {upside:+.0f}%")
    elif upside < -10:
        score -= 5
        signals.append(f"목표가 하향 {upside:+.0f}%")

    # ── 4) 옵션 흐름 — 시장 심리 보조 ──
    opts = stock.get("options_flow") or {}
    pc_ratio = opts.get("put_call_ratio")

    if pc_ratio is not None:
        if pc_ratio < 0.5:
            score += 6
            signals.append(f"콜 우세 (P/C {pc_ratio:.2f})")
        elif pc_ratio < 0.8:
            score += 2
        elif pc_ratio > 1.5:
            score -= 8
            signals.append(f"풋 우세 — 약세 시그널 (P/C {pc_ratio:.2f})")
        elif pc_ratio > 1.0:
            score -= 3

    # ── 5) 공매도 압력 ──
    short = stock.get("short_interest") or {}
    short_pct = short.get("short_pct")

    # Polygon stub 보완: Finnhub basic_financials에서 공매도 비율 가져오기
    if short_pct is None:
        fh_metrics = stock.get("finnhub_metrics") or {}
        short_pct = fh_metrics.get("short_pct_outstanding") or fh_metrics.get("short_pct_float")

    if short_pct is not None:
        if short_pct > 25:
            score -= 8
            signals.append(f"공매도 과다 ({short_pct:.1f}%)")
        elif short_pct > 15:
            score -= 4
            signals.append(f"공매도 경계 ({short_pct:.1f}%)")
        elif short_pct < 3:
            score += 3

    # ── 6) 실적 서프라이즈 — 최근 모멘텀 ──
    earnings = stock.get("earnings_surprises") or []
    if earnings:
        latest = earnings[0]
        surprise = latest.get("surprise_pct", 0)
        if surprise > 10:
            score += 5
            signals.append(f"실적 서프라이즈 {surprise:+.1f}%")
        elif surprise < -10:
            score -= 5
            signals.append(f"실적 쇼크 {surprise:+.1f}%")

    score = max(0.0, min(100.0, score))

    return {
        "flow_score": round(score),
        "flow_signals": signals,
        "foreign_net": net_shares,
        "institution_net": 0,
        "foreign_5d_sum": 0,
        "institution_5d_sum": 0,
        "foreign_ratio": 0,
        "foreign_consec_buy": 0,
        "foreign_consec_sell": 0,
        "inst_consec_buy": 0,
        "inst_consec_sell": 0,
        "_us_flow_detail": {
            "insider_mspr": mspr,
            "inst_change_pct": inst_chg,
            "analyst_buy_ratio": round(buy / total_analysts, 2) if total_analysts > 0 else None,
            "put_call_ratio": pc_ratio,
            "short_pct": short_pct,
        },
    }
