"""
Monthly 관리자 리포트 PDF — 7장 구조.

7장:
  COVER  월간 성과 카드 + KPI 6 + 한 줄
  제1장  월간 성과 총결산 (월별 비교 / VAMS PnL / 전략 기여도)
  제2장  시스템 성능 리뷰 (Brain 추이 / 섹터 정확도 / 데이터 안정성 / LLM 비용)
  제3장  매크로 환경 월간 (지표 변화 + 이벤트 결산 + 자금 흐름)
  제4장  섹터·테마 월간 (순위 + 이달의 테마 + 다음 달 주목)
  제5장  WatchList 월간 결산
  제6장  파라미터 조정 검토 (가중치 + 임계 점검)
  제7장  다음 달 전략 방향
"""
from __future__ import annotations

import os
from typing import Any, Dict

from api.config import DATA_DIR, now_kst
from api.reports.pdf_generator import VerityPDF, _norm_text
from api.utils.dilution import (
    can_show_probability, scenario_label, validation_status_summary,
)


def _render_cover(pdf, analysis, portfolio, val_summary):
    period_label = analysis.get("period_label", "월간")
    date_range = analysis.get("date_range", {})
    recs = analysis.get("recommendations", {}) or {}
    port = analysis.get("portfolio", {}) or {}
    vams = portfolio.get("vams") or {}

    pdf._set_font("B", 17); pdf.set_text_color(*pdf.WHITE); pdf.set_x(12)
    pdf.cell(0, 10, f"VERITY {period_label.upper()} ADMIN REPORT")
    pdf.ln(8)
    pdf._set_font("", 9); pdf.set_text_color(*pdf.GRAY); pdf.set_x(12)
    pdf.multi_cell(180, pdf.LH_BOX,
                   "관리자용 — 월간 성과 회고 + 시스템 성능 리뷰 + 파라미터 조정", align="L")
    pdf.ln(2); pdf.set_x(12)
    pdf.cell(0, 6, f"기간: {date_range.get('start', '?')} ~ {date_range.get('end', '?')}")
    pdf.ln(5); pdf.set_x(12)
    pdf.cell(0, 6, f"발행 시각: {now_kst().strftime('%Y-%m-%d %H:%M KST')}")
    pdf.ln(8)

    if not val_summary.get("validated"):
        y = pdf.get_y(); pdf.set_fill_color(60, 30, 0); pdf.rect(10, y, 190, 8, "F")
        pdf._set_font("B", 8); pdf.set_text_color(*pdf.YELLOW); pdf.set_xy(14, y + 1.5)
        pdf.cell(0, 5, f"⚠ {val_summary.get('watermark_label', '검증 진행 중')}")
        pdf.set_y(y + 12)

    # KPI 6
    pdf._set_font("B", 13); pdf.set_text_color(*pdf.ACCENT); pdf.set_x(12)
    pdf.cell(0, 8, "월간 성과 KPI"); pdf.ln(10)

    buy_recs = recs.get("total_buy_recs", 0)
    hit_rate = recs.get("hit_rate_pct", 0) or 0
    avg_return = recs.get("avg_return_pct", 0) or 0
    vams_return = port.get("cum_return_pct") or vams.get("cum_return_pct", 0) or 0
    top_winner = recs.get("top_winner", {}) or {}
    top_loser = recs.get("top_loser", {}) or {}

    pdf.metric_row([
        {"label": "BUY 추천", "value": f"{buy_recs}건", "color": pdf.WHITE},
        {"label": "적중률", "value": f"{hit_rate}%",
         "color": pdf.GREEN if hit_rate >= 55 else pdf.YELLOW if hit_rate >= 40 else pdf.RED},
        {"label": "평균 수익률", "value": f"{avg_return:+.2f}%",
         "color": pdf.GREEN if avg_return >= 0 else pdf.RED},
        {"label": "VAMS", "value": f"{vams_return:+.2f}%",
         "color": pdf.GREEN if vams_return >= 0 else pdf.RED},
    ])
    pdf.metric_row([
        {"label": "최고 수익", "value": _norm_text(top_winner.get("name", "-"))[:8],
         "color": pdf.GREEN},
        {"label": "최대 손실", "value": _norm_text(top_loser.get("name", "-"))[:8],
         "color": pdf.RED},
        {"label": "기간", "value": f"{analysis.get('days_available', 0)}일", "color": pdf.WHITE},
        {"label": "데이터 누적", "value": f"{analysis.get('snapshot_count', 0)}회",
         "color": pdf.WHITE},
    ])

    pdf._set_font("B", 11); pdf.set_text_color(*pdf.WHITE); pdf.set_x(15)
    if hit_rate >= 55:
        line = "이달 시스템 정상 작동 — 다음 달 같은 패턴 유지"; c = pdf.GREEN
    elif hit_rate < 40 and buy_recs > 5:
        line = "이달 적중률 부진 — 파라미터 조정 검토 필요"; c = pdf.RED
    else:
        line = "이달 혼조 — 부분 검토 영역"; c = pdf.YELLOW
    pdf.set_text_color(*c)
    pdf.multi_cell(180, 7, line, align="L"); pdf.ln(3)


