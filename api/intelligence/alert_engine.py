"""
VERITY 능동 알림 엔진 — "비서의 두뇌"

모든 수집 데이터(매크로, 기술적, 뉴스, 수급, 예측, 실적, 섹터)를
통합 분석하여 사용자에게 "지금 알아야 할 것"을 우선순위로 생성.

알림 레벨:
  CRITICAL (즉시 행동) — 손절, VIX 폭등, 실적 D-1
  WARNING  (주의 필요) — 과매수/과매도, 환율 급변, 실적 D-3
  INFO     (참고)      — 섹터 전환, 신규 매수 기회
"""
from datetime import datetime, timedelta

from api.analyzers.commodity_narrator import narrative_for_commodity


def generate_alerts(portfolio: dict) -> list:
    """포트폴리오 전체 데이터를 분석하여 프로액티브 알림 리스트 생성"""
    alerts = []

    macro = portfolio.get("macro", {})
    recommendations = portfolio.get("recommendations", [])
    holdings = portfolio.get("vams", {}).get("holdings", [])
    sectors = portfolio.get("sectors", [])
    rotation = portfolio.get("sector_rotation", {})
    headlines = portfolio.get("headlines", [])
    events = portfolio.get("global_events", [])

    alerts.extend(_check_macro_risks(macro))
    alerts.extend(_check_holdings_risks(holdings, recommendations))
    alerts.extend(_check_earnings_proximity(recommendations))
    alerts.extend(_check_timing_opportunities(recommendations))
    alerts.extend(_check_news_urgency(headlines))
    alerts.extend(_check_event_proximity(events))
    alerts.extend(_check_sector_rotation(rotation))
    alerts.extend(_check_consensus_export_divergence(recommendations))
    alerts.extend(_check_value_chain_trade_hot(recommendations))
    alerts.extend(_check_commodity_mom_vs_portfolio(portfolio, recommendations, holdings))

    alerts.sort(key=lambda x: {"CRITICAL": 0, "WARNING": 1, "INFO": 2}.get(x["level"], 3))

    return alerts[:10]


def generate_briefing(portfolio: dict) -> dict:
    """비서의 한마디 — 지금 상황을 한 문장으로 요약"""
    alerts = generate_alerts(portfolio)
    macro = portfolio.get("macro", {})
    mood = macro.get("market_mood", {})
    holdings = portfolio.get("vams", {}).get("holdings", [])
    total_return = portfolio.get("vams", {}).get("total_return_pct", 0)

    critical = [a for a in alerts if a["level"] == "CRITICAL"]
    warnings = [a for a in alerts if a["level"] == "WARNING"]

    if critical:
        tone = "urgent"
        headline = critical[0]["message"]
    elif warnings:
        tone = "cautious"
        headline = warnings[0]["message"]
    elif mood.get("score", 50) >= 65:
        tone = "positive"
        headline = f"시장 분위기 {mood.get('label', '양호')} — 보유 종목 모니터링 유지"
    elif mood.get("score", 50) <= 35:
        tone = "defensive"
        headline = f"시장 분위기 {mood.get('label', '비관')} — 방어적 포지션 유지 권고"
    else:
        tone = "neutral"
        headline = "특이사항 없음 — 기존 전략 유지"

    action_items = []
    for a in alerts[:3]:
        if a.get("action"):
            action_items.append(a["action"])

    return {
        "headline": headline,
        "tone": tone,
        "alerts": alerts,
        "action_items": action_items,
        "portfolio_status": f"총자산 수익률 {total_return:+.1f}% | 보유 {len(holdings)}종목",
        "alert_counts": {
            "critical": len(critical),
            "warning": len(warnings),
            "info": len(alerts) - len(critical) - len(warnings),
        },
    }


