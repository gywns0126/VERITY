"""trend_overlay — 200일선 추세 게이트 (A1, SHADOW 꼬리리스크 오버레이).

목적 (2026-06-15): 지수 종가가 200일 이동평균 아래면 "방어(현금)", 위면 "위험노출"로
판정하는 Faber GTAA 게이트. 약세장 풀노출 누수를 줄이는 **꼬리리스크 감축 오버레이**.

🚨 포지셔닝 (적대적 검증 2026-06-14): "MDD 약세장 방어"는 다출처 confirmed(Faber 2007 +
   독립 백테스트), 그러나 **"CAGR 동일한 공짜 알파"는 out-of-sample 소멸**(STW 1999 /
   Faber GTAA 11년중 8년 언더퍼폼). 따라서 이건 "공짜 알파"가 아니라 **MDD 감축 오버레이**다.
   whipsaw turnover 비용 실재(2011/2015/2016/2020). KR 양도세 0% 는 거래세만 0(~2029).
🚨 SHADOW ONLY — 실 포트폴리오 노출 변경 0. shadow_exposure 필드 기록만. brain-input 0.
🚨 TARGET 지수 미확정 (PM 승인 사항): KOSPI(^KS11) vs S&P500(^GSPC) 둘 다 로깅 →
   어느 시장 게이트가 우월한지 N 누적 후 PM 결정.

산식 prior (그리드서치 금지 — RULE 7): lookback=200(Faber 강제), 일별 모니터 + 월말 신호
플래그(Faber 원전), binary 게이트. N-게이트: regime 전환 연 2~6회 → forward-only N≥252
도달에 수십 년 → wire 는 B4(부분 backtest + 라이브 N Bayesian) 병행 필수 ([[project_verity_backtest_sprint]]).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

SHADOW_OUT = os.path.join(DATA_DIR, "metadata", "trend_overlay_prediction_trail.jsonl")

# target 지수 — 둘 다 로깅, PM 이 N 누적 후 선택.
_INDICES = [
    {"key": "kospi", "yf": "^KS11"},
    {"key": "sp500", "yf": "^GSPC"},
]
_SMA_WINDOW = 200   # Faber 강제 (그리드서치 금지)


def _fetch_closes(yf_ticker: str) -> Optional[List[float]]:
    """지수 일별 종가 리스트 (오래→최근). 기존 yfinance safe 헬퍼 재사용."""
    try:
        import yfinance as yf
        from api.collectors.yfinance_safe import safe_yf_call

        t = yf.Ticker(yf_ticker)
        # 200일 SMA + 마진 → 14개월(~290 거래일)
        hist = safe_yf_call(lambda: t.history(period="14mo"), label=f"{yf_ticker}.history(14mo)")
        if hist is None or hist.empty:
            return None
        closes = hist.dropna(subset=["Close"])["Close"].tolist()
        return [float(c) for c in closes] if closes else None
    except Exception:
        return None


def _gate_state(closes: List[float]) -> Dict[str, Any]:
    """현재 종가 vs 200일 SMA → 게이트 판정."""
    if len(closes) < _SMA_WINDOW:
        return {"status": "insufficient", "have": len(closes), "need": _SMA_WINDOW}
    sma = sum(closes[-_SMA_WINDOW:]) / _SMA_WINDOW
    cur = closes[-1]
    above = cur >= sma
    return {
        "status": "ok",
        "close": round(cur, 2),
        "sma200": round(sma, 2),
        "gap_pct": round(100.0 * (cur - sma) / sma, 2),
        "gate": "risk_on" if above else "defensive",
        # shadow_exposure: 게이트가 함의하는 주식노출(binary). 실 포트 미반영 — 기록만.
        "shadow_equity_exposure": 1.0 if above else 0.0,
    }


def _is_month_end_signal() -> bool:
    """Faber 원전 = 월말 종가 신호. 오늘이 이번 달 마지막 영업일 근처(말일 -2)인지."""
    d = now_kst().date()
    # 다음달 1일 - 오늘 <= 3일 이고 평일이면 월말 신호로 간주 (영업일 근사)
    import calendar
    last_day = calendar.monthrange(d.year, d.month)[1]
    return (last_day - d.day) <= 2


def compute_overlay() -> Dict[str, Any]:
    """지수별 200MA 게이트 (SHADOW). brain 미입력."""
    is_month_end = _is_month_end_signal()
    per_index: Dict[str, Any] = {}
    for idx in _INDICES:
        closes = _fetch_closes(idx["yf"])
        if not closes:
            per_index[idx["key"]] = {"status": "fetch_fail", "yf": idx["yf"]}
            continue
        per_index[idx["key"]] = {**_gate_state(closes), "yf": idx["yf"]}
    return {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "is_month_end_signal": is_month_end,
        "indices": per_index,
        "caveat": ("SHADOW 꼬리리스크 오버레이. '공짜 알파' 아님(OOS 소멸)=MDD 감축 only. "
                   "target 지수 PM 미확정(둘 다 로깅). brain-input 0. wire=N>=252+B4 backtest 병행."),
    }


def run_shadow() -> Dict[str, Any]:
    """게이트 산출 → trend_overlay_prediction_trail.jsonl 적재(brain 무입력) → 반환."""
    result = compute_overlay()
    entry = {
        "ts_kst": now_kst().isoformat(),
        "shadow": True,
        "brain_input": False,
        "is_month_end_signal": result["is_month_end_signal"],
        "gates": {
            k: {"gate": v.get("gate"), "gap_pct": v.get("gap_pct"),
                "shadow_equity_exposure": v.get("shadow_equity_exposure")}
            for k, v in result["indices"].items() if v.get("status") == "ok"
        },
        "caveat": result["caveat"],
    }
    try:
        os.makedirs(os.path.dirname(SHADOW_OUT), exist_ok=True)
        with open(SHADOW_OUT, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return result


if __name__ == "__main__":
    r = run_shadow()
    print(f"[trend_overlay] SHADOW (월말신호={r['is_month_end_signal']})")
    print(f"  ⚠ {r['caveat']}")
    for k, v in r["indices"].items():
        if v.get("status") == "ok":
            print(f"  {k:6} {v['gate']:10} close={v['close']} sma200={v['sma200']} "
                  f"gap={v['gap_pct']:+.1f}% exposure={v['shadow_equity_exposure']}")
        else:
            print(f"  {k:6} {v.get('status')} ({v.get('yf')})")