def _render_chap1_performance(pdf, analysis):
    pdf.add_page(); pdf.chapter_title(1, "월간 성과 총결산")
    recs = analysis.get("recommendations", {}) or {}
    port = analysis.get("portfolio", {}) or {}

    # 1-A. 월별 성과 비교 (4주 또는 월별 분해)
    pdf.subsection_title("1-A. 주차별 성과")
    weekly = recs.get("weekly_breakdown") or []
    if weekly:
        for w in weekly[:5]:
            pdf._set_font("", 9); pdf.set_text_color(204, 204, 204); pdf.set_x(18)
            label = w.get("label", "?")
            pdf.cell(20, 6, label)
            pdf.cell(25, 6, f"BUY {w.get('buy_count', 0)}건")
            pdf.cell(25, 6, f"적중 {w.get('hit_rate', 0)}%")
            pdf.cell(0, 6, f"평균 {w.get('avg_return', 0):+.2f}%")
            pdf.ln(6)
    else:
        pdf.text_block(f"BUY {recs.get('total_buy_recs', 0)}건 / 적중 {recs.get('hit_count', '-')}건 / "
                      f"평균 {recs.get('avg_return_pct', 0):+.2f}%")

    # 1-B. PnL 곡선
    pdf.subsection_title("1-B. VAMS PnL 추이")
    pnl_curve = port.get("pnl_curve") or []
    if pnl_curve:
        pdf.text_block(f"월초 → 월말: {pnl_curve[0].get('value', 0):,.0f}원 → {pnl_curve[-1].get('value', 0):,.0f}원\n"
                      f"최고점: {max((p.get('value', 0) for p in pnl_curve)):,.0f}원\n"
                      f"최저점: {min((p.get('value', 0) for p in pnl_curve)):,.0f}원\n"
                      f"MDD: {port.get('mdd_pct', 0):.2f}%")
    else:
        pdf.text_block("PnL 추이 데이터 미수집", color=pdf.GRAY)

    # 1-C. 전략별 기여도
    pdf.subsection_title("1-C. 전략별 기여도")
    contrib = analysis.get("strategy_contribution") or {}
    if contrib:
        for k, v in contrib.items():
            pdf.text_block(f"· {k}: {v}")
    else:
        pdf.text_block("전략 기여도 분해 데이터 미수집 (기여도 추적 모듈 연결 필요)", color=pdf.GRAY)