def _check_macro_risks(macro: dict) -> list:
    alerts = []
    vix = macro.get("vix", {}).get("value", 0)
    vix_chg = macro.get("vix", {}).get("change_pct", 0)

    if vix > 35:
        alerts.append({
            "level": "CRITICAL",
            "category": "macro",
            "message": f"VIX {vix} — 시장 극도 공포. 신규 매수 자제, 현금 확보 우선",
            "action": "신규 매수 중단, 현금 비중 50% 이상 유지",
        })
    elif vix > 28:
        alerts.append({
            "level": "WARNING",
            "category": "macro",
            "message": f"VIX {vix} — 변동성 확대 구간. 보수적 접근 필요",
            "action": "손절선 점검, 추가 매수 보류",
        })

    if vix_chg > 15:
        alerts.append({
            "level": "CRITICAL",
            "category": "macro",
            "message": f"VIX 일일 {vix_chg:+.1f}% 급등 — 패닉 매도 가능성",
            "action": "보유 종목 손절선 즉시 점검",
        })

    usd = macro.get("usd_krw", {})
    usd_val = usd.get("value", 0)
    if usd_val > 1450:
        alerts.append({
            "level": "WARNING",
            "category": "macro",
            "message": f"원달러 {usd_val:,.0f}원 — 원화 약세 심화. 수출주 주목, 수입주 경계",
            "action": "자동차·반도체 등 수출 비중 높은 종목 관심",
        })

    spread = macro.get("yield_spread", {}).get("value", 1)
    if spread is not None and spread < 0:
        alerts.append({
            "level": "WARNING",
            "category": "macro",
            "message": f"장단기 금리 역전({spread}%p) — 경기침체 선행 신호 감지",
            "action": "방어주(유틸리티/헬스케어) 비중 확대 고려",
        })

    sp_chg = macro.get("sp500", {}).get("change_pct", 0)
    nq_chg = macro.get("nasdaq", {}).get("change_pct", 0)
    if sp_chg < -2 or nq_chg < -2:
        alerts.append({
            "level": "WARNING",
            "category": "macro",
            "message": f"미국증시 급락 (S&P {sp_chg:+.1f}%, 나스닥 {nq_chg:+.1f}%) — 갭하락 경계",
            "action": "장 초반 매수 자제, 오후 안정 후 대응",
        })

    return alerts


def _check_holdings_risks(holdings: list, recommendations: list) -> list:
    alerts = []
    rec_map = {r["ticker"]: r for r in recommendations}

    for h in holdings:
        ret = h.get("return_pct", 0)
        name = h.get("name", h.get("ticker", "?"))
        ticker = h.get("ticker", "")

        if ret <= -7:
            alerts.append({
                "level": "CRITICAL",
                "category": "holding",
                "message": f"{name} 수익률 {ret:+.1f}% — 손절선 접근. 즉시 점검 필요",
                "action": f"{name} 매도 여부 결정 필요",
            })
        elif ret <= -4:
            alerts.append({
                "level": "WARNING",
                "category": "holding",
                "message": f"{name} 수익률 {ret:+.1f}% — 하락 추세. 추가 매수 보류",
                "action": f"{name} 반등 시그널 확인 후 대응",
            })

        rec = rec_map.get(ticker, {})
        timing = rec.get("timing", {})
        ts = timing.get("timing_score", 50)
        if ts <= 25 and ret < 0:
            alerts.append({
                "level": "CRITICAL",
                "category": "holding",
                "message": f"{name} 타이밍 {ts}점 + 손실 {ret:+.1f}% — 매도 강력 권고",
                "action": f"{name} 즉시 매도 검토",
            })

    return alerts


def _check_earnings_proximity(recommendations: list) -> list:
    alerts = []
    now = datetime.now()

    for stock in recommendations:
        earnings = stock.get("earnings", {})
        next_date_str = earnings.get("next_earnings")
        if not next_date_str:
            continue

        try:
            next_date = datetime.strptime(next_date_str[:10], "%Y-%m-%d")
            days_until = (next_date - now).days

            name = stock.get("name", stock.get("ticker", "?"))

            if 0 <= days_until <= 1:
                alerts.append({
                    "level": "CRITICAL",
                    "category": "earnings",
                    "message": f"{name} 실적발표 D-{days_until} — 변동성 최대 구간",
                    "action": f"{name} 실적 발표 전 비중 조절 필수",
                })
            elif 2 <= days_until <= 3:
                alerts.append({
                    "level": "WARNING",
                    "category": "earnings",
                    "message": f"{name} 실적발표 D-{days_until} — 변동성 확대 주의",
                    "action": f"{name} 신규 매수 보류, 기존 보유분 점검",
                })
            elif 4 <= days_until <= 7:
                alerts.append({
                    "level": "INFO",
                    "category": "earnings",
                    "message": f"{name} 실적발표 D-{days_until} — 실적 기대감/우려 선반영 가능",
                    "action": None,
                })
        except (ValueError, TypeError):
            continue

    return alerts


