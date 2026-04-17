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
from api.config import (
    MACRO_DGS10_DEFENSE_PCT,
    ALERT_USD_KRW_ABS_CHANGE_CRITICAL,
    ALERT_USD_KRW_ABS_CHANGE_WARNING,
    ALERT_USD_KRW_CHANGE_PCT_CRITICAL,
    ALERT_USD_KRW_CHANGE_PCT_WARNING,
    ALERT_USD_KRW_LEVEL_INFO_KRW,
)


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
    alerts.extend(_check_market_fear_greed(portfolio.get("market_fear_greed", {})))
    alerts.extend(_check_sec_risk_scan(portfolio.get("sec_risk_scan", {}), recommendations, holdings))
    alerts.extend(_check_fund_flow_rotation(portfolio.get("fund_flows", {})))
    alerts.extend(_check_cftc_cot(portfolio.get("cftc_cot", {})))
    alerts.extend(_check_holdings_risks(holdings, recommendations))
    alerts.extend(_check_earnings_proximity(recommendations))
    alerts.extend(_check_timing_opportunities(recommendations))
    alerts.extend(_check_news_urgency(headlines))
    alerts.extend(_check_event_proximity(events))
    alerts.extend(_check_sector_rotation(rotation))
    alerts.extend(_check_consensus_export_divergence(recommendations))
    alerts.extend(_check_value_chain_trade_hot(recommendations))
    alerts.extend(_check_commodity_mom_vs_portfolio(portfolio, recommendations, holdings))
    alerts.extend(_check_price_targets(recommendations))
    alerts.extend(_detect_flash_moves(macro, recommendations))
    alerts.extend(_check_macro_event_dday(events))
    alerts.extend(_check_dual_model_conflicts(portfolio, recommendations))
    alerts.extend(_check_program_trading(portfolio.get("program_trading", {})))
    alerts.extend(_check_expiry_status(portfolio.get("expiry_status", {})))
    alerts.extend(_check_geopolitical_exposure(recommendations, holdings))

    alerts = _deduplicate_and_prioritize(alerts)
    return alerts


def _deduplicate_and_prioritize(alerts: list, max_total: int = 20) -> list:
    """V5.1: 알림 중복 제거 + 카테고리별 보장 + 우선순위 정렬.

    규칙:
    1. 같은 category 내 같은 level → 최초 2개만 유지
    2. CRITICAL은 모두 보존 (최대 10개)
    3. 각 주요 카테고리에서 최소 1개 보장 (WARNING 이상)
    4. 나머지는 level 우선순위로 채움
    """
    _LEVEL_RANK = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}

    seen: dict = {}
    for a in alerts:
        cat = a.get("category", "unknown")
        lvl = a.get("level", "INFO")
        key = (cat, lvl)
        seen.setdefault(key, []).append(a)

    deduped = []
    for key, group in seen.items():
        limit = 10 if key[1] == "CRITICAL" else 2
        deduped.extend(group[:limit])

    deduped.sort(key=lambda x: _LEVEL_RANK.get(x.get("level", "INFO"), 3))

    critical = [a for a in deduped if a.get("level") == "CRITICAL"]
    warning = [a for a in deduped if a.get("level") == "WARNING"]
    info = [a for a in deduped if a.get("level") == "INFO"]

    result = list(critical)

    cats_covered = {a.get("category") for a in result}
    for a in warning:
        if a.get("category") not in cats_covered or len(result) < max_total:
            result.append(a)
            cats_covered.add(a.get("category"))

    remaining = max_total - len(result)
    if remaining > 0:
        for a in info:
            if len(result) >= max_total:
                break
            result.append(a)

    return result[:max_total]


def generate_briefing(portfolio: dict) -> dict:
    """비서의 한마디 — 지금 상황을 한 문장으로 요약"""
    alerts = generate_alerts(portfolio)
    macro = portfolio.get("macro", {})
    mood = macro.get("market_mood", {})
    holdings = portfolio.get("vams", {}).get("holdings", [])
    total_return = portfolio.get("vams", {}).get("total_return_pct", 0)

    critical = [a for a in alerts if a["level"] == "CRITICAL"]
    warnings = [a for a in alerts if a["level"] == "WARNING"]

    dual_high = [
        a for a in alerts
        if a.get("category") == "ai_consensus" and a.get("level") in ("CRITICAL", "WARNING")
    ]

    if critical:
        tone = "urgent"
        headline = critical[0]["message"]
    elif dual_high:
        tone = "cautious"
        headline = dual_high[0]["message"]
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
        if a.get("action") and a.get("level") in ("CRITICAL", "WARNING"):
            action_items.append(a["action"])

    if dual_high:
        action_items.insert(0, "Gemini·Claude 불일치 종목 우선 수동 검토")
        action_items = action_items[:4]

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


