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
  - llm_cost.summarize_cost (호출량만; 실청구액은 공급자 콘솔 링크)
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
    _methodology_narrative,
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
        pdf.set_fill_color(235, 235, 235)
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
    pdf.set_text_color(60, 60, 60)
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
    pdf.set_text_color(60, 60, 60)
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
    pdf.set_text_color(60, 60, 60)
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
        pdf.set_text_color(60, 60, 60)
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
            pdf.set_text_color(60, 60, 60)
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

    # 3-3. 타이밍 시그널 분포 (sentiment + technical 분리)
    _render_timing_signal_distribution(pdf, portfolio)

    # 3-4. trade_plan v0 자체 검증
    _render_trade_plan_meta(pdf, portfolio)


def _render_timing_signal_distribution(pdf: VerityPDF, portfolio: Dict[str, Any]):
    """timing_signal (sentiment 70% + technical 30%) 분포 — brain grade 와 별개의 단기 시그널."""
    recs = portfolio.get("recommendations") or []
    pdf.subsection_title("3-3. 타이밍 시그널 분포 (sentiment 70% + technical 30%)")

    dist: Dict[str, int] = {}
    for r in recs:
        ts = r.get("timing_signal") or {}
        sig = ts.get("signal") or "—"
        dist[sig] = dist.get(sig, 0) + 1

    total = sum(dist.values())
    if total == 0:
        pdf.text_block("timing_signal 미산출 — verity_brain.analyze_stock 후속 cron 대기")
        return

    LABELS = {"STRONG_BUY": "강한 진입", "BUY": "진입 우위", "NEUTRAL": "중립",
              "WEAK": "약세", "WAIT": "대기"}
    COLORS = {"STRONG_BUY": pdf.GREEN, "BUY": pdf.GREEN, "NEUTRAL": pdf.WHITE,
              "WEAK": pdf.YELLOW, "WAIT": pdf.RED}

    for sig in ("STRONG_BUY", "BUY", "NEUTRAL", "WEAK", "WAIT"):
        cnt = dist.get(sig, 0)
        pct = round(cnt / total * 100, 1) if total else 0
        c = COLORS.get(sig, pdf.WHITE)
        pdf._set_font("", 9)
        pdf.set_text_color(*c)
        pdf.set_x(18)
        pdf.cell(35, 6, LABELS.get(sig, sig))
        pdf.set_text_color(*pdf.WHITE)
        pdf.cell(20, 6, f"{cnt}종목")
        pdf.set_text_color(*pdf.GRAY)
        pdf.cell(20, 6, f"({pct}%)")
        bar_w = max(2, pct * 1.0)
        pdf.set_fill_color(*c)
        pdf.rect(95, pdf.get_y() + 1, bar_w, 4, "F")
        pdf.ln(7)

    pdf._set_font("", 8)
    pdf.set_text_color(*pdf.GRAY)
    pdf.set_x(15)
    pdf.multi_cell(0, 4,
        "brain_score (펀더멘털) 와 분리. timing_signal 동시 STRONG/BUY 시 강한 confirm. "
        "WEAK/WAIT 비율 급증 시 단기 시장 약세 신호.")
    pdf.ln(2)