def _render_chap2_system(pdf, analysis, portfolio):
    pdf.add_page(); pdf.chapter_title(2, "시스템 성능 리뷰")
    brain = analysis.get("brain_accuracy", {}) or {}

    pdf.subsection_title("2-A. Brain 적중률 추이")
    weekly_acc = brain.get("weekly_accuracy") or []
    if weekly_acc:
        for i, w in enumerate(weekly_acc[-4:]):
            label = ["Week 1", "Week 2", "Week 3", "Week 4"][i]
            acc = w.get("accuracy") or w.get("hit_rate") or 0
            pdf._set_font("", 9); pdf.set_text_color(204, 204, 204); pdf.set_x(18)
            pdf.cell(30, 6, label); pdf.cell(0, 6, f"{acc:.1f}%"); pdf.ln(6)
    else:
        pdf.text_block("Brain 적중률 누적 데이터 부족", color=pdf.GRAY)

    pdf.subsection_title("2-B. 섹터 예측 정확도")
    sectors = analysis.get("sectors", {}) or {}
    pdf.text_block(f"포착 정확도: {sectors.get('prediction_accuracy_pct', '-')}%")

    pdf.subsection_title("2-C. 데이터 파이프라인 안정성")
    health = portfolio.get("system_health", {}) or {}
    pdf.metric_row([
        {"label": "Deadman 발동", "value": str(health.get("deadman_count_month", 0)),
         "color": pdf.RED if health.get("deadman_count_month", 0) > 3 else pdf.GREEN},
        {"label": "파싱 오류", "value": str(health.get("parse_errors_month", 0)), "color": pdf.YELLOW},
        {"label": "수집 실패", "value": str(health.get("fetch_failures_month", 0)), "color": pdf.YELLOW},
        {"label": "가동률", "value": f"{health.get('uptime_pct', 99)}%", "color": pdf.GREEN},
    ])

    # 2-D. LLM 비용 ROI (Phase 1.5 통합)
    pdf.subsection_title("2-D. LLM 비용")
    try:
        from api.metadata import llm_cost
        cost = llm_cost.summarize_cost(days=30)
        pdf.text_block(f"이달 호출 {cost['calls']}회 / 비용 ${cost['total_usd']} (~{cost['total_krw_est']:,}원)")
        if cost.get("by_provider"):
            for p, v in cost["by_provider"].items():
                pdf.text_block(f"  · {p}: ${v}")
    except Exception:
        pdf.text_block("LLM 비용 추적 데이터 부족 (모듈 연결 후 누적 시작)", color=pdf.GRAY)


def _render_chap3_macro(pdf, analysis):
    pdf.add_page(); pdf.chapter_title(3, "매크로 환경 월간 리뷰")
    macro = analysis.get("macro", {}) or {}

    pdf.subsection_title("3-1. 월간 핵심 지표 변화")
    pdf.metric_row([
        {"label": "VIX 평균", "value": str(macro.get("vix_avg", "-")), "color": pdf.WHITE},
        {"label": "환율 평균", "value": f"{macro.get('usd_krw_avg', '-')}원", "color": pdf.WHITE},
        {"label": "S&P500", "value": f"{macro.get('sp500_monthly_pct', 0):+.2f}%",
         "color": pdf.GREEN if (macro.get('sp500_monthly_pct') or 0) >= 0 else pdf.RED},
        {"label": "코스피", "value": f"{macro.get('kospi_monthly_pct', 0):+.2f}%",
         "color": pdf.GREEN if (macro.get('kospi_monthly_pct') or 0) >= 0 else pdf.RED},
    ])

    pdf.subsection_title("3-2. 주요 이벤트 결산")
    events = macro.get("events_review") or []
    if events:
        for e in events[:5]:
            pdf.text_block(f"· {_norm_text(e.get('name', ''))}: "
                          f"예상 {e.get('consensus', '?')} / 실제 {e.get('actual', '?')} / "
                          f"VERITY 시나리오 {e.get('scenario_match', '?')}")
    else:
        pdf.text_block("이벤트 결산 데이터 미수집", color=pdf.GRAY)


def _render_chap4_sectors(pdf, analysis):
    pdf.add_page(); pdf.chapter_title(4, "섹터·테마 월간 총정리")
    sectors = analysis.get("sectors", {}) or {}

    pdf.subsection_title("4-1. 섹터 월간 순위")
    top = sectors.get("top3_sectors") or []
    bottom = sectors.get("bottom3_sectors") or []
    pdf._set_font("B", 9); pdf.set_text_color(*pdf.GREEN); pdf.set_x(18)
    pdf.cell(0, 6, "▲ TOP 3"); pdf.ln(6)
    for s in top[:3]:
        pdf._set_font("", 9); pdf.set_text_color(204, 204, 204); pdf.set_x(20)
        pdf.cell(50, 5, _norm_text(s.get("name", "")))
        pdf.cell(0, 5, f"{s.get('change_pct', 0):+.2f}%"); pdf.ln(5)
    pdf.ln(2)
    pdf._set_font("B", 9); pdf.set_text_color(*pdf.RED); pdf.set_x(18)
    pdf.cell(0, 6, "▼ BOTTOM 3"); pdf.ln(6)
    for s in bottom[:3]:
        pdf._set_font("", 9); pdf.set_text_color(204, 204, 204); pdf.set_x(20)
        pdf.cell(50, 5, _norm_text(s.get("name", "")))
        pdf.cell(0, 5, f"{s.get('change_pct', 0):+.2f}%"); pdf.ln(5)

    pdf.subsection_title("4-2. 이달의 테마")
    themes = sectors.get("themes") or analysis.get("themes") or []
    if themes:
        for t in themes[:3]:
            pdf.text_block(f"· {_norm_text(t.get('name', ''))} — {_norm_text(t.get('summary', ''))}")
    else:
        pdf.text_block("테마 분석 데이터 미수집", color=pdf.GRAY)

    pdf.subsection_title("4-3. 다음 달 주목 섹터")
    next_focus = sectors.get("next_month_focus") or []
    if next_focus:
        for f in next_focus[:3]:
            pdf.text_block(f"※ {_norm_text(f.get('name', ''))} — {_norm_text(f.get('reason', ''))}")
    else:
        pdf.text_block("다음 달 주목 섹터 데이터 미수집", color=pdf.GRAY)


