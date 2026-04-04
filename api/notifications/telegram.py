"""
텔레그램 알림 모듈
- 손절/매수 알림
- 일일 리포트 전송
"""
import requests
from typing import Any, Dict, List, Optional

from api.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from api.intelligence.alert_engine import get_commodity_daily_footer


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


def send_alerts(alerts: list[dict]):
    """알림 목록 전송"""
    if not alerts:
        return

    lines = ["<b>🔔 안심 AI 비서 알림</b>\n"]
    for alert in alerts:
        lines.append(alert["message"])

    send_message("\n".join(lines))


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