def _render_trade_plan_meta(pdf: VerityPDF, portfolio: Dict[str, Any]):
    """trade_plan v0_log 누적 분해 통계. memory: 종합값 단일 신뢰 X, 분해/baseline 동시."""
    meta = portfolio.get("trade_plan_meta") or {}
    pdf.subsection_title("3-4. trade_plan v0 자체 검증")

    if not meta or meta.get("status") == "empty":
        pdf.text_block("운영 시작 전 — 진입 후보 누적 대기. 첫 BUY+entry_active 종목 발생 시 로깅 시작.")
        return

    sample = meta.get("sample_size") or {}
    total = sample.get("total", 0)
    n_open = sample.get("open", 0)
    n_closed = sample.get("closed", 0)
    min_for = sample.get("min_for_decompose", 30)
    pdf.text_block(
        f"누적 진입 후보 {total}건 (open {n_open} · closed {n_closed}) · "
        f"h5 채움 {sample.get('with_h5', 0)} · h14 {sample.get('with_h14', 0)} · h30 {sample.get('with_h30', 0)}"
    )

    # horizon 별 hit rate / median return / IC
    horizons = meta.get("horizon_summary") or {}
    pdf._set_font("", 9)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(18)
    pdf.cell(20, 6, "호라이즌")
    pdf.cell(20, 6, "n")
    pdf.cell(28, 6, "Hit Rate")
    pdf.cell(28, 6, "Median Ret")
    pdf.cell(20, 6, "IC")
    pdf.ln(6)
    for key in ("h5", "h14", "h30"):
        h = horizons.get(key) or {}
        n = h.get("n", 0)
        hr = h.get("hit_rate_pct")
        mr = h.get("median_return_pct")
        ic = h.get("ic")
        pdf.set_x(18)
        pdf.set_text_color(*pdf.GRAY)
        pdf.cell(20, 6, key)
        pdf.cell(20, 6, str(n))
        if hr is None:
            pdf.cell(28, 6, "-")
        else:
            pdf.set_text_color(*(pdf.GREEN if hr >= 55 else pdf.YELLOW if hr >= 45 else pdf.RED))
            pdf.cell(28, 6, f"{hr}%")
        pdf.set_text_color(*pdf.WHITE)
        pdf.cell(28, 6, "-" if mr is None else f"{mr:+.2f}%")
        pdf.cell(20, 6, "-" if ic is None else f"{ic:+.3f}")
        pdf.ln(6)
    pdf.ln(2)

    if meta.get("status") == "insufficient_data":
        need = max(0, min_for - total)
        pdf._set_font("", 8)
        pdf.set_text_color(*pdf.YELLOW)
        pdf.set_x(15)
        pdf.cell(0, 5, f"※ 분해 통계 활성 임계 미달 ({total}/{min_for}). {need}건 더 누적 후 피처/섹터/시간차 baseline 표시")
        pdf.ln(6)
        return

    # 시간차 baseline (drift 측정)
    ts = meta.get("timeseries_baseline") or {}
    windows = ts.get("windows") or {}
    pdf._set_font("", 9)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(15)
    pdf.cell(0, 6, "시간차 baseline (h14 hit rate · drift 측정)")
    pdf.ln(6)
    for label, ko in (("first_30d", "첫 30일"), ("30_60d", "30~60일"), ("60d_plus", "60일+")):
        w = windows.get(label) or {}
        pdf.set_x(18)
        pdf.set_text_color(*pdf.GRAY)
        pdf.cell(28, 6, ko)
        pdf.cell(20, 6, f"n={w.get('n', 0)}")
        hr = w.get("hit_rate_pct")
        if hr is None:
            pdf.set_text_color(*pdf.GRAY)
            pdf.cell(28, 6, "-")
        else:
            pdf.set_text_color(*(pdf.GREEN if hr >= 55 else pdf.YELLOW if hr >= 45 else pdf.RED))
            pdf.cell(28, 6, f"{hr}%")
        mr = w.get("median_return_pct")
        pdf.set_text_color(*pdf.WHITE)
        pdf.cell(0, 6, "-" if mr is None else f"median {mr:+.2f}%")
        pdf.ln(6)
    pdf.ln(2)

    # verdict_strength 분위 (multi_score 4분위 → return)
    vs = meta.get("verdict_strength") or {}
    if isinstance(vs, dict) and vs.get("status") != "insufficient_data":
        quartiles = vs.get("quartile_mean_return_pct") or []
        if quartiles:
            pdf._set_font("", 9)
            pdf.set_text_color(*pdf.WHITE)
            pdf.set_x(15)
            pdf.cell(0, 6, "verdict 강도 (multi_score 4분위 → h14 평균 수익)")
            pdf.ln(6)
            pdf._set_font("", 8)
            for q in quartiles:
                pdf.set_x(18)
                pdf.set_text_color(*pdf.GRAY)
                pdf.cell(20, 5, f"Q{q.get('q', 0) + 1}")
                pdf.cell(18, 5, f"n={q.get('n', 0)}")
                mr = q.get("mean_return_pct")
                if mr is None:
                    pdf.set_text_color(*pdf.GRAY)
                    pdf.cell(0, 5, "-")
                else:
                    pdf.set_text_color(*(pdf.GREEN if mr > 0 else pdf.RED))
                    pdf.cell(0, 5, f"{mr:+.2f}%")
                pdf.ln(5)
            pdf.ln(2)

    pdf._set_font("", 8)
    pdf.set_text_color(*pdf.GRAY)
    pdf.set_x(15)
    pdf.multi_cell(0, 4,
        "정책: 종합값 단일 신뢰 금지 (decompose). v0 휴리스틱 — 결정 룰은 단순(BB/MA/RSI), "
        "자동 액션은 verdict 상태 전이만. 사후 hit rate < 45% 지속 시 룰 재검토 신호.")
    pdf.ln(2)


# ─── 제4장 — 종목 판단 ────────────────────────────────────

