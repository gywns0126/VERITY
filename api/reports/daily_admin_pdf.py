"""
Daily 관리자 리포트 PDF v2 — 7장 구조.

사용자 요구 구조:
  COVER — 30초 브리핑 (오늘의 판단 + 핵심 근거 3줄 + 오늘 할 일 3줄)
  제1장 — 매크로 환경 (신호등 3개 + 주요 지표 표)
  제2장 — 이벤트 캘린더 (D-7, 컨센서스 + 서프라이즈 시나리오)
  제3장 — Verity Brain 종합 판단 (점수 + VCI + 등급 분포)
  제4장 — 종목 판단 (BUY 3 / 보유 / 회피 3)
  제5장 — 섹터 동향 (상승/하락 + 자금 이동 + 다이버전스)
  제6장 — VAMS 현황 (KPI 4개 + 보유 + PnL 추이)
  제7장 — AI 모델 이견 검토 (이견 있는 종목만)

Phase 1.5 메타데이터 통합:
  - validation_status_summary 워터마크
  - brain_learning.trend_summary (12주 적중률 추이)
  - llm_cost.summarize_cost (월간 비용 ROI)
  - user_actions.summarize (본인 vs 시스템 적중률)

기존 generate_daily_pdf 는 보존. v2는 별도 호출.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst
from api.reports.pdf_generator import (
    VerityPDF, _norm_text, _safe_report_text, _portfolio_updated_str, _doc_id,
    _macro_environment_narrative, _capital_flow_narrative,
    _commodity_impact_narrative, _x_sentiment_narrative,
    _stock_detail_block, _conclusion_narrative, _rec_by_ticker,
)
from api.utils.dilution import (
    apply_grade_guard, brain_grade_from_score, grade_label,
    is_validated, validation_status_summary, scenario_label,
    can_show_probability,
)
from api.utils.macro_meta import macro_as_of_line


# ─── COVER — 30초 브리핑 ────────────────────────────────────

def _render_cover(pdf: VerityPDF, portfolio: Dict[str, Any], val_summary: Dict[str, Any]):
    """30초 브리핑 — 한 페이지."""
    date_str = now_kst().strftime("%Y년 %m월 %d일")
    brain = portfolio.get("verity_brain", {}) or {}
    market_brain = brain.get("market_brain", {}) or {}
    macro = portfolio.get("macro", {}) or {}
    mood = macro.get("market_mood", {}) or {}
    report = portfolio.get("daily_report", {}) or {}
    briefing = portfolio.get("briefing", {}) or {}

    avg_brain = market_brain.get("avg_brain_score")
    grade_raw = brain_grade_from_score(avg_brain)
    grade_lbl = grade_label(grade_raw)
    mood_score = mood.get("score", 50)
    mood_label = mood.get("label", "중립")

    # 제목
    pdf._set_font("B", 17)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(12)
    pdf.cell(0, 10, "VERITY DAILY ADMIN REPORT")
    pdf.ln(8)
    pdf._set_font("", 9)
    pdf.set_text_color(*pdf.GRAY)
    pdf.set_x(12)
    pdf.multi_cell(180, pdf.LH_BOX, "관리자용 — 본인 의사결정 지원 (참고용 · 투자자문 또는 매매 권유 아님)", align="L")
    pdf.ln(2)
    pdf.set_x(12)
    pdf.cell(0, 6, f"문서번호: {_doc_id(portfolio)}")
    pdf.ln(5)
    pdf.set_x(12)
    pdf.cell(0, 6, f"작성·집계 기준: {_portfolio_updated_str(portfolio)}")
    pdf.ln(5)
    pdf.set_x(12)
    pdf.cell(0, 6, f"보고 일자: {date_str}")
    pdf.ln(8)

    # 검증 워터마크
    if not val_summary.get("validated"):
        y = pdf.get_y()
        pdf.set_fill_color(60, 30, 0)
        pdf.rect(10, y, 190, 8, "F")
        pdf._set_font("B", 8)
        pdf.set_text_color(*pdf.YELLOW)
        pdf.set_xy(14, y + 1.5)
        pdf.cell(0, 5, f"⚠ {val_summary.get('watermark_label', '검증 진행 중')}")
        pdf.set_y(y + 12)

    # 30초 브리핑 박스
    pdf._set_font("B", 13)
    pdf.set_text_color(*pdf.ACCENT)
    pdf.set_x(12)
    pdf.cell(0, 8, "30초 브리핑")
    pdf.ln(8)

    # 오늘의 판단 (큰 글씨)
    pdf._set_font("B", 22)
    grade_color = pdf.GRADE_COLORS.get(grade_raw, pdf.WHITE)
    pdf.set_text_color(*grade_color)
    pdf.set_x(15)
    judgment_word = pdf.GRADE_LABELS.get(grade_raw, grade_raw)
    pdf.cell(0, 12, f"오늘의 판단: {judgment_word}")
    pdf.ln(13)

    pdf._set_font("", 10)
    pdf.set_text_color(*pdf.GRAY)
    pdf.set_x(15)
    pdf.cell(0, 6, f"Brain {avg_brain or '-'}점 · 매크로 분위기 {mood_score}점 ({mood_label})")
    pdf.ln(10)

    # 핵심 근거 3줄
    pdf._set_font("B", 10)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(15)
    pdf.cell(0, 6, "핵심 근거 3줄")
    pdf.ln(6)

    pdf._set_font("", 9)
    pdf.set_text_color(204, 204, 204)
    macro_line = (briefing.get("macro_line")
                  or _safe_report_text(report.get("macro_summary"))
                  or f"매크로: VIX {macro.get('vix', {}).get('value', '-')}, "
                     f"USD/KRW {macro.get('usd_krw', {}).get('value', '-')}원, "
                     f"분위기 {mood_label}")
    brain_line = (briefing.get("brain_line")
                  or f"Brain: 평균 {avg_brain or '-'}점, VCI {market_brain.get('avg_vci', 0):+d}, "
                     f"등급 {grade_lbl}")
    risk_line = briefing.get("max_risk_line") or _safe_report_text(report.get("risk_watch")) or "최대 리스크 — 데이터 부족"

    for line in [f"· 매크로: {_norm_text(macro_line)}",
                 f"· Brain: {_norm_text(brain_line)}",
                 f"· 리스크: {_norm_text(risk_line)}"]:
        pdf.set_x(18)
        pdf.multi_cell(177, pdf.LH_BODY, line, align="L")
        pdf.ln(1)
    pdf.ln(4)

    # 오늘 할 일 3줄
    pdf._set_font("B", 10)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(15)
    pdf.cell(0, 6, "오늘 할 일")
    pdf.ln(6)
    pdf._set_font("", 9)
    pdf.set_text_color(204, 204, 204)
    actions = briefing.get("action_items") or report.get("action_items") or []
    for a in (actions[:3] if actions else ["신규 매수: 없음 (관망)", "보유 종목 액션: 점검만", "경계 트리거: VIX 25 돌파 시 재검토"]):
        pdf.set_x(18)
        pdf.multi_cell(177, pdf.LH_BODY, f"· {_norm_text(a)}", align="L")
        pdf.ln(1)


# ─── 제1장 — 매크로 환경 ───────────────────────────────────

def _render_chap1_macro(pdf: VerityPDF, portfolio: Dict[str, Any]):
    pdf.add_page()
    pdf.chapter_title(1, "매크로 환경")
    macro = portfolio.get("macro", {}) or {}

    # 신호등 3개
    pdf.subsection_title("1-1. 시장 신호등")
    vix = (macro.get("vix") or {}).get("value", 0)
    usd_krw_chg = (macro.get("usd_krw") or {}).get("change_pct", 0)
    sp500_chg = (macro.get("sp500") or {}).get("change_pct", 0)

    def _light(v, warn, danger, reverse=False):
        if reverse:
            if v > danger: return ("🔴", pdf.RED)
            if v > warn: return ("🟡", pdf.YELLOW)
            return ("🟢", pdf.GREEN)
        if v > danger: return ("🟢", pdf.GREEN)
        if v > warn: return ("🟡", pdf.YELLOW)
        return ("🔴", pdf.RED)

    global_icon, global_c = _light(vix, 25, 35, reverse=True)
    kr_icon, kr_c = _light(abs(usd_krw_chg), 0.5, 1.0, reverse=True)
    flow_icon, flow_c = _light(sp500_chg, -1.5, -0.5)

    pdf._set_font("", 10)
    for icon, color, label, value in [
        (global_icon, global_c, "글로벌 위험선호", f"VIX {vix}"),
        (kr_icon, kr_c, "국내 매크로", f"환율 변동 {usd_krw_chg:+.2f}%"),
        (flow_icon, flow_c, "유동성 흐름", f"S&P500 {sp500_chg:+.2f}%"),
    ]:
        pdf.set_text_color(*color)
        pdf.set_x(18)
        pdf.cell(8, 6, icon)
        pdf.set_text_color(*pdf.WHITE)
        pdf.set_x(28)
        pdf.cell(0, 6, f"{label} — {value}")
        pdf.ln(7)
    pdf.ln(2)

    # 1-2. 주요 지표 표
    pdf.subsection_title("1-2. 주요 지표")
    fred = macro.get("fred") or {}
    ecos = macro.get("ecos") or {}
    mood = macro.get("market_mood", {})
    pdf.metric_row([
        {"label": "시장 분위기", "value": f"{mood.get('label', '-')} ({mood.get('score', 50)}점)",
         "color": pdf.GREEN if mood.get('score', 50) >= 60 else pdf.YELLOW if mood.get('score', 50) >= 40 else pdf.RED},
        {"label": "VIX", "value": str(vix or "-"), "color": pdf.RED if vix and float(vix) > 25 else pdf.GREEN},
        {"label": "USD/KRW", "value": f"{macro.get('usd_krw', {}).get('value', '-')}원", "color": pdf.WHITE},
        {"label": "FRED 10Y", "value": f"{fred.get('dgs10', {}).get('value', '-')}%", "color": pdf.BLUE},
    ])
    pdf.metric_row([
        {"label": "S&P500", "value": f"{sp500_chg:+.2f}%", "color": pdf.GREEN if sp500_chg >= 0 else pdf.RED},
        {"label": "WTI", "value": f"${macro.get('wti_oil', {}).get('value', '-')}", "color": pdf.WHITE},
        {"label": "금", "value": f"${macro.get('gold', {}).get('value', '-')}", "color": pdf.YELLOW},
        {"label": "한국 기준금리", "value": f"{ecos.get('korea_policy_rate', {}).get('value', '-')}%",
         "color": pdf.BLUE},
    ])

    # macro_as_of_line — 시점 표기
    aof = macro_as_of_line(macro)
    if aof:
        pdf._set_font("", 7)
        pdf.set_text_color(*pdf.DARK_GRAY)
        pdf.set_x(15)
        pdf.cell(0, 4, aof)
        pdf.ln(6)

    # 1-3. 매크로 진단 요지
    pdf.subsection_title("1-3. 진단 요지")
    pdf.narrative_paragraphs(_macro_environment_narrative(macro))


# ─── 제2장 — 이벤트 캘린더 ─────────────────────────────────

def _render_chap2_events(pdf: VerityPDF, portfolio: Dict[str, Any]):
    pdf.add_page()
    pdf.chapter_title(2, "이벤트 캘린더 (D-7)")
    events = portfolio.get("global_events") or portfolio.get("events") or []

    if not events:
        pdf.narrative_paragraphs("D-7 이내 주요 이벤트 없음.")
        return

    pdf._set_font("", 9)
    pdf.set_text_color(204, 204, 204)
    for i, ev in enumerate(events[:5], 1):
        name = _norm_text(ev.get("name") or ev.get("event") or "")
        date = ev.get("date", "")
        impact = _norm_text(ev.get("impact_summary") or ev.get("description") or "")
        cons = _norm_text(ev.get("consensus") or "")
        surprise = _norm_text(ev.get("surprise_scenario") or "")
        if not name:
            continue
        pdf.set_x(15)
        pdf._set_font("B", 10)
        pdf.set_text_color(*pdf.YELLOW if i == 1 else pdf.WHITE)  # 1순위 강조
        pdf.cell(0, 6, f"{i}. {name}  (D-{date})")
        pdf.ln(6)
        pdf._set_font("", 8)
        pdf.set_text_color(204, 204, 204)
        if impact:
            pdf.set_x(18)
            pdf.multi_cell(175, pdf.LH_COMPACT, f"영향 요약: {impact[:150]}", align="L")
        if cons:
            pdf.set_x(18)
            pdf.multi_cell(175, pdf.LH_COMPACT, f"컨센서스: {cons[:120]}", align="L")
        if surprise:
            pdf.set_x(18)
            pdf.set_text_color(*pdf.ORANGE)
            pdf.multi_cell(175, pdf.LH_COMPACT, f"서프라이즈: {surprise[:200]}", align="L")
            pdf.set_text_color(204, 204, 204)
        pdf.ln(3)


# ─── 제3장 — Verity Brain 종합 판단 ────────────────────────

def _render_chap3_brain(pdf: VerityPDF, portfolio: Dict[str, Any], validated: bool):
    pdf.add_page()
    pdf.chapter_title(3, "Verity Brain 종합 판단")
    brain = portfolio.get("verity_brain", {}) or {}
    mb = brain.get("market_brain") or {}
    recs = portfolio.get("recommendations") or []

    # 종합 점수 + 분해
    pdf.subsection_title("3-1. 종합 점수 + VCI")
    avg_brain = mb.get("avg_brain_score")
    avg_fact = mb.get("avg_fact_score")
    avg_sent = mb.get("avg_sentiment_score")
    avg_vci = mb.get("avg_vci", 0) or 0

    pdf.metric_row([
        {"label": "Brain 평균", "value": f"{avg_brain or '-'}점",
         "color": pdf.GRADE_COLORS.get(brain_grade_from_score(avg_brain), pdf.WHITE)},
        {"label": "팩트", "value": f"{avg_fact or '-'}점", "color": pdf.WHITE},
        {"label": "심리", "value": f"{avg_sent or '-'}점", "color": pdf.PURPLE},
        {"label": "VCI", "value": f"{avg_vci:+d}", "color": pdf.RED if abs(avg_vci) >= 20 else pdf.GREEN},
    ])

    # VCI 해석
    if avg_vci > 5:
        vci_interp = f"심리가 팩트보다 {avg_vci:+d}포인트 앞서 있음 — 시장이 펀더멘털 대비 낙관적"
    elif avg_vci < -5:
        vci_interp = f"심리가 팩트보다 {avg_vci:+d}포인트 뒤처짐 — 시장이 펀더멘털 대비 비관적 (역발상 검토 영역)"
    else:
        vci_interp = "팩트와 심리 정합 — 추세 신뢰도 높음"
    pdf.text_block(f"VCI 해석: {vci_interp}")

    # 등급 분포
    pdf.subsection_title("3-2. 등급 분포")
    dist: Dict[str, int] = {}
    for r in recs:
        g = (r.get("verity_brain") or {}).get("grade") or r.get("recommendation") or "UNKNOWN"
        dist[g] = dist.get(g, 0) + 1
    total = sum(dist.values()) or 1
    for grade in ["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"]:
        cnt = dist.get(grade, 0)
        pct = round(cnt / total * 100, 1) if total else 0
        pdf._set_font("", 9)
        c = pdf.GRADE_COLORS.get(grade, pdf.WHITE)
        pdf.set_text_color(*c)
        pdf.set_x(18)
        pdf.cell(35, 6, f"{pdf.GRADE_LABELS.get(grade, grade)}")
        pdf.set_text_color(*pdf.WHITE)
        pdf.cell(20, 6, f"{cnt}종목")
        pdf.set_text_color(*pdf.GRAY)
        pdf.cell(20, 6, f"({pct}%)")
        # 작은 막대
        bar_w = max(2, pct * 1.0)
        pdf.set_fill_color(*c)
        pdf.rect(95, pdf.get_y() + 1, bar_w, 4, "F")
        pdf.ln(7)

    # 검증 미완료 경고
    if not validated:
        pdf._set_font("", 8)
        pdf.set_text_color(*pdf.YELLOW)
        pdf.set_x(15)
        pdf.cell(0, 5, "※ 검증 미완료 — 등급 분포는 참고. 본인 검토 후 판단 권장")
        pdf.ln(6)


# ─── 제4장 — 종목 판단 ────────────────────────────────────

def _render_chap4_stocks(pdf: VerityPDF, portfolio: Dict[str, Any], validated: bool):
    pdf.add_page()
    pdf.chapter_title(4, "종목 판단")
    recs = portfolio.get("recommendations") or []
    vams = portfolio.get("vams") or {}
    holdings = vams.get("holdings") or []

    # 4-A. BUY 종목 TOP 3
    pdf.subsection_title("4-A. 오늘의 BUY 종목 (최대 3)")
    buys = sorted(
        [r for r in recs if (r.get("verity_brain") or {}).get("grade") in ("STRONG_BUY", "BUY")
         or r.get("recommendation") in ("STRONG_BUY", "BUY")],
        key=lambda r: -((r.get("verity_brain") or {}).get("brain_score") or 0)
    )[:3]
    if not buys:
        pdf.text_block("오늘 없음 — 사유: BUY 등급 후보 부재 또는 매크로 필터 차단", color=pdf.GRAY)
    else:
        if not validated:
            pdf._set_font("", 7)
            pdf.set_text_color(*pdf.YELLOW)
            pdf.set_x(15)
            pdf.cell(0, 4, "※ 검증 미완료 상태 — '관찰 후보' 라벨 적용. 실거래 결정 시 본인 판단 필수")
            pdf.ln(5)
        for i, r in enumerate(buys, 1):
            grade = (r.get("verity_brain") or {}).get("grade") or r.get("recommendation") or "WATCH"
            score = (r.get("verity_brain") or {}).get("brain_score") or 0
            extra = f"신뢰도 {score:.0f}점"
            pdf.stock_row(i, _norm_text(r.get("name", "?")), r.get("ticker", "-"),
                          int(score), grade, extra)
            pdf.ln(2)

    # 4-B. 보유 종목 점검 (VAMS 연동)
    if holdings:
        pdf.subsection_title("4-B. 보유 종목 점검 (VAMS)")
        pdf._set_font("", 8)
        for h in holdings[:5]:
            name = _norm_text(h.get("name", "?"))
            entry = h.get("buy_price", 0)
            current = h.get("current_price", 0)
            target = h.get("target_price")
            stop = h.get("stop_loss")
            ret = h.get("return_pct", 0)
            ret_color = pdf.GREEN if ret >= 0 else pdf.RED
            pdf.set_x(15)
            pdf.set_text_color(*pdf.WHITE)
            pdf._set_font("B", 9)
            pdf.cell(50, 5, name)
            pdf._set_font("", 8)
            pdf.set_text_color(*ret_color)
            pdf.cell(20, 5, f"{ret:+.2f}%")
            pdf.set_text_color(*pdf.GRAY)
            pdf.cell(0, 5, f"진입 {entry:,.0f} → 현재 {current:,.0f}"
                          + (f" / 목표 {target:,.0f}" if target else "")
                          + (f" / 손절 {stop:,.0f}" if stop else ""))
            pdf.ln(5)
        pdf.ln(2)

    # 4-C. 회피 종목 TOP 3
    pdf.subsection_title("4-C. 주의·회피 종목 TOP 3")
    avoids = sorted(
        [r for r in recs if (r.get("verity_brain") or {}).get("grade") in ("CAUTION", "AVOID")],
        key=lambda r: ((r.get("verity_brain") or {}).get("brain_score") or 100)
    )[:3]
    if not avoids:
        pdf.text_block("회피 등급 종목 없음")
    else:
        for r in avoids:
            grade = (r.get("verity_brain") or {}).get("grade") or "AVOID"
            score = (r.get("verity_brain") or {}).get("brain_score") or 0
            risks = (r.get("verity_brain") or {}).get("red_flags", {})
            reason = ""
            if risks.get("auto_avoid"):
                reason = "; ".join(risks["auto_avoid"][:1])
            elif risks.get("downgrade"):
                reason = "; ".join(risks["downgrade"][:1])
            pdf.set_x(15)
            pdf._set_font("B", 9)
            pdf.set_text_color(*pdf.GRADE_COLORS.get(grade, pdf.RED))
            pdf.cell(60, 5, _norm_text(r.get("name", "?")))
            pdf._set_font("", 8)
            pdf.set_text_color(*pdf.GRAY)
            pdf.cell(15, 5, f"{score:.0f}점")
            pdf.set_text_color(204, 204, 204)
            pdf.multi_cell(110, pdf.LH_COMPACT, _norm_text(reason)[:80] or "사유 데이터 없음", align="L")
            pdf.ln(1)


# ─── 제5장 — 섹터 동향 ────────────────────────────────────

def _render_chap5_sectors(pdf: VerityPDF, portfolio: Dict[str, Any]):
    pdf.add_page()
    pdf.chapter_title(5, "섹터 동향")
    sectors = portfolio.get("sectors") or []
    if not sectors:
        pdf.narrative_paragraphs("섹터 데이터 미수집.")
        return

    sorted_secs = sorted(sectors, key=lambda s: -(s.get("change_pct") or 0))
    winners = sorted_secs[:3]
    losers = sorted_secs[-3:][::-1]

    pdf.subsection_title("5-1. 상승 TOP 3")
    for s in winners:
        chg = s.get("change_pct", 0) or 0
        pdf.set_x(18)
        pdf._set_font("B", 9)
        pdf.set_text_color(*pdf.GREEN)
        pdf.cell(60, 6, _norm_text(s.get("name", "")))
        pdf.cell(0, 6, f"{chg:+.2f}%")
        pdf.ln(6)

    pdf.subsection_title("5-2. 하락 TOP 3")
    for s in losers:
        chg = s.get("change_pct", 0) or 0
        pdf.set_x(18)
        pdf._set_font("B", 9)
        pdf.set_text_color(*pdf.RED)
        pdf.cell(60, 6, _norm_text(s.get("name", "")))
        pdf.cell(0, 6, f"{chg:+.2f}%")
        pdf.ln(6)

    # 자금 흐름
    cf = (portfolio.get("macro") or {}).get("capital_flow") or {}
    if cf:
        pdf.subsection_title("5-3. 자금 흐름")
        pdf.narrative_paragraphs(_capital_flow_narrative(cf))


# ─── 제6장 — VAMS 현황 ───────────────────────────────────

def _render_chap6_vams(pdf: VerityPDF, portfolio: Dict[str, Any]):
    pdf.add_page()
    pdf.chapter_title(6, "VAMS 현황")
    vams = portfolio.get("vams") or {}

    total_asset = vams.get("total_asset", 0)
    cash = vams.get("cash", 0)
    holdings = vams.get("holdings") or []
    cash_pct = round(cash / total_asset * 100, 1) if total_asset else 0
    cum_return = vams.get("cum_return_pct", 0)

    pdf.metric_row([
        {"label": "총 자산", "value": f"{total_asset:,.0f}원", "color": pdf.WHITE},
        {"label": "누적 수익률", "value": f"{cum_return:+.2f}%",
         "color": pdf.GREEN if cum_return >= 0 else pdf.RED},
        {"label": "현금 비중", "value": f"{cash_pct}%", "color": pdf.YELLOW},
        {"label": "보유 종목", "value": f"{len(holdings)}종목", "color": pdf.WHITE},
    ])

    # Brain 적중률 추이 (4주 롤링) — brain_learning 모듈에서
    try:
        from api.metadata import brain_learning
        trend = brain_learning.trend_summary(days=28)
        if trend.get("hit_rate_14d_avg") is not None:
            pdf.subsection_title("6-2. Brain 적중률 추이 (4주)")
            pdf.text_block(f"14d 적중률 평균 {trend['hit_rate_14d_avg']}%, "
                          f"방향 {trend.get('hit_rate_14d_trend', 'n/a')}")
    except Exception:
        pass


# ─── 제7장 — AI 모델 이견 검토 ────────────────────────────

def _render_chap7_ai_disagreement(pdf: VerityPDF, portfolio: Dict[str, Any]):
    pdf.add_page()
    pdf.chapter_title(7, "AI 모델 이견 검토")
    recs = portfolio.get("recommendations") or []

    disagreements = []
    for r in recs:
        gem = (r.get("ai_verdict") or "")
        cla = (r.get("claude_verdict") or "")
        if r.get("agrees_with_gemini") is False or (
            r.get("override_recommendation") and r.get("override_recommendation") != r.get("recommendation")
        ):
            disagreements.append(r)

    if not disagreements:
        pdf.narrative_paragraphs("이번 이견 없음 — Gemini/Claude 판정 일치")
        return

    pdf._set_font("", 9)
    for r in disagreements[:5]:
        pdf.set_x(15)
        pdf._set_font("B", 10)
        pdf.set_text_color(*pdf.WHITE)
        pdf.cell(0, 6, f"{_norm_text(r.get('name', '?'))} ({r.get('ticker', '-')})")
        pdf.ln(6)
        pdf._set_font("", 8)
        pdf.set_text_color(204, 204, 204)
        pdf.set_x(18)
        pdf.multi_cell(175, pdf.LH_COMPACT,
                       f"Gemini: {_safe_report_text(r.get('ai_verdict', ''))[:100]}", align="L")
        pdf.set_x(18)
        pdf.multi_cell(175, pdf.LH_COMPACT,
                       f"Claude: {_safe_report_text(r.get('claude_verdict', ''))[:100]}", align="L")
        adopt = r.get("override_recommendation") or r.get("recommendation")
        pdf.set_x(18)
        pdf.set_text_color(*pdf.YELLOW)
        pdf.multi_cell(175, pdf.LH_COMPACT,
                       f"채택: {adopt} (보수 원칙)", align="L")
        pdf.set_text_color(204, 204, 204)
        pdf.ln(3)


# ─── 결론 + 면책 ─────────────────────────────────────────

def _render_conclusion(pdf: VerityPDF, portfolio: Dict[str, Any], val_summary: Dict[str, Any]):
    pdf.add_page()
    pdf._set_font("B", 13)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(12)
    pdf.cell(0, 9, "결론 및 면책")
    pdf.ln(10)
    pdf.narrative_paragraphs(_conclusion_narrative(portfolio))

    pdf._set_font("", 8)
    pdf.set_text_color(*pdf.DARK_GRAY)
    pdf.set_x(15)
    pdf.multi_cell(180, pdf.LH_COMPACT,
                   "본 보고서는 VERITY 자동 분석 시스템의 출력물로, 투자자문업법상 자문이 아닙니다. "
                   "기재된 종목·등급·시나리오는 본인 의사결정 참고용이며 매매 권유가 아닙니다. "
                   "최종 책임은 투자자 본인에게 있습니다.", align="L")
    pdf.ln(3)
    pdf.set_x(15)
    pdf.cell(0, 5, f"검증 상태: {val_summary.get('watermark_label', '')}")


# ─── Public entry ────────────────────────────────────────

def generate_daily_admin_pdf_v2(portfolio: Dict[str, Any]) -> str:
    """Daily 관리자 리포트 PDF v2 — 7장 구조."""
    vams = portfolio.get("vams") or {}
    val_summary = validation_status_summary(vams)

    pdf = VerityPDF()
    pdf.add_page()

    _render_cover(pdf, portfolio, val_summary)
    _render_chap1_macro(pdf, portfolio)
    _render_chap2_events(pdf, portfolio)
    _render_chap3_brain(pdf, portfolio, validated=val_summary["validated"])
    _render_chap4_stocks(pdf, portfolio, validated=val_summary["validated"])
    _render_chap5_sectors(pdf, portfolio)
    _render_chap6_vams(pdf, portfolio)
    _render_chap7_ai_disagreement(pdf, portfolio)
    _render_conclusion(pdf, portfolio, val_summary)

    out_dir = os.path.join(DATA_DIR, "reports")
    os.makedirs(out_dir, exist_ok=True)
    fname = f"verity_daily_admin_{now_kst().strftime('%Y%m%d_%H%M')}.pdf"
    path = os.path.join(out_dir, fname)
    pdf.output(path)
    # Latest alias — Framer 컴포넌트가 안정 URL 로 다운로드
    import shutil
    shutil.copy2(path, os.path.join(out_dir, "verity_daily_admin.pdf"))
    return path