def _check_dual_model_conflicts(portfolio: dict, recommendations: list) -> list:
    """듀얼 모델 합의 상태 기반 수동검토 알림."""
    alerts = []
    dual_rows = []
    for s in recommendations:
        dc = s.get("dual_consensus")
        if isinstance(dc, dict):
            dual_rows.append((s, dc))
    if not dual_rows:
        return alerts

    manual_rows = [(s, dc) for s, dc in dual_rows if dc.get("manual_review_required")]
    high_rows = [(s, dc) for s, dc in dual_rows if dc.get("conflict_level") == "high"]
    agree_n = sum(1 for _, dc in dual_rows if dc.get("agreement"))
    agree_pct = round(agree_n / max(len(dual_rows), 1) * 100, 1)

    if manual_rows:
        names = ", ".join(s.get("name", "?") for s, _ in manual_rows[:3])
        lvl = "CRITICAL" if high_rows else "WARNING"
        alerts.append({
            "level": lvl,
            "category": "ai_consensus",
            "message": f"AI 합의 충돌 {len(manual_rows)}건 — 수동검토 필요 ({names})",
            "action": "HYBRID 카드에서 G/C 근거 확인 후 최종 수동판단",
        })

    if agree_pct < 70:
        alerts.append({
            "level": "WARNING",
            "category": "ai_consensus",
            "message": f"듀얼 모델 합의율 {agree_pct}% — 자동판단 신뢰도 점검 구간",
            "action": "충돌 high/medium 종목 중심으로 포지션 크기 축소 검토",
        })

    cv = portfolio.get("cross_verification") or {}
    w = cv.get("weights_used") or {}
    if w:
        alerts.append({
            "level": "INFO",
            "category": "ai_consensus",
            "message": f"당일 가중치 Gemini {w.get('gemini', '-')} / Claude {w.get('claude', '-')}",
            "action": "30일 리더보드 기반 자동 조정치 참고",
        })

    return alerts[:3]


def _check_market_fear_greed(mfg: dict) -> list:
    """CNN Fear & Greed 극단값 알림."""
    alerts = []
    if not mfg.get("ok"):
        return alerts
    val = mfg.get("value", 50)
    chg = mfg.get("change_1d")
    desc = mfg.get("description_kr", "")
    if val <= 20:
        alerts.append({
            "level": "WARNING",
            "category": "market_sentiment",
            "message": f"CNN Fear & Greed {val} ({desc}) — 극도 공포 구간, 역발상 매수 기회 탐색",
            "action": "패닉 구간 우량주 관심 목록 검토",
        })
    elif val >= 80:
        alerts.append({
            "level": "WARNING",
            "category": "market_sentiment",
            "message": f"CNN Fear & Greed {val} ({desc}) — 극도 탐욕 구간, 차익 실현 고려",
            "action": "수익 실현 및 현금 비중 확대 검토",
        })
    if chg is not None and abs(chg) >= 15:
        direction = "급등" if chg > 0 else "급락"
        alerts.append({
            "level": "INFO",
            "category": "market_sentiment",
            "message": f"시장 심리 {direction}: F&G {chg:+.0f}pt (전일 대비)",
            "action": "시장 심리 급변 모니터링",
        })
    return alerts