def _render_stock_mini_block(pdf: VerityPDF, rank: int, r: Dict[str, Any]):
    """종목 1개 mini deep-dive (한화 패턴 압축형, ~5 lines / ~30mm).

    표시 항목:
      [Header] 순위. 종목명 (티커) · 등급 · Brain 점수 · VCI
      [Layer 1] target / stop / R-multiple / trailing
      [Layer 2] sector / market_cap / per / pbr / dividend
      [Layer 3] red flags 또는 timing_signal verdict
      [Layer 4] AI 추천 사유 한 줄 (verity_brain.summary 또는 ai_verdict)
    """
    if pdf.get_y() > 250:
        pdf.add_page()

    vb = r.get("verity_brain") or {}
    grade = vb.get("grade") or r.get("recommendation") or "WATCH"
    score = vb.get("brain_score") or 0
    vci = (vb.get("vci") or {}).get("vci")
    name = _norm_text(r.get("name", "?"))
    ticker = r.get("ticker", "-")

    # Header
    y = pdf.get_y()
    pdf.set_x(15)
    pdf._set_font("B", 10)
    pdf.set_text_color(*pdf.GRADE_COLORS.get(grade, pdf.INK))
    pdf.cell(8, 6, f"{rank}.")
    pdf._set_font("B", 10)
    pdf.set_text_color(*pdf.INK)
    pdf.cell(70, 6, f"{name} ({ticker})")
    pdf._set_font("", 8)
    pdf.set_text_color(*pdf.GRADE_COLORS.get(grade, pdf.INK))
    pdf.cell(20, 6, pdf.GRADE_LABELS.get(grade, grade))
    pdf.set_text_color(*pdf.INK_SECONDARY)
    pdf.cell(25, 6, f"Brain {int(score)}점")
    if vci is not None:
        try:
            pdf.cell(20, 6, f"VCI {float(vci):+.0f}")
        except (TypeError, ValueError):
            pass
    pdf.ln(6)

    # Layer 1 — target / stop / R
    target = r.get("target_price") or vb.get("target_price")
    stop = r.get("stop_loss") or vb.get("stop_loss")
    cur = r.get("price") or r.get("current_price")
    r_mult = vb.get("r_multiple") or r.get("r_multiple")
    layer1 = []
    if cur:
        layer1.append(f"현재 {_fmt_num(cur)}")
    if target:
        layer1.append(f"목표 {_fmt_num(target)}")
    if stop:
        layer1.append(f"손절 {_fmt_num(stop)}")
    if r_mult is not None:
        try:
            layer1.append(f"R {float(r_mult):.2f}")
        except (TypeError, ValueError):
            pass
    if layer1:
        pdf.set_x(23)
        pdf._set_font("", 8)
        pdf.set_text_color(*pdf.INK_SECONDARY)
        pdf.cell(0, 5, "  ·  ".join(layer1))
        pdf.ln(5)

    # Layer 2 — sector / cap / per / pbr / dividend
    sector = _norm_text(r.get("sector") or "")
    mcap = r.get("market_cap")
    per = r.get("per") or vb.get("per")
    pbr = r.get("pbr") or vb.get("pbr")
    div_yield = r.get("dividend_yield") or r.get("div_yield")
    layer2 = []
    if sector:
        layer2.append(f"{sector[:14]}")
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
    if div_yield is not None:
        try:
            layer2.append(f"배당 {float(div_yield):.2f}%")
        except (TypeError, ValueError):
            pass
    if layer2:
        pdf.set_x(23)
        pdf._set_font("", 8)
        pdf.set_text_color(*pdf.INK_TERTIARY)
        pdf.cell(0, 5, "  ·  ".join(layer2))
        pdf.ln(5)

    # Layer 3 — red flags 또는 timing_signal
    red_flags = vb.get("red_flags", {}) or {}
    flags = []
    if isinstance(red_flags, dict):
        if red_flags.get("auto_avoid"):
            flags.extend([f"⚠{_norm_text(x)[:25]}" for x in red_flags["auto_avoid"][:2]])
        if red_flags.get("downgrade"):
            flags.extend([f"▼{_norm_text(x)[:25]}" for x in red_flags["downgrade"][:1]])
    timing = (r.get("timing_signal") or {}).get("signal") or vb.get("timing_signal_label")
    if timing and not flags:
        flags.append(f"timing {timing}")
    if flags:
        pdf.set_x(23)
        pdf._set_font("", 8)
        pdf.set_text_color(*pdf.INK_SECONDARY)
        pdf.cell(0, 5, "  ·  ".join(flags)[:130])
        pdf.ln(5)

    # Layer 4 — AI 추천 사유 (한 줄)
    summary = _safe_report_text(
        vb.get("summary") or r.get("ai_verdict") or r.get("summary") or "",
        placeholder="",
    )
    if summary:
        pdf.set_x(23)
        pdf._set_font("", 8)
        pdf.set_text_color(*pdf.INK_SECONDARY)
        pdf.multi_cell(165, 5, summary[:160], align="L")

    # 카드 외곽 (얇은 좌측 strip)
    pdf.set_fill_color(*pdf.GRADE_COLORS.get(grade, pdf.INK))
    pdf.rect(15, y + 1, 0.8, pdf.get_y() - y - 1, "F")
    pdf.ln(2)


def _fmt_num(v) -> str:
    """가격 포맷 — 1만원 이상=만/조 단위, 미만=원 그대로."""
    try:
        f = float(v)
        if f >= 1e8:
            return f"{f/1e8:.1f}억"
        if f >= 1e4:
            return f"{f:,.0f}"
        return f"{f:.2f}"
    except (TypeError, ValueError):
        return str(v)


