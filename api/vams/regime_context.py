"""VAMS 게이트 판정에 붙일 국면 맥락 — 기준 변경 아님, **기록 의무**.

## 왜 (PM 승인 2026-08-18)

VAMS 게이트(65거래일 · expectancy ≥0.25R · SQN ≥1.7)는 **절대 기준**이라 국면을 통제하지
않는다. 크립토에서 같은 결함을 확인했다 — 절대 Sharpe 기준이 추세 없는 해에 시스템이
설계대로 방어 중인데도 FAIL 을 냈고, 그래서 게이트를 국면 조건부(v2)로 바꿨다.

주식도 국면 의존이 실측된다 (KR 동일가중 2,874종목 × 1,614일):
**200d MA 위 Sharpe 1.83 vs 아래 −1.03 · 차이 +23.75bp · t=+2.58**

그런데 🚨 **주식 게이트를 국면 조건부로 바꾸지는 않는다.** 지표 선택이 사전등록 대상이고
(후보 3개를 이미 봤다 — 200d MA t=+2.58 / 20일 모멘텀 t=+5.11 / 60일 t=+2.47),
급조하면 크립토 도구를 그대로 옮겨 **잘못된 안심**을 만든다. 실제로 200d MA 는 KR 에서
VAMS 거래창(−14.69%)을 **100% 강세**로 오판했다.

**그래서 이 모듈은 판정을 바꾸지 않는다.** 판정문에 국면을 **병기**해서
"국면 탓" 과 "실력 탓" 을 나중에 분리할 수 있게 남기기만 한다. 소급 불가한 정보이므로
지금 기록을 시작하는 것이 핵심이다(`regime_prediction.py` 와 같은 논리).

상세 = `docs/KR_REGIME_WATCH_ASSESSMENT_2026_08_18.md`

## 🚨 판정에 쓰지 않는 이유를 코드로 강제

반환 dict 는 `advisory_only=True` 를 달고, 어떤 `pass`/`verdict` 키도 만들지 않는다.
소비처가 실수로 게이트에 넣으면 키가 없어 즉시 깨진다.
"""
from __future__ import annotations

import glob
import json
import os
from typing import Any, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHUNKS = os.path.join(_ROOT, "data", "kr_chart_daily", "chunk_*.json")

MOM_SHORT = 20          # 20일 모멘텀 — 후보 중 t 최고(+5.11)이나 **채택 아님**(§4 사전등록 대상)
MA_LONG = 200           # 200d MA — 크립토 방식. KR 에서 실패 사례가 있어 병기만 한다
MIN_TICKERS = 50        # 이보다 적은 날은 시장 수익 계산에서 제외


def _market_series() -> tuple[list[int], list[float]]:
    """동일가중 시장 프록시 일수익. → (날짜, 수익률)

    자체 일봉만 쓴다 — 외부 지수 API 의존을 만들지 않는다.
    250봉 청크라 장기 MA 는 앞부분이 비지만, 게이트 창(65거래일)에는 충분하다.
    """
    per_day: dict[int, dict[str, float]] = {}
    for f in sorted(glob.glob(CHUNKS)):
        try:
            stocks = json.load(open(f)).get("stocks", {})
        except Exception:
            continue
        for tk, v in stocks.items():
            for row in (v.get("c") or []):
                per_day.setdefault(int(row[0]), {})[tk] = float(row[4])
    days = sorted(per_day)
    dates, rets, prev = [], [], {}
    for d in days:
        cur = per_day[d]
        rs = [cur[t] / prev[t] - 1.0 for t in cur if t in prev and prev[t] > 0]
        prev.update(cur)
        if len(rs) >= MIN_TICKERS:
            dates.append(d)
            rets.append(sum(rs) / len(rs))
    return dates, rets


def describe(window_start: Optional[int] = None,
             window_end: Optional[int] = None) -> dict[str, Any]:
    """게이트 창의 국면 맥락. **advisory only — 판정에 쓰지 않는다.**

    Args:
        window_start / window_end: YYYYMMDD. None 이면 전체 보유 구간

    Returns:
        {"advisory_only": True, "market_return_pct", "momentum_weak_ratio",
         "ma200_above_ratio", "note", ...}
        🚨 `pass` · `verdict` 키를 만들지 않는다 — 게이트에 잘못 꽂으면 즉시 깨지도록.
    """
    out: dict[str, Any] = {
        "advisory_only": True,
        "not_a_gate": "판정에 쓰지 않는다. 국면 탓과 실력 탓을 사후 분리하기 위한 기록이다.",
        "source": "자체 일봉 동일가중 프록시 (kr_chart_daily)",
    }
    try:
        dates, rets = _market_series()
    except Exception as e:
        out["error"] = f"시장 프록시 산출 실패: {str(e)[:120]}"
        return out
    if len(dates) < MOM_SHORT + 5:
        out["error"] = f"관측 {len(dates)}일 — 국면 산출 불가"
        return out

    eq, acc = [], 1.0
    for r in rets:
        acc *= (1 + r)
        eq.append(acc)

    lo = window_start or dates[0]
    hi = window_end or dates[-1]
    idx = [i for i, d in enumerate(dates) if lo <= d <= hi]
    if not idx:
        out["error"] = f"창 {lo}~{hi} 에 관측 0일"
        return out

    mkt = 1.0
    for i in idx:
        mkt *= (1 + rets[i])

    weak = ma_above = ma_known = 0
    for i in idx:
        if i >= MOM_SHORT and eq[i] / eq[i - MOM_SHORT] - 1 <= 0:
            weak += 1
        if i >= MA_LONG - 1:
            ma_known += 1
            if eq[i] > sum(eq[i - MA_LONG + 1:i + 1]) / MA_LONG:
                ma_above += 1

    out.update({
        "window": [dates[idx[0]], dates[idx[-1]]],
        "trading_days": len(idx),
        "market_return_pct": round((mkt - 1) * 100, 2),
        "momentum_weak_ratio": round(weak / len(idx) * 100, 1),
        "ma200_above_ratio": (round(ma_above / ma_known * 100, 1) if ma_known else None),
        "ma200_days_known": ma_known,
    })
    out["note"] = (
        f"창 {out['window'][0]}~{out['window'][1]} · 시장 {out['market_return_pct']:+.2f}% · "
        f"{MOM_SHORT}일 모멘텀 약세 {out['momentum_weak_ratio']:.0f}%"
        + (f" · 200d MA 위 {out['ma200_above_ratio']:.0f}%" if out["ma200_above_ratio"] is not None else "")
        + " — 🚨 참고용. 200d MA 는 2026-06~08 창을 100% 강세로 오판한 전력이 있다"
          "(급등 직후 급락을 후행 지표가 못 잡음)."
    )
    return out