def _check_sec_risk_scan(risk_scan: dict, recommendations: list, holdings: list) -> list:
    """SEC 8-K 리스크 키워드 스캔 결과 중 보유/추천 종목 매칭 알림."""
    alerts = []
    if not risk_scan.get("ok"):
        return alerts

    port_tickers = set()
    for r in recommendations:
        t = r.get("ticker", "")
        if t:
            port_tickers.add(t.upper())
    for h in holdings:
        t = str(h.get("ticker", ""))
        if t:
            port_tickers.add(t.upper())

    for f in risk_scan.get("filings", []):
        ft = (f.get("ticker") or "").upper()
        if ft and ft in port_tickers:
            kw = f.get("keyword_matched", "")
            company = f.get("company", ft)
            level = "CRITICAL" if kw in ("going concern", "material weakness", "restatement") else "WARNING"
            alerts.append({
                "level": level,
                "category": "sec_risk",
                "message": f"SEC 8-K 리스크: {company} ({ft}) — \"{kw}\" 공시 감지 ({f.get('filed_date', '')})",
                "action": f"{ft} 공시 원문 확인 후 포지션 재검토",
            })
    return alerts[:5]


def _check_fund_flow_rotation(fund_flows: dict) -> list:
    """펀드 플로우 로테이션 시그널 알림."""
    alerts = []
    if not fund_flows.get("ok"):
        return alerts
    rot = fund_flows.get("rotation_signal", "neutral")
    detail = fund_flows.get("rotation_detail", {})
    conf = detail.get("confidence", 0)

    if rot == "cash_flight" and conf >= 50:
        alerts.append({
            "level": "WARNING",
            "category": "fund_flow",
            "message": f"자금 이탈: 주식·채권 동반 유출 (확신도 {conf}%) — 현금 비중 확대 고려",
            "action": "방어적 포지션 전환 검토",
        })
    elif rot == "risk_off" and conf >= 50:
        alerts.append({
            "level": "INFO",
            "category": "fund_flow",
            "message": f"리스크 오프: 안전자산·채권 유입 우위 (확신도 {conf}%)",
            "action": "안전자산 비중 점검",
        })
    return alerts


def _check_cftc_cot(cot_data: dict) -> list:
    """CFTC COT 기관 포지셔닝 극단값 알림."""
    alerts = []
    if not cot_data.get("ok"):
        return alerts
    summary = cot_data.get("summary", {})
    sig = summary.get("overall_signal", "neutral")
    conv = summary.get("conviction_level", 0)

    if sig == "bearish" and conv >= 60:
        alerts.append({
            "level": "WARNING",
            "category": "institutional_positioning",
            "message": f"CFTC COT: 기관 순매도 포지션 강화 (확신도 {conv}%)",
            "action": "기관 약세 전환 모니터링, 추격 매수 자제",
        })
    elif sig == "bullish" and conv >= 70:
        alerts.append({
            "level": "INFO",
            "category": "institutional_positioning",
            "message": f"CFTC COT: 기관 순매수 포지션 확대 (확신도 {conv}%)",
            "action": "기관 강세 시그널 참고",
        })
    return alerts


