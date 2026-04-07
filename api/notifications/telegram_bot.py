"""
VERITY 대화형 텔레그램 봇

사용자 질의 예시:
  "배리티, 삼성전자 지금 어때?"
  "지금 시장 어때?"
  "오늘 뭐 사야 돼?"
  "포트폴리오 현황"
  "경고 있어?"

GitHub Actions에서 poll 모드로 실행.
키워드 매칭 실패 시 Gemini chat_engine으로 폴백.

보안: TELEGRAM_ALLOWED_CHAT_IDS(쉼표 구분 정수 chat_id)를 설정하면 해당 ID만 응답.
미설정이면 발신자 전원에게 응답(기존 동작).
"""
import json
import os
import re
from datetime import datetime
from typing import Optional

from api.config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_ALLOWED_CHAT_IDS,
    DATA_DIR,
)
from api.notifications.telegram import send_message

_GEMINI_DAILY_LIMIT = int(os.environ.get("GEMINI_DAILY_LIMIT", "50"))
_gemini_counter_path = os.path.join(DATA_DIR, ".gemini_chat_counter.json")


def _gemini_quota_ok() -> bool:
    """오늘 Gemini 호출 횟수가 한도 이내인지 확인."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(_gemini_counter_path, "r") as f:
            counter = json.load(f)
    except Exception:
        counter = {}
    return counter.get(today, 0) < _GEMINI_DAILY_LIMIT


def _gemini_increment():
    """오늘 Gemini 호출 카운터 +1."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(_gemini_counter_path, "r") as f:
            counter = json.load(f)
    except Exception:
        counter = {}
    counter = {k: v for k, v in counter.items() if k >= today}
    counter[today] = counter.get(today, 0) + 1
    try:
        with open(_gemini_counter_path, "w") as f:
            json.dump(counter, f)
    except Exception:
        pass


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

    if _match_any(text, ["복기", "왜 틀", "오심", "실패", "포스트모텀", "틀렸"]):
        return _answer_postmortem(data)

    if _match_any(text, ["시뮬레이션", "vams", "누적", "성과"]):
        return _answer_simulation(data)

    if _match_any(text, ["의견 분열", "교차검증", "gemini", "claude", "크로스"]):
        return _answer_cross_verification(data)

    if text.startswith("/approve_strategy"):
        return _handle_approve_strategy()

    if text.startswith("/reject_strategy"):
        return _handle_reject_strategy()

    if text.startswith("/rollback_strategy"):
        return _handle_rollback_strategy()

    if text.startswith("/strategy_status") or _match_any(text, ["전략 상태", "브레인 버전", "v2 상태"]):
        return _answer_strategy_status()

    stock_name = _extract_stock_name(text, data)
    if stock_name:
        return _answer_stock(stock_name, data)

    if _gemini_quota_ok():
        try:
            from api.intelligence.chat_engine import ask
            answer = ask(text, context=data)
            _gemini_increment()
            return f"🤖 <b>AI 비서</b>\n\n{answer}"
        except Exception:
            pass

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


def _answer_postmortem(data: dict) -> str:
    """AI 오심 복기 답변"""
    pm = data.get("postmortem", {})
    if not pm or not pm.get("failures"):
        return "최근 유의미한 AI 오심이 없습니다. 시스템이 잘 작동 중입니다. ✅"

    lines = [
        f"<b>🔍 AI 오심 복기</b>",
        f"<i>{pm.get('period', '?')} | {pm.get('analyzed_count', 0)}건</i>",
        "",
    ]

    for f in pm.get("failures", [])[:5]:
        emoji = "📉" if f.get("type") == "false_buy" else "📈"
        lines.append(f"{emoji} <b>{f.get('name', '?')}</b>")
        lines.append(f"  판정: {f.get('original_rec', '?')} → 실제: {f.get('actual_return', 0):+.1f}%")
        reason = f.get("postmortem", "")
        if reason:
            lines.append(f"  💬 {reason[:120]}")
        misleading = f.get("misleading_factor", "")
        if misleading:
            lines.append(f"  ⚠️ 오류 팩터: {misleading}")
        lines.append("")

    lesson = pm.get("lesson", "")
    if lesson:
        lines.append(f"<b>교훈:</b> {lesson}")

    suggestion = pm.get("system_suggestion", "")
    if suggestion:
        lines.append(f"<b>개선안:</b> {suggestion}")

    return "\n".join(lines)


def _answer_simulation(data: dict) -> str:
    """VAMS 시뮬레이션 누적 성과 답변"""
    vams = data.get("vams", {})
    sim = vams.get("simulation_stats", {})

    lines = [
        f"<b>📊 VAMS 시뮬레이션 성과</b>",
        "",
        f"💰 총자산: <b>{vams.get('total_asset', 0):,.0f}원</b>",
        f"📈 수익률: <b>{vams.get('total_return_pct', 0):+.2f}%</b>",
        f"💵 현금: {vams.get('cash', 0):,.0f}원",
        f"보유: {len(vams.get('holdings', []))}종목",
    ]

    if sim:
        lines.extend([
            "",
            f"<b>누적 매매 통계</b>",
            f"  총 {sim.get('total_trades', 0)}회 | 승률 {sim.get('win_rate', 0):.1f}%",
            f"  실현 손익: {sim.get('realized_pnl', 0):+,.0f}원",
            f"  최고 자산: {sim.get('peak_asset', 0):,.0f}원",
            f"  최대 낙폭: {sim.get('max_drawdown_pct', 0):.1f}%",
        ])
        best = sim.get("best_trade")
        worst = sim.get("worst_trade")
        if best:
            lines.append(f"  🏆 최고: {best.get('name', '?')} ({best.get('pnl', 0):+,.0f}원)")
        if worst:
            lines.append(f"  💀 최악: {worst.get('name', '?')} ({worst.get('pnl', 0):+,.0f}원)")
    else:
        lines.append("\n아직 시뮬레이션 통계가 생성되지 않았습니다.")

    return "\n".join(lines)