def _check_timing_opportunities(recommendations: list) -> list:
    alerts = []

    strong_buys = [
        s for s in recommendations
        if s.get("timing", {}).get("action") == "STRONG_BUY"
        and s.get("multi_factor", {}).get("multi_score", 0) >= 60
    ]

    if strong_buys:
        names = ", ".join(s["name"] for s in strong_buys[:3])
        alerts.append({
            "level": "INFO",
            "category": "opportunity",
            "message": f"강한 매수 시그널: {names} — 기술적+AI 모두 긍정",
            "action": f"분할 매수 고려 ({names})",
        })

    oversold = [
        s for s in recommendations
        if s.get("technical", {}).get("rsi", 50) <= 30
        and s.get("prediction", {}).get("up_probability", 50) >= 55
    ]

    for s in oversold[:2]:
        alerts.append({
            "level": "INFO",
            "category": "opportunity",
            "message": f"{s['name']} RSI {s['technical']['rsi']} 과매도 + AI 상승확률 {s['prediction']['up_probability']}%",
            "action": f"{s['name']} 반등 매수 타이밍 모니터링",
        })

    return alerts


def _check_news_urgency(headlines: list) -> list:
    alerts = []
    neg_urgent = [
        h for h in headlines
        if h.get("sentiment") == "negative" and h.get("urgency", 0) >= 0.7
    ]

    if len(neg_urgent) >= 3:
        alerts.append({
            "level": "WARNING",
            "category": "news",
            "message": f"긴급 악재 뉴스 {len(neg_urgent)}건 — 시장 전반 리스크 확대",
            "action": "신규 매수 자제, 뉴스 동향 모니터링",
        })
    elif neg_urgent:
        alerts.append({
            "level": "INFO",
            "category": "news",
            "message": f"악재 뉴스 감지: {neg_urgent[0]['title'][:40]}...",
            "action": None,
        })

    return alerts


def _check_event_proximity(events: list) -> list:
    alerts = []
    now = datetime.now()

    for ev in events:
        try:
            ev_date = datetime.strptime(ev["date"][:10], "%Y-%m-%d")
            days = (ev_date - now).days
            if 0 <= days <= 2:
                alerts.append({
                    "level": "WARNING",
                    "category": "event",
                    "message": f"{ev['name']} D-{days} — {ev.get('impact', '시장 변동성 확대 예상')}",
                    "action": ev.get("action", "관련 포지션 점검"),
                })
            elif 3 <= days <= 5:
                alerts.append({
                    "level": "INFO",
                    "category": "event",
                    "message": f"{ev['name']} D-{days} — {ev.get('impact', '사전 대비 권고')}",
                    "action": None,
                })
        except (ValueError, TypeError, KeyError):
            continue

    return alerts


def _check_value_chain_trade_hot(recommendations: list) -> list:
    """밸류체인 시드 종목이 trade_analysis(거래대금 상위 스캔) 유니버스와 겹칠 때 참고 알림."""
    alerts = []
    for stock in recommendations:
        vc = stock.get("value_chain") or {}
        if not vc.get("active"):
            continue
        bonus = int(vc.get("score_bonus") or 0)
        name = stock.get("name", stock.get("ticker", "?"))
        roles = vc.get("roles") or []
        labels = [r.get("node_label_ko") for r in roles if r.get("node_label_ko")]
        label_part = ", ".join(dict.fromkeys(labels)) if labels else "밸류체인"
        alerts.append({
            "level": "INFO",
            "category": "value_chain",
            "message": (
                f"{name}: {label_part} 노드 + 거래대금 상위 스캔 종목 교차 — "
                f"멀티팩터 가산 +{bonus} 반영됨"
            ),
            "action": None,
        })
    return alerts[:8]


