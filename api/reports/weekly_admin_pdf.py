"""
Weekly 관리자 리포트 PDF — 6장 구조.

6장:
  COVER  주간 성과 카드 + KPI 4 + 한 줄 판단
  제1장  주간 성과 복기 (BUY 성과 / 보류 검증 / Brain 4주 롤링)
  제2장  전략 검증 (놓친 기회 + 후회 분석 + 다이버전스)
  제3장  매크로 주간 리뷰
  제4장  다음 주 시나리오 3개 (검증 미완료 시 라벨링만, 확률 X)
  제5장  WatchList 업데이트
  제6장  리스크 레지스터

데이터 소스: generate_periodic_analysis('weekly') + portfolio.json
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from api.config import DATA_DIR, now_kst
from api.reports.pdf_generator import VerityPDF, _norm_text, _safe_report_text
from api.utils.dilution import (
    can_show_probability, scenario_label, validation_status_summary,
)
from api.utils.macro_meta import macro_as_of_line


def _render_cover(pdf: VerityPDF, analysis: Dict[str, Any], portfolio: Dict[str, Any],
                  val_summary: Dict[str, Any]):
    """주간 성과 카드 + KPI 4."""
    period_label = analysis.get("period_label", "주간")
    date_range = analysis.get("date_range", {})
    recs = analysis.get("recommendations", {}) or {}
    port = analysis.get("portfolio", {}) or {}
    vams = portfolio.get("vams") or {}

    pdf._set_font("B", 17)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(12)
    pdf.cell(0, 10, f"VERITY {period_label.upper()} ADMIN REPORT")
    pdf.ln(8)
    pdf._set_font("", 9)
    pdf.set_text_color(*pdf.GRAY)
    pdf.set_x(12)
    pdf.multi_cell(180, pdf.LH_BOX,
                   "관리자용 — 주간 전략 검증 + 다음 주 시나리오 (참고용 · 매매 권유 아님)", align="L")
    pdf.ln(2)
    pdf.set_x(12)
    pdf.cell(0, 6, f"기간: {date_range.get('start', '?')} ~ {date_range.get('end', '?')}")
    pdf.ln(5)
    pdf.set_x(12)
    pdf.cell(0, 6, f"발행 시각: {now_kst().strftime('%Y-%m-%d %H:%M KST')}")
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

    # KPI 4
    pdf._set_font("B", 13)
    pdf.set_text_color(*pdf.ACCENT)
    pdf.set_x(12)
    pdf.cell(0, 8, "주간 성과 KPI")
    pdf.ln(10)

    buy_recs = recs.get("total_buy_recs", 0)
    hit_rate = recs.get("hit_rate_pct", 0) or 0
    avg_return = recs.get("avg_return_pct", 0) or 0
    vams_return = port.get("cum_return_pct") or vams.get("cum_return_pct", 0) or 0

    pdf.metric_row([
        {"label": "BUY 추천", "value": f"{buy_recs}건", "color": pdf.WHITE},
        {"label": "적중률", "value": f"{hit_rate}%",
         "color": pdf.GREEN if hit_rate >= 55 else pdf.YELLOW if hit_rate >= 40 else pdf.RED},
        {"label": "평균 수익률", "value": f"{avg_return:+.2f}%",
         "color": pdf.GREEN if avg_return >= 0 else pdf.RED},
        {"label": "VAMS 누적", "value": f"{vams_return:+.2f}%",
         "color": pdf.GREEN if vams_return >= 0 else pdf.RED},
    ])

    # 한 줄 판단
    pdf._set_font("B", 11)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(15)
    if hit_rate >= 55 and avg_return > 0:
        line = "이번 주 시스템 정상 작동 — 다음 주 같은 패턴 유지"
        c = pdf.GREEN
    elif buy_recs == 0:
        line = "이번 주 의도적 보류 — 매크로 필터 차단 또는 신호 부재"
        c = pdf.YELLOW
    elif hit_rate < 40:
        line = "이번 주 적중률 부진 — 다음 주 임계 점검 필요"
        c = pdf.RED
    else:
        line = "이번 주 혼조 — 부분적 검토 영역 존재"
        c = pdf.YELLOW
    pdf.set_text_color(*c)
    pdf.multi_cell(180, 7, line, align="L")
    pdf.ln(3)


def _render_chap1_performance(pdf: VerityPDF, analysis: Dict[str, Any]):
    """제1장 주간 성과 복기."""
    pdf.add_page()
    pdf.chapter_title(1, "주간 성과 복기")
    recs = analysis.get("recommendations", {}) or {}
    brain = analysis.get("brain_accuracy", {}) or {}

    # 1-A. BUY 추천 성과표
    pdf.subsection_title("1-A. BUY 추천 성과")
    buy_details = recs.get("buy_details") or recs.get("recent_buys") or []
    if not buy_details:
        if recs.get("total_buy_recs", 0) == 0:
            pdf.text_block("이번 주 BUY 0건 — 의도적 보류 (매크로 필터 또는 신호 부재)", color=pdf.YELLOW)
        else:
            pdf.text_block(f"BUY {recs.get('total_buy_recs', 0)}건 / 적중 {recs.get('hit_count', '?')}건 / "
                          f"평균 {recs.get('avg_return_pct', 0):+.2f}%")
    else:
        pdf._set_font("", 9)
        for r in buy_details[:8]:
            pdf.set_x(15)
            pdf.set_text_color(*pdf.WHITE)
            pdf._set_font("B", 9)
            name = _norm_text(r.get("name", "?"))
            pdf.cell(60, 5, name)
            ret = r.get("return_pct", 0) or 0
            pdf._set_font("", 9)
            pdf.set_text_color(*pdf.GREEN if ret >= 0 else pdf.RED)
            pdf.cell(20, 5, f"{ret:+.2f}%")
            pdf.set_text_color(*pdf.GRAY)
            pdf.cell(0, 5, f"진입 {r.get('entry_price', '?')} → 현재 {r.get('current_price', '?')}")
            pdf.ln(5)
        pdf.ln(2)

    # 1-B. Brain 적중률 4주 롤링
    pdf.subsection_title("1-B. Brain 적중률 추이 (4주 롤링)")
    weekly_acc = brain.get("weekly_accuracy") or brain.get("rolling") or []
    if weekly_acc:
        pdf._set_font("", 9)
        pdf.set_text_color(204, 204, 204)
        for i, w in enumerate(weekly_acc[-4:]):
            label = f"{i+1}주 전" if i < 3 else "이번 주"
            acc = w.get("accuracy") or w.get("hit_rate") or 0
            pdf.set_x(18)
            pdf.cell(30, 6, label)
            pdf.cell(0, 6, f"{acc:.1f}%")
            pdf.ln(6)
    else:
        pdf.text_block("Brain 적중률 추이 데이터 미수집 (시간 누적 필요)", color=pdf.GRAY)


def _render_chap2_strategy_review(pdf: VerityPDF, analysis: Dict[str, Any]):
    """제2장 전략 검증."""
    pdf.add_page()
    pdf.chapter_title(2, "전략 검증")
    meta = analysis.get("meta_analysis", {}) or {}
    sectors = analysis.get("sectors", {}) or {}

    # 2-A. 시스템이 옳았는가
    pdf.subsection_title("2-A. 이번 주 시스템 평가")
    best_predictor = meta.get("best_predictor", "데이터 부족")
    worst_predictor = meta.get("worst_predictor")
    pdf.text_block(f"가장 잘 작동한 시그널: {best_predictor}")
    if worst_predictor:
        pdf.text_block(f"가장 약했던 시그널: {worst_predictor}")

    # 2-B. 놓친 기회 분석 (후회)
    pdf.subsection_title("2-B. 놓친 기회 분석")
    missed = meta.get("missed_opportunities") or []
    if missed:
        pdf._set_font("", 9)
        pdf.set_text_color(204, 204, 204)
        for m in missed[:3]:
            pdf.set_x(18)
            pdf.multi_cell(177, pdf.LH_COMPACT, f"· {_norm_text(m)}", align="L")
            pdf.ln(1)
    else:
        pdf.text_block("놓친 기회 데이터 미수집 (postmortem 누적 필요)", color=pdf.GRAY)

    # 2-C. 섹터 다이버전스
    pdf.subsection_title("2-C. 섹터 다이버전스 신호")
    divergences = sectors.get("divergence_alerts") or sectors.get("anomalies") or []
    if divergences:
        pdf._set_font("", 9)
        pdf.set_text_color(*pdf.YELLOW)
        for d in divergences[:3]:
            pdf.set_x(18)
            pdf.multi_cell(177, pdf.LH_COMPACT, f"⚠ {_norm_text(d)}", align="L")
            pdf.ln(1)
    else:
        pdf.text_block("다이버전스 없음 (주가-자금 흐름 일치)", color=pdf.GRAY)


def _render_chap3_macro(pdf: VerityPDF, analysis: Dict[str, Any]):
    """제3장 매크로 주간 리뷰."""
    pdf.add_page()
    pdf.chapter_title(3, "매크로 환경 주간 리뷰")
    macro = analysis.get("macro", {}) or {}

    # 주간 평균 vs 전주
    pdf.subsection_title("3-1. 주간 핵심 지표 변화")
    pdf.metric_row([
        {"label": "주간 VIX 평균", "value": str(macro.get("vix_avg", "-")), "color": pdf.WHITE},
        {"label": "주간 환율 평균", "value": f"{macro.get('usd_krw_avg', '-')}원", "color": pdf.WHITE},
        {"label": "주간 분위기", "value": str(macro.get("mood_avg", "-")),
         "color": pdf.GREEN if (macro.get("mood_avg") or 50) >= 55 else pdf.YELLOW},
        {"label": "S&P500 주간", "value": f"{macro.get('sp500_weekly_pct', 0):+.2f}%",
         "color": pdf.GREEN if (macro.get("sp500_weekly_pct") or 0) >= 0 else pdf.RED},
    ])

    # 자금 흐름
    pdf.subsection_title("3-2. 주간 자금 흐름")
    flow = macro.get("flow_summary", {}) or {}
    foreign_net = flow.get("foreign_net_weekly", 0)
    inst_net = flow.get("institution_net_weekly", 0)
    pdf.text_block(f"외국인 주간 순매수: {foreign_net:+,}억\n"
                  f"기관 주간 순매수: {inst_net:+,}억")


def _render_chap4_scenarios(pdf: VerityPDF, analysis: Dict[str, Any], validated: bool):
    """제4장 다음 주 시나리오 (3개)."""
    pdf.add_page()
    pdf.chapter_title(4, "다음 주 시나리오")

    show_prob = can_show_probability(validated=validated, backtest_samples=0)

    scenarios = analysis.get("next_week_scenarios") or [
        {"role": "primary", "trigger": "FOMC 동결 + PCE 안정",
         "reaction": "위험선호 재개, 코스피 상방", "action": "VIX 18 이하 안정 확인 후 BUY 재개 검토"},
        {"role": "alternative", "trigger": "FOMC 매파 서프라이즈 또는 PCE 상회",
         "reaction": "성장주 급락, 달러 강세", "action": "관망 연장, 현금 비중 유지 또는 확대"},
        {"role": "tail", "trigger": "BOJ 인상 → 엔캐리 청산 트리거",
         "reaction": "글로벌 자산 동반 급락", "action": "전 보유 포지션 점검, 손절선 재확인"},
    ]

    if not show_prob:
        pdf._set_font("", 8)
        pdf.set_text_color(*pdf.GRAY)
        pdf.set_x(15)
        pdf.cell(0, 5, "※ 검증 미완료 — 확률 표기 대신 라벨링만 사용 (백테스트 샘플 200+ 누적 시 확률 도입)")
        pdf.ln(6)

    for s in scenarios[:3]:
        role = s.get("role", "primary")
        label = scenario_label(role, validated=validated)
        c = pdf.GREEN if role == "primary" else pdf.YELLOW if role == "alternative" else pdf.RED

        pdf._set_font("B", 11)
        pdf.set_text_color(*c)
        pdf.set_x(15)
        pdf.cell(0, 7, label)
        pdf.ln(8)

        pdf._set_font("", 9)
        pdf.set_text_color(204, 204, 204)
        for k, prefix in [("trigger", "조건"), ("reaction", "예상 반응"), ("action", "VERITY 대응")]:
            v = _norm_text(s.get(k, ""))
            if v:
                pdf.set_x(18)
                pdf._set_font("B", 9)
                pdf.set_text_color(*pdf.WHITE)
                pdf.cell(28, 6, f"{prefix}:")
                pdf._set_font("", 9)
                pdf.set_text_color(204, 204, 204)
                pdf.multi_cell(150, pdf.LH_BODY, v, align="L")
        pdf.ln(3)


def _render_chap5_watchlist(pdf: VerityPDF, portfolio: Dict[str, Any]):
    """제5장 WatchList 업데이트."""
    pdf.add_page()
    pdf.chapter_title(5, "WatchList 업데이트")
    wl = portfolio.get("watchlist") or portfolio.get("watch_list") or {}

    if not wl:
        pdf.narrative_paragraphs("WatchList 데이터 미수집 (portfolio.watchlist 누적 필요)")
        return

    new_in = wl.get("new_in") or wl.get("added") or []
    new_out = wl.get("new_out") or wl.get("removed") or []
    target_changes = wl.get("target_changes") or []
    focus = wl.get("focus_next_week") or []

    if new_in:
        pdf.subsection_title("5-1. 신규 편입")
        for w in new_in[:5]:
            pdf.text_block(f"+ {_norm_text(w.get('name', '?'))} — {_norm_text(w.get('reason', ''))}")

    if new_out:
        pdf.subsection_title("5-2. 편입 제거")
        for w in new_out[:5]:
            pdf.text_block(f"- {_norm_text(w.get('name', '?'))} — {_norm_text(w.get('reason', ''))}")

    if target_changes:
        pdf.subsection_title("5-3. 목표가 조정")
        for t in target_changes[:5]:
            pdf.text_block(f"* {_norm_text(t.get('name', '?'))}: "
                          f"{t.get('old_target', '?')} → {t.get('new_target', '?')}")

    if focus:
        pdf.subsection_title("5-4. 다음 주 집중 모니터링 (최대 3)")
        for f in focus[:3]:
            pdf.text_block(f"※ {_norm_text(f.get('name', '?'))} — {_norm_text(f.get('reason', ''))}")


def _render_chap6_risk(pdf: VerityPDF, portfolio: Dict[str, Any]):
    """제6장 리스크 레지스터."""
    pdf.add_page()
    pdf.chapter_title(6, "리스크 레지스터")
    risks = portfolio.get("risk_register") or portfolio.get("risk_watch") or {}

    if isinstance(risks, str):
        pdf.text_block(_safe_report_text(risks))
        return
    if not risks:
        pdf.text_block("리스크 레지스터 데이터 미수집", color=pdf.GRAY)
        return

    new_risks = risks.get("new_this_week") if isinstance(risks, dict) else []
    persistent = risks.get("persistent") if isinstance(risks, dict) else []
    resolved_conditions = risks.get("resolution_conditions") if isinstance(risks, dict) else []

    if new_risks:
        pdf.subsection_title("6-1. 이번 주 신규 리스크")
        for r in new_risks[:5]:
            pdf.text_block(f"⚠ {_norm_text(r)}")
    else:
        pdf.text_block("이번 주 신규 리스크: 없음", color=pdf.GREEN)

    if persistent:
        pdf.subsection_title("6-2. 지속 모니터링 리스크")
        for r in persistent[:5]:
            pdf.text_block(f"· {_norm_text(r)}")

    if resolved_conditions:
        pdf.subsection_title("6-3. 해소 조건")
        for c in resolved_conditions[:5]:
            pdf.text_block(f"→ {_norm_text(c)}")


def _render_conclusion(pdf: VerityPDF, val_summary: Dict[str, Any]):
    pdf.add_page()
    pdf._set_font("B", 13)
    pdf.set_text_color(*pdf.WHITE)
    pdf.set_x(12)
    pdf.cell(0, 9, "다음 주 전략 + 면책")
    pdf.ln(10)
    pdf.narrative_paragraphs(
        "본 주간 보고서는 누적 데이터에 기반한 회고 + 다음 주 시나리오를 정리한다. "
        "시나리오는 가능성 분포를 보기 위한 것이지 단일 미래 예측이 아니다. "
        "최종 의사결정은 본인 책임이다."
    )

    pdf._set_font("", 8)
    pdf.set_text_color(*pdf.DARK_GRAY)
    pdf.set_x(15)
    pdf.cell(0, 5, f"검증 상태: {val_summary.get('watermark_label', '')}")


# ─── Public entry ────────────────────────────────────────

def generate_weekly_admin_pdf(analysis: Dict[str, Any], portfolio: Dict[str, Any]) -> str:
    """Weekly 관리자 PDF 생성. analysis = generate_periodic_analysis('weekly')."""
    vams = portfolio.get("vams") or {}
    val_summary = validation_status_summary(vams)

    pdf = VerityPDF()
    pdf.add_page()

    _render_cover(pdf, analysis, portfolio, val_summary)
    _render_chap1_performance(pdf, analysis)
    _render_chap2_strategy_review(pdf, analysis)
    _render_chap3_macro(pdf, analysis)
    _render_chap4_scenarios(pdf, analysis, validated=val_summary["validated"])
    _render_chap5_watchlist(pdf, portfolio)
    _render_chap6_risk(pdf, portfolio)
    _render_conclusion(pdf, val_summary)

    out_dir = os.path.join(DATA_DIR, "reports")
    os.makedirs(out_dir, exist_ok=True)
    fname = f"verity_weekly_admin_{now_kst().strftime('%Y%m%d_%H%M')}.pdf"
    path = os.path.join(out_dir, fname)
    pdf.output(path)
    import shutil
    shutil.copy2(path, os.path.join(out_dir, "verity_weekly_admin.pdf"))
    return path