def _check_macro_risks(macro: dict) -> list:
    alerts = []
    fred = macro.get("fred") or {}
    dgs = fred.get("dgs10") or {}
    dgs_v = dgs.get("value")
    if dgs_v is not None and float(dgs_v) >= MACRO_DGS10_DEFENSE_PCT:
        alerts.append({
            "level": "CRITICAL",
            "category": "macro",
            "message": (
                f"FRED DGS10 {float(dgs_v):.2f}% (≥{MACRO_DGS10_DEFENSE_PCT}%) — "
                "금리 방패 구간, 신규 매수 자제·현금 비중 확대"
            ),
            "action": "브레인 등급 관망 상한 적용 중 — 방어 우선",
        })
    elif dgs.get("change_5d_pp") is not None and float(dgs["change_5d_pp"]) >= 0.15:
        alerts.append({
            "level": "WARNING",
            "category": "macro",
            "message": f"FRED DGS10 5영업일 +{float(dgs['change_5d_pp']):.2f}%p 급등 — 금리 모멘텀 점검",
            "action": "멀티팩터 펀더멘털 감점 반영 구간",
        })

    rp = fred.get("us_recession_smoothed_prob") or {}
    rp_v = rp.get("pct")
    if rp_v is not None:
        rpv = float(rp_v)
        if rpv >= 35:
            alerts.append({
                "level": "CRITICAL",
                "category": "macro",
                "message": f"FRED 리세션 스무딩 확률 {rpv:.1f}% — 미국 경기 하방·포트 방어",
                "action": "현금·저변동·대내수 비중 점검",
            })
        elif rpv >= 18:
            alerts.append({
                "level": "WARNING",
                "category": "macro",
                "message": f"FRED 리세션 스무딩 확률 {rpv:.1f}% — 선제 시나리오 점검",
                "action": "수출·IT 사이클 민감 종목 비중 조절",
            })

    vix_c = fred.get("vix_close") or {}
    if vix_c.get("change_5d") is not None and float(vix_c["change_5d"]) >= 5:
        alerts.append({
            "level": "WARNING",
            "category": "macro",
            "message": f"FRED VIXCLS 5영업일 +{float(vix_c['change_5d']):.1f}pt — 공포 지수 급등",
            "action": "신규 진입·레버리지 자제",
        })

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
    usd_val = usd.get("value", 0) or 0
    usd_abs_chg = usd.get("change", 0) or 0
    usd_pct_chg = usd.get("change_pct", 0) or 0
    try:
        usd_val = float(usd_val)
        usd_abs_chg = float(usd_abs_chg)
        usd_pct_chg = float(usd_pct_chg)
    except (TypeError, ValueError):
        usd_val = usd_abs_chg = usd_pct_chg = 0.0

    move_any = abs(usd_abs_chg) > 0.01 or abs(usd_pct_chg) > 0.001
    if move_any:
        if (
            abs(usd_pct_chg) >= ALERT_USD_KRW_CHANGE_PCT_CRITICAL
            or abs(usd_abs_chg) >= ALERT_USD_KRW_ABS_CHANGE_CRITICAL
        ):
            alerts.append({
                "level": "CRITICAL",
                "category": "macro",
                "message": (
                    f"원달러 급변 — {usd_val:,.2f}원 (전일대비 {usd_abs_chg:+.2f}원, {usd_pct_chg:+.2f}%) "
                    "수입물가·외환 리스크 점검"
                ),
                "action": "환헤지·원자재·수입 비중 높은 종목 즉시 점검",
            })
        elif (
            abs(usd_pct_chg) >= ALERT_USD_KRW_CHANGE_PCT_WARNING
            or abs(usd_abs_chg) >= ALERT_USD_KRW_ABS_CHANGE_WARNING
        ):
            alerts.append({
                "level": "WARNING",
                "category": "macro",
                "message": (
                    f"원달러 변동 확대 — {usd_val:,.2f}원 ({usd_abs_chg:+.2f}원, {usd_pct_chg:+.2f}%)"
                ),
                "action": "수출·수입주 환율 민감도 확인",
            })

    if (
        usd_val > 0
        and usd_val >= ALERT_USD_KRW_LEVEL_INFO_KRW
        and not (
            abs(usd_pct_chg) >= ALERT_USD_KRW_CHANGE_PCT_WARNING
            or abs(usd_abs_chg) >= ALERT_USD_KRW_ABS_CHANGE_WARNING
        )
    ):
        alerts.append({
            "level": "INFO",
            "category": "macro",
            "message": (
                f"원달러 {usd_val:,.0f}원대 — 고환율 수준(참고). 급변 알림은 전일대비 변동 기준"
            ),
            "action": None,
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


# ─── Phase 4 확장: 목표가/급등락/이벤트 알림 ──────────────

def _check_price_targets(recommendations: list) -> list:
    """목표가 도달/근접/급락 알림."""
    alerts = []
    for r in recommendations:
        price = r.get("price") or r.get("current_price")
        target = r.get("target_price") or (r.get("consensus", {}).get("target_price"))
        name = r.get("name", "?")
        if not price or not target:
            continue
        try:
            price = float(price)
            target = float(target)
        except (TypeError, ValueError):
            continue
        if price <= 0 or target <= 0:
            continue

        ratio = price / target
        if ratio >= 1.0:
            alerts.append({
                "level": "WARNING",
                "category": "price_target",
                "message": f"{name} 목표가 {target:,.0f}원 도달 (현재 {price:,.0f}원)",
                "action": "차익 실현 또는 목표가 상향 여부 검토",
            })
        elif ratio >= 0.9:
            alerts.append({
                "level": "INFO",
                "category": "price_target",
                "message": f"{name} 목표가 90% 근접 ({price:,.0f} / {target:,.0f}원)",
                "action": "분할 매도 또는 홀딩 전략 점검",
            })

        entry = r.get("entry_price") or r.get("avg_buy_price")
        if entry:
            try:
                entry = float(entry)
                drop = (price - entry) / entry * 100
                if drop <= -10:
                    alerts.append({
                        "level": "CRITICAL",
                        "category": "stop_loss",
                        "message": f"{name} 매입가 대비 {drop:+.1f}% 하락 ({price:,.0f} / 매입 {entry:,.0f}원)",
                        "action": "손절 또는 비중 축소 즉시 검토",
                    })
            except (TypeError, ValueError):
                pass
    return alerts


def _detect_flash_moves(macro: dict, recommendations: list) -> list:
    """급등락 감지 (VIX 급등 + 종목 급변)."""
    alerts = []

    vix = macro.get("vix", {})
    vix_val = vix.get("value", 0)
    vix_chg = vix.get("change_pct", 0)
    # VIX 절대 수준은 _check_macro_risks에서 처리 → 여기서는 "변화율"만 체크 (중복 방지)
    if vix_chg >= 20 and vix_val <= 35:
        alerts.append({
            "level": "CRITICAL",
            "category": "flash_move",
            "message": f"VIX {vix_val} (일내 +{vix_chg:.1f}%) — 시장 공포 급등",
            "action": "신규 매수 중단, 현금 비중 확대, 손절 라인 점검",
        })

    sp_chg = macro.get("sp500", {}).get("change_pct", 0)
    nq_chg = macro.get("nasdaq", {}).get("change_pct", 0)
    if sp_chg <= -3 or nq_chg <= -3:
        alerts.append({
            "level": "CRITICAL",
            "category": "flash_move",
            "message": f"미장 급락 — S&P {sp_chg:+.1f}%, 나스닥 {nq_chg:+.1f}%",
            "action": "국내 시장 갭다운 대비. 보유 종목 손절 라인 재확인",
        })

    for r in recommendations:
        chg = r.get("change_pct") or r.get("day_change_pct")
        name = r.get("name", "?")
        if chg is None:
            continue
        try:
            chg = float(chg)
        except (TypeError, ValueError):
            continue
        if chg >= 10:
            alerts.append({
                "level": "WARNING",
                "category": "flash_move",
                "message": f"{name} 급등 +{chg:.1f}% — 과열 주의",
                "action": "분할 매도 또는 추가 매수 자제",
            })
        elif chg <= -8:
            alerts.append({
                "level": "WARNING",
                "category": "flash_move",
                "message": f"{name} 급락 {chg:+.1f}% — 하방 리스크",
                "action": "원인 파악 후 손절/추매 결정",
            })

    return alerts


def _check_macro_event_dday(events: list) -> list:
    """매크로 이벤트 D-day/전일 알림."""
    alerts = []
    now = datetime.now()

    for ev in (events or []):
        date_str = ev.get("date") or ev.get("event_date")
        name = ev.get("name") or ev.get("event", "이벤트")
        if not date_str:
            continue
        try:
            d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            continue

        days = (d.date() - now.date()).days
        impact = ev.get("impact") or ev.get("severity") or "medium"

        if days == 0:
            level = "CRITICAL" if impact in ("high", "critical") else "WARNING"
            alerts.append({
                "level": level,
                "category": "macro_event",
                "message": f"오늘 {name} 발표",
                "action": "발표 전후 변동성 주의. 포지션 축소 검토",
            })
        elif days == 1:
            alerts.append({
                "level": "WARNING",
                "category": "macro_event",
                "message": f"내일 {name} 발표 (D-1)",
                "action": "발표 전 포지션 정리 또는 헷지 검토",
            })
        elif 2 <= days <= 3 and impact in ("high", "critical"):
            alerts.append({
                "level": "INFO",
                "category": "macro_event",
                "message": f"{name} D-{days} (중요도 높음)",
                "action": "이벤트 대비 전략 수립",
            })

    return alerts


def _check_program_trading(prog: dict) -> list:
    """프로그램 매매동향 기반 알림."""
    alerts = []
    if not prog or not prog.get("ok", False):
        return alerts

    if prog.get("sell_bomb"):
        alerts.append({
            "level": "CRITICAL",
            "category": "program_trading",
            "message": (
                f"프로그램 매도 폭탄: 비차익 {prog.get('non_arb_net_bn', 0):+,.0f}억"
                f" / 총 {prog.get('total_net_bn', 0):+,.0f}억"
            ),
            "action": f"추격 매수 즉시 중지 / 신규 포지션 금지. 사유: {prog.get('sell_bomb_reason', '')}",
        })
    elif prog.get("signal") in ("STRONG_SELL_PRESSURE", "SELL_PRESSURE"):
        alerts.append({
            "level": "WARNING",
            "category": "program_trading",
            "message": (
                f"프로그램 매도 우세: 비차익 {prog.get('non_arb_net_bn', 0):+,.0f}억"
                f" / 총 {prog.get('total_net_bn', 0):+,.0f}억"
            ),
            "action": "단기 매수 자제, 프로그램 수급 추이 확인 필요",
        })
    elif prog.get("signal") == "STRONG_BUY_PRESSURE":
        alerts.append({
            "level": "INFO",
            "category": "program_trading",
            "message": f"프로그램 매수 우세: 총 순매수 {prog.get('total_net_bn', 0):+,.0f}억",
            "action": "프로그램 매수 유입 지속 시 단기 상승 동력",
        })

    return alerts


def _check_expiry_status(expiry: dict) -> list:
    """만기일 캘린더 기반 알림."""
    alerts = []
    if not expiry:
        return alerts

    watch_level = expiry.get("watch_level", "NORMAL")
    reason = expiry.get("reason")

    if watch_level == "FULL_WATCH":
        alerts.append({
            "level": "CRITICAL",
            "category": "expiry",
            "message": f"만기일 관망: {reason}",
            "action": "BUY → WATCH 강등 적용. 추격매수 완전 중지, 기존 포지션 축소 검토",
        })
    elif watch_level == "CAUTION":
        alerts.append({
            "level": "WARNING",
            "category": "expiry",
            "message": f"만기일 주의: {reason}",
            "action": "신규 진입 자제, 기존 포지션 유지. 포지션 한도 50% 적용",
        })

    return alerts


# ─── 지정학 노출 (DART 사업보고서 파싱 결과 기반) ─────────

_SANCTION_ZONES = {"RU": "러시아", "IR": "이란", "KP": "북한", "SY": "시리아", "VE": "베네수엘라"}
_TARIFF_HIGH_ZONES = {"CN": "중국"}
_TAIWAN_RISK = {"TW": "대만"}


def _check_geopolitical_exposure(recommendations: list, holdings: list) -> list:
    """
    DART 사업보고서 파싱으로 얻은 국가별 노출을 기반으로 지정학 리스크 알림.
    - CN > 40%: 관세·디커플링 리스크 CRITICAL
    - CN > 25%: WARNING
    - TW > 20%: 양안 리스크 WARNING
    - 제재 지역(RU/IR 등) 5%+: CRITICAL
    - 포트폴리오 차원 중국 고노출 종목 3개↑: 집중 경보
    """
    alerts: list = []
    hi_cn: list = []
    hold_tickers = {str(h.get("ticker", "")) for h in (holdings or []) if h.get("ticker")}

    for s in recommendations or []:
        fac_data = (s.get("facilities_dart") or {}).get("data") or {}
        exp = fac_data.get("country_exposure") or {}
        if not isinstance(exp, dict) or not exp:
            continue
        name = s.get("name", s.get("ticker", "?"))
        ticker = str(s.get("ticker", ""))
        is_holding = ticker in hold_tickers

        def _f(key: str) -> float:
            try:
                return float(exp.get(key) or 0)
            except (TypeError, ValueError):
                return 0.0

        cn = _f("CN")
        tw = _f("TW")

        sanctioned_pct = 0.0
        sanctioned_zones: list[str] = []
        for code, label in _SANCTION_ZONES.items():
            v = _f(code)
            if v >= 3:
                sanctioned_pct += v
                sanctioned_zones.append(f"{label} {v:.0f}%")

        if sanctioned_zones:
            alerts.append({
                "level": "CRITICAL",
                "category": "geopolitical",
                "message": f"{name}: 제재 지역 노출 — {', '.join(sanctioned_zones)} (공시·제재 리스크)",
                "action": f"{name} 해당 지역 매출·자산 비중 즉시 확인",
            })

        if cn >= 40:
            lvl = "CRITICAL" if is_holding else "WARNING"
            tag = " · 보유 종목" if is_holding else ""
            alerts.append({
                "level": lvl,
                "category": "geopolitical",
                "message": f"{name}: 중국 노출 {cn:.0f}%{tag} — 관세·디커플링 고위험",
                "action": "중국 의존 매출·생산 비중 점검 및 헤지 검토",
            })
            hi_cn.append((name, cn, is_holding))
        elif cn >= 25:
            alerts.append({
                "level": "WARNING",
                "category": "geopolitical",
                "message": f"{name}: 중국 노출 {cn:.0f}% — 관세 민감 구간",
                "action": "분기 매출 믹스·현지 생산 이전 동향 모니터링",
            })
            hi_cn.append((name, cn, is_holding))

        if tw >= 20:
            alerts.append({
                "level": "WARNING",
                "category": "geopolitical",
                "message": f"{name}: 대만 노출 {tw:.0f}% — 양안 리스크 주의",
                "action": "공급망 대체선 확보·재고 수준 점검",
            })

    # 포트폴리오 차원 중국 집중
    if len(hi_cn) >= 3:
        hi_cn_sorted = sorted(hi_cn, key=lambda x: -x[1])
        hold_n = sum(1 for _, _, h in hi_cn if h)
        top = ", ".join(f"{n}({p:.0f}%)" for n, p, _ in hi_cn_sorted[:3])
        hold_note = f" (보유 {hold_n}종목 포함)" if hold_n else ""
        alerts.append({
            "level": "WARNING" if hold_n else "INFO",
            "category": "geopolitical",
            "message": f"포트 중국 고노출 {len(hi_cn)}종목{hold_note}: {top}",
            "action": "섹터·국가 분산 리밸런싱 검토",
        })

    return alerts[:8]


def build_geopolitical_hotspots(recommendations: list, holdings: list) -> dict:
    """
    포트폴리오 레벨 지정학 노출 요약을 briefing에 노출할 수 있는 dict로 집계.
    """
    hold_tickers = {str(h.get("ticker", "")) for h in (holdings or []) if h.get("ticker")}
    per_country: dict[str, float] = {}
    per_country_count: dict[str, int] = {}
    top_cn: list[dict] = []
    top_sanctioned: list[dict] = []
    covered = 0

    for s in recommendations or []:
        fac = (s.get("facilities_dart") or {}).get("data") or {}
        exp = fac.get("country_exposure") or {}
        if not isinstance(exp, dict) or not exp:
            continue
        covered += 1
        name = s.get("name", s.get("ticker", "?"))
        ticker = str(s.get("ticker", ""))
        is_hold = ticker in hold_tickers

        for k, v in exp.items():
            try:
                vv = float(v)
            except (TypeError, ValueError):
                continue
            if vv <= 0:
                continue
            per_country[k] = per_country.get(k, 0.0) + vv
            per_country_count[k] = per_country_count.get(k, 0) + 1

        try:
            cn = float(exp.get("CN") or 0)
        except (TypeError, ValueError):
            cn = 0.0
        if cn >= 25:
            top_cn.append({"name": name, "ticker": ticker, "pct": cn, "is_holding": is_hold})

        for code, label in _SANCTION_ZONES.items():
            try:
                v = float(exp.get(code) or 0)
            except (TypeError, ValueError):
                v = 0.0
            if v >= 3:
                top_sanctioned.append({
                    "name": name, "ticker": ticker,
                    "zone": label, "code": code, "pct": v, "is_holding": is_hold,
                })

    avg_country = [
        {
            "code": k,
            "avg_pct": round(per_country[k] / per_country_count[k], 1),
            "company_count": per_country_count[k],
        }
        for k in per_country
    ]
    avg_country.sort(key=lambda x: -x["avg_pct"])

    top_cn.sort(key=lambda x: -x["pct"])
    top_sanctioned.sort(key=lambda x: -x["pct"])

    return {
        "covered_companies": covered,
        "country_avg_exposure": avg_country[:10],
        "china_high_exposure": top_cn[:10],
        "sanctioned_exposure": top_sanctioned[:10],
    }
