"""
텔레그램 알림 모듈
- 손절/매수 알림
- 일일 리포트 전송
"""
import requests
from typing import Any, Dict, List, Optional

from api.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, now_kst
from api.intelligence.alert_engine import get_commodity_daily_footer


def _html_escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def send_message(text: str) -> bool:
    """텔레그램 메시지 전송"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[Telegram] 토큰/챗ID 미설정 → 콘솔 출력:\n{text}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("[Telegram] 메시지 전송 성공")
            return True
        else:
            print(f"[Telegram] 전송 실패: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"[Telegram] 오류: {e}")
        return False


def send_alerts(alerts: list[dict]) -> bool:
    """알림 목록 전송. 성공 시 True (토큰 미설정 시 콘솔만이면 False)."""
    if not alerts:
        return False

    lines = ["<b>🔔 안심 AI 비서 알림</b>\n"]
    for alert in alerts:
        lines.append(alert["message"])

    return send_message("\n".join(lines))


def send_daily_report(portfolio: dict):
    """일일 요약 리포트 + 비서 브리핑 전송"""
    briefing = portfolio.get("briefing", {})
    vams = portfolio.get("vams", {})
    total = vams.get("total_asset", 0)
    cash = vams.get("cash", 0)
    ret = vams.get("total_return_pct", 0)
    holdings = vams.get("holdings", [])

    lines = [
        "<b>📋 VERITY 일일 브리핑</b>",
        f"━━━━━━━━━━━━━━━",
    ]

    if briefing:
        lines.append(f"\n<b>{briefing.get('headline', '')}</b>")
        actions = briefing.get("action_items", [])
        if actions:
            lines.append("")
            for a in actions[:3]:
                lines.append(f"  → {a}")

        counts = briefing.get("alert_counts", {})
        parts = []
        if counts.get("critical"):
            parts.append(f"🔴긴급 {counts['critical']}")
        if counts.get("warning"):
            parts.append(f"🟡주의 {counts['warning']}")
        if counts.get("info"):
            parts.append(f"🔵참고 {counts['info']}")
        if parts:
            lines.append(f"\n경고: {' | '.join(parts)}")

    tr = portfolio.get("tail_risk_digest_last") or {}
    today = now_kst().strftime("%Y-%m-%d")
    tr_line = (tr.get("one_liner") or "").strip()
    if tr.get("date_kst") == today and tr_line:
        lines.append(
            f"\n<i>⚠ 오늘 꼬리위험 알림 요약: {_html_escape(tr_line)}</i>"
        )

    lines.extend([
        f"\n<b>포트폴리오</b>",
        f"💰 {total:,.0f}원 ({ret:+.2f}%) | 보유 {len(holdings)}종목",
    ])

    if holdings:
        for h in holdings:
            emoji = "🟢" if h.get("return_pct", 0) >= 0 else "🔴"
            lines.append(
                f"  {emoji} {h['name']}: {h.get('return_pct', 0):+.1f}%"
            )

    recs = portfolio.get("recommendations", [])
    buys = [r for r in recs if r.get("recommendation") == "BUY"]
    if buys:
        lines.append(f"\n<b>매수 추천:</b>")
        for r in buys[:3]:
            ts = r.get("timing", {}).get("timing_score", 0)
            lines.append(f"  🎯 {r['name']} (타이밍 {ts}점)")

    events = portfolio.get("global_events", [])
    upcoming = [e for e in events if e.get("d_day", 99) <= 3]
    if upcoming:
        lines.append(f"\n<b>임박 이벤트:</b>")
        for e in upcoming[:2]:
            lines.append(f"  ⚡ D-{e['d_day']} {e['name']}")

    ci = portfolio.get("commodity_impact") or {}
    narr = ci.get("narrative_lines") or []
    if narr:
        lines.append(f"\n<b>🛢 원자재 브리핑</b>")
        for ln in narr[:3]:
            lines.append(f"  {ln}")

    if not narr:
        comm_f = get_commodity_daily_footer(portfolio)
        if comm_f:
            lines.append("")
            lines.append(f"<i>🛢 {comm_f}</i>")

    send_message("\n".join(lines))


def send_morning_briefing(portfolio: dict):
    """장 개장 전 모닝 브리핑 — quick 모드 결과 기반"""
    briefing = portfolio.get("briefing", {})
    macro = portfolio.get("macro", {})
    mood = macro.get("market_mood", {})
    events = portfolio.get("global_events", [])
    rotation = portfolio.get("sector_rotation", {})
    vams = portfolio.get("vams", {})
    ret = vams.get("total_return_pct", 0)
    holdings = vams.get("holdings", [])

    lines = [
        "<b>☀️ VERITY 모닝 브리핑</b>",
        "━━━━━━━━━━━━━━━",
    ]

    if briefing.get("headline"):
        lines.append(f"\n<b>{briefing['headline']}</b>")

    mood_score = int(mood.get("score", 50) or 50)
    lines.append(f"\n<b>시장 분위기</b>: {mood.get('label', '—')} ({mood_score}점)")

    fx = macro.get("usd_krw", {})
    vix = macro.get("vix", {})
    sp = macro.get("sp500", {})
    ndx = macro.get("nasdaq", {})
    spc = sp.get("change_pct")
    try:
        ndxc = float(ndx.get("change_pct") or 0)
    except (TypeError, ValueError):
        ndxc = 0.0
    try:
        usd_pct = float(fx.get("change_pct") or 0)
    except (TypeError, ValueError):
        usd_pct = 0.0
    try:
        vix_v = float(vix.get("value") or 0)
    except (TypeError, ValueError):
        vix_v = 0.0
    try:
        spf = float(spc) if spc is not None else None
    except (TypeError, ValueError):
        spf = None

    macro_notable = False
    if spf is not None:
        macro_notable = (
            abs(spf) >= 1.0
            or abs(ndxc) >= 1.0
            or abs(usd_pct) >= 0.5
            or vix_v >= 22.0
        )
    show_index_line = spf is not None and (
        mood_score < 40 or mood_score > 60 or macro_notable
    )
    if show_index_line:
        lines.append(
            f"S&P {spf:+.2f}% | NDX {ndxc:+.2f}%"
            f" | VIX {vix.get('value', '—')} | 환율 {fx.get('value', '—')}"
        )

    upcoming = [e for e in events if (e.get("d_day") or 99) <= 7]
    if upcoming:
        lines.append(f"\n<b>이번 주 이벤트</b>")
        for e in upcoming[:4]:
            lines.append(f"  D-{e['d_day']} {e['name']}")

    if rotation.get("cycle_label"):
        lines.append(f"\n<b>섹터 전략</b>: {rotation['cycle_label']}")

    if holdings:
        lines.append(f"\n<b>포트폴리오</b> ({ret:+.2f}%)")
        for h in holdings[:5]:
            emoji = "\U0001F7E2" if (h.get("return_pct") or 0) >= 0 else "\U0001F534"
            lines.append(f"  {emoji} {h['name']}: {h.get('return_pct', 0):+.1f}%")

    # Claude 모닝 전략 코멘트 (full에서 생성된 것)
    ms = portfolio.get("claude_morning_strategy") or {}
    scenario = (ms.get("scenario") or "").strip()
    if scenario:
        lines.append(f"\n<b>🧠 Claude 전략 코멘트</b>")
        lines.append(scenario)
        for wp in (ms.get("watch_points") or [])[:2]:
            lines.append(f"  • {wp}")
        risk_note = (ms.get("risk_note") or "").strip()
        if risk_note:
            lines.append(f"  ⚠️ {risk_note}")
        top_comment = (ms.get("top_pick_comment") or "").strip()
        if top_comment:
            lines.append(f"  🎯 {top_comment}")

    actions = briefing.get("action_items", [])
    if actions:
        lines.append(f"\n<b>오늘 액션</b>")
        for a in actions[:3]:
            lines.append(f"  → {a}")

    lines.append("\n<i>장 개장 전 모닝 브리핑 · VERITY AI</i>")
    send_message("\n".join(lines))


def send_deadman_alert(reasons: list[str]) -> bool:
    """Deadman's Switch 발동 — 긴급 중단 알림"""
    lines = [
        "<b>🚨 VERITY 긴급: 분석 중단됨</b>",
        "<b>Deadman's Switch 발동</b>",
        "",
    ]
    for r in reasons:
        lines.append(f"  ⛔ {r}")
    lines.extend([
        "",
        "데이터 소스 복구 확인 후 수동 재실행 필요:",
        "<code>ANALYSIS_MODE=full</code> → workflow_dispatch",
    ])
    return send_message("\n".join(lines))


