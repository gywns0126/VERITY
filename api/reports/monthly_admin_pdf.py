"""
Monthly 관리자 리포트 PDF — Daily v2 디자인 정합 10장 구조.

장 구성 (daily 와 톤 매칭 + 월간 특수 CH 0):
  COVER    30초 월간 브리핑
  제0장    반성 및 개선 방안 (postmortem + Brain 자체 개선 제안 — 사용자 요청 2026-05-15)
  제1장    매크로 환경 변화 (월간 + macro_outlook narrative)
  제2장    추천 성과 복기 (주차별 + winner/loser + performance_review narrative)
  제3장    AI 브레인 등급별 실적 (등급별 + Factor IC + brain_review narrative)
  제4장    종목 월간 (TOP 5 winners mini + 보유 종목 + worst mini)
  제5장    섹터 동향 — 돈의 흐름 (TOP 10 + 자금흐름 + sector_analysis narrative)
  제6장    VAMS 월간 (KPI + PnL curve + MDD)
  제7장    Black Swan + 헤드라인 월간
  제8장    Postmortem 월간 + Market Horizon
  제9장    다음 월간 전략 + 리스크 주의 (strategy + risk_watch narrative)

데이터 흐름:
  api/main.py → generate_periodic_analysis('monthly') → enrich_monthly_analysis
  → renderer 가 portfolio.monthly_report.* narrative + enriched key 둘 다 read.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from api.config import DATA_DIR, now_kst
from api.reports.pdf_generator import VerityPDF, _norm_text
from api.utils.dilution import (
    brain_grade_from_score, validation_status_summary,
)
from api.utils.macro_meta import macro_as_of_line
from api.intelligence.monthly_aggregator import enrich_monthly_analysis


def _fmt_num(v) -> str:
    try:
        f = float(v)
        if f >= 1e8:
            return f"{f/1e8:.1f}억"
        if f >= 1e4:
            return f"{f:,.0f}"
        return f"{f:.2f}"
    except (TypeError, ValueError):
        return str(v)


def _render_narrative(pdf: VerityPDF, text: str, label: str = "") -> None:
    """monthly_report.* narrative 블록 — VerityReport 톤 정합.

    Section 본문 텍스트 (10pt, INK_SECONDARY, 풀폭). 빈 텍스트면 조용히 skip.
    """
    if not text or not str(text).strip():
        return
    pdf.ln(1)
    if label:
        pdf._set_font("B", 8); pdf.set_text_color(*pdf.INK_TERTIARY); pdf.set_x(15)
        pdf.cell(0, 5, label); pdf.ln(5)
    pdf._set_font("", 9); pdf.set_text_color(*pdf.INK_SECONDARY); pdf.set_x(15)
    pdf.multi_cell(180, pdf.LH_BODY, _norm_text(str(text)), align="L")
    pdf.ln(2)


# ─── COVER — 30초 월간 브리핑 ──────────────────────────────────

def _render_cover(pdf: VerityPDF, analysis: Dict[str, Any],
                  portfolio: Dict[str, Any], val_summary: Dict[str, Any]):
    period_label = analysis.get("period_label", "월간")
    date_range = analysis.get("date_range") or {}
    recs = analysis.get("recommendations") or {}
    port = analysis.get("portfolio") or {}
    brief = analysis.get("briefing_monthly") or {}
    vams = portfolio.get("vams") or {}
    market_brain = (portfolio.get("verity_brain") or {}).get("market_brain") or {}

    # 제목
    pdf._set_font("B", 17); pdf.set_text_color(*pdf.WHITE); pdf.set_x(12)
    pdf.cell(0, 10, f"VERITY {period_label.upper()} ADMIN REPORT"); pdf.ln(8)
    pdf._set_font("", 9); pdf.set_text_color(*pdf.GRAY); pdf.set_x(12)
    pdf.multi_cell(180, pdf.LH_BOX,
                   "관리자용 — 월간 성과 회고 + 시스템 성능 리뷰 + 파라미터 조정 (참고용 · 투자자문 아님)",
                   align="L")
    pdf.ln(2); pdf.set_x(12)
    pdf.cell(0, 6, f"기간: {date_range.get('start', '?')} ~ {date_range.get('end', '?')} "
                   f"({analysis.get('days_available', 0)}일 / {analysis.get('snapshot_count', 0)} snapshot)")
    pdf.ln(5); pdf.set_x(12)
    pdf.cell(0, 6, f"발행 시각: {now_kst().strftime('%Y-%m-%d %H:%M KST')}")
    pdf.ln(8)

    # 워터마크
    if not val_summary.get("validated"):
        y = pdf.get_y(); pdf.set_fill_color(235, 235, 235); pdf.rect(10, y, 190, 8, "F")
        pdf._set_font("B", 8); pdf.set_text_color(*pdf.YELLOW); pdf.set_xy(14, y + 1.5)
        pdf.cell(0, 5, f"⚠ {val_summary.get('watermark_label', '검증 진행 중')}")
        pdf.set_y(y + 12)

    # 30초 브리핑 박스 — daily 패턴 정합
    pdf._set_font("B", 13); pdf.set_text_color(*pdf.ACCENT); pdf.set_x(12)
    pdf.cell(0, 8, "30초 월간 브리핑"); pdf.ln(8)

    hit_rate = recs.get("hit_rate_pct") or 0
    avg_brain = market_brain.get("avg_brain_score")
    grade_raw = brain_grade_from_score(avg_brain)
    judgment = pdf.GRADE_LABELS.get(grade_raw, grade_raw)

    # 큰 글씨 판정
    pdf._set_font("B", 22)
    grade_color = pdf.GRADE_COLORS.get(grade_raw, pdf.WHITE)
    pdf.set_text_color(*grade_color); pdf.set_x(15)
    if hit_rate >= 55:
        verdict_word = "정상 작동"
    elif hit_rate < 40 and (recs.get("total_buy_recs") or 0) > 5:
        verdict_word = "조정 필요"
    else:
        verdict_word = "혼조 검토"
    pdf.cell(0, 12, f"이달의 판단: {verdict_word}"); pdf.ln(13)

    pdf._set_font("", 10); pdf.set_text_color(*pdf.GRAY); pdf.set_x(15)
    pdf.cell(0, 6, f"적중률 {hit_rate}% · 평균 수익 {recs.get('avg_return_pct', 0):+.2f}% · "
                   f"VAMS {port.get('period_return_pct', 0):+.2f}%")
    pdf.ln(10)

    # 핵심 근거 3줄
    pdf._set_font("B", 10); pdf.set_text_color(*pdf.WHITE); pdf.set_x(15)
    pdf.cell(0, 6, "핵심 근거 3줄"); pdf.ln(6)
    pdf._set_font("", 9); pdf.set_text_color(60, 60, 60)
    for line in [
        f"· 매크로: {_norm_text(brief.get('macro_line', '-'))}",
        f"· 성과: {_norm_text(brief.get('perf_line', '-'))}",
        f"· 판단: {_norm_text(brief.get('verdict_line', '-'))}",
    ]:
        pdf.set_x(18); pdf.multi_cell(177, pdf.LH_BODY, line, align="L"); pdf.ln(1)
    pdf.ln(4)

    # 다음 달 액션
    pdf._set_font("B", 10); pdf.set_text_color(*pdf.WHITE); pdf.set_x(15)
    pdf.cell(0, 6, "다음 달 액션"); pdf.ln(6)
    pdf._set_font("", 9); pdf.set_text_color(60, 60, 60)
    for a in (brief.get("action_items") or [])[:3]:
        pdf.set_x(18); pdf.multi_cell(177, pdf.LH_BODY, f"· {_norm_text(a)}", align="L"); pdf.ln(1)


# ─── 제0장 — 반성 및 개선 방안 (사용자 요청 2026-05-15) ──────────

def _render_chap0_reflection(pdf: VerityPDF, analysis: Dict[str, Any],
                              portfolio: Dict[str, Any]) -> None:
    """리포트 최상단 반성·개선 박스 — Brain 이 문제 정의·시스템 개선 제안.

    Source:
      - postmortem (현 portfolio): status / lesson / system_suggestion / misleading_factors
      - postmortem_monthly (30일 합산): top_misleading_factors / suggestions_sample
      - monthly_report.brain_review (Brain 자체 등급별 오판 분석)
      - monthly_report.strategy (다음 단계 개선 방향)
      - trade_plan_evolution_signals (있을 경우만)

    데이터 0 이면 "이달은 검토할 문제 없음" 명시 — silent skip 금지
    (feedback_data_collection_verification_mandatory 정합).
    """
    pdf.add_page(); pdf.chapter_title(0, "반성 및 개선 방안")
    pm = portfolio.get("postmortem") or {}
    pm_monthly = analysis.get("postmortem_monthly") or {}
    monthly = portfolio.get("monthly_report") or {}
    tpe = portfolio.get("trade_plan_evolution_signals") or {}

    # 0-1. 이달의 문제 정의 (problems)
    pdf.subsection_title("0-1. 이달의 문제 정의")
    has_problems = False

    # 현 postmortem (가장 최신)
    pm_status = pm.get("status")
    if pm_status == "clean":
        msg = pm.get("message") or "유의미한 AI 오심 없음"
        pdf.text_block(f"단기 (~30일) 진단: {msg}", color=pdf.GREEN)
        has_problems = True  # clean 도 정보
    elif pm.get("lesson"):
        pdf.text_block(f"단기 교훈: {_norm_text(str(pm['lesson']))[:300]}")
        has_problems = True

    # 30일 합산 misleading factors (Brain 결정에 오도 빈도 TOP)
    top_mis = pm_monthly.get("top_misleading_factors") or []
    if top_mis:
        pdf.ln(1)
        pdf._set_font("B", 8); pdf.set_text_color(*pdf.RED); pdf.set_x(15)
        pdf.cell(0, 5, "오도성 팩터 30일 빈도 TOP 5 (= 시스템 신뢰도 깎는 입력)"); pdf.ln(5)
        pdf._set_font("", 8)
        for m in top_mis:
            pdf.set_x(20); pdf.set_text_color(*pdf.INK_SECONDARY)
            pdf.cell(120, 5, _norm_text(m.get("factor", ""))[:40])
            pdf.set_text_color(*pdf.RED)
            pdf.cell(0, 5, f"{m.get('count', 0)}회 출현"); pdf.ln(5)
        has_problems = True

    # Brain 자체 등급별 평가 — 오판 포인트
    brain_review = monthly.get("brain_review")
    if brain_review:
        _render_narrative(pdf, brain_review, "Brain 자체 등급별 오판 분석")
        has_problems = True

    if not has_problems:
        pdf.text_block(
            "이달은 검토할 문제 없음 — 데이터 누적 부족 (postmortem 30일 < 임계).",
            color=pdf.GRAY,
        )

    # 0-2. 시스템 개선 제안 (Brain 의 system_suggestion)
    pdf.ln(2); pdf.subsection_title("0-2. 시스템 개선 제안 — Brain 의 진단")
    has_suggestion = False

    # 현 postmortem system_suggestion
    if pm.get("system_suggestion"):
        pdf._set_font("B", 8); pdf.set_text_color(*pdf.ACCENT); pdf.set_x(15)
        pdf.cell(0, 5, "최신 단기 제안"); pdf.ln(5)
        pdf._set_font("", 9); pdf.set_text_color(*pdf.INK); pdf.set_x(15)
        pdf.multi_cell(180, pdf.LH_BODY,
                       f"· {_norm_text(str(pm['system_suggestion']))[:400]}", align="L")
        pdf.ln(1)
        has_suggestion = True

    # 30일 합산 suggestions sample
    suggestions = pm_monthly.get("suggestions_sample") or []
    if suggestions:
        pdf._set_font("B", 8); pdf.set_text_color(*pdf.ACCENT); pdf.set_x(15)
        pdf.cell(0, 5, "30일 누적 제안 sample"); pdf.ln(5)
        pdf._set_font("", 9); pdf.set_text_color(*pdf.INK_SECONDARY)
        for s in suggestions[:3]:
            pdf.set_x(18)
            pdf.multi_cell(177, pdf.LH_BODY, f"· {_norm_text(str(s))[:280]}", align="L")
            pdf.ln(1)
        has_suggestion = True

    # trade_plan_evolution 신호 (있을 경우)
    tpe_sigs = (tpe.get("signals") or []) if isinstance(tpe, dict) else []
    if tpe_sigs:
        pdf._set_font("B", 8); pdf.set_text_color(*pdf.ORANGE); pdf.set_x(15)
        pdf.cell(0, 5, "Trade Plan 진화 신호"); pdf.ln(5)
        pdf._set_font("", 9); pdf.set_text_color(*pdf.INK_SECONDARY)
        for s in tpe_sigs[:4]:
            if isinstance(s, dict):
                txt = s.get("description") or s.get("signal") or str(s)
            else:
                txt = str(s)
            pdf.set_x(18)
            pdf.multi_cell(177, pdf.LH_BODY, f"· {_norm_text(txt)[:280]}", align="L")
        has_suggestion = True
    elif tpe.get("note"):
        pdf._set_font("", 8); pdf.set_text_color(*pdf.GRAY); pdf.set_x(15)
        pdf.cell(0, 5, f"Trade Plan 진화 신호: {_norm_text(str(tpe['note']))[:140]}")
        pdf.ln(5)

    if not has_suggestion:
        pdf.text_block(
            "Brain 의 시스템 개선 제안 — 30일 내 임계 충족 사례 부족 (오심 < 표본).",
            color=pdf.GRAY,
        )

    # 0-3. 다음 달 가드 (strategy + risk_watch 통합)
    pdf.ln(2); pdf.subsection_title("0-3. 다음 달 가드")
    strategy = monthly.get("strategy")
    risk_watch = monthly.get("risk_watch")
    if strategy:
        _render_narrative(pdf, strategy, "다음 달 전략 방향 (Brain 제안)")
    if risk_watch:
        _render_narrative(pdf, risk_watch, "경계 리스크")
    if not strategy and not risk_watch:
        pdf.text_block("Brain 의 다음 단계 narrative 미생성 (Gemini periodic_report 후속 cron 대기)",
                       color=pdf.GRAY)


# ─── 제1장 — 매크로 환경 월간 ──────────────────────────────────

def _render_chap1_macro(pdf: VerityPDF, analysis: Dict[str, Any], portfolio: Dict[str, Any]):
    pdf.add_page(); pdf.chapter_title(1, "매크로 환경 변화")
    flat = analysis.get("macro_flat") or {}
    macro = portfolio.get("macro") or {}

    pdf.subsection_title("1-1. 월간 시장 신호등")
    vix_avg = flat.get("vix_avg") or 0
    sp_pct = flat.get("sp500_monthly_pct") or 0
    kospi_pct = flat.get("kospi_monthly_pct") or 0

    def _light(v, warn, danger, reverse=False):
        if reverse:
            if v > danger: return ("🔴", pdf.RED)
            if v > warn: return ("🟡", pdf.YELLOW)
            return ("🟢", pdf.GREEN)
        if v > danger: return ("🟢", pdf.GREEN)
        if v > warn: return ("🟡", pdf.YELLOW)
        return ("🔴", pdf.RED)

    vix_icon, vix_c = _light(vix_avg, 22, 30, reverse=True)
    sp_icon, sp_c = _light(sp_pct, -3, 0)
    kospi_icon, kospi_c = _light(kospi_pct, -3, 0)

    pdf._set_font("", 10)
    for icon, color, label, value in [
        (vix_icon, vix_c, "글로벌 위험선호", f"VIX 평균 {vix_avg}"),
        (sp_icon, sp_c, "미장 흐름", f"S&P500 {sp_pct:+.2f}%"),
        (kospi_icon, kospi_c, "한국 흐름", f"KOSPI {kospi_pct:+.2f}%"),
    ]:
        pdf.set_text_color(*color); pdf.set_x(18); pdf.cell(8, 6, icon)
        pdf.set_text_color(*pdf.WHITE); pdf.set_x(28)
        pdf.cell(0, 6, f"{label} — {value}"); pdf.ln(7)
    pdf.ln(2)

    pdf.subsection_title("1-2. 월간 주요 지표 평균·변화")
    pdf.metric_row([
        {"label": "VIX 평균", "value": str(flat.get("vix_avg") or "-"),
         "color": pdf.RED if vix_avg > 22 else pdf.GREEN},
        {"label": "USD/KRW 평균", "value": f"{flat.get('usd_krw_avg', '-')}원", "color": pdf.WHITE},
        {"label": "S&P500", "value": f"{sp_pct:+.2f}%",
         "color": pdf.GREEN if sp_pct >= 0 else pdf.RED},
        {"label": "KOSPI", "value": f"{kospi_pct:+.2f}%",
         "color": pdf.GREEN if kospi_pct >= 0 else pdf.RED},
    ])

    # macro_as_of (시점 표기 의무 — feedback_macro_timestamp_policy)
    aof = macro_as_of_line(macro)
    if aof:
        pdf._set_font("", 7); pdf.set_text_color(*pdf.DARK_GRAY); pdf.set_x(15)
        pdf.cell(0, 4, aof); pdf.ln(6)

    pdf.subsection_title("1-3. 월간 이벤트 결산")
    events = flat.get("events_review") or []
    if events:
        for e in events[:6]:
            pdf._set_font("", 9); pdf.set_text_color(60, 60, 60); pdf.set_x(18)
            pdf.multi_cell(177, pdf.LH_BODY,
                           f"· {_norm_text(e.get('name', ''))} ({e.get('date', '-')}) — "
                           f"컨센 {e.get('consensus', '-')} / 실제 {e.get('actual', '-')} / "
                           f"VERITY 시나리오 {e.get('scenario_match', '-')}", align="L")
    else:
        pdf.text_block("이벤트 결산 데이터 미수집", color=pdf.GRAY)

    # 1-4. 매크로 환경 변화 (Brain narrative — monthly_report.macro_outlook)
    monthly = portfolio.get("monthly_report") or {}
    if monthly.get("macro_outlook"):
        pdf.subsection_title("1-4. 매크로 환경 변화 — Brain 해설")
        _render_narrative(pdf, monthly.get("macro_outlook"))


# ─── 제2장 — 추천 성과 복기 (VerityReport 톤) ────────────────

def _render_chap2_performance(pdf: VerityPDF, analysis: Dict[str, Any],
                              portfolio: Dict[str, Any]):
    recs = analysis.get("recommendations") or {}
    port = analysis.get("portfolio") or {}
    hit_rate = recs.get("hit_rate_pct") or 0
    pdf.add_page()
    pdf.chapter_title(2, f"추천 성과 복기 — 적중률 {hit_rate}%")

    # 2-1. 주차별 성과
    pdf.subsection_title("2-1. 주차별 BUY 적중·평균 수익률")
    weekly = recs.get("weekly_breakdown") or []
    if weekly:
        pdf._set_font("B", 7); pdf.set_text_color(*pdf.INK_TERTIARY); pdf.set_x(15)
        pdf.cell(25, 5, "주차"); pdf.cell(30, 5, "BUY 건수", align="R")
        pdf.cell(30, 5, "적중률", align="R"); pdf.cell(35, 5, "평균 수익률", align="R")
        pdf.ln(5)
        pdf.set_draw_color(*pdf.BORDER); pdf.set_line_width(0.2)
        y = pdf.get_y(); pdf.line(15, y, 135, y); pdf.ln(1)
        for w in weekly[:8]:
            hr = w.get("hit_rate", 0)
            ar = w.get("avg_return", 0)
            pdf.set_x(15); pdf._set_font("B", 8); pdf.set_text_color(*pdf.INK)
            pdf.cell(25, 5, str(w.get("label", "?")))
            pdf._set_font("", 8); pdf.set_text_color(*pdf.INK_SECONDARY)
            pdf.cell(30, 5, f"{w.get('buy_count', 0)}건", align="R")
            pdf.set_text_color(*(pdf.GREEN if hr >= 55 else pdf.YELLOW if hr >= 45 else pdf.RED))
            pdf.cell(30, 5, f"{hr}%", align="R")
            pdf.set_text_color(*(pdf.GREEN if ar >= 0 else pdf.RED))
            pdf.cell(35, 5, f"{ar:+.2f}%", align="R")
            pdf.ln(5)
    else:
        pdf.text_block("주차별 분해 데이터 부족 (snapshot < 2)", color=pdf.GRAY)

    # 2-2. VAMS PnL 추이
    pdf.subsection_title("2-2. VAMS 자산 추이")
    pnl = port.get("pnl_curve") or []
    if pnl:
        start = pnl[0].get("value", 0); end = pnl[-1].get("value", 0)
        peak = max(p.get("value", 0) for p in pnl)
        trough = min(p.get("value", 0) for p in pnl)
        pdf.metric_row([
            {"label": "월초", "value": _fmt_num(start), "color": pdf.WHITE},
            {"label": "월말", "value": _fmt_num(end),
             "color": pdf.GREEN if end >= start else pdf.RED},
            {"label": "최고점", "value": _fmt_num(peak), "color": pdf.GREEN},
            {"label": "최저점", "value": _fmt_num(trough), "color": pdf.YELLOW},
        ])
        # MDD (양수 magnitude — feedback_mdd_magnitude_display)
        mdd = port.get("mdd_pct") or port.get("max_drawdown_pct") or 0
        pdf._set_font("", 9); pdf.set_text_color(*pdf.INK_SECONDARY); pdf.set_x(18)
        pdf.cell(0, 5, f"MDD: {abs(mdd):.2f}% · 데이터 포인트 {len(pnl)}일"); pdf.ln(6)
    else:
        pdf.text_block("PnL 추이 데이터 미수집 (VAMS snapshot 누적 필요)", color=pdf.GRAY)

    # 2-3. Top winner / Top loser mini card
    blocks = analysis.get("top_blocks") or {}
    winners = blocks.get("winners") or []
    losers = blocks.get("losers") or []
    if winners or losers:
        pdf.subsection_title("2-3. 이달의 winner / loser 한 줄 요약")
        for r in winners[:3]:
            pdf._set_font("", 9); pdf.set_text_color(*pdf.GREEN); pdf.set_x(18)
            pdf.cell(0, 5, f"▲ {_norm_text(r.get('name', '?'))} ({r.get('ticker', '-')}) "
                          f"{r.get('return_pct', 0):+.2f}% · Brain {int(r.get('orig_brain_score') or 0)}점")
            pdf.ln(5)
        for r in losers[:3]:
            pdf._set_font("", 9); pdf.set_text_color(*pdf.RED); pdf.set_x(18)
            pdf.cell(0, 5, f"▼ {_norm_text(r.get('name', '?'))} ({r.get('ticker', '-')}) "
                          f"{r.get('return_pct', 0):+.2f}% · Brain {int(r.get('orig_brain_score') or 0)}점")
            pdf.ln(5)

    # 2-4. 성과 복기 해설 (Brain narrative — performance_review)
    monthly = portfolio.get("monthly_report") or {}
    if monthly.get("performance_review"):
        pdf.subsection_title("2-4. 성과 복기 — Brain 해설")
        _render_narrative(pdf, monthly.get("performance_review"))
    if monthly.get("executive_summary"):
        pdf.subsection_title("2-5. 한 줄 요약")
        _render_narrative(pdf, monthly.get("executive_summary"))


# ─── 제3장 — AI 브레인 등급별 실적 ────────────────────────────

def _render_chap3_brain(pdf: VerityPDF, analysis: Dict[str, Any], portfolio: Dict[str, Any]):
    pdf.add_page(); pdf.chapter_title(3, "AI 브레인 등급별 실적")
    ba = analysis.get("brain_accuracy") or {}
    market_brain = (portfolio.get("verity_brain") or {}).get("market_brain") or {}

    pdf.subsection_title("3-1. 월말 시점 종합 점수")
    avg_brain = market_brain.get("avg_brain_score")
    avg_fact = market_brain.get("avg_fact_score")
    avg_sent = market_brain.get("avg_sentiment_score")
    avg_vci = market_brain.get("avg_vci", 0) or 0
    pdf.metric_row([
        {"label": "Brain 평균", "value": f"{avg_brain or '-'}점",
         "color": pdf.GRADE_COLORS.get(brain_grade_from_score(avg_brain), pdf.WHITE)},
        {"label": "팩트", "value": f"{avg_fact or '-'}점", "color": pdf.WHITE},
        {"label": "심리", "value": f"{avg_sent or '-'}점", "color": pdf.PURPLE},
        {"label": "VCI", "value": f"{avg_vci:+d}", "color": pdf.RED if abs(avg_vci) >= 20 else pdf.GREEN},
    ])

    pdf.subsection_title("3-2. 등급별 적중률 + 평균 수익 (30일 집계)")
    grades = ba.get("grades") or {}
    if grades:
        pdf._set_font("B", 7); pdf.set_text_color(*pdf.INK_TERTIARY); pdf.set_x(15)
        pdf.cell(40, 5, "등급"); pdf.cell(25, 5, "건수", align="R")
        pdf.cell(40, 5, "평균 수익률", align="R"); pdf.cell(40, 5, "적중률", align="R"); pdf.ln(5)
        pdf.set_draw_color(*pdf.BORDER); pdf.set_line_width(0.2)
        y = pdf.get_y(); pdf.line(15, y, 160, y); pdf.ln(1)
        for g in ("STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"):
            row = grades.get(g) or {}
            if not row:
                continue
            pdf.set_x(15); pdf._set_font("B", 8); pdf.set_text_color(*pdf.INK)
            pdf.cell(40, 5, pdf.GRADE_LABELS.get(g, g))
            pdf._set_font("", 8); pdf.set_text_color(*pdf.INK_SECONDARY)
            pdf.cell(25, 5, f"{row.get('count', '-')}건", align="R")
            try:
                pdf.cell(40, 5, f"{float(row.get('avg_return', 0)):+.2f}%", align="R")
            except (TypeError, ValueError):
                pdf.cell(40, 5, "-", align="R")
            try:
                pdf.cell(40, 5, f"{float(row.get('hit_rate', 0)):.1f}%", align="R")
            except (TypeError, ValueError):
                pdf.cell(40, 5, "-", align="R")
            pdf.ln(5)
        insight = _norm_text(ba.get("insight") or "")
        if insight:
            pdf.ln(1); pdf.text_block(f"인사이트: {insight}")
    else:
        pdf.text_block("Brain 등급별 누적 데이터 부족", color=pdf.INK_TERTIARY)

    # 3-3. Factor IC 월간 (ICIR 순)
    pdf.subsection_title("3-3. Factor IC 월간 (예측력 — ICIR 순)")
    fic = analysis.get("factor_ic_monthly") or {}
    ranking = fic.get("ranking") or (fic.get("monthly_rollup") or {}).get("by_factor") or []
    if ranking:
        pdf._set_font("", 8)
        for it in ranking[:12]:
            name = _norm_text(it.get("factor") or "-")
            icir = it.get("icir") or it.get("avg_icir")
            ic = it.get("ic") or it.get("avg_ic")
            obs = it.get("obs") or it.get("n_obs")
            pdf.set_x(15); pdf._set_font("B", 8); pdf.set_text_color(*pdf.INK)
            pdf.cell(60, 5, name[:24])
            pdf._set_font("", 8); pdf.set_text_color(*pdf.INK_SECONDARY)
            try:
                pdf.cell(30, 5, f"ICIR {float(icir):+.3f}", align="R")
            except (TypeError, ValueError):
                pdf.cell(30, 5, "ICIR -", align="R")
            if ic is not None:
                try:
                    pdf.cell(30, 5, f"IC {float(ic):+.3f}", align="R")
                except (TypeError, ValueError):
                    pdf.cell(30, 5, "IC -", align="R")
            if obs is not None:
                pdf.cell(30, 5, f"n={obs}", align="R")
            pdf.ln(5)
        sig = fic.get("significant_factors") or []
        if sig:
            pdf.ln(1)
            pdf.text_block(f"유의 팩터 ({len(sig)}): " + ", ".join(map(str, sig[:12])))
    else:
        pdf.text_block("Factor IC 월간 누적 데이터 부족 (factor_ic builder cron 누적 필요)",
                      color=pdf.INK_TERTIARY)

    # 3-4. Brain 학습 추이 (월간)
    pdf.subsection_title("3-4. Brain 학습 추이")
    try:
        from api.metadata import brain_learning
        trend = brain_learning.trend_summary(days=30)
        if trend.get("samples", 0) >= 2:
            pdf.text_block(f"누적 {trend['samples']}일 / 14d 적중률 평균 "
                          f"{trend.get('hit_rate_14d_avg', '-')}% / 방향 "
                          f"{trend.get('hit_rate_14d_trend', 'n/a')}")
        else:
            pdf.text_block("Brain 학습 누적 데이터 부족", color=pdf.GRAY)
    except Exception:
        pdf.text_block("Brain 학습 데이터 부족", color=pdf.GRAY)

    # 3-5. Brain 등급 평가 해설 (Brain narrative — brain_review)
    monthly = portfolio.get("monthly_report") or {}
    if monthly.get("brain_review"):
        pdf.subsection_title("3-5. Brain 등급 평가 — 자체 해설")
        _render_narrative(pdf, monthly.get("brain_review"))

    # 3-6. 메타 분석 — 5 보조 입력 ranking + Brain 종합 판단자 별 패널
    # feedback_brain_synthesizer_role: Brain 을 보조 신호와 한 차트에 섞지 말 것.
    # 상승장 거품 제거: excess_accuracy = accuracy - market_drift_pct.
    meta = analysis.get("meta_analysis") or {}
    aux = meta.get("findings_aux") or []
    brain_node = meta.get("findings_brain")
    drift_pct = meta.get("market_drift_pct", 50.0)
    aux_labels = meta.get("aux_labels") or {
        "multi_factor": "멀티팩터 종합",
        "consensus": "컨센서스",
        "timing": "매매 타이밍",
        "prediction": "AI 예측(XGBoost)",
        "sentiment": "뉴스 감성",
    }
    if aux:
        pdf.subsection_title(f"3-6. 메타 분석 — 보조 입력 신호 (5) · 시장 baseline {drift_pct}%")
        # baseline 설명 박스
        pdf._set_font("", 8); pdf.set_text_color(*pdf.INK_TERTIARY); pdf.set_x(15)
        pdf.multi_cell(180, pdf.LH_COMPACT,
                       f"※ 같은 기간 종목 상승 비율 = {drift_pct}% — "
                       f"무뇌 '전부 BUY' predictor 의 적중률. 실력 = accuracy - baseline = excess. "
                       f"excess > 0 → 시장 drift 위 / < 0 → 역방향 또는 노이즈.",
                       align="L")
        pdf.ln(2)
        pdf._set_font("B", 7); pdf.set_text_color(*pdf.INK_TERTIARY); pdf.set_x(15)
        pdf.cell(50, 5, "보조 입력")
        pdf.cell(30, 5, "적중률", align="R")
        pdf.cell(35, 5, "excess (실력)", align="R")
        pdf.cell(25, 5, "표본", align="R"); pdf.ln(5)
        pdf.set_draw_color(*pdf.BORDER); pdf.set_line_width(0.2)
        y = pdf.get_y(); pdf.line(15, y, 155, y); pdf.ln(1)
        for f in aux:
            acc = f.get("accuracy_pct") or 0
            excess = f.get("excess_accuracy_pct") or 0
            sz = f.get("sample_size") or 0
            # excess 기준 색상 — 실력 위주
            color = pdf.GREEN if excess >= 5 else pdf.YELLOW if excess >= -5 else pdf.RED
            pdf.set_x(15); pdf._set_font("B", 8); pdf.set_text_color(*pdf.INK)
            pdf.cell(50, 5, aux_labels.get(f.get("source"), f.get("source")))
            pdf._set_font("", 8); pdf.set_text_color(*pdf.INK_SECONDARY)
            pdf.cell(30, 5, f"{acc}%", align="R")
            pdf.set_text_color(*color)
            pdf.cell(35, 5, f"{excess:+.1f}%p", align="R")
            pdf.set_text_color(*pdf.INK_TERTIARY)
            pdf.cell(25, 5, f"n={sz}", align="R")
            pdf.ln(5)

    if brain_node:
        pdf.ln(1); pdf.subsection_title("3-7. Brain 종합 판단자 성적 (참고치 · 보조 신호와 동급 비교 X)")
        b_acc = brain_node.get("accuracy_pct") or 0
        b_excess = brain_node.get("excess_accuracy_pct") or 0
        b_sz = brain_node.get("sample_size") or 0
        # excess 강조 — 절대치보다 실력이 본질
        b_color = pdf.GREEN if b_excess >= 5 else pdf.YELLOW if b_excess >= -5 else pdf.RED
        pdf._set_font("B", 10); pdf.set_text_color(*b_color); pdf.set_x(15)
        pdf.cell(0, 6, f"Brain excess: {b_excess:+.1f}%p  (적중률 {b_acc}% / baseline {drift_pct}% / n={b_sz})")
        pdf.ln(7)
        pdf._set_font("", 8); pdf.set_text_color(*pdf.INK_TERTIARY); pdf.set_x(15)
        pdf.multi_cell(180, pdf.LH_COMPACT,
                       f"※ {brain_node.get('note', '')}\n"
                       f"※ Brain = 위 5개 보조 입력 신호를 종합하여 최종 결정하는 판단자. 단순 5개 평균이 아니라 "
                       f"가중 조합(fact 0.70 / sentiment 0.30) + VCI(임계 ±25/±15, 보너스 +5/-10 비대칭) + "
                       f"매크로 가드(macro_size_multiplier 0.85, position sizing 적용) + 룰 거부권(red_flag 이중 페널티 -5점 + grade 강등 / quadrant 미선호 -5 + 강등)의 결과.\n"
                       f"※ 등급 임계 STRONG_BUY≥75 / BUY≥60 / WATCH≥45 / CAUTION≥25 / AVOID<25 (5단계 등간격, CAUTION만 25). "
                       f"산식 일체 = 가설 (Phase 0 운영 누적 ≈ 23일, VAMS reset 후 ≈ 9일). 365일 trail 도달 ~2027-05.\n"
                       f"※ IC-DEAD freeze (2026-05-25 commit 5efac33b): N<50 산식 자유 tweak 금지 규율. PM 사전 결정 4 factor 비활성, 나머지 자동 drift neutral 복원.\n"
                       f"※ 상승장 거품 제거: excess > 0 → 시장 drift 위의 실력. "
                       f"단순 accuracy_pct 는 상승장에서 무뇌 'BUY 전부' 와 구분 불가 "
                       f"(memory `project_market_horizon` 현 verdict = euphoria).",
                       align="L")
        # 낮은 값이면 알려진 결함 hint
        if b_excess < -5:
            pdf.ln(1); pdf._set_font("", 8); pdf.set_text_color(*pdf.YELLOW); pdf.set_x(15)
            pdf.multi_cell(180, pdf.LH_COMPACT,
                           f"⚠ Brain excess {b_excess:+.1f}%p — 시장 drift 보다 못한 실력. "
                           f"`project_brain_score_funnel_audit` 메모리 (BUY 0건 / max 50점 보수 편향) 정합. "
                           f"5/17 ATR verdict 후 Phase 1.5.1 sprint 진입 시 임계값 재정렬 큐.",
                           align="L")

    # 3-8. 메타 분석 해설 (narrative)
    if monthly.get("meta_insight"):
        pdf.subsection_title("3-8. 메타 분석 — Brain 해설")
        _render_narrative(pdf, monthly.get("meta_insight"))


# ─── 종목 mini block (daily 정합 압축형) ───────────────────────

def _render_stock_mini_block(pdf: VerityPDF, rank: int, r: Dict[str, Any]):
    """월간용 stock mini block — 종목 1개 ~5 줄. daily 패턴 정합."""
    if pdf.get_y() > 245:
        pdf.add_page()
    vb = r.get("verity_brain") or {}
    grade = vb.get("grade") or r.get("recommendation") or "WATCH"
    score = r.get("orig_brain_score") or vb.get("brain_score") or 0
    name = _norm_text(r.get("name", "?"))
    ticker = r.get("ticker", "-")
    ret = r.get("return_pct")

    y = pdf.get_y(); pdf.set_x(15)
    pdf._set_font("B", 10)
    pdf.set_text_color(*pdf.GRADE_COLORS.get(grade, pdf.INK))
    pdf.cell(8, 6, f"{rank}.")
    pdf._set_font("B", 10); pdf.set_text_color(*pdf.INK)
    pdf.cell(60, 6, f"{name} ({ticker})")
    pdf._set_font("", 8)
    pdf.set_text_color(*pdf.GRADE_COLORS.get(grade, pdf.INK))
    pdf.cell(20, 6, pdf.GRADE_LABELS.get(grade, grade))
    pdf.set_text_color(*pdf.INK_SECONDARY)
    pdf.cell(25, 6, f"Brain {int(score)}점")
    if ret is not None:
        ret_color = pdf.GREEN if ret >= 0 else pdf.RED
        pdf.set_text_color(*ret_color)
        pdf.cell(30, 6, f"{ret:+.2f}%")
    pdf.ln(6)

    # Layer 1 — buy/current price
    bp = r.get("buy_price"); cp = r.get("current_price") or r.get("price")
    layer1 = []
    if bp:
        layer1.append(f"진입 {_fmt_num(bp)}")
    if cp:
        layer1.append(f"현재 {_fmt_num(cp)}")
    target = r.get("target_price") or vb.get("target_price")
    if target:
        layer1.append(f"목표 {_fmt_num(target)}")
    if layer1:
        pdf.set_x(23); pdf._set_font("", 8); pdf.set_text_color(*pdf.INK_SECONDARY)
        pdf.cell(0, 5, "  ·  ".join(layer1)); pdf.ln(5)

    # Layer 2 — sector / market_cap / per / pbr
    sector = _norm_text(r.get("sector") or "")
    mcap = r.get("market_cap"); per = r.get("per") or vb.get("per")
    pbr = r.get("pbr") or vb.get("pbr")
    layer2 = []
    if sector:
        layer2.append(sector[:14])
    if mcap:
        try:
            mc_f = float(mcap)
            if mc_f > 1e12:
                layer2.append(f"시총 {mc_f/1e12:.1f}조")
            elif mc_f > 1e8:
                layer2.append(f"시총 {mc_f/1e8:.0f}억")
        except (TypeError, ValueError):
            pass
    if per is not None:
        try:
            layer2.append(f"PER {float(per):.1f}")
        except (TypeError, ValueError):
            pass
    if pbr is not None:
        try:
            layer2.append(f"PBR {float(pbr):.2f}")
        except (TypeError, ValueError):
            pass
    if layer2:
        pdf.set_x(23); pdf._set_font("", 8); pdf.set_text_color(*pdf.INK_TERTIARY)
        pdf.cell(0, 5, "  ·  ".join(layer2)); pdf.ln(5)

    # Layer 3 — AI verdict
    summary = _norm_text(vb.get("summary") or r.get("ai_verdict") or "")
    if summary:
        pdf.set_x(23); pdf._set_font("", 8); pdf.set_text_color(*pdf.INK_SECONDARY)
        pdf.multi_cell(165, 5, summary[:160], align="L")

    # 좌측 strip
    pdf.set_fill_color(*pdf.GRADE_COLORS.get(grade, pdf.INK))
    pdf.rect(15, y + 1, 0.8, pdf.get_y() - y - 1, "F")
    pdf.ln(2)


# ─── 제4장 — 종목 월간 결산 ────────────────────────────────────

def _render_chap4_stocks(pdf: VerityPDF, analysis: Dict[str, Any]):
    pdf.add_page(); pdf.chapter_title(4, "종목 월간 결산")
    blocks = analysis.get("top_blocks") or {}
    winners = blocks.get("winners") or []
    losers = blocks.get("losers") or []
    holdings = analysis.get("holdings_monthly") or []

    pdf.subsection_title(f"4-A. 이달의 TOP 5 winners")
    if winners:
        for i, r in enumerate(winners[:5], 1):
            _render_stock_mini_block(pdf, i, r)
    else:
        pdf.text_block("월초 BUY 종목 매칭 부족 (snapshot 누적 필요)", color=pdf.GRAY)

    pdf.subsection_title(f"4-B. 보유 종목 월간 perf ({len(holdings)}종목 전체)")
    if holdings:
        pdf._set_font("B", 7); pdf.set_text_color(*pdf.INK_TERTIARY); pdf.set_x(15)
        pdf.cell(50, 5, "종목"); pdf.cell(35, 5, "월초 가", align="R")
        pdf.cell(35, 5, "월말 가", align="R"); pdf.cell(30, 5, "수익률", align="R")
        pdf.cell(20, 5, "보유 유지", align="R"); pdf.ln(5)
        pdf.set_draw_color(*pdf.BORDER); pdf.set_line_width(0.2)
        y = pdf.get_y(); pdf.line(15, y, 185, y); pdf.ln(1)
        for h in holdings[:15]:
            ret = h.get("return_pct") or 0
            pdf.set_x(15); pdf._set_font("B", 8); pdf.set_text_color(*pdf.INK)
            pdf.cell(50, 5, _norm_text(h.get("name", "?"))[:18])
            pdf._set_font("", 8); pdf.set_text_color(*pdf.INK_SECONDARY)
            pdf.cell(35, 5, _fmt_num(h.get("start_price")), align="R")
            pdf.cell(35, 5, _fmt_num(h.get("end_price")), align="R")
            pdf.set_text_color(*(pdf.GREEN if ret >= 0 else pdf.RED))
            pdf.cell(30, 5, f"{ret:+.2f}%", align="R")
            pdf.set_text_color(*pdf.INK_TERTIARY)
            pdf.cell(20, 5, "보유" if h.get("still_held") else "청산", align="R"); pdf.ln(5)
    else:
        pdf.text_block("보유 종목 추적 데이터 부족", color=pdf.GRAY)

    pdf.subsection_title("4-C. 월간 worst 종목")
    if losers:
        for i, r in enumerate(losers[:3], 1):
            _render_stock_mini_block(pdf, i, r)
    else:
        pdf.text_block("worst 데이터 부족", color=pdf.GRAY)


# ─── 제5장 — 섹터 동향 (돈의 흐름) ─────────────────────────────

def _render_chap5_sectors(pdf: VerityPDF, analysis: Dict[str, Any],
                          portfolio: Dict[str, Any]):
    pdf.add_page(); pdf.chapter_title(5, "섹터 동향 — 돈의 흐름")
    sectors = analysis.get("sectors") or {}
    top = sectors.get("top3_sectors") or sectors.get("top_sectors") or []
    bottom = sectors.get("bottom3_sectors") or sectors.get("bottom_sectors") or []

    pdf.subsection_title(f"5-1. 상승 TOP 10 (전체 {len(top + bottom)}개)")
    if top:
        pdf._set_font("", 9)
        for i, s in enumerate(top[:10], 1):
            chg = s.get("change_pct") or s.get("avg_change_pct") or 0
            pdf.set_x(18); pdf.set_text_color(*pdf.GREEN)
            pdf.cell(8, 5, f"{i}.")
            pdf.set_text_color(*pdf.INK); pdf.cell(60, 5, _norm_text(s.get("name", "?"))[:18])
            pdf.set_text_color(*pdf.GREEN); pdf.cell(0, 5, f"{chg:+.2f}%"); pdf.ln(5)
    else:
        pdf.text_block("섹터 상승 데이터 부족", color=pdf.GRAY)

    pdf.subsection_title("5-2. 하락 TOP 10")
    if bottom:
        pdf._set_font("", 9)
        for i, s in enumerate(bottom[:10], 1):
            chg = s.get("change_pct") or s.get("avg_change_pct") or 0
            pdf.set_x(18); pdf.set_text_color(*pdf.RED)
            pdf.cell(8, 5, f"{i}.")
            pdf.set_text_color(*pdf.INK); pdf.cell(60, 5, _norm_text(s.get("name", "?"))[:18])
            pdf.set_text_color(*pdf.RED); pdf.cell(0, 5, f"{chg:+.2f}%"); pdf.ln(5)
    else:
        pdf.text_block("섹터 하락 데이터 부족", color=pdf.GRAY)

    # 5-3. 자금 흐름 (cftc_cot + fund_flow_trend)
    pdf.subsection_title("5-3. 자금 흐름 (CFTC + Fund Flow)")
    cot = analysis.get("cftc_cot_trend") or {}
    ff = analysis.get("fund_flow_trend") or {}
    if cot.get("available"):
        pdf.text_block(f"CFTC COT 우세 시그널: {cot.get('dominant_signal', '-')} "
                      f"(데이터 {cot.get('data_points', 0)}건)")
    if ff.get("available"):
        pdf.text_block(f"Fund Flow 우세 로테이션: {ff.get('dominant_signal', '-')} "
                      f"(데이터 {ff.get('data_points', 0)}건)")
    if not cot.get("available") and not ff.get("available"):
        pdf.text_block("자금 흐름 데이터 부족", color=pdf.GRAY)

    # 5-4. 다음 달 주목 섹터
    pdf.subsection_title("5-4. 다음 달 주목 섹터")
    next_focus = sectors.get("next_month_focus") or sectors.get("themes") or []
    if next_focus:
        for f in next_focus[:3]:
            pdf.text_block(f"※ {_norm_text(f.get('name', ''))} — "
                          f"{_norm_text(f.get('reason') or f.get('summary', ''))}")
    else:
        pdf.text_block("다음 달 주목 섹터 데이터 미수집", color=pdf.GRAY)

    # 5-5. 섹터 동향 — Brain 해설 (monthly_report.sector_analysis)
    monthly = portfolio.get("monthly_report") or {}
    if monthly.get("sector_analysis"):
        pdf.subsection_title("5-5. 섹터 동향 — Brain 해설")
        _render_narrative(pdf, monthly.get("sector_analysis"))


# ─── 제6장 — VAMS 월간 ────────────────────────────────────────

def _render_chap6_vams(pdf: VerityPDF, analysis: Dict[str, Any], portfolio: Dict[str, Any]):
    pdf.add_page(); pdf.chapter_title(6, "VAMS 월간 현황")
    port = analysis.get("portfolio") or {}
    vams = portfolio.get("vams") or {}

    pdf.subsection_title("6-1. KPI")
    cum = port.get("period_return_pct") or 0
    mdd = port.get("max_drawdown_pct") or port.get("mdd_pct") or 0
    total = _norm_text(str(vams.get("total_asset", "-")))
    cash = _norm_text(str(vams.get("cash", "-")))
    pdf.metric_row([
        {"label": "월간 수익률", "value": f"{cum:+.2f}%",
         "color": pdf.GREEN if cum >= 0 else pdf.RED},
        {"label": "MDD", "value": f"{abs(mdd):.2f}%",
         "color": pdf.RED if abs(mdd) > 10 else pdf.YELLOW if abs(mdd) > 5 else pdf.GREEN},
        {"label": "총 자산", "value": _fmt_num(vams.get("total_asset")), "color": pdf.WHITE},
        {"label": "현금", "value": _fmt_num(vams.get("cash")), "color": pdf.WHITE},
    ])

    pdf.subsection_title("6-2. 자산 추이 (전체 30일)")
    pnl = port.get("pnl_curve") or []
    if pnl:
        pdf._set_font("", 7); pdf.set_text_color(*pdf.INK_TERTIARY); pdf.set_x(15)
        # 간단 ASCII sparkline 대용 — value 변동 텍스트 트레이스
        first = pnl[0].get("value", 0); last = pnl[-1].get("value", 0)
        delta_pct = round((last - first) / first * 100, 2) if first else 0
        pdf.cell(0, 5, f"{pnl[0].get('date', '-')} → {pnl[-1].get('date', '-')} "
                       f"({len(pnl)}일 추적) · 누적 {delta_pct:+.2f}%")
        pdf.ln(6)
        # 마지막 10일 트레이스
        pdf._set_font("", 7); pdf.set_text_color(*pdf.INK_SECONDARY)
        for p in pnl[-10:]:
            pdf.set_x(18)
            pdf.cell(0, 4, f"  {p.get('date', '-')}  {_fmt_num(p.get('value', 0))}")
            pdf.ln(4)
    else:
        pdf.text_block("자산 추이 데이터 미수집", color=pdf.GRAY)

    # 6-3. Vision Metric — Antifragility + FOMO (2028 Golden Goose 추적, Perplexity Q6)
    pdf.subsection_title("6-3. 2028 Vision Metric (월간)")
    try:
        from api.quant.antifragility import assess_antifragility
        from api.quant.fomo_score import compute_fomo_score
        # 일별 pnl_curve → return series 추정
        returns = []
        for i in range(1, len(pnl)):
            prev = pnl[i-1].get("value", 0)
            cur = pnl[i].get("value", 0)
            if prev > 0:
                returns.append((cur - prev) / prev)
        if len(returns) >= 10:
            af = assess_antifragility(returns)
            pdf._set_font("", 8); pdf.set_text_color(*pdf.WHITE); pdf.set_x(15)
            verdict = af.get("verdict", "n/a")
            color = (pdf.GREEN if verdict == "antifragile_confirmed"
                     else pdf.YELLOW if verdict == "partial_antifragile"
                     else pdf.RED if verdict == "fragile" else pdf.WHITE)
            pdf.cell(60, 5, "  Antifragility verdict")
            pdf.set_text_color(*color)
            pdf.cell(0, 5, f"{verdict} ({af.get('conditions_met', 0)}/4 충족)")
            pdf.ln(5)
            pdf.set_text_color(*pdf.WHITE); pdf.set_x(15)
            skew = af.get("skewness", 0)
            kurt = af.get("kurtosis", 0)
            pdf.cell(0, 5, f"  Skew {skew:+.2f} (>0 = right tail) / Kurt {kurt:.2f} (>3 = fat tail)")
            pdf.ln(5)
        # FOMO Score
        history = vams.get("history") or vams.get("trade_history") or []
        if history:
            fomo = compute_fomo_score(history, days_window=30)
            fs = fomo.get("fomo_score")
            interp = fomo.get("interpretation")
            color = (pdf.GREEN if interp == "anti_fomo_achieved"
                     else pdf.YELLOW if interp == "caution" else pdf.RED)
            pdf._set_font("", 8); pdf.set_text_color(*pdf.WHITE); pdf.set_x(15)
            pdf.cell(60, 5, "  FOMO Score (30d)")
            pdf.set_text_color(*color)
            pdf.cell(0, 5, f"{fs if fs is not None else 'n/a'} ({interp})")
            pdf.set_text_color(*pdf.WHITE); pdf.ln(5)
    except Exception as e:
        pdf.text_block(f"Vision metric 산출 실패: {e}", color=pdf.GRAY)


# ─── 제7장 — Black Swan + 헤드라인 월간 ────────────────────────

def _render_chap7_blackswan_headlines(pdf: VerityPDF, analysis: Dict[str, Any]):
    pdf.add_page(); pdf.chapter_title(7, "Black Swan + 헤드라인 월간")
    bs = analysis.get("black_swan_events") or {}

    pdf.subsection_title("7-1. Black Swan 30일 결산")
    if bs.get("available") and bs.get("count", 0) > 0:
        sev = bs.get("severity_dist") or {}
        pdf.text_block(f"총 {bs.get('count', 0)}건 · 고심각도(≥8) {sev.get('high_8plus', 0)}건 · "
                      f"중심각도(5~7) {sev.get('mid_5to7', 0)}건 · "
                      f"텔레그램 발송 {bs.get('telegram_sent_count', 0)}건")
        cats = bs.get("category_dist") or {}
        if cats:
            pdf._set_font("", 8); pdf.set_text_color(*pdf.INK_SECONDARY); pdf.set_x(18)
            cat_line = ", ".join(f"{k}:{v}" for k, v in list(cats.items())[:6])
            pdf.multi_cell(177, pdf.LH_COMPACT, f"카테고리: {cat_line}", align="L"); pdf.ln(1)
        top_events = bs.get("top_events") or []
        for e in top_events[:4]:
            pdf._set_font("", 8); pdf.set_text_color(*pdf.INK); pdf.set_x(18)
            pdf.multi_cell(177, pdf.LH_COMPACT,
                           f"· [{e.get('severity', '?')}] {_norm_text(e.get('summary_ko', ''))[:150]}",
                           align="L"); pdf.ln(1)
    else:
        pdf.text_block("30일 내 black swan 이벤트 없음", color=pdf.GRAY)

    pdf.subsection_title("7-2. 헤드라인 카테고리 분포 (최근 7일)")
    hl = analysis.get("headlines_monthly") or {}
    if hl:
        for cat, items in list(hl.items())[:5]:
            pdf._set_font("B", 9); pdf.set_text_color(*pdf.INK); pdf.set_x(15)
            pdf.cell(0, 5, f"[{cat}] {len(items)}건"); pdf.ln(5)
            pdf._set_font("", 8); pdf.set_text_color(*pdf.INK_SECONDARY)
            for h in items[:3]:
                pdf.set_x(20)
                pdf.multi_cell(175, pdf.LH_COMPACT,
                               f"· {_norm_text(h.get('title', ''))[:130]} ({h.get('source', '-')})",
                               align="L")
    else:
        pdf.text_block("헤드라인 데이터 미수집", color=pdf.GRAY)


# ─── 제8장 — Postmortem 월간 + Market Horizon ─────────────────

def _render_chap8_postmortem_horizon(pdf: VerityPDF, analysis: Dict[str, Any]):
    pdf.add_page(); pdf.chapter_title(8, "Postmortem + Market Horizon 월간")

    # 8-1. Postmortem 월간 합산
    pm = analysis.get("postmortem_monthly") or {}
    pdf.subsection_title("8-1. Postmortem 월간 (운영 self-review)")
    if pm.get("snapshot_count_with_pm", 0) > 0:
        pdf.text_block(f"분석 완료 snapshot {pm['snapshot_count_with_pm']}일 · "
                      f"누적 실패 종목 {pm.get('total_analyzed', 0)}건")
        top_mis = pm.get("top_misleading_factors") or []
        if top_mis:
            pdf.ln(1); pdf._set_font("B", 8); pdf.set_text_color(*pdf.INK); pdf.set_x(15)
            pdf.cell(0, 5, "오도성 팩터 빈도 TOP 5"); pdf.ln(5)
            pdf._set_font("", 8)
            for m in top_mis:
                pdf.set_x(20); pdf.set_text_color(*pdf.INK_SECONDARY)
                pdf.cell(80, 5, _norm_text(m.get("factor", ""))[:30])
                pdf.set_text_color(*pdf.INK); pdf.cell(0, 5, f"{m.get('count', 0)}회"); pdf.ln(5)
        samples = pm.get("lessons_sample") or pm.get("summaries_sample") or []
        if samples:
            pdf.ln(1); pdf._set_font("B", 8); pdf.set_text_color(*pdf.INK); pdf.set_x(15)
            pdf.cell(0, 5, "주요 교훈 sample"); pdf.ln(5)
            pdf._set_font("", 8); pdf.set_text_color(*pdf.INK_SECONDARY)
            for s in samples[:3]:
                pdf.set_x(20); pdf.multi_cell(175, pdf.LH_COMPACT,
                                              f"· {_norm_text(s)[:200]}", align="L")
    else:
        pdf.text_block("postmortem 누적 데이터 부족", color=pdf.GRAY)

    # 8-2. Market Horizon 30d
    mh = analysis.get("market_horizon_monthly") or {}
    pdf.subsection_title("8-2. Market Horizon (사이클 진단 30일)")
    if mh.get("available"):
        pdf.text_block(f"현 verdict: {mh.get('current_verdict', '-')} · "
                      f"현 cycle stage: {mh.get('current_cycle_stage', '-')}")
        vdist = mh.get("verdict_distribution") or {}
        if vdist:
            pdf.ln(1); pdf._set_font("", 8); pdf.set_text_color(*pdf.INK_SECONDARY); pdf.set_x(18)
            line = "verdict 분포: " + ", ".join(f"{k}({v}일)" for k, v in vdist.items())
            pdf.multi_cell(177, pdf.LH_COMPACT, line, align="L")
    else:
        pdf.text_block("market_horizon 데이터 부족", color=pdf.GRAY)

    # 8-3. 본인 vs 시스템
    pdf.subsection_title("8-3. 본인 vs 시스템 적중률")
    try:
        from api.metadata import user_actions
        ua = user_actions.summarize(days=30)
        if ua.get("total_actions", 0) > 0:
            pdf.text_block(f"본인 액션 {ua['total_actions']}건 · 시스템 일치 "
                          f"{ua['agreement_count']}건 ({ua['agreement_rate']}%)")
        else:
            pdf.text_block("본인 액션 누적 데이터 부족", color=pdf.GRAY)
    except Exception:
        pdf.text_block("user_actions 데이터 부족", color=pdf.GRAY)


# ─── 제9장 — 다음 달 전략 + 파라미터 ─────────────────────────

def _render_chap9_next(pdf: VerityPDF, analysis: Dict[str, Any],
                       portfolio: Dict[str, Any],
                       val_summary: Dict[str, Any]):
    pdf.add_page(); pdf.chapter_title(9, "다음 월간 전략 + 리스크 주의")
    meta = analysis.get("meta_analysis") or {}
    monthly = portfolio.get("monthly_report") or {}

    # 9-0. Brain 의 다음 단계 전략 (narrative — strategy)
    if monthly.get("strategy"):
        pdf.subsection_title("9-0. 다음 월간 전략 — Brain 제안")
        _render_narrative(pdf, monthly.get("strategy"))

    # 9-0B. 리스크 주의 (narrative — risk_watch)
    if monthly.get("risk_watch"):
        pdf.subsection_title("9-0B. 경계할 리스크")
        _render_narrative(pdf, monthly.get("risk_watch"))

    pdf.subsection_title("9-1. 가장 강한/약한 시그널")
    pdf.text_block(
        f"가장 강한 시그널: {meta.get('best_predictor', '-')}\n"
        f"가장 약한 시그널: {meta.get('worst_predictor', '-')}"
    )

    pdf.subsection_title("9-2. LLM 비용 월간")
    try:
        from api.metadata import llm_cost
        cost = llm_cost.summarize_cost(days=30)
        pdf.text_block(f"호출 {cost['calls']}회 · 비용 ${cost['total_usd']} "
                      f"(~{cost['total_krw_est']:,}원)")
        if cost.get("by_provider"):
            for p, v in cost["by_provider"].items():
                pdf._set_font("", 8); pdf.set_text_color(*pdf.INK_SECONDARY); pdf.set_x(18)
                pdf.cell(0, 5, f"· {p}: ${v}"); pdf.ln(5)
    except Exception:
        pdf.text_block("LLM 비용 데이터 부족", color=pdf.GRAY)

    pdf.subsection_title("9-3. 데이터 파이프라인 안정성")
    try:
        from api.metadata import data_health
        hs = data_health.summarize(days=30)
        pdf.text_block(f"deadman 발동 {hs.get('deadman_count', 0)}건 · "
                      f"파싱 오류 {hs.get('parse_errors', 0)}건 · "
                      f"수집 실패 {hs.get('fetch_failures', 0)}건 · "
                      f"가동률 {hs.get('uptime_pct', 99)}%")
    except Exception:
        pdf.text_block("데이터 파이프라인 안정성 데이터 부족", color=pdf.GRAY)

    pdf.subsection_title("9-4. 가중치 조정 결정")
    if not val_summary.get("validated"):
        pdf._set_font("", 8); pdf.set_text_color(*pdf.YELLOW); pdf.set_x(15)
        pdf.multi_cell(180, pdf.LH_COMPACT,
                       "※ 검증 미완료 — 백테스트 통과 없는 가중치 변경 금지 "
                       "(continuous_evolution 정책)", align="L")
        pdf.ln(2)
    pdf.text_block("이달 적중률 + 백테스트 + factor IC 기반 — 본인 검토 후 결정")


# ─── 결론 + 면책 ─────────────────────────────────────────────

def _render_conclusion(pdf: VerityPDF, val_summary: Dict[str, Any]):
    pdf.add_page()
    pdf._set_font("B", 13); pdf.set_text_color(*pdf.WHITE); pdf.set_x(12)
    pdf.cell(0, 9, "결론 및 면책"); pdf.ln(10)
    pdf._set_font("", 8); pdf.set_text_color(*pdf.DARK_GRAY); pdf.set_x(15)
    pdf.multi_cell(180, pdf.LH_COMPACT,
                   "본 보고서는 VERITY 자동 분석 시스템의 월간 출력물로, "
                   "투자자문업법상 자문이 아닙니다. 기재된 종목·등급·시나리오는 "
                   "본인 의사결정 참고용이며 매매 권유가 아닙니다. "
                   "최종 책임은 투자자 본인에게 있습니다.", align="L")
    pdf.ln(3); pdf.set_x(15)
    pdf.cell(0, 5, f"검증 상태: {val_summary.get('watermark_label', '')}")


# ─── Public entry ────────────────────────────────────────────

def generate_monthly_admin_pdf(analysis: Dict[str, Any],
                               portfolio: Dict[str, Any]) -> str:
    """Monthly 관리자 9장 PDF — daily v2 정합 디자인.

    analysis 는 enrich_monthly_analysis 통해 추가 key 부여됨 (destructive).
    """
    val_summary = validation_status_summary(portfolio.get("vams") or {})
    # enrich (idempotent — 기존 키 보존)
    try:
        analysis = enrich_monthly_analysis(analysis, portfolio)
    except Exception as _e:
        import logging
        logging.warning("monthly enrich 실패: %s", _e)

    pdf = VerityPDF(); pdf.add_page()
    _render_cover(pdf, analysis, portfolio, val_summary)
    # CH 0 — 반성 + 개선 (최상단, 사용자 요청 2026-05-15)
    try:
        _render_chap0_reflection(pdf, analysis, portfolio)
    except Exception as _e:
        import logging; logging.warning("monthly chap0 reflection 실패: %s", _e)
    _render_chap1_macro(pdf, analysis, portfolio)
    _render_chap2_performance(pdf, analysis, portfolio)
    _render_chap3_brain(pdf, analysis, portfolio)
    _render_chap4_stocks(pdf, analysis)
    _render_chap5_sectors(pdf, analysis, portfolio)
    _render_chap6_vams(pdf, analysis, portfolio)
    # 신규 7~9 — 회귀 가드 (실패해도 결론까지)
    try:
        _render_chap7_blackswan_headlines(pdf, analysis)
    except Exception as _e:
        import logging; logging.warning("monthly chap7 실패: %s", _e)
    try:
        _render_chap8_postmortem_horizon(pdf, analysis)
    except Exception as _e:
        import logging; logging.warning("monthly chap8 실패: %s", _e)
    try:
        _render_chap9_next(pdf, analysis, portfolio, val_summary)
    except Exception as _e:
        import logging; logging.warning("monthly chap9 실패: %s", _e)
    _render_conclusion(pdf, val_summary)

    out_dir = os.path.join(DATA_DIR, "reports")
    os.makedirs(out_dir, exist_ok=True)
    fname = f"verity_monthly_admin_{now_kst().strftime('%Y%m%d_%H%M')}.pdf"
    path = os.path.join(out_dir, fname)
    pdf.output(path)
    import shutil
    shutil.copy2(path, os.path.join(out_dir, "verity_monthly_admin.pdf"))
    return path
