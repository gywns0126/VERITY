"""
채권·ETF 전용 실행 스크립트 (bond_etf_analysis.yml 워크플로우용)
BOND_ETF_MODE 환경변수: bonds / etfs / all
기존 main.py STEP 1.55와 동일 로직을 독립 실행 가능하도록 분리.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api.config import now_kst
from api.vams.engine import load_portfolio, save_portfolio

MODE = os.environ.get("BOND_ETF_MODE", "all").strip().lower()


def _run_bonds(portfolio: dict) -> dict:
    """채권 수집 + 분석."""
    from api.collectors.yieldcurve import get_full_yield_curve_data
    from api.analyzers.bondanalyzer import run_bond_analysis

    print("[BOND] 수익률 곡선 + 신용 스프레드 수집 시작")
    bonds_raw = get_full_yield_curve_data()
    portfolio["bonds"] = bonds_raw

    yc = bonds_raw.get("yield_curves", {})
    kr_shape = yc.get("kr", {}).get("curve_shape", "-")
    us_shape = yc.get("us", {}).get("curve_shape", "-")
    n_alerts = len(bonds_raw.get("inversion_alerts", []))
    print(f"[BOND] 수익률 곡선: KR={kr_shape} / US={us_shape} | 역전 경보: {n_alerts}건")

    print("[BOND] 채권 분석 실행")
    analysis = run_bond_analysis(bonds_raw)
    portfolio.setdefault("bond_analysis", {})
    portfolio["bond_analysis"] = analysis
    regime = analysis.get("bond_regime", {})
    print(f"[BOND] regime: {json.dumps(regime, ensure_ascii=False)}")

    return {
        "kr_shape": kr_shape,
        "us_shape": us_shape,
        "n_alerts": n_alerts,
        "regime": regime,
    }


def _run_etfs(portfolio: dict) -> dict:
    """ETF 수집 + 스크리닝."""
    from api.collectors.etfdata import get_top_etf_summary
    from api.collectors.etfus import get_us_etf_summary, get_bond_etf_summary
    from api.analyzers.etfscreener import run_full_etf_screening

    print("[ETF] KR ETF 수집 시작")
    kr_etfs = get_top_etf_summary()
    print(f"[ETF] KR ETF: {len(kr_etfs)}개")

    print("[ETF] US ETF 수집 시작")
    us_etfs = get_us_etf_summary()
    print(f"[ETF] US ETF: {len(us_etfs)}개")

    print("[ETF] 채권 ETF 수집 시작")
    bond_etfs = get_bond_etf_summary()
    print(f"[ETF] 채권 ETF: {len(bond_etfs)}개")

    ts = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")

    print("[ETF] 멀티팩터 스크리닝 실행")
    screening = run_full_etf_screening(kr_etfs, us_etfs + bond_etfs)
    portfolio["etf_screening"] = screening

    top20 = screening.get("overall_top20", [])

    all_etfs_simple = sorted(
        [*kr_etfs, *us_etfs, *bond_etfs],
        key=lambda e: abs(e.get("return_1m", 0) or 0),
        reverse=True,
    )
    portfolio["etfs"] = {
        "kr_top": kr_etfs,
        "us_top": us_etfs,
        "us_bond": bond_etfs,
        "overall_top20": top20 if top20 else all_etfs_simple[:20],
        "updated_at": ts,
    }
    print(f"[ETF] 스크리닝 완료: TOP 20 = {len(top20)}개")

    return {
        "kr_count": len(kr_etfs),
        "us_count": len(us_etfs),
        "bond_count": len(bond_etfs),
        "top3": top20[:3],
    }


def _send_summary(mode: str, bond_result: dict, etf_result: dict, status: str):
    """텔레그램 요약 전송."""
    try:
        from api.notifications.telegram import send_message
    except ImportError:
        print("[Telegram] 알림 모듈 임포트 실패 — 스킵")
        return

    emoji = "✅" if status == "success" else "❌"
    ts = now_kst().strftime("%m/%d %H:%M")
    lines = [f"{emoji} <b>VERITY 채권·ETF 업데이트</b>", f"⏰ {ts} KST\n"]

    if bond_result and mode in ("bonds", "all"):
        shape_map = {"normal": "📈", "flat": "➡️", "inverted": "🔴", "humped": "🔶"}
        us_shape = bond_result.get("us_shape", "-")
        kr_shape = bond_result.get("kr_shape", "-")
        us_emoji = shape_map.get(us_shape, "❓")
        lines.append("🏦 <b>채권 시황</b>")
        lines.append(f"  미국 곡선: {us_emoji} {us_shape}")
        lines.append(f"  한국 곡선: {kr_shape}")
        n_alerts = bond_result.get("n_alerts", 0)
        if n_alerts > 0:
            lines.append(f"  ⚠️ 역전 경보 {n_alerts}건")

    if etf_result and mode in ("etfs", "all"):
        lines.append("")
        lines.append("📊 <b>ETF 스크리닝</b>")
        lines.append(
            f"  KR {etf_result.get('kr_count', 0)}개 / "
            f"US {etf_result.get('us_count', 0)}개 / "
            f"채권 {etf_result.get('bond_count', 0)}개"
        )
        top3 = etf_result.get("top3", [])
        for e in top3:
            score = e.get("verity_etf_score", 0)
            ticker = e.get("ticker", "?")
            signal = e.get("signal", "")
            lines.append(f"  {ticker} {signal} ({score:.0f}점)")

    msg = "\n".join(lines)
    send_message(msg)


def main():
    print(f"{'='*50}")
    print(f"[run_bond_etf] 모드: {MODE} | {now_kst().isoformat()}")
    print(f"{'='*50}")

    portfolio = load_portfolio()
    bond_result = {}
    etf_result = {}
    status = "success"

    try:
        if MODE in ("bonds", "all"):
            bond_result = _run_bonds(portfolio)

        if MODE in ("etfs", "all"):
            etf_result = _run_etfs(portfolio)

        save_portfolio(portfolio)
        print(f"\n[run_bond_etf] portfolio.json 저장 완료")

    except Exception as e:
        status = "failure"
        print(f"\n[run_bond_etf] 오류 발생: {e}")
        traceback.print_exc()
        save_portfolio(portfolio)

    _send_summary(MODE, bond_result, etf_result, status)
    print(f"\n[run_bond_etf] 완료 (status={status})")

    if status != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()