def _check_consensus_export_divergence(recommendations: list) -> list:
    """컨센서스 낙관 vs 관세청 수출 약화 괴리."""
    alerts = []
    for stock in recommendations:
        name = stock.get("name", stock.get("ticker", "?"))
        for w in stock.get("consensus", {}).get("warnings", []):
            if "기관 낙관 주의" not in w:
                continue
            alerts.append({
                "level": "WARNING",
                "category": "consensus",
                "message": f"{name}: {w}",
                "action": "실적·수출·가이던스 교차 검증 권고",
            })
    return alerts


def get_commodity_daily_footer(portfolio: dict) -> str:
    """일일 리포트/텔레그램 하단 — 원자재 한 줄 (서술 우선, 없으면 수치만)."""
    ci = portfolio.get("commodity_impact") or {}
    lines = ci.get("narrative_lines") or []
    if lines and lines[0]:
        return str(lines[0])
    rows = ci.get("commodity_mom_alerts") or []
    if not rows:
        return ""
    top = rows[0]
    t = top.get("commodity_ticker", "?")
    p = top.get("vs_prior_month_avg_pct")
    if p is None:
        return ""
    return (
        f"원자재: {t} 전월평균 대비 {float(p):+.1f}% "
        f"(긴급 알림 임계 ±{ci.get('mom_alert_threshold_pct', 10)}%)"
    )


def _check_commodity_mom_vs_portfolio(
    portfolio: dict,
    recommendations: list,
    holdings: list,
) -> list:
    """
    전월 평균 대비 원자재 급변(기본 10%+)일 때만 알림.
    보유·추천 종목이 해당 원자재와 연동된 경우 메시지에 표시.
    """
    alerts = []
    ci = portfolio.get("commodity_impact") or {}
    rows = ci.get("commodity_mom_alerts") or []
    if not rows:
        return alerts

    rec_map = {str(r.get("ticker", "")).zfill(6): r for r in recommendations}
    hold_names = {str(h.get("ticker", "")).zfill(6): h.get("name", "") for h in holdings}

    for top in rows[:5]:
        ct = top.get("commodity_ticker")
        pct = top.get("vs_prior_month_avg_pct")
        if ct is None or pct is None:
            continue
        abs_p = abs(float(pct))
        th = float(ci.get("mom_alert_threshold_pct") or 10)
        if abs_p < th:
            continue

        linked = []
        by_t = ci.get("by_ticker") or {}
        for tid, block in by_t.items():
            pr = (block or {}).get("primary") or {}
            if pr.get("commodity_ticker") != ct:
                continue
            name = rec_map.get(tid, {}).get("name") or hold_names.get(tid) or tid
            linked.append(name)

        msg = (
            f"원자재 {ct} 전월 평균 대비 {float(pct):+.1f}% — "
            f"원가·마진 점검 구간"
        )
        if linked:
            msg += f" (연동 종목: {', '.join(linked[:4])})"

        story = narrative_for_commodity(ci, ct)
        if story:
            msg = f"{story}"

        level = "CRITICAL" if abs_p >= th * 1.5 else "WARNING"
        alerts.append({
            "level": level,
            "category": "commodity",
            "message": msg,
            "action": "해당 섹터 마진·판가전이(컨센서스) 교차 확인",
        })

    return alerts


def _check_sector_rotation(rotation: dict) -> list:
    alerts = []
    cycle = rotation.get("cycle_label")
    if not cycle:
        return alerts

    recommended = rotation.get("recommended_sectors", [])
    if recommended:
        top_names = ", ".join(s["name"] for s in recommended[:3])
        alerts.append({
            "level": "INFO",
            "category": "strategy",
            "message": f"현재 {cycle} — 추천 섹터: {top_names}",
            "action": f"포트폴리오 내 {cycle} 우호 섹터 비중 점검",
        })

    return alerts