def _render_chap4_stocks(pdf: VerityPDF, portfolio: Dict[str, Any], validated: bool):
    pdf.add_page()
    pdf.chapter_title(4, "종목 판단")
    recs = portfolio.get("recommendations") or []
    vams = portfolio.get("vams") or {}
    holdings = vams.get("holdings") or []

    # 4-A. BUY 종목 TOP 10 — 옛 3 → 10 (사용자 피드백 "양과 질")
    pdf.subsection_title(f"4-A. 오늘의 BUY 종목 (최대 10, 전체 {len(recs)}건)")
    buys = sorted(
        [r for r in recs if (r.get("verity_brain") or {}).get("grade") in ("STRONG_BUY", "BUY")
         or r.get("recommendation") in ("STRONG_BUY", "BUY")],
        key=lambda r: -((r.get("verity_brain") or {}).get("brain_score") or 0)
    )[:10]
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
            _render_stock_mini_block(pdf, i, r)
            pdf.narrative_paragraphs(_stock_detail_block(r))
            pdf.ln(1)

    # 4-B. 보유 종목 점검 (VAMS 연동) — 5 → 전체
    if holdings:
        pdf.subsection_title(f"4-B. 보유 종목 점검 (VAMS, {len(holdings)}종목 전체)")
        pdf._set_font("", 8)
        for h in holdings:
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
            # 보유 종목 Brain v5 산출 trail — recommendations 에서 ticker match
            full_rec = _rec_by_ticker(recs, h.get("ticker"))
            if full_rec:
                pdf.narrative_paragraphs(_stock_detail_block(full_rec))
                pdf.ln(1)
        pdf.ln(2)

    # 4-C. 회피 종목 TOP 10 — 옛 3 → 10
    avoids = sorted(
        [r for r in recs if (r.get("verity_brain") or {}).get("grade") in ("CAUTION", "AVOID")],
        key=lambda r: ((r.get("verity_brain") or {}).get("brain_score") or 100)
    )[:10]
    pdf.subsection_title(f"4-C. 주의·회피 종목 TOP {len(avoids)}")
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
            pdf.set_text_color(60, 60, 60)
            pdf.multi_cell(110, pdf.LH_COMPACT, _norm_text(reason)[:80] or "사유 데이터 없음", align="L")
            pdf.narrative_paragraphs(_stock_detail_block(r))
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

    def _sector_row(s: Dict[str, Any]):
        chg = s.get("change_pct", 0) or 0
        n_stocks = s.get("stock_count") or s.get("n_stocks") or "-"
        avg_score = s.get("avg_brain_score") or s.get("avg_score") or "-"
        net_flow = s.get("net_flow_krw") or s.get("foreign_net_buy") or None
        pdf.set_x(15)
        pdf._set_font("B", 8)
        pdf.set_text_color(*pdf.INK)
        pdf.cell(55, 5, _norm_text(s.get("name", ""))[:18])
        pdf._set_font("", 8)
        pdf.set_text_color(*pdf.INK)
        pdf.cell(20, 5, f"{chg:+.2f}%", align="R")
        pdf.set_text_color(*pdf.INK_SECONDARY)
        pdf.cell(20, 5, f"{n_stocks}", align="R")
        pdf.cell(25, 5, f"{avg_score}", align="R")
        if net_flow is not None:
            try:
                pdf.cell(50, 5, f"{float(net_flow)/1e8:+,.1f}억", align="R")
            except (TypeError, ValueError):
                pdf.cell(50, 5, "-", align="R")
        pdf.ln(5)

    def _table_header():
        pdf._set_font("B", 7)
        pdf.set_text_color(*pdf.INK_TERTIARY)
        pdf.set_x(15)
        pdf.cell(55, 5, "섹터")
        pdf.cell(20, 5, "변동률", align="R")
        pdf.cell(20, 5, "종목수", align="R")
        pdf.cell(25, 5, "평균 점수", align="R")
        pdf.cell(50, 5, "외인 순매수", align="R")
        pdf.ln(5)
        pdf.set_draw_color(*pdf.BORDER)
        pdf.set_line_width(0.2)
        y = pdf.get_y()
        pdf.line(15, y, 185, y)
        pdf.ln(1)

    pdf.subsection_title(f"5-1. 상승 TOP 10 (전체 {len(sectors)}개)")
    _table_header()
    for s in sorted_secs[:10]:
        _sector_row(s)

    pdf.ln(3)
    pdf.subsection_title("5-2. 하락 TOP 10")
    _table_header()
    for s in sorted_secs[-10:][::-1]:
        _sector_row(s)

    # 5-3. 자금 흐름
    cf = (portfolio.get("macro") or {}).get("capital_flow") or {}
    if cf:
        pdf.subsection_title("5-3. 자금 흐름")
        pdf.narrative_paragraphs(_capital_flow_narrative(cf))

    # 5-4. 섹터 로테이션 신호
    rot = portfolio.get("sector_rotation") or {}
    if rot:
        pdf.subsection_title("5-4. 섹터 로테이션 신호")
        leaders = rot.get("leaders") or rot.get("rotating_into") or []
        laggards = rot.get("laggards") or rot.get("rotating_out") or []
        verdict = _norm_text(rot.get("verdict") or rot.get("signal") or "")
        if verdict:
            pdf.text_block(f"로테이션 verdict: {verdict}")
        if leaders:
            pdf.text_block(
                "유입 후보 — " +
                ", ".join(_norm_text(l.get("name") if isinstance(l, dict) else l) for l in leaders[:5])
            )
        if laggards:
            pdf.text_block(
                "유출 후보 — " +
                ", ".join(_norm_text(l.get("name") if isinstance(l, dict) else l) for l in laggards[:5])
            )


# ─── 제6장 — VAMS 현황 ───────────────────────────────────