def _render_chap5_watchlist(pdf, portfolio):
    pdf.add_page(); pdf.chapter_title(5, "WatchList 월간 결산")
    wl = portfolio.get("watchlist") or {}
    if not wl:
        pdf.text_block("WatchList 데이터 미수집", color=pdf.GRAY); return
    if wl.get("month_summary"):
        pdf.text_block(_norm_text(wl["month_summary"]))
    next_month = wl.get("next_month_draft") or []
    if next_month:
        pdf.subsection_title("5-1. 다음 달 WatchList 초안")
        for w in next_month[:5]:
            pdf.text_block(f"+ {_norm_text(w.get('name', ''))} — {_norm_text(w.get('reason', ''))}")


def _render_chap6_params(pdf, analysis, val_summary):
    pdf.add_page(); pdf.chapter_title(6, "파라미터 조정 검토")
    meta = analysis.get("meta_analysis", {}) or {}

    pdf.subsection_title("6-1. 가중치 효과성")
    pdf.text_block(f"가장 강한 시그널: {meta.get('best_predictor', '-')}\n"
                  f"가장 약한 시그널: {meta.get('worst_predictor', '-')}")

    pdf.subsection_title("6-2. 조정 결정")
    pdf.text_block("이달 적중률 + 백테스트 결과 기반 — 본인 검토 후 결정 필수")
    if not val_summary.get("validated"):
        pdf._set_font("", 8); pdf.set_text_color(*pdf.YELLOW); pdf.set_x(18)
        pdf.multi_cell(177, pdf.LH_COMPACT,
                       "※ 검증 미완료 — 백테스트 통과 없는 가중치 변경 금지 (continuous_evolution 정책)",
                       align="L")
        pdf.ln(2)


def _render_chap7_next(pdf, analysis, val_summary):
    pdf.add_page(); pdf.chapter_title(7, "다음 달 전략 방향")
    pdf.subsection_title("7-1. 매크로 전망")
    pdf.text_block("다음 달 주요 이벤트 + 기본/리스크 시나리오 (LLM 분석 결과 통합 예정)")
    pdf.subsection_title("7-2. 포지션 전략")
    pdf.text_block("현금 비중 목표 / 집중 섹터 / 회피 섹터 / 전략 전환 트리거")
    pdf._set_font("", 8); pdf.set_text_color(*pdf.DARK_GRAY); pdf.set_x(15)
    pdf.cell(0, 5, f"검증 상태: {val_summary.get('watermark_label', '')}")


def generate_monthly_admin_pdf(analysis: Dict[str, Any], portfolio: Dict[str, Any]) -> str:
    val_summary = validation_status_summary(portfolio.get("vams") or {})
    pdf = VerityPDF(); pdf.add_page()
    _render_cover(pdf, analysis, portfolio, val_summary)
    _render_chap1_performance(pdf, analysis)
    _render_chap2_system(pdf, analysis, portfolio)
    _render_chap3_macro(pdf, analysis)
    _render_chap4_sectors(pdf, analysis)
    _render_chap5_watchlist(pdf, portfolio)
    _render_chap6_params(pdf, analysis, val_summary)
    _render_chap7_next(pdf, analysis, val_summary)

    out_dir = os.path.join(DATA_DIR, "reports")
    os.makedirs(out_dir, exist_ok=True)
    fname = f"verity_monthly_admin_{now_kst().strftime('%Y%m%d_%H%M')}.pdf"
    path = os.path.join(out_dir, fname)
    pdf.output(path)
    return path
