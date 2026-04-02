"""
VERITY 대화형 텔레그램 봇

사용자 질의 예시:
  "배리티, 삼성전자 지금 어때?"
  "지금 시장 어때?"
  "오늘 뭐 사야 돼?"
  "포트폴리오 현황"
  "경고 있어?"

GitHub Actions에서 poll 모드로 실행.
"""
import json
import os
import re
from typing import Optional

from api.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DATA_DIR
from api.notifications.telegram import send_message


def load_latest_data() -> dict:
    path = os.path.join(DATA_DIR, "portfolio.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            txt = f.read().replace("NaN", "null").replace("Infinity", "null").replace("-Infinity", "null")
        return json.loads(txt)
    except Exception:
        return {}


def handle_query(text: str) -> str:
    """사용자 질의를 분석하여 답변 생성"""
    text = text.strip().lower()
    data = load_latest_data()

    if not data:
        return "데이터가 아직 준비되지 않았습니다. 분석 실행 후 다시 시도해주세요."

    if _match_any(text, ["시장", "매크로", "분위기", "상황"]):
        return _answer_market(data)

    if _match_any(text, ["경고", "알림", "위험", "리스크"]):
        return _answer_alerts(data)

    if _match_any(text, ["포트폴리오", "보유", "자산", "현황"]):
        return _answer_portfolio(data)

    if _match_any(text, ["추천", "뭐 사", "매수", "기회"]):
        return _answer_recommendations(data)

    if _match_any(text, ["브리핑", "요약", "한줄"]):
        return _answer_briefing(data)

    stock_name = _extract_stock_name(text, data)
    if stock_name:
        return _answer_stock(stock_name, data)

    return _answer_briefing(data)


def _match_any(text: str, keywords: list) -> bool:
    return any(kw in text for kw in keywords)


def _extract_stock_name(text: str, data: dict) -> Optional[str]:
    recs = data.get("recommendations", [])
    holdings = data.get("vams", {}).get("holdings", [])

    all_names = [r["name"] for r in recs] + [h["name"] for h in holdings]

    for name in all_names:
        if name.lower() in text or name.replace(" ", "") in text.replace(" ", ""):
            return name

    return None


def _answer_briefing(data: dict) -> str:
    briefing = data.get("briefing", {})
    if not briefing:
        return "아직 브리핑이 생성되지 않았습니다."

    lines = [
        f"<b>📋 VERITY 브리핑</b>",
        f"",
        f"<b>{briefing.get('headline', '데이터 없음')}</b>",
        f"",
    ]

    counts = briefing.get("alert_counts", {})
    if counts.get("critical", 0) > 0:
        lines.append(f"🔴 긴급 {counts['critical']}건")
    if counts.get("warning", 0) > 0:
        lines.append(f"🟡 주의 {counts['warning']}건")

    actions = briefing.get("action_items", [])
    if actions:
        lines.append(f"\n<b>지금 해야 할 것:</b>")
        for a in actions[:3]:
            lines.append(f"  → {a}")

    lines.append(f"\n{briefing.get('portfolio_status', '')}")

    return "\n".join(lines)


def _answer_market(data: dict) -> str:
    macro = data.get("macro", {})
    mood = macro.get("market_mood", {})
    ms = data.get("market_summary", {})
    diags = macro.get("macro_diagnosis", [])

    lines = [
        f"<b>🌍 시장 현황</b>",
        f"",
        f"분위기: <b>{mood.get('label', '?')}</b> ({mood.get('score', 0)}점/100)",
        f"KOSPI: {ms.get('kospi', {}).get('value', '?')} ({ms.get('kospi', {}).get('change_pct', '?')}%)",
        f"KOSDAQ: {ms.get('kosdaq', {}).get('value', '?')} ({ms.get('kosdaq', {}).get('change_pct', '?')}%)",
        f"USD/KRW: {macro.get('usd_krw', {}).get('value', '?')}",
        f"VIX: {macro.get('vix', {}).get('value', '?')}",
    ]

    if diags:
        lines.append(f"\n<b>진단:</b>")
        for d in diags[:3]:
            lines.append(f"  • {d}")

    events = data.get("global_events", [])
    upcoming = [e for e in events if e.get("d_day", 99) <= 3]
    if upcoming:
        lines.append(f"\n<b>임박 이벤트:</b>")
        for e in upcoming[:3]:
            lines.append(f"  ⚡ D-{e['d_day']} {e['name']}")

    return "\n".join(lines)


def _answer_alerts(data: dict) -> str:
    briefing = data.get("briefing", {})
    alerts = briefing.get("alerts", [])

    if not alerts:
        return "현재 활성 경고가 없습니다. ✅"

    lines = [f"<b>🚨 VERITY 경고</b>", ""]

    icons = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵"}
    for a in alerts[:7]:
        icon = icons.get(a["level"], "⚪")
        lines.append(f"{icon} {a['message']}")
        if a.get("action"):
            lines.append(f"   → {a['action']}")

    return "\n".join(lines)


def _answer_portfolio(data: dict) -> str:
    vams = data.get("vams", {})
    holdings = vams.get("holdings", [])

    lines = [
        f"<b>💼 포트폴리오</b>",
        f"",
        f"총자산: <b>{vams.get('total_asset', 0):,.0f}원</b>",
        f"현금: {vams.get('cash', 0):,.0f}원",
        f"수익률: <b>{vams.get('total_return_pct', 0):+.2f}%</b>",
        f"보유: {len(holdings)}종목",
    ]

    if holdings:
        lines.append("")
        for h in holdings:
            emoji = "🟢" if h.get("return_pct", 0) >= 0 else "🔴"
            lines.append(f"{emoji} {h['name']}: {h.get('return_pct', 0):+.1f}% ({h.get('quantity', 0)}주)")

    return "\n".join(lines)


def _answer_recommendations(data: dict) -> str:
    recs = data.get("recommendations", [])
    buys = [r for r in recs if r.get("recommendation") == "BUY" or r.get("timing", {}).get("action") in ("STRONG_BUY", "BUY")]

    if not buys:
        watches = [r for r in recs if r.get("recommendation") == "WATCH"]
        if watches:
            lines = [f"<b>👀 관찰 종목 (적극 매수 시그널 없음)</b>", ""]
            for s in watches[:5]:
                timing = s.get("timing", {})
                lines.append(f"  • {s['name']}: 안심{s.get('safety_score', 0)}점 | 종합{s.get('multi_factor', {}).get('multi_score', 0)}점 | 타이밍{timing.get('timing_score', 50)}점")
            return "\n".join(lines)
        return "현재 적극 매수 추천 종목이 없습니다. 관망 모드."

    lines = [f"<b>🎯 매수 추천</b>", ""]
    for s in buys[:5]:
        timing = s.get("timing", {})
        pred = s.get("prediction", {})
        lines.append(f"<b>{s['name']}</b>")
        lines.append(f"  안심 {s.get('safety_score', 0)}점 | 종합 {s.get('multi_factor', {}).get('multi_score', 0)}점")
        lines.append(f"  타이밍 {timing.get('timing_score', 50)}점 | AI상승확률 {pred.get('up_probability', 50)}%")
        verdict = s.get("ai_verdict", "")
        if verdict:
            lines.append(f"  → {verdict[:80]}")
        lines.append("")

    return "\n".join(lines)


def _answer_stock(name: str, data: dict) -> str:
    recs = data.get("recommendations", [])
    stock = next((r for r in recs if r["name"] == name), None)

    if not stock:
        holdings = data.get("vams", {}).get("holdings", [])
        h = next((x for x in holdings if x["name"] == name), None)
        if h:
            return (
                f"<b>💼 {name} (보유중)</b>\n"
                f"수익률: {h.get('return_pct', 0):+.1f}%\n"
                f"매수가: {h.get('buy_price', 0):,.0f}원 → 현재: {h.get('current_price', 0):,.0f}원\n"
                f"수량: {h.get('quantity', 0)}주"
            )
        return f"{name}에 대한 최신 분석 데이터가 없습니다."

    timing = stock.get("timing", {})
    pred = stock.get("prediction", {})
    tech = stock.get("technical", {})
    mf = stock.get("multi_factor", {})
    flow = stock.get("flow", {})

    lines = [
        f"<b>📊 {name} 분석</b>",
        f"",
        f"추천: <b>{stock.get('recommendation', '?')}</b>",
        f"안심점수: {stock.get('safety_score', 0)}점",
        f"종합점수: {mf.get('multi_score', 0)}점 ({mf.get('grade', '?')})",
        f"",
        f"<b>타이밍:</b> {timing.get('timing_score', 50)}점 ({timing.get('action', '?')})",
        f"<b>AI상승확률:</b> {pred.get('up_probability', 50)}%",
        f"<b>RSI:</b> {tech.get('rsi', '?')} | <b>MACD:</b> {'골든' if tech.get('macd_signal') == 'bullish' else '데드' if tech.get('macd_signal') == 'bearish' else '중립'}",
        f"<b>수급:</b> {flow.get('flow_score', 50)}점 | {', '.join(flow.get('flow_signals', [])[:2]) or '중립'}",
    ]

    verdict = stock.get("ai_verdict", "")
    if verdict:
        lines.append(f"\n<b>AI 판단:</b>\n{verdict[:200]}")

    actions = timing.get("reasons", [])
    if actions:
        lines.append(f"\n<b>근거:</b>")
        for r in actions[:4]:
            lines.append(f"  • {r}")

    return "\n".join(lines)


def run_poll_once():
    """한 번의 폴링으로 새 메시지 처리 (GitHub Actions에서 호출)"""
    if not TELEGRAM_BOT_TOKEN:
        print("[TelegramBot] 토큰 미설정")
        return

    import requests as req

    offset_path = os.path.join(DATA_DIR, ".telegram_offset")
    offset = 0
    if os.path.exists(offset_path):
        try:
            with open(offset_path, "r") as f:
                offset = int(f.read().strip())
        except Exception:
            pass

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"offset": offset, "timeout": 5, "limit": 10}

    try:
        resp = req.get(url, params=params, timeout=15)
        data = resp.json()
    except Exception as e:
        print(f"[TelegramBot] 폴링 실패: {e}")
        return

    if not data.get("ok"):
        return

    for update in data.get("result", []):
        update_id = update["update_id"]
        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")

        if text and chat_id:
            print(f"[TelegramBot] 질의: {text}")
            answer = handle_query(text)

            send_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": answer,
                "parse_mode": "HTML",
            }
            try:
                req.post(send_url, json=payload, timeout=10)
            except Exception as e:
                print(f"[TelegramBot] 응답 실패: {e}")

        offset = update_id + 1

    with open(offset_path, "w") as f:
        f.write(str(offset))