def _answer_cross_verification(data: dict) -> str:
    """AI 교차검증 결과 답변"""
    cv = data.get("cross_verification", {})
    if not cv:
        return "최근 AI 교차검증 데이터가 없습니다. full 모드 분석 후 확인 가능합니다."

    disagreements = cv.get("disagreements", [])
    if not disagreements:
        return f"Gemini와 Claude가 {cv.get('total_analyzed', 0)}종목 모두 동의했습니다. ✅"

    lines = [
        f"<b>⚠️ AI 의견 분열</b>",
        f"<i>분석 {cv.get('total_analyzed', 0)}종목 중 {len(disagreements)}건 의견 차이</i>",
        "",
    ]

    for d in disagreements[:5]:
        lines.append(f"<b>{d.get('name', '?')}</b>")
        lines.append(f"  Gemini: {d.get('gemini_rec', '?')} → Claude: {d.get('claude_rec', '?')}")
        reason = d.get("reason", "")
        if reason:
            lines.append(f"  💬 {reason[:100]}")
        lines.append("")

    lines.append("<i>의견이 갈리는 종목은 신중하게 접근하세요.</i>")
    return "\n".join(lines)


def _handle_approve_strategy() -> str:
    """전략 제안 승인 처리."""
    try:
        from api.intelligence.strategy_evolver import (
            _load_registry,
            _save_registry,
            apply_proposal,
        )
        registry = _load_registry()
        pending = registry.get("pending_proposal")
        if not pending:
            return "대기 중인 전략 제안이 없습니다."

        proposal = pending["proposal"]
        bt_result = pending["backtest_result"]
        new_ver = apply_proposal(proposal, bt_result)

        registry["pending_proposal"] = None
        stats = registry.get("cumulative_stats", {})
        stats["hit_count"] = stats.get("hit_count", 0) + 1
        accepted = stats.get("accepted", 0)
        if accepted > 0:
            stats["hit_rate_pct"] = round(stats["hit_count"] / accepted * 100, 1)
        _save_registry(registry)

        return (
            f"<b>✅ 전략 v{new_ver} 승인 완료</b>\n\n"
            f"사유: {proposal.get('reason', '?')}\n"
            f"Sharpe: {bt_result.get('sharpe', 0):.2f}\n\n"
            f"다음 full 분석부터 새 가중치가 적용됩니다."
        )
    except Exception as e:
        return f"승인 처리 실패: {str(e)[:80]}"


def _handle_reject_strategy() -> str:
    """전략 제안 거절 처리."""
    try:
        from api.intelligence.strategy_evolver import reject_proposal
        success = reject_proposal("사령관 거절")
        if success:
            return "<b>❌ 전략 제안 거절 완료</b>\n현행 가중치가 유지됩니다."
        return "대기 중인 전략 제안이 없습니다."
    except Exception as e:
        return f"거절 처리 실패: {str(e)[:80]}"


def _handle_rollback_strategy() -> str:
    """직전 버전으로 전략 롤백."""
    try:
        from api.intelligence.strategy_evolver import rollback_strategy
        new_ver = rollback_strategy()
        if new_ver:
            return (
                f"<b>🔄 전략 롤백 완료 (v{new_ver})</b>\n"
                f"직전 버전 가중치로 복원했습니다."
            )
        return "롤백할 이전 버전이 없습니다."
    except Exception as e:
        return f"롤백 실패: {str(e)[:80]}"


def _answer_strategy_status() -> str:
    """Brain V2 전략 상태 표시."""
    try:
        from api.intelligence.strategy_evolver import get_strategy_status
        status = get_strategy_status()

        lines = [
            "<b>🧠 Brain V2 전략 상태</b>",
            "",
            f"버전: v{status.get('current_version', '?')}",
            f"자동 모드: {'ON' if status.get('auto_approve') else 'OFF'}",
        ]

        stats = status.get("stats", {})
        if stats.get("total_proposals", 0) > 0:
            lines.extend([
                "",
                "<b>누적 통계</b>",
                f"  제안: {stats.get('total_proposals', 0)}회",
                f"  채택: {stats.get('accepted', 0)}회 | 거절: {stats.get('rejected', 0)}회",
                f"  적중률: {stats.get('hit_rate_pct', 0):.1f}%",
            ])

        if status.get("pending"):
            lines.append("\n⏳ 승인 대기 중인 제안이 있습니다.")
            lines.append("  /approve_strategy 또는 /reject_strategy")

        fw = status.get("fact_weights", {})
        if fw:
            lines.append("\n<b>현행 Fact 가중치</b>")
            for k, v in sorted(fw.items(), key=lambda x: -x[1]):
                bar = "█" * int(v * 20)
                lines.append(f"  {k}: {v:.2f} {bar}")

        return "\n".join(lines)
    except Exception as e:
        return f"전략 상태 조회 실패: {str(e)[:80]}"


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
            if TELEGRAM_ALLOWED_CHAT_IDS and chat_id not in TELEGRAM_ALLOWED_CHAT_IDS:
                print(f"[TelegramBot] 허용 목록에 없는 chat_id 무시: {chat_id}")
            else:
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
