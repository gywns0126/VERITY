"""
텔레그램 알림 모듈
- 손절/매수 알림
- 일일 리포트 전송
"""
import requests
from api.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


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

    send_message("\n".join(lines))
