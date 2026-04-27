"""
Quarterly / Semi-Annual / Annual 관리자 PDF — 통합 모듈.

각 단위는 7~8장 구조이지만 핵심 차별화는:
  Quarterly  — Constitution 분기 개정 + 다음 분기 로드맵
  Semi-Annual — 모델 심층 분석 + Constitution 반기 점검
  Annual     — 벤치마크 비교 + Brain 패턴 도출 + 내년 로드맵

Monthly admin 패턴 재사용. 단위별 데이터 매핑만 다름.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from api.config import DATA_DIR, now_kst
from api.reports.pdf_generator import VerityPDF, _norm_text
from api.utils.dilution import (
    can_show_probability, scenario_label, validation_status_summary,
)


_TITLES = {
    "quarterly": ("VERITY QUARTERLY ADMIN REPORT", "분기"),
    "semi": ("VERITY SEMI-ANNUAL ADMIN REPORT", "반기"),
    "annual": ("VERITY ANNUAL ADMIN REPORT", "연간"),
}

_KPI_COUNT = {"quarterly": 8, "semi": 10, "annual": 12}


def _render_cover(pdf, period, analysis, portfolio, val_summary):
    title, label = _TITLES.get(period, ("VERITY ADMIN", "기간"))
    date_range = analysis.get("date_range", {})
    recs = analysis.get("recommendations", {}) or {}
    port = analysis.get("portfolio", {}) or {}
    vams = portfolio.get("vams") or {}

    pdf._set_font("B", 17); pdf.set_text_color(*pdf.WHITE); pdf.set_x(12)
    pdf.cell(0, 10, title); pdf.ln(8)
    pdf._set_font("", 9); pdf.set_text_color(*pdf.GRAY); pdf.set_x(12)
    pdf.multi_cell(180, pdf.LH_BOX, f"관리자용 — {label} 성과 + 시스템 진화 + 다음 {label} 전략",
                   align="L"); pdf.ln(2)
    pdf.set_x(12); pdf.cell(0, 6, f"기간: {date_range.get('start', '?')} ~ {date_range.get('end', '?')}")
    pdf.ln(5); pdf.set_x(12)
    pdf.cell(0, 6, f"발행: {now_kst().strftime('%Y-%m-%d %H:%M KST')}"); pdf.ln(8)

    if not val_summary.get("validated"):
        y = pdf.get_y(); pdf.set_fill_color(60, 30, 0); pdf.rect(10, y, 190, 8, "F")
        pdf._set_font("B", 8); pdf.set_text_color(*pdf.YELLOW); pdf.set_xy(14, y + 1.5)
        pdf.cell(0, 5, f"⚠ {val_summary.get('watermark_label', '검증 진행 중')}")
        pdf.set_y(y + 12)

    # KPI (단위별 6/8/10/12)
    pdf._set_font("B", 13); pdf.set_text_color(*pdf.ACCENT); pdf.set_x(12)
    pdf.cell(0, 8, f"{label} 성과 KPI"); pdf.ln(10)

    buy_recs = recs.get("total_buy_recs", 0)
    hit_rate = recs.get("hit_rate_pct", 0) or 0
    avg_return = recs.get("avg_return_pct", 0) or 0
    vams_return = port.get("cum_return_pct") or vams.get("cum_return_pct", 0) or 0
    mdd = port.get("mdd_pct", 0) or 0
    sharpe = port.get("sharpe", 0) or 0
    top_w = recs.get("top_winner", {}) or {}
    top_l = recs.get("top_loser", {}) or {}

    pdf.metric_row([
        {"label": "BUY 추천", "value": f"{buy_recs}건", "color": pdf.WHITE},
        {"label": "적중률", "value": f"{hit_rate}%",
         "color": pdf.GREEN if hit_rate >= 55 else pdf.RED if hit_rate < 40 else pdf.YELLOW},
        {"label": "평균 수익률", "value": f"{avg_return:+.2f}%",
         "color": pdf.GREEN if avg_return >= 0 else pdf.RED},
        {"label": "VAMS", "value": f"{vams_return:+.2f}%",
         "color": pdf.GREEN if vams_return >= 0 else pdf.RED},
    ])
    pdf.metric_row([
        {"label": "MDD", "value": f"{mdd:.2f}%",
         "color": pdf.RED if abs(mdd) > 15 else pdf.YELLOW if abs(mdd) > 10 else pdf.GREEN},
        {"label": "샤프", "value": f"{sharpe:.2f}",
         "color": pdf.GREEN if sharpe >= 1 else pdf.RED if sharpe < 0 else pdf.YELLOW},
        {"label": "최고 종목", "value": _norm_text(top_w.get("name", "-"))[:8], "color": pdf.GREEN},
        {"label": "최악 종목", "value": _norm_text(top_l.get("name", "-"))[:8], "color": pdf.RED},
    ])

    # Annual 전용 — 벤치마크 비교
    if period == "annual":
        bench = analysis.get("benchmark_comparison") or {}
        kospi = bench.get("kospi_pct", 0)
        sp500 = bench.get("sp500_pct", 0)
        alpha_kospi = vams_return - kospi
        alpha_sp = vams_return - sp500
        pdf.metric_row([
            {"label": "코스피", "value": f"{kospi:+.2f}%", "color": pdf.WHITE},
            {"label": "vs 코스피", "value": f"{alpha_kospi:+.2f}%",
             "color": pdf.GREEN if alpha_kospi >= 0 else pdf.RED},
            {"label": "S&P500", "value": f"{sp500:+.2f}%", "color": pdf.WHITE},
            {"label": "vs S&P500", "value": f"{alpha_sp:+.2f}%",
             "color": pdf.GREEN if alpha_sp >= 0 else pdf.RED},
        ])

    # 한 줄 판단
    pdf._set_font("B", 11)
    if hit_rate >= 55 and avg_return > 0:
        line, c = f"{label} 시스템 정상 작동", pdf.GREEN
    elif hit_rate < 40 and buy_recs > 10:
        line, c = f"{label} 적중률 부진 — 파라미터 점검 필요", pdf.RED
    else:
        line, c = f"{label} 혼조 — 부분 검토", pdf.YELLOW
    pdf.set_text_color(*c); pdf.set_x(15)
    pdf.multi_cell(180, 7, line, align="L"); pdf.ln(3)


def _render_chap1_performance(pdf, period, analysis):
    pdf.add_page(); _, label = _TITLES.get(period, ("", ""))
    pdf.chapter_title(1, f"{label} 성과 총결산")
    recs = analysis.get("recommendations", {}) or {}
    port = analysis.get("portfolio", {}) or {}

    pdf.subsection_title(f"1-A. 하위 단위 비교")
    breakdown = recs.get("sub_period_breakdown") or recs.get("monthly_breakdown") or []
    if breakdown:
        for s in breakdown[:6]:
            pdf._set_font("", 9); pdf.set_text_color(204, 204, 204); pdf.set_x(18)
            pdf.cell(20, 6, s.get("label", "?"))
            pdf.cell(25, 6, f"BUY {s.get('buy_count', 0)}건")
            pdf.cell(25, 6, f"적중 {s.get('hit_rate', 0)}%")
            pdf.cell(0, 6, f"평균 {s.get('avg_return', 0):+.2f}%"); pdf.ln(6)
    else:
        pdf.text_block(f"BUY {recs.get('total_buy_recs', 0)}건 / 적중 {recs.get('hit_count', '-')}건")

    pdf.subsection_title("1-B. PnL 곡선")
    pnl = port.get("pnl_curve") or []
    if pnl:
        pdf.text_block(f"시작 → 끝: {pnl[0].get('value', 0):,.0f}원 → {pnl[-1].get('value', 0):,.0f}원")
    else:
        pdf.text_block("PnL 누적 데이터 부족", color=pdf.GRAY)

    pdf.subsection_title("1-C. 전략별 기여도")
    contrib = analysis.get("strategy_contribution") or {}
    if contrib:
        for k, v in contrib.items():
            pdf.text_block(f"· {k}: {v}")
    else:
        pdf.text_block("기여도 분해 미수집", color=pdf.GRAY)


def _render_chap2_system(pdf, period, analysis, portfolio):
    pdf.add_page(); _, label = _TITLES.get(period, ("", ""))
    pdf.chapter_title(2, f"시스템 성능 {label} 리뷰")
    brain = analysis.get("brain_accuracy", {}) or {}

    pdf.subsection_title(f"2-A. Brain 적중률 추이")
    weekly_acc = brain.get("weekly_accuracy") or []
    if weekly_acc:
        pdf._set_font("", 9); pdf.set_text_color(204, 204, 204)
        for i, w in enumerate(weekly_acc):
            acc = w.get("accuracy") or w.get("hit_rate") or 0
            pdf.set_x(18); pdf.cell(30, 6, f"Week {i+1}")
            pdf.cell(0, 6, f"{acc:.1f}%"); pdf.ln(6)
    else:
        pdf.text_block(f"{label} 추이 데이터 부족", color=pdf.GRAY)

    # Semi-Annual 이상 — 모델 심층 분석
    if period in ("semi", "annual"):
        pdf.subsection_title("2-B. 모델 강점·약점 (구조적 패턴)")
        meta = analysis.get("meta_analysis", {}) or {}
        strong = meta.get("strong_market_envs") or ["데이터 누적 필요"]
        weak = meta.get("weak_market_envs") or ["데이터 누적 필요"]
        pdf.text_block(f"강한 시장 환경: {', '.join(strong[:3])}")
        pdf.text_block(f"약한 시장 환경: {', '.join(weak[:3])}")

    # AI 모델 이견
    pdf.subsection_title("2-C. AI 모델 이견 통계")
    disagreements = analysis.get("ai_disagreement_stats") or {}
    if disagreements:
        pdf.text_block(f"이견 발생 {disagreements.get('count', 0)}건 / "
                      f"보수 원칙 적중률 {disagreements.get('conservative_hit_rate', '-')}%")
    else:
        pdf.text_block("이견 통계 데이터 부족", color=pdf.GRAY)

    # 데이터 안정성
    pdf.subsection_title("2-D. 데이터 파이프라인 안정성")
    health = portfolio.get("system_health", {}) or {}
    pdf.metric_row([
        {"label": "Deadman", "value": str(health.get("deadman_count", 0)),
         "color": pdf.RED if health.get("deadman_count", 0) > 5 else pdf.GREEN},
        {"label": "파싱 오류", "value": str(health.get("parse_errors", 0)), "color": pdf.YELLOW},
        {"label": "수집 실패", "value": str(health.get("fetch_failures", 0)), "color": pdf.YELLOW},
        {"label": "가동률", "value": f"{health.get('uptime_pct', 99)}%", "color": pdf.GREEN},
    ])

    days_map = {"quarterly": 90, "semi": 180, "annual": 365}
    days = days_map.get(period, 30)

    # LLM 비용
    pdf.subsection_title("2-E. LLM 비용")
    try:
        from api.metadata import llm_cost
        cost = llm_cost.summarize_cost(days=days)
        pdf.text_block(f"기간 호출 {cost['calls']}회 / 비용 ${cost['total_usd']} (~{cost['total_krw_est']:,}원)")
    except Exception:
        pdf.text_block("LLM 비용 데이터 부족", color=pdf.GRAY)

    # Brain 학습 추이 (자기진화)
    pdf.subsection_title("2-F. Brain 학습 추이")
    try:
        from api.metadata import brain_learning
        trend = brain_learning.trend_summary(days=days)
        if trend.get("samples", 0) >= 2:
            pdf.text_block(f"기간 누적 {trend['samples']}일 / "
                          f"14d 적중률 평균 {trend.get('hit_rate_14d_avg', '-')}% / "
                          f"방향 {trend.get('hit_rate_14d_trend', 'n/a')}")
            buy_change = trend.get("buy_count_change", 0)
            if buy_change != 0:
                pdf.text_block(f"BUY 등급 분포 변화: {buy_change:+d}건 (시작 vs 끝)")
        else:
            pdf.text_block("Brain 학습 누적 데이터 부족 (Daily 리포트 cron 시작 후 누적)", color=pdf.GRAY)
    except Exception:
        pdf.text_block("Brain 학습 추이 데이터 부족", color=pdf.GRAY)

    # 본인 vs 시스템 적중률 (Quarterly+ 핵심 KPI)
    pdf.subsection_title("2-G. 본인 vs 시스템 적중률")
    try:
        from api.metadata import user_actions
        ua = user_actions.summarize(days=days)
        total = ua.get("total_actions", 0)
        if total > 0:
            pdf.text_block(f"본인 액션 {total}건 / 시스템 일치 {ua['agreement_count']}건 "
                          f"({ua['agreement_rate']}%)")
            disagree_buy = ua.get("user_buy_system_avoid", 0)
            disagree_sell = ua.get("user_sell_system_buy", 0)
            if disagree_buy or disagree_sell:
                pdf.text_block(f"불일치 — 본인 BUY/시스템 AVOID: {disagree_buy}건 · "
                              f"본인 SELL/시스템 BUY: {disagree_sell}건")
        else:
            pdf.text_block("본인 액션 누적 데이터 부족 (검증 정책상 실거래 시 누적)", color=pdf.GRAY)
    except Exception:
        pdf.text_block("user_actions 데이터 부족", color=pdf.GRAY)

    # 백테스트 vs 실거래 갭
    pdf.subsection_title("2-H. 백테스트-실거래 갭")
    try:
        from api.metadata import backtest_gap
        gap = backtest_gap.summarize_gap(days=days)
        if gap.get("samples", 0) > 0:
            pdf.text_block(f"표본 {gap['samples']}건 / 평균 진입 슬리피지 {gap.get('avg_entry_slippage_pct', '-')}% / "
                          f"누적 갭 {gap.get('total_return_gap_pct_sum', 0):+.2f}%")
        else:
            pdf.text_block("백테스트-실거래 갭 데이터 부족 (실거래 또는 시뮬레이션 시 누적)", color=pdf.GRAY)
    except Exception:
        pdf.text_block("backtest_gap 데이터 부족", color=pdf.GRAY)


def _render_chap3_macro(pdf, period, analysis):
    pdf.add_page(); _, label = _TITLES.get(period, ("", ""))
    pdf.chapter_title(3, f"매크로 환경 {label} 리뷰")
    macro = analysis.get("macro", {}) or {}

    pdf.subsection_title(f"3-1. {label} 핵심 지표 변화")
    pdf.metric_row([
        {"label": "VIX 평균", "value": str(macro.get("vix_avg", "-")), "color": pdf.WHITE},
        {"label": "환율 평균", "value": f"{macro.get('usd_krw_avg', '-')}원", "color": pdf.WHITE},
        {"label": "S&P500", "value": f"{macro.get(f'sp500_{period}_pct', macro.get('sp500_weekly_pct', 0)):+.2f}%",
         "color": pdf.GREEN if (macro.get(f'sp500_{period}_pct') or 0) >= 0 else pdf.RED},
        {"label": "코스피", "value": f"{macro.get(f'kospi_{period}_pct', 0):+.2f}%",
         "color": pdf.GREEN if (macro.get(f'kospi_{period}_pct') or 0) >= 0 else pdf.RED},
    ])

    pdf.subsection_title("3-2. 경기 국면 판단")
    regime = macro.get("regime", "데이터 부족")
    pdf.text_block(f"{label} 시작 → 끝 국면: {regime}")


def _render_chap4_sectors(pdf, period, analysis):
    pdf.add_page(); _, label = _TITLES.get(period, ("", ""))
    pdf.chapter_title(4, f"섹터·테마 {label} 총정리")
    sectors = analysis.get("sectors", {}) or {}

    pdf.subsection_title(f"4-1. {label} 섹터 순위")
    for kind, items, c in [("▲", sectors.get("top3_sectors", [])[:3], pdf.GREEN),
                            ("▼", sectors.get("bottom3_sectors", [])[:3], pdf.RED)]:
        pdf._set_font("B", 9); pdf.set_text_color(*c); pdf.set_x(18); pdf.cell(0, 6, kind); pdf.ln(6)
        for s in items:
            pdf._set_font("", 9); pdf.set_text_color(204, 204, 204); pdf.set_x(20)
            pdf.cell(50, 5, _norm_text(s.get("name", "")))
            pdf.cell(0, 5, f"{s.get('change_pct', 0):+.2f}%"); pdf.ln(5)
        pdf.ln(2)

    pdf.subsection_title(f"4-2. {label}을 지배한 테마")
    themes = sectors.get("themes") or analysis.get("themes") or []
    for t in themes[:3]:
        pdf.text_block(f"· {_norm_text(t.get('name', ''))} — {_norm_text(t.get('summary', ''))}")
    if not themes:
        pdf.text_block("테마 분석 데이터 부족", color=pdf.GRAY)


def _render_chap5_stocks(pdf, period, analysis):
    pdf.add_page(); _, label = _TITLES.get(period, ("", ""))
    pdf.chapter_title(5, f"종목 성과 {label} 결산")
    recs = analysis.get("recommendations", {}) or {}

    pdf.subsection_title(f"5-1. 그룹별 성과")
    by_group = recs.get("by_group") or {}
    if by_group:
        for k, v in by_group.items():
            pdf.text_block(f"· {k}: {v}")
    else:
        pdf.text_block("그룹 분해 데이터 부족", color=pdf.GRAY)

    if period == "annual":
        pdf.subsection_title("5-2. Brain 예측 패턴 (연간 도출)")
        patterns = analysis.get("brain_patterns") or {}
        pdf.text_block(f"잘 찾는 종목 패턴: {patterns.get('strong', '데이터 부족')}")
        pdf.text_block(f"놓치는 종목 패턴: {patterns.get('weak', '데이터 부족')}")


def _render_chap6_params(pdf, period, analysis, val_summary):
    pdf.add_page(); _, label = _TITLES.get(period, ("", ""))
    pdf.chapter_title(6, f"시스템 파라미터 {label} 재조정")
    meta = analysis.get("meta_analysis", {}) or {}

    pdf.subsection_title(f"6-1. {label} 효과성 진단")
    pdf.text_block(f"가장 강한 시그널: {meta.get('best_predictor', '-')}")
    pdf.text_block(f"가장 약한 시그널: {meta.get('worst_predictor', '-')}")

    pdf.subsection_title("6-2. 조정 결정")
    pdf.text_block(f"{label} 데이터 기반 — 본인 검토 후 결정")

    if not val_summary.get("validated"):
        pdf._set_font("", 8); pdf.set_text_color(*pdf.YELLOW); pdf.set_x(18)
        pdf.multi_cell(177, pdf.LH_COMPACT,
                       "※ 검증 미완료 — 백테스트 통과 없는 가중치 변경 금지", align="L")


def _render_chap7_constitution(pdf, period):
    """Quarterly+ 전용 — Constitution 개정."""
    pdf.add_page(); _, label = _TITLES.get(period, ("", ""))
    pdf.chapter_title(7, f"Constitution {label} 개정")

    pdf.subsection_title(f"7-1. {label} 운용 결과")
    pdf.text_block(f"각 조항이 {label} 동안 잘 지켜졌는지 점검 (본인 수동 입력 필요)")

    pdf.subsection_title("7-2. 개정 트리거")
    pdf.text_block("· 적중률 50% 미만 N분기 연속")
    pdf.text_block("· 단일 분기 평균 -10% 이하")
    pdf.text_block("· 그 외엔 '유지가 default'")
    pdf._set_font("", 8); pdf.set_text_color(*pdf.YELLOW); pdf.set_x(18)
    pdf.multi_cell(177, pdf.LH_COMPACT,
                   "※ Constitution 개정은 정신을 깨뜨림. 자주 바꾸지 말 것 (continuous_evolution 가드).",
                   align="L")


def _render_chap8_next(pdf, period, val_summary):
    """다음 단위 전략 + 면책."""
    pdf.add_page(); _, label = _TITLES.get(period, ("", ""))
    next_label = {"quarterly": "다음 분기", "semi": "하반기", "annual": "내년"}.get(period, "다음")
    pdf.chapter_title(8, f"{next_label} 전략 방향")

    pdf.subsection_title(f"8-1. {next_label} 매크로 전망")
    pdf.text_block(f"{next_label} 핵심 이벤트 / 기본·리스크·꼬리 시나리오 (LLM 통합 예정)")

    if period == "annual":
        pdf.subsection_title("8-2. 내년 시스템 개발 로드맵")
        pdf.text_block("· 신규 데이터 소스 추가 ≤ 3개")
        pdf.text_block("· AI 모델 변경 ≤ 1회")
        pdf.text_block("· 분기별 마일스톤 (Q1/Q2/Q3/Q4 각각)")
        pdf._set_font("", 8); pdf.set_text_color(*pdf.YELLOW); pdf.set_x(18)
        pdf.multi_cell(177, pdf.LH_COMPACT,
                       "※ 1년 = 부분 cycle. '존재 가치 없음' 결론은 다음 1년 후에 가능", align="L")

    pdf._set_font("", 8); pdf.set_text_color(*pdf.DARK_GRAY); pdf.set_x(15)
    pdf.cell(0, 5, f"검증 상태: {val_summary.get('watermark_label', '')}")


# ─── Public entry ────────────────────────────────────────

def _generate(period: str, analysis: Dict[str, Any], portfolio: Dict[str, Any]) -> str:
    val_summary = validation_status_summary(portfolio.get("vams") or {})
    pdf = VerityPDF(); pdf.add_page()

    _render_cover(pdf, period, analysis, portfolio, val_summary)
    _render_chap1_performance(pdf, period, analysis)
    _render_chap2_system(pdf, period, analysis, portfolio)
    _render_chap3_macro(pdf, period, analysis)
    _render_chap4_sectors(pdf, period, analysis)
    _render_chap5_stocks(pdf, period, analysis)
    _render_chap6_params(pdf, period, analysis, val_summary)
    _render_chap7_constitution(pdf, period)
    _render_chap8_next(pdf, period, val_summary)

    out_dir = os.path.join(DATA_DIR, "reports")
    os.makedirs(out_dir, exist_ok=True)
    fname = f"verity_{period}_admin_{now_kst().strftime('%Y%m%d_%H%M')}.pdf"
    path = os.path.join(out_dir, fname)
    pdf.output(path)
    import shutil
    shutil.copy2(path, os.path.join(out_dir, f"verity_{period}_admin.pdf"))
    return path


def generate_quarterly_admin_pdf(analysis, portfolio): return _generate("quarterly", analysis, portfolio)
def generate_semi_admin_pdf(analysis, portfolio): return _generate("semi", analysis, portfolio)
def generate_annual_admin_pdf(analysis, portfolio): return _generate("annual", analysis, portfolio)