def send_cross_verification_alert(disagreements: list[dict]) -> bool:
    """Gemini vs Claude 의견 분열 알림"""
    if not disagreements:
        return False
    lines = [
        "<b>⚠️ AI 의견 분열 감지</b>",
        "Gemini와 Claude의 판단이 다릅니다.",
        "",
    ]
    for d in disagreements[:5]:
        name = d.get("name", "?")
        gemini_rec = d.get("gemini_rec", "?")
        claude_rec = d.get("claude_rec", "?")
        reason = d.get("reason", "")
        lines.append(f"<b>{name}</b>")
        lines.append(f"  Gemini: {gemini_rec} → Claude: {claude_rec}")
        if reason:
            lines.append(f"  💬 {reason[:100]}")
        lines.append("")
    lines.append("<i>두 AI 판단이 갈리는 종목은 신중하게 접근하세요.</i>")
    return send_message("\n".join(lines))


def send_postmortem_report(report: dict) -> bool:
    """AI 오심 포스트모텀 리포트 전송"""
    if not report or not report.get("failures"):
        return False

    lines = [
        "<b>🔍 AI 오심 복기 리포트</b>",
        f"<i>기간: {report.get('period', '?')} | 분석: {report.get('analyzed_count', 0)}건</i>",
        "",
    ]

    summary = report.get("summary", "")
    if summary:
        lines.append(f"{summary}")
        lines.append("")

    for f in report.get("failures", [])[:5]:
        emoji = "📉" if f.get("type") == "false_buy" else "📈"
        lines.append(f"{emoji} <b>{f.get('name', '?')}</b>")
        lines.append(f"  판정: {f.get('original_rec', '?')} → 실제: {f.get('actual_return', 0):+.1f}%")
        reason = f.get("postmortem", "")
        if reason:
            lines.append(f"  💬 {reason[:120]}")
        lines.append("")

    lesson = report.get("lesson", "")
    if lesson:
        lines.append(f"<b>교훈:</b> {lesson}")

    return send_message("\n".join(lines))