def _render_chap6_vams(pdf: VerityPDF, portfolio: Dict[str, Any]):
    pdf.add_page()
    pdf.chapter_title(6, "VAMS 현황")
    vams = portfolio.get("vams") or {}

    total_asset = vams.get("total_asset", 0)
    cash = vams.get("cash", 0)
    holdings = vams.get("holdings") or []
    cash_pct = round(cash / total_asset * 100, 1) if total_asset else 0
    cum_return = vams.get("total_return_pct", vams.get("cum_return_pct", 0))

    pdf.metric_row([
        {"label": "총 자산", "value": f"{total_asset:,.0f}원", "color": pdf.WHITE},
        {"label": "누적 수익률", "value": f"{cum_return:+.2f}%",
         "color": pdf.GREEN if cum_return >= 0 else pdf.RED},
        {"label": "현금 비중", "value": f"{cash_pct}%", "color": pdf.YELLOW},
        {"label": "보유 종목", "value": f"{len(holdings)}종목", "color": pdf.WHITE},
    ])

    # 6-1. KIS 실시간 시세 (price_pulse merge, P2-1 보강 2026-05-17)
    if holdings:
        pdf.subsection_title("6-1. 보유 종목 실시간 시세 (price_pulse)")
        pdf._set_font("", 8)
        pdf.set_text_color(*pdf.WHITE)
        for h in holdings[:10]:
            t = h.get("ticker", "?")
            name = h.get("name", "?")[:14]
            qty = h.get("quantity", 0)
            cur_p = h.get("current_price", 0)
            avg_p = h.get("avg_price", 0)
            ret_pct = ((cur_p / avg_p - 1) * 100) if avg_p else 0
            color = pdf.GREEN if ret_pct >= 0 else pdf.RED
            pdf.set_x(15)
            pdf.cell(35, 5, f"{name}({t})")
            pdf.cell(30, 5, f"{qty}주", align="R")
            pdf.cell(30, 5, f"{cur_p:,.0f}", align="R")
            pdf.set_text_color(*color)
            pdf.cell(30, 5, f"{ret_pct:+.2f}%", align="R")
            pdf.set_text_color(*pdf.WHITE)
            pdf.ln(5)

    # 6-2. Brain 적중률 추이 (4주 롤링)
    try:
        from api.metadata import brain_learning
        trend = brain_learning.trend_summary(days=28)
        if trend.get("hit_rate_14d_avg") is not None:
            pdf.subsection_title("6-2. Brain 적중률 추이 (4주)")
            pdf.text_block(f"14d 적중률 평균 {trend['hit_rate_14d_avg']}%, "
                          f"방향 {trend.get('hit_rate_14d_trend', 'n/a')}")
    except Exception:
        pass

    # 6-3. Factor IC adjustment 현황 (P2-1 보강 — Brain v6 alpha decay 추적)
    try:
        import json
        ic_path = "data/metadata/ic_adjustments.json"
        with open(ic_path, "r", encoding="utf-8") as f:
            ic = json.load(f)
        if ic.get("status") == "ok":
            adj = ic.get("adjustments") or {}
            pdf.subsection_title("6-3. Factor IC Adjustment (alpha decay 추적)")
            pdf._set_font("", 8)
            for factor, info in list(adj.items())[:10]:
                status = info.get("status", "?")
                mult = info.get("multiplier", 1.0)
                color = (pdf.RED if status == "DEAD"
                         else pdf.YELLOW if status == "WEAKENING"
                         else pdf.GREEN)
                pdf.set_x(15)
                pdf.set_text_color(*pdf.WHITE)
                pdf.cell(60, 5, f"  {factor}")
                pdf.set_text_color(*color)
                pdf.cell(40, 5, f"× {mult:.2f} ({status})")
                pdf.set_text_color(*pdf.WHITE)
                pdf.ln(5)
    except Exception:
        pass

    # 6-4. Cross-verification (Gemini vs Claude 합의도, P2-1 보강)
    recs = portfolio.get("recommendations") or []
    if recs:
        n_agree = sum(1 for r in recs if r.get("agrees_with_gemini") is not False)
        n_total = len(recs)
        agree_pct = round(n_agree / n_total * 100, 1) if n_total else 0
        pdf.subsection_title("6-4. AI cross-verification (Gemini ↔ Claude)")
        color = (pdf.GREEN if agree_pct >= 85
                 else pdf.YELLOW if agree_pct >= 70 else pdf.RED)
        pdf._set_font("", 9)
        pdf.set_text_color(*color)
        pdf.set_x(15)
        pdf.cell(0, 6, f"  합의도 {agree_pct}% ({n_agree}/{n_total} 종목)")
        pdf.set_text_color(*pdf.WHITE)
        pdf.ln(6)


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
        pdf.set_text_color(60, 60, 60)
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
        pdf.set_text_color(60, 60, 60)
        pdf.ln(3)


# ─── 제8장 — 헤드라인 모니터 (신규) ───────────────────────

def _render_chap8_headlines(pdf: VerityPDF, portfolio: Dict[str, Any]):
    """국내·미국·Bloomberg 헤드라인 통합 표 — portfolio.json 의 51건 cover."""
    pdf.add_page()
    pdf.chapter_title(8, "헤드라인 모니터")

    sources = [
        ("8-1. 국내 헤드라인", portfolio.get("headlines") or []),
        ("8-2. 미국 헤드라인", portfolio.get("us_headlines") or []),
        ("8-3. Bloomberg / Google Finance", portfolio.get("bloomberg_google_headlines") or []),
    ]
    n_total = sum(len(s[1]) for s in sources)
    if n_total == 0:
        pdf.narrative_paragraphs("헤드라인 데이터 미수집.")
        return

    for label, items in sources:
        if not items:
            continue
        pdf.subsection_title(f"{label} ({len(items)}건)")
        pdf._set_font("", 8)
        for i, h in enumerate(items[:12], 1):
            title = _norm_text(h.get("title") or h.get("headline") or "")
            source = _norm_text(h.get("source") or h.get("publisher") or "")
            sent = h.get("sentiment") or h.get("sentiment_score")
            time_s = _norm_text(h.get("published_at") or h.get("time") or "")[:16]
            if not title:
                continue
            pdf.set_x(15)
            pdf._set_font("B", 8)
            pdf.set_text_color(*pdf.INK)
            pdf.cell(8, 5, f"{i}.")
            pdf._set_font("", 8)
            pdf.multi_cell(170, 5, title[:80], align="L")
            meta_parts = []
            if source:
                meta_parts.append(source)
            if time_s:
                meta_parts.append(time_s)
            if sent is not None:
                try:
                    sent_v = float(sent)
                    sent_label = "긍정" if sent_v > 0.2 else "부정" if sent_v < -0.2 else "중립"
                    meta_parts.append(f"감성 {sent_label}({sent_v:+.2f})")
                except (TypeError, ValueError):
                    pass
            if meta_parts:
                pdf._set_font("", 7)
                pdf.set_text_color(*pdf.INK_TERTIARY)
                pdf.set_x(23)
                pdf.cell(0, 4, " · ".join(meta_parts))
                pdf.ln(5)
            else:
                pdf.ln(1)


