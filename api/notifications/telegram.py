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
    """일일 요약 리포트 전송"""
    vams = portfolio.get("vams", {})
    total = vams.get("total_asset", 0)
    cash = vams.get("cash", 0)
    ret = vams.get("total_return_pct", 0)
    holdings = vams.get("holdings", [])

    lines = [
        "<b>📊 일일 안심 리포트</b>",
        f"━━━━━━━━━━━━━━━",
        f"💰 총 자산: <b>{total:,.0f}원</b>",
        f"💵 현금: {cash:,.0f}원",
        f"📈 수익률: <b>{ret:+.2f}%</b>",
        f"📦 보유 종목: {len(holdings)}개",
    ]

    if holdings:
        lines.append(f"\n<b>보유 현황:</b>")
        for h in holdings:
            emoji = "🟢" if h["return_pct"] >= 0 else "🔴"
            lines.append(
                f"  {emoji} {h['name']}: {h['return_pct']:+.1f}% "
                f"({h['quantity']}주 @ {h['current_price']:,}원)"
            )

    recs = portfolio.get("recommendations", [])
    if recs:
        lines.append(f"\n<b>오늘의 추천:</b>")
        for r in recs[:3]:
            lines.append(
                f"  🎯 {r['name']} (안심{r['safety_score']}점) "
                f"- {r.get('ai_verdict', '')}"
            )

    send_message("\n".join(lines))
