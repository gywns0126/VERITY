"""
월간 검증 리포트 — 매월 1일 텔레그램 발송.

대시보드 안 보는 날에도 누적 지표를 강제로 보게 하는 장치. 3·6·12개월 체크포인트를
놓치지 않는 것이 목적.

입력: portfolio.vams.validation_report + portfolio.vams.adjusted_performance
출력: 텔레그램 메시지 1개 (HTML 미사용 plaintext)

main.py 호출 시점: 매월 1일 16:00 KST 파이프라인 실행 시 자동 (별도 cron 불필요).
"""
from __future__ import annotations

from typing import Optional

from api.notifications.telegram import send_message


_VERDICT_EMOJI = {
    "PASS": "✅",
    "WATCH": "🟡",
    "FAIL": "🔴",
    "INSUFFICIENT_DATA": "⏳",
}


def _fmt_pct(n, digits: int = 2) -> str:
    if n is None:
        return "—"
    try:
        v = float(n)
    except (TypeError, ValueError):
        return "—"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.{digits}f}%"


def _fmt_pp(n, digits: int = 2) -> str:
    s = _fmt_pct(n, digits)
    return s.replace("%", "%p") if s != "—" else "—"


def _fmt_ratio(n, digits: int = 2) -> str:
    if n is None:
        return "—"
    try:
        return f"{float(n):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _pass_mark(p) -> str:
    if p is True:
        return "✓"
    if p is False:
        return "✗"
    return "—"


def build_report(portfolio: dict) -> Optional[str]:
    """validation_report + adjusted_performance 를 텍스트로 포맷.
    둘 다 없으면 None 반환 (발송 생략용)."""
    vams = (portfolio or {}).get("vams", {}) or {}
    vr = vams.get("validation_report")
    adj = vams.get("adjusted_performance")
    if not vr and not adj:
        return None

    lines = ["📊 <b>VAMS 월간 검증 리포트</b>"]

    # Overall verdict
    if vr:
        overall = vr.get("overall", "INSUFFICIENT_DATA")
        emoji = _VERDICT_EMOJI.get(overall, "⏳")
        window = vr.get("window", {}) or {}
        days = window.get("days", 0)
        start = window.get("validation_start_configured") or window.get("start") or "?"
        lines.append(f"{emoji} <b>{overall}</b> · D+{days} · since {start}")

    # 보정 수익률 요약
    if adj:
        raw = adj.get("raw_return_pct")
        adjusted = adj.get("adjusted_return_pct")
        gap = adj.get("gap_pp")
        lines.append("")
        lines.append("<b>수익률 (보정 전/후)</b>")
        lines.append(f"  원       {_fmt_pct(raw)}")
        lines.append(f"  보정     {_fmt_pct(adjusted)}  (비용 {_fmt_pp(gap)})")

    # 지표 현황
    if vr:
        m = vr.get("metrics", {}) or {}
        lines.append("")
        lines.append("<b>지표 (통과 여부)</b>")

        mr = m.get("cumulative_return", {})
        lines.append(f"  {_pass_mark(mr.get('pass'))} 누적수익   {_fmt_pct(mr.get('vams_return_pct'))} vs KOSPI {_fmt_pct(mr.get('benchmark_return_pct'))}  (α {_fmt_pp(mr.get('excess_pp'))})")

        mm = m.get("mdd", {})
        lines.append(f"  {_pass_mark(mm.get('pass'))} MDD비율    {_fmt_ratio(mm.get('ratio'))} (VAMS {_fmt_pct(mm.get('vams_mdd_pct'))} / 벤치 {_fmt_pct(mm.get('benchmark_mdd_pct'))})")

        mw = m.get("win_rate", {})
        wr = mw.get("win_rate")
        wr_pct = f"{wr*100:.1f}%" if wr is not None else "—"
        lines.append(f"  {_pass_mark(mw.get('pass'))} 승률       {wr_pct}  ({mw.get('wins', 0)}승 {mw.get('losses', 0)}패 / {mw.get('trades', 0)}건)")

        mp = m.get("profit_loss_ratio", {})
        lines.append(f"  {_pass_mark(mp.get('pass'))} 손익비     {_fmt_ratio(mp.get('pl_ratio'))}")

        ms = m.get("sharpe", {})
        lines.append(f"  {_pass_mark(ms.get('pass'))} 샤프(연율) {_fmt_ratio(ms.get('annualized'))}  ({ms.get('verdict', '—')})")

        mg = m.get("regime_coverage", {})
        rc_label = "covered" if mg.get("covered") else "not yet"
        lines.append(f"  {_pass_mark(mg.get('pass'))} 레짐커버   {rc_label}  (벤치MDD {_fmt_pct(mg.get('peak_drawdown_pct'))})")

        mc = m.get("cost_efficiency", {})
        lines.append(f"  {_pass_mark(mc.get('pass'))} 비용/α     {_fmt_ratio(mc.get('cost_to_alpha_ratio'))}  (gap {_fmt_pp(mc.get('gap_pp_total'))} / α {_fmt_pp(mc.get('alpha_pp'))})")

        # 샘플 체크
        sc = vr.get("sample_checks", {}) or {}
        lines.append("")
        lines.append("<b>샘플</b>")
        lines.append(f"  거래일 {window.get('days', 0)}/{sc.get('days_required', 60)}  매매 {mw.get('trades', 0)}/{sc.get('trades_required', 20)}")

    lines.append("")
    lines.append("<i>※ 판정 기준 변경은 git 커밋으로 이력. 결과 후 기준 조정 금지.</i>")
    return "\n".join(lines)


def send_monthly_report(portfolio: dict, dedupe: bool = True) -> bool:
    """월간 리포트 생성 + 전송. 리포트 비어 있으면 False 반환."""
    text = build_report(portfolio)
    if not text:
        print("[monthly_validation] validation_report/adjusted_performance 없음 — 스킵")
        return False
    return send_message(text, dedupe=dedupe)