# ─── 제9장 — Postmortem + 모델 검증 (신규) ──────────────────

def _render_chap9_postmortem(pdf: VerityPDF, portfolio: Dict[str, Any]):
    """어제 판단 vs 실제 결과 + 모델 검증 — 실 schema 정합 (2026-05-11 정정)."""
    pdf.add_page()
    pdf.chapter_title(9, "Postmortem + 모델 검증")

    pm = portfolio.get("postmortem") or {}
    fic = portfolio.get("factor_ic") or {}
    cv = portfolio.get("cross_verification") or {}
    bq = portfolio.get("brain_quality") or {}
    ba = portfolio.get("brain_accuracy") or {}
    horizon = portfolio.get("market_horizon") or {}

    # ── 9-1. 어제 결심 vs 오늘 결심 (brain_learning.jsonl 직접 비교) ──
    pdf.subsection_title("9-1. 어제 결심 vs 오늘 결심")
    try:
        from api.metadata import brain_learning
        cmp = brain_learning.compare_yesterday_vs_today()
    except Exception as _e:
        cmp = None

    if cmp:
        y_v = cmp.get("yesterday_verdict") or "-"
        t_v = cmp.get("today_verdict") or "-"
        changed = cmp.get("verdict_changed")
        y_date = cmp.get("yesterday_date", "-")
        t_date = cmp.get("today_date", "-")
        deltas = cmp.get("deltas") or {}

        pdf._set_font("", 8)
        # verdict change
        pdf.set_x(15)
        pdf.set_text_color(*pdf.INK_TERTIARY)
        pdf.cell(55, 5, f"판단 변화 ({y_date} → {t_date})")
        pdf.set_text_color(*pdf.INK)
        change_arrow = " ⇒ " if changed else " = "
        pdf.cell(0, 5, f"{y_v}{change_arrow}{t_v}{' ⚠ 등급 변경' if changed else ''}")
        pdf.ln(6)

        # 점수 delta rows
        def _row(k: str, v):
            pdf.set_x(15)
            pdf.set_text_color(*pdf.INK_TERTIARY)
            pdf.cell(55, 5, k)
            pdf.set_text_color(*pdf.INK)
            try:
                pdf.cell(0, 5, f"{float(v):+.2f}")
            except (TypeError, ValueError):
                pdf.cell(0, 5, "-")
            pdf.ln(5)

        for label, key in (
            ("Brain 평균 점수 Δ", "brain_score"),
            ("팩트 점수 Δ", "fact_score"),
            ("심리 점수 Δ", "sentiment_score"),
            ("VCI Δ", "vci"),
            ("매크로 분위기 Δ", "mood_score"),
        ):
            if deltas.get(key) is not None:
                _row(label, deltas.get(key))

        # 후보 추가·제거
        added = cmp.get("buy_candidates_added") or []
        removed = cmp.get("buy_candidates_removed") or []
        a_added = cmp.get("avoid_candidates_added") or []
        a_removed = cmp.get("avoid_candidates_removed") or []
        if added or removed or a_added or a_removed:
            pdf.ln(1)
            pdf._set_font("B", 8)
            pdf.set_text_color(*pdf.INK)
            pdf.set_x(15)
            pdf.cell(0, 5, "후보 변경")
            pdf.ln(5)
            pdf._set_font("", 8)
            for label, items in (
                ("BUY 추가", added), ("BUY 제거", removed),
                ("AVOID 추가", a_added), ("AVOID 제거", a_removed),
            ):
                if not items:
                    continue
                names = ", ".join(f"{_norm_text(c.get('name', ''))}({c.get('ticker', '')})"
                                   for c in items[:8])
                pdf.set_x(18)
                pdf.set_text_color(*pdf.INK_TERTIARY)
                pdf.cell(45, 5, label)
                pdf.set_text_color(*pdf.INK_SECONDARY)
                pdf.multi_cell(135, 5, names, align="L")
    else:
        pdf.text_block(
            "어제 vs 오늘 비교 — 데이터 부족 (brain_learning.jsonl 누적 < 2일).",
            color=pdf.INK_TERTIARY,
        )

    # ── 9-1B. 운영 self-review (postmortem 풀) ──
    pdf.ln(2)
    pdf.subsection_title("9-1B. 운영 self-review (postmortem)")
    status = pm.get("status") or "n/a"
    period = pm.get("period") or "-"
    analyzed_n = pm.get("analyzed_count") or 0
    summary = _norm_text(pm.get("summary") or "")
    lesson = _norm_text(pm.get("lesson") or "")
    suggestion = _norm_text(pm.get("system_suggestion") or "")
    misleading = pm.get("misleading_factors") or {}

    pdf._set_font("", 8)
    rows91 = [
        ("기간", period),
        ("상태", "정상" if status == "ok" else f"⚠ {status}"),
        ("분석 종목 수", str(analyzed_n)),
    ]
    for k, v in rows91:
        pdf.set_x(15)
        pdf.set_text_color(*pdf.INK_TERTIARY)
        pdf.cell(55, 5, k)
        pdf.set_text_color(*pdf.INK)
        pdf.cell(0, 5, str(v))
        pdf.ln(5)
    if summary:
        pdf.ln(1)
        pdf.text_block(f"요약: {summary}")
    if lesson:
        pdf.text_block(f"교훈: {lesson}")
    if suggestion:
        pdf.text_block(f"시스템 제안: {suggestion}")
    if misleading:
        pdf.ln(1)
        pdf._set_font("B", 8)
        pdf.set_text_color(*pdf.INK)
        pdf.set_x(15)
        pdf.cell(0, 5, "오도성 팩터 (misleading)")
        pdf.ln(5)
        pdf._set_font("", 8)
        items = list(misleading.items())[:8] if isinstance(misleading, dict) else []
        for k, v in items:
            pdf.set_x(18)
            pdf.set_text_color(*pdf.INK_SECONDARY)
            pdf.cell(60, 5, _norm_text(k)[:22])
            pdf.set_text_color(*pdf.INK)
            try:
                pdf.cell(40, 5, f"{float(v):+.3f}", align="R")
            except (TypeError, ValueError):
                pdf.cell(40, 5, str(v)[:20], align="R")
            pdf.ln(5)

    # ── 9-2. Factor IC ranking ──
    if fic:
        pdf.ln(3)
        pdf.subsection_title("9-2. Factor IC (예측력 — ICIR 순)")
        ranking = fic.get("ranking") or []
        if not ranking:
            mr = fic.get("monthly_rollup") or {}
            ranking = mr.get("by_factor") or []
        pdf._set_font("", 8)
        for it in ranking[:12] if isinstance(ranking, list) else []:
            name = _norm_text(it.get("factor") or "-")
            icir = it.get("icir") or it.get("avg_icir")
            ic = it.get("ic") or it.get("avg_ic")
            obs = it.get("obs") or it.get("n_obs")
            pdf.set_x(15)
            pdf._set_font("B", 8)
            pdf.set_text_color(*pdf.INK)
            pdf.cell(60, 5, name[:24])
            pdf._set_font("", 8)
            pdf.set_text_color(*pdf.INK_SECONDARY)
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
            pdf.text_block(
                f"유의 팩터 ({len(sig)}): " + ", ".join(map(str, sig[:12]))
            )

    # ── 9-3. Brain Accuracy 등급별 ──
    grades = ba.get("grades") or {}
    if grades:
        pdf.ln(3)
        pdf.subsection_title("9-3. Brain 등급별 적중률 + 평균 수익")
        pdf._set_font("B", 7)
        pdf.set_text_color(*pdf.INK_TERTIARY)
        pdf.set_x(15)
        pdf.cell(40, 5, "등급")
        pdf.cell(25, 5, "건수", align="R")
        pdf.cell(40, 5, "평균 수익률", align="R")
        pdf.cell(40, 5, "적중률", align="R")
        pdf.ln(5)
        pdf.set_draw_color(*pdf.BORDER)
        pdf.set_line_width(0.2)
        y = pdf.get_y(); pdf.line(15, y, 160, y); pdf.ln(1)
        order = ["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"]
        for g in order:
            row = grades.get(g) or {}
            if not row:
                continue
            pdf.set_x(15)
            pdf._set_font("B", 8)
            pdf.set_text_color(*pdf.INK)
            pdf.cell(40, 5, pdf.GRADE_LABELS.get(g, g))
            pdf._set_font("", 8)
            pdf.set_text_color(*pdf.INK_SECONDARY)
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
            pdf.ln(1)
            pdf.text_block(f"인사이트: {insight}")

    # ── 9-4. Brain Quality + Cross Verification ──
    pdf.ln(3)
    pdf.subsection_title("9-4. Brain 품질 + Cross Verification")
    pdf._set_font("", 8)
    qrows: List[tuple] = []
    if bq:
        qrows.append(("Brain Quality Score", f"{bq.get('score', '-')}"))
        qrows.append(("Quality 상태", str(bq.get("status", "-"))))
        comps = bq.get("components") or {}
        if comps:
            qrows.append(("· 적중률 컴포넌트", f"{comps.get('positive_hit_rate_score', '-')}"))
            qrows.append(("· AVOID 회피 컴포넌트", f"{comps.get('avoid_avoidance_score', '-')}"))
            qrows.append(("· 등급 분리도 컴포넌트", f"{comps.get('grade_separation_score', '-')}"))
    if cv:
        qrows.append(("Cross Verify 분석 종목", str(cv.get("total_analyzed", "-"))))
        qrows.append(("Cross Verify 이견 (override)", str(cv.get("override_count", "-"))))
    for k, v in qrows:
        pdf.set_x(15)
        pdf.set_text_color(*pdf.INK_TERTIARY)
        pdf.cell(75, 5, k)
        pdf.set_text_color(*pdf.INK)
        pdf.cell(0, 5, str(v))
        pdf.ln(5)
    # Cross verification 의 disagreements 상위 5
    disagreements = cv.get("disagreements") or [] if cv else []
    if disagreements:
        pdf.ln(1)
        pdf._set_font("B", 8)
        pdf.set_text_color(*pdf.INK)
        pdf.set_x(15)
        pdf.cell(0, 5, f"이견 종목 (top {min(5, len(disagreements))})")
        pdf.ln(5)
        for d in disagreements[:5]:
            name = _norm_text(d.get("name") or "-")
            tk = d.get("ticker") or "-"
            gem = d.get("gemini_rec") or "-"
            cla = d.get("claude_rec") or "-"
            reason = _norm_text(d.get("reason") or "")[:80]
            pdf.set_x(18)
            pdf._set_font("B", 8)
            pdf.set_text_color(*pdf.INK)
            pdf.cell(60, 5, f"{name} ({tk})")
            pdf._set_font("", 8)
            pdf.set_text_color(*pdf.INK_SECONDARY)
            pdf.cell(0, 5, f"Gemini {gem} vs Claude {cla}")
            pdf.ln(5)
            if reason:
                pdf.set_x(20)
                pdf._set_font("", 7)
                pdf.set_text_color(*pdf.INK_TERTIARY)
                pdf.multi_cell(170, 4, f"근거: {reason}", align="L")
                pdf.ln(1)

    # ── 9-5. Market Horizon (사이클 진단) ──
    if horizon:
        pdf.ln(3)
        pdf.subsection_title("9-5. Market Horizon (사이클 진단)")
        verdict_full = _norm_text(horizon.get("verdict") or "")
        stage_label = _norm_text(horizon.get("cycle_stage_label_ko") or horizon.get("cycle_stage") or "-")
        recession = horizon.get("recession_prob_12m")
        cape_p = horizon.get("cape_percentile")
        cape_v = horizon.get("cape_value")
        as_of = _norm_text(horizon.get("as_of") or "")

        if verdict_full:
            pdf.text_block(verdict_full)

        pdf._set_font("", 8)
        hrows = [
            ("사이클 단계", stage_label),
            ("12M 침체확률", f"{float(recession)*100:.1f}%" if recession is not None else "-"),
            ("CAPE 백분위", f"{cape_p}%ile" if cape_p is not None else "-"),
            ("CAPE 값", f"{cape_v}" if cape_v is not None else "-"),
            ("as_of", as_of[:16]),
        ]
        for k, v in hrows:
            pdf.set_x(15)
            pdf.set_text_color(*pdf.INK_TERTIARY)
            pdf.cell(55, 5, k)
            pdf.set_text_color(*pdf.INK)
            pdf.cell(0, 5, str(v))
            pdf.ln(5)

        # signals / analog horizons / black swan events 추가 노출
        signals = horizon.get("signals") or []
        if signals:
            pdf.ln(1)
            pdf._set_font("B", 8)
            pdf.set_text_color(*pdf.INK)
            pdf.set_x(15)
            pdf.cell(0, 5, f"Horizon 신호 ({len(signals)})")
            pdf.ln(5)
            pdf._set_font("", 8)
            for s in signals[:8] if isinstance(signals, list) else []:
                if isinstance(s, dict):
                    name = _norm_text(s.get("name") or s.get("signal") or "-")
                    v = s.get("value") or s.get("status") or "-"
                else:
                    name, v = _norm_text(str(s)), ""
                pdf.set_x(18)
                pdf.set_text_color(*pdf.INK_SECONDARY)
                pdf.cell(80, 5, name[:32])
                pdf.set_text_color(*pdf.INK)
                pdf.cell(0, 5, str(v)[:50])
                pdf.ln(5)

        bs_events = horizon.get("recent_black_swan_events") or []
        if bs_events:
            pdf.ln(1)
            pdf._set_font("B", 8)
            pdf.set_text_color(*pdf.INK)
            pdf.set_x(15)
            pdf.cell(0, 5, f"최근 Black Swan 이벤트 ({len(bs_events)})")
            pdf.ln(5)
            pdf._set_font("", 8)
            for ev in bs_events[:5] if isinstance(bs_events, list) else []:
                if not isinstance(ev, dict):
                    continue
                pdf.set_x(18)
                pdf.set_text_color(*pdf.INK_SECONDARY)
                pdf.multi_cell(175, 5,
                    f"· {_norm_text(ev.get('date',''))} · {_norm_text(ev.get('name') or ev.get('event',''))[:100]}",
                    align="L")


