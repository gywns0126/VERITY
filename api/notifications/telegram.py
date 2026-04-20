"""
텔레그램 알림 모듈
- 손절/매수 알림
- 일일 리포트 전송
- 최종 메시지 중복 방지 (프로세스 내, hash 기반)
"""
from __future__ import annotations
import hashlib
import re
import requests
from typing import Any, Dict, List, Optional

from api.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, now_kst


def _html_escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ── 최종 메시지 중복 방지 ──
# 프로세스 실행 중 이미 보낸 메시지의 정규화된 fingerprint 를 set 에 저장.
# 동일 text 를 다시 send_message 로 호출하면 skip.
# (alert-item 단위 dedupe 는 telegram_dedupe.py, 이것은 최종 합쳐진 message 단위.)
_SENT_FINGERPRINTS: set[str] = set()

# 정규화 — 타임스탬프/분-단위 차이가 동일 의미 메시지를 중복 처리하지 못 하는 것 방지
_TS_PATTERNS = [
    re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?"),  # 2026-04-20 14:30:00
    re.compile(r"\d{2}:\d{2}(:\d{2})?"),                        # 14:30, 14:30:00
    re.compile(r"\d+[일시분초]\s*전"),                            # "3분 전", "1시간 전"
    re.compile(r"\d{4}-\d{2}-\d{2}"),                           # 2026-04-20
]


def _message_fingerprint(text: str) -> str:
    """메시지 본문 정규화 후 SHA-256. 공백/타임스탬프/상대시각 차이는 무시."""
    t = text or ""
    for pat in _TS_PATTERNS:
        t = pat.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha256(t.encode("utf-8")).hexdigest()[:24]


def reset_message_dedupe_cache() -> None:
    """테스트/수동 리셋용."""
    _SENT_FINGERPRINTS.clear()