def send_vams_simulation_report(portfolio: dict) -> bool:
    """VAMS 시뮬레이션 누적 성과 리포트"""
    vams = portfolio.get("vams", {})
    sim = vams.get("simulation_stats", {})
    if not sim:
        return False

    lines = [
        "<b>📊 VAMS 시뮬레이션 성과</b>",
        f"━━━━━━━━━━━━━━━",
        f"💰 총자산: <b>{vams.get('total_asset', 0):,.0f}원</b>",
        f"📈 누적 수익률: <b>{vams.get('total_return_pct', 0):+.2f}%</b>",
        f"💵 현금: {vams.get('cash', 0):,.0f}원",
        f"🏷 보유: {len(vams.get('holdings', []))}종목",
        "",
        f"<b>누적 통계</b>",
        f"  총 매매: {sim.get('total_trades', 0)}회",
        f"  승률: {sim.get('win_rate', 0):.1f}%",
        f"  실현 손익: {sim.get('realized_pnl', 0):+,.0f}원",
        f"  최대 낙폭: {sim.get('max_drawdown_pct', 0):.1f}%",
        f"  최고 자산: {sim.get('peak_asset', 0):,.0f}원",
    ]

    best = sim.get("best_trade")
    worst = sim.get("worst_trade")
    if best:
        lines.append(f"\n  🏆 최고: {best.get('name', '?')} ({best.get('pnl', 0):+,.0f}원)")
    if worst:
        lines.append(f"  💀 최악: {worst.get('name', '?')} ({worst.get('pnl', 0):+,.0f}원)")

    return send_message("\n".join(lines))


def send_export_trade_top3(
    top_rows: List[Dict[str, Any]],
    pipeline_note: Optional[str] = None,
) -> bool:
    """수출 모멘텀 기준 상위 3종목 요약 전송"""
    lines = [
        "<b>📦 오늘의 수출 유망 종목 TOP 3</b>",
        "<i>거래대금 상위 스캔 → HS 매핑 → 관세청 수출 추이</i>",
        "",
    ]
    if pipeline_note:
        lines.append(f"⚠️ {pipeline_note}")
        lines.append("")

    if not top_rows:
        lines.append("집계 가능한 수출 증가율 데이터가 없습니다. API 키·HS 매핑을 확인하세요.")
        return send_message("\n".join(lines))

    for i, r in enumerate(top_rows, 1):
        mom = r.get("mom_export_pct")
        yoy = r.get("yoy_export_pct")
        mom_s = f"{mom:+.1f}%" if mom is not None else "n/a"
        yoy_s = f"{yoy:+.1f}%" if yoy is not None else "n/a"
        lines.append(f"<b>{i}. {r.get('name', '?')}</b> ({r.get('ticker', '')})")
        lines.append(f"   품목: {r.get('product', '')}")
        lines.append(f"   HS: {r.get('hscode', '')} | 기준월: {r.get('latest_yymm', '')}")
        lines.append(f"   수출액 전월비 {mom_s} · 전년동월비 {yoy_s}")
        lines.append("")

    return send_message("\n".join(lines))