# ─── 제10장 — 분석 산식 · 자체 검증 trail ───────────────────

def _render_chap10_methodology(pdf: VerityPDF, portfolio: Dict[str, Any]):
    """Brain v5 자체 산식 + VAMS 프로필 + KIS 정책 + Phase 0 trail.

    LLM 무료 tier 가 가지지 못한 자기 자산 노출 (CLAUDE.md RULE 6 정합).
    값 변경 0, _methodology_narrative() helper 의 가/나/다/라/마/바 6장 출력.
    """
    pdf.add_page()
    pdf.chapter_title(10, "분석 산식 · 자체 검증 trail")
    pdf.narrative_paragraphs(_methodology_narrative())


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
    # 신규 챕터 — 사용자 피드백 "양과 질 모두 챙겨" (2026-05-11)
    try:
        _render_chap8_headlines(pdf, portfolio)
    except Exception as _e:
        # 신규 챕터 실패 시 *결론까지* 산출 보존 — 회귀 가드
        import logging; logging.warning("chap8 headlines 실패: %s", _e)
    try:
        _render_chap9_postmortem(pdf, portfolio)
    except Exception as _e:
        import logging; logging.warning("chap9 postmortem 실패: %s", _e)
    # 자체 산식 trail (Brain v5 B1~B6 + VAMS V1~V5 + KIS 정책) — LLM 못 가지는 자기 자산
    try:
        _render_chap10_methodology(pdf, portfolio)
    except Exception as _e:
        import logging; logging.warning("chap10 methodology 실패: %s", _e)
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