def send_message(text: str, dedupe: bool = True) -> bool:
    """텔레그램 메시지 전송.

    dedupe=True (기본): 프로세스 내 이미 보낸 동일 메시지면 skip (완전 중복 방지).
    dedupe=False: hash 체크 우회 (강제 발송 — 예: 상태 업데이트 재전송).
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[Telegram] 토큰/챗ID 미설정 → 콘솔 출력:\n{text}")
        return False

    if dedupe:
        fp = _message_fingerprint(text)
        if fp in _SENT_FINGERPRINTS:
            print(f"[Telegram] 중복 메시지 스킵 (fp={fp})")
            return False
        # 전송 시도 전에 등록 — 실패 시 제거해서 재시도 가능하게
        _SENT_FINGERPRINTS.add(fp)
    else:
        fp = None

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
            # 실패 시 fingerprint 해제 — 다음 번 재시도 허용
            if fp is not None:
                _SENT_FINGERPRINTS.discard(fp)
            print(f"[Telegram] 전송 실패: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        if fp is not None:
            _SENT_FINGERPRINTS.discard(fp)
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
    dual_rows = [r for r in recs if isinstance(r.get("dual_consensus"), dict)]
    if dual_rows:
        agree_n = sum(
            1 for r in dual_rows
            if bool((r.get("dual_consensus") or {}).get("agreement", False))
        )
        manual_rows = [
            r for r in dual_rows
            if bool((r.get("dual_consensus") or {}).get("manual_review_required", False))
        ]
        agree_pct = round(agree_n / max(len(dual_rows), 1) * 100, 1)
        lines.append(
            f"\n<b>AI 합의</b>: 합의율 {agree_pct}% | 수동검토 {len(manual_rows)}건"
        )
        if manual_rows:
            top_manual = ", ".join(r.get("name", "?") for r in manual_rows[:3])
            lines.append(f"  ⚠️ 수동검토: {top_manual}")

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
        try:
            from api.intelligence.alert_engine import get_commodity_daily_footer
            comm_f = get_commodity_daily_footer(portfolio)
        except Exception:
            comm_f = ""
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
    recs = portfolio.get("recommendations", [])

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

    dual_rows = [r for r in recs if isinstance(r.get("dual_consensus"), dict)]
    if dual_rows:
        manual_rows = [
            r for r in dual_rows
            if bool((r.get("dual_consensus") or {}).get("manual_review_required", False))
        ]
        if manual_rows:
            names = ", ".join(r.get("name", "?") for r in manual_rows[:2])
            lines.append(f"\n<b>AI 수동검토</b>: {len(manual_rows)}건 ({names})")

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


def send_cross_verification_alert(
    disagreements: list[dict],
    weights_used: Optional[Dict[str, Any]] = None,
) -> bool:
    """Gemini vs Claude 의견 분열 알림"""
    if not disagreements:
        return False
    lines = [
        "<b>⚠️ AI 의견 분열 감지</b>",
        "Gemini와 Claude의 판단이 다릅니다.",
        "",
    ]
    if weights_used:
        lines.append(
            f"가중치: Gemini {weights_used.get('gemini', '-')} / Claude {weights_used.get('claude', '-')}"
        )
        lines.append("")
    for d in disagreements[:5]:
        name = d.get("name", "?")
        gemini_rec = d.get("gemini_rec", "?")
        claude_rec = d.get("claude_rec", "?")
        reason = d.get("reason", "")
        conflict_level = d.get("conflict_level")
        lines.append(f"<b>{name}</b>")
        lines.append(f"  Gemini: {gemini_rec} → Claude: {claude_rec}")
        if conflict_level:
            lvl_label = str(conflict_level).upper()
            lines.append(f"  충돌강도: {lvl_label}")
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


# ══════════════════════════════════════════════════
#  Trading 알림 (타이밍 전이 / 가상매매 / 실매매)
# ══════════════════════════════════════════════════

_TRANSITION_HEADER = {
    "enter_buy": ("🟢", "매수 진입 신호"),
    "enter_strong_buy": ("🟢🟢", "강한 매수 진입"),
    "escalate_buy": ("🟢⬆️", "매수 시그널 강화"),
    "cool_down": ("🟡", "상승 동력 약화"),
    "reverse_sell": ("🔴", "매도 전환 신호"),
    "reverse_strong_sell": ("🔴🔴", "강한 매도 전환"),
    "enter_sell": ("🔴", "매도 신호"),
    "enter_strong_sell": ("🔴🔴", "강한 매도 신호"),
    "escalate_sell": ("🔴⬆️", "매도 시그널 강화"),
    "recover": ("🔵", "회복 신호"),
    "recover_strong": ("🔵🟢", "강한 회복 전환"),
}


def send_timing_signal_alert(transitions: List[Dict[str, Any]]) -> bool:
    """매수/매도 타이밍 action 전이 알림 (수동 매매용)."""
    if not transitions:
        return False

    lines = ["<b>⏱ 매수/매도 타이밍 알림</b>", ""]

    for t in transitions:
        icon, label = _TRANSITION_HEADER.get(
            t.get("significance", ""), ("⚪", "타이밍 변화")
        )
        name = _html_escape(str(t.get("name", "?")))
        ticker = _html_escape(str(t.get("ticker", "")))
        hold_tag = " 🏷 <b>보유중</b>" if t.get("is_held") else ""
        from_a = t.get("from_action", "?")
        to_a = t.get("to_action", "?")
        score = t.get("score", 50)
        prev_score = t.get("prev_score", 50)
        safety = t.get("safety_score", 0)
        price = t.get("price")
        currency = t.get("currency", "KRW")

        lines.append(f"{icon} <b>{name}</b> ({ticker}){hold_tag}")
        lines.append(f"   {label}: {from_a} → <b>{to_a}</b>")
        lines.append(f"   타이밍 {prev_score}점 → <b>{score}점</b> | 안심 {safety}점")
        if price:
            if currency == "USD":
                lines.append(f"   현재가: ${float(price):,.2f}")
            else:
                lines.append(f"   현재가: {int(float(price)):,}원")

        reasons = t.get("reasons") or []
        for r in reasons[:3]:
            lines.append(f"   • {_html_escape(str(r))}")
        lines.append("")

    lines.append("<i>타이밍 전이 감지 · VERITY AI</i>")
    return send_message("\n".join(lines))


def send_paper_trade_alert(events: List[Dict[str, Any]]) -> bool:
    """VAMS 가상매매 체결 요약 알림.

    events: [{type, name, ticker, qty, price, reason, pnl?}, ...]
    """
    if not events:
        return False

    buys = [e for e in events if e.get("type") == "NEW_BUY"]
    sells = [e for e in events if e.get("type") == "STOP_LOSS"]
    blocks = [e for e in events if e.get("type") == "EXPOSURE_BLOCK"]

    lines = ["<b>📝 VAMS 가상매매 체결</b>", ""]

    if buys:
        lines.append(f"<b>🟢 신규 매수 ({len(buys)}건)</b>")
        for e in buys:
            name = _html_escape(str(e.get("name", "?")))
            qty = e.get("qty", 0)
            price = e.get("price", 0)
            reason = _html_escape(str(e.get("reason", ""))[:60])
            lines.append(f"  ✅ {name} {qty}주 @ {price:,.0f}")
            if reason:
                lines.append(f"     └ {reason}")
        lines.append("")

    if sells:
        lines.append(f"<b>🔴 손절/익절 ({len(sells)}건)</b>")
        for e in sells:
            name = _html_escape(str(e.get("name", "?")))
            pnl = e.get("pnl", 0)
            reason = _html_escape(str(e.get("reason", ""))[:60])
            emoji = "💰" if pnl >= 0 else "💀"
            lines.append(f"  {emoji} {name}: {pnl:+,.0f}원")
            if reason:
                lines.append(f"     └ {reason}")
        lines.append("")

    if blocks:
        lines.append(f"<b>⛔ 매수 차단 ({len(blocks)}건)</b>")
        for e in blocks[:3]:
            name = _html_escape(str(e.get("name", "?")))
            reason = _html_escape(str(e.get("reason", ""))[:80])
            lines.append(f"  {name}: {reason}")

    return send_message("\n".join(lines))


def send_auto_trade_intent(orders: List[Dict[str, Any]], dry_run: bool = False) -> bool:
    """실거래 주문 제출 직전 알림."""
    if not orders:
        return False

    header = "🤖 <b>자동매매 주문 예정</b>"
    if dry_run:
        header += " <i>[DRY RUN]</i>"

    lines = [header, ""]

    for o in orders:
        side = o.get("side", "?").upper()
        name = _html_escape(str(o.get("name", o.get("ticker", "?"))))
        ticker = _html_escape(str(o.get("ticker", "")))
        qty = o.get("qty", 0)
        price = o.get("price", 0)
        market = o.get("market", "KR")
        currency = "USD" if market == "US" else "KRW"

        side_icon = "🟢" if side == "BUY" else "🔴"
        price_str = f"${price:,.2f}" if currency == "USD" else f"{int(price):,}원"
        total_str = (
            f"${price * qty:,.2f}" if currency == "USD"
            else f"{int(price * qty):,}원"
        )

        lines.append(f"{side_icon} <b>{side}</b> {name} ({ticker})")
        lines.append(f"   {qty}주 @ {price_str} = {total_str}")

        reason = _html_escape(str(o.get("reason", ""))[:80])
        if reason:
            lines.append(f"   💬 {reason}")
        lines.append("")

    if dry_run:
        lines.append("<i>⚠️ DRY RUN 모드 — 실제 주문은 전송되지 않습니다</i>")

    return send_message("\n".join(lines))


def send_auto_trade_filled(results: List[Dict[str, Any]]) -> bool:
    """실거래 주문 체결 후 알림."""
    if not results:
        return False

    lines = ["<b>✅ 자동매매 체결 완료</b>", ""]

    for r in results:
        side = r.get("side", "?").upper()
        name = _html_escape(str(r.get("name", r.get("ticker", "?"))))
        ticker = _html_escape(str(r.get("ticker", "")))
        qty = r.get("filled_qty", r.get("qty", 0))
        price = r.get("filled_price", r.get("price", 0))
        order_id = r.get("order_id", "")
        market = r.get("market", "KR")
        currency = "USD" if market == "US" else "KRW"
        price_str = f"${price:,.2f}" if currency == "USD" else f"{int(price):,}원"

        icon = "🟢" if side == "BUY" else "🔴"
        lines.append(f"{icon} <b>{side}</b> {name} ({ticker})")
        lines.append(f"   체결: {qty}주 @ {price_str}")
        if order_id:
            lines.append(f"   주문번호: <code>{order_id}</code>")

        pnl = r.get("pnl")
        if pnl is not None and side == "SELL":
            emoji = "💰" if pnl >= 0 else "💀"
            lines.append(f"   {emoji} 실현손익: {pnl:+,.0f}원")
        lines.append("")

    return send_message("\n".join(lines))


def send_auto_trade_failed(order: Dict[str, Any], error: str) -> bool:
    """실거래 주문 실패 알림."""
    side = order.get("side", "?").upper()
    name = _html_escape(str(order.get("name", order.get("ticker", "?"))))
    ticker = _html_escape(str(order.get("ticker", "")))
    qty = order.get("qty", 0)

    lines = [
        "<b>⚠️ 자동매매 주문 실패</b>",
        "",
        f"{side} {name} ({ticker}) {qty}주",
        f"사유: {_html_escape(str(error)[:200])}",
    ]
    return send_message("\n".join(lines))


def send_auto_trade_blocked(blocks: List[Dict[str, Any]]) -> bool:
    """자동매매 차단 사유 요약 (일일 한도 초과, 킬스위치, 장외시간 등)."""
    if not blocks:
        return False

    lines = ["<b>🛡 자동매매 차단</b>", ""]
    for b in blocks[:10]:
        name = _html_escape(str(b.get("name", b.get("ticker", "?"))))
        reason = _html_escape(str(b.get("reason", ""))[:100])
        lines.append(f"  • {name}: {reason}")

    return send_message("\n".join(lines))
