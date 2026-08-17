"""fx_hedge_regime — FX 헤지 레짐 게이트 + 달러 노출 상한. 2026-08-11 PM 승인.

사전등록 `docs/PREREG_FX_HEDGE_REGIME_2026_08_11.md` (v2). 요약:

  레짐   USDKRW < 1,391 → OFF(목표 0) · ≥ 1,509 → ON · 사이 = 데드밴드(직전 상태 유지)
         임계 1,450 = verity_brain 원화 페널티(PM 7/8 승인) 재사용 · 밴드 = ±60일 실현 1σ(4.08%)
  크기   ON 일 때 목표 = max(0, 0.30 × 총자산 − USD 주식 평가액)  — §1-3 "헤지 사이징 후
         같은 방향 자산이 얹혀 42.7%" 구멍을 닫는다
  재산출 트리거 = ① 레짐 전환 ② USD 종목 진입/청산 ③ 월말 ④ 최초 1회(등록 §3 즉시 축소).
         그 사이 드리프트는 방치 — 연속 추적은 USD 회전(14일)마다 매매를 강제하고,
         허용밴드 %p 신설은 근거 없는 파라미터라 기각(등록 §2-2)

🚨 판정·조정만 한다. 예측하지 않는다 — 코드베이스에 FX 전망 함수는 0건이다(등록 §1-1).
🚨 부분 축소는 **멱등** — 최초 축소는 고정 op id 로 1회만, 이후는 조정 후 목표=현재라
   자연 수렴. 과거 리저브 진입이 비-영속 run 에 소비돼 유실된 사고 경로 재발 방지(등록 §7).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

# ── 등록값 (사전등록 §2-1 v2 정정 반영: 하단 1,391) ──────────────────────────
BAND_LO = 1391.0
BAND_HI = 1509.0
TARGET_RATIO = 0.30
PREREG = "docs/PREREG_FX_HEDGE_REGIME_2026_08_11.md"
INITIAL_OP_ID = "fx_hedge_prereg_20260811_initial"
# 초기 상태 = ON (등록 §2-1 backcast — 마지막 결정적 신호 = 2026-07 초 ≥1,509, 이후 <1,391 관측 0)
INITIAL_STATE = "ON"
# 🚨 2026-08-17 — env 우회 신설. 이게 없어서 테스트가 **운영 원장에 실제로 append** 했다
#   (스위트 1회당 동일 fx_hedge_regime 이벤트 6행, 전부 같은 초). telegram 통수 원장과
#   같은 클래스이며 처방도 같다. `stoploss_watch.RULE_LOG_PATH` 도 같은 변수를 읽는다.
RULE_LOG_PATH = os.environ.get("VERITY_RULE_LOG_PATH") or os.path.join(
    DATA_DIR, "metadata", "rule_change_log.jsonl")


def _usd_stock_value(v: Dict[str, Any]) -> float:
    """USD 보유 평가액 합 (current_price 는 KRW 환산 저장 — 2026-08-06 통화 정규화 후)."""
    return sum(
        float(h.get("current_price") or 0) * float(h.get("quantity") or 0)
        for h in (v.get("holdings") or [])
        if h.get("currency") == "USD"
    )


def _usd_ticker_set(v: Dict[str, Any]) -> List[str]:
    return sorted({str(h.get("ticker")) for h in (v.get("holdings") or [])
                   if h.get("currency") == "USD"})


def _append_rule_log(entry: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(RULE_LOG_PATH), exist_ok=True)
        with open(RULE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 로그 실패가 규칙 적용을 막지 않는다 (적용 사실은 ops 에 남는다)


def _reduce(v: Dict[str, Any], amount: float, fx: float) -> Dict[str, Any]:
    """리저브 → 현금. 총자산 불변. 실현분은 리저브 로컬 누계로만 기록한다
    (total_realized_pnl 은 종목 청산 통계라 정의를 섞지 않는다)."""
    r = v["fx_hedge_reserve"]
    cur = float(r.get("current_krw") or 0)
    amount = min(amount, cur)
    if amount <= 0 or cur <= 0:
        return {"moved": 0.0}
    f = amount / cur
    realized = round(f * float(r.get("pnl_krw") or 0), 2)
    r["usd_value"] = float(r["usd_value"]) * (1 - f)
    r["krw_invested"] = round(float(r["krw_invested"]) * (1 - f), 2)
    r["current_krw"] = round(cur - amount, 2)
    r["pnl_krw"] = round(r["current_krw"] - r["krw_invested"], 2)
    r["realized_pnl_cum"] = round(float(r.get("realized_pnl_cum") or 0) + realized, 2)
    v["cash"] = float(v.get("cash") or 0) + amount
    if r["current_krw"] <= 1:          # 전량 청산 — 재진입은 enter_fx_hedge 경로 재사용
        v["fx_hedge_reserve_closed"] = r
        v["fx_hedge_reserve"] = None
    return {"moved": round(amount, 2), "realized": realized}


def _increase(v: Dict[str, Any], amount: float, fx: float) -> Dict[str, Any]:
    """현금 → 리저브. 가용 현금 한도 내에서만 — 우선순위 파라미터를 새로 만들지 않는다."""
    cash = float(v.get("cash") or 0)
    amount = min(amount, max(0.0, cash))
    if amount <= 0:
        return {"moved": 0.0}
    r = v.get("fx_hedge_reserve")
    if not r:
        # 🚨 재진입 종목은 **청산 기록에서 승계**한다. 하드코딩하면 원 헤지와 다른 상품으로
        #    조용히 갈아탈 수 있다. 승계할 기록이 없으면 진입하지 않고 결손으로 신고한다.
        closed = v.get("fx_hedge_reserve_closed") or {}
        tk, nm = closed.get("ticker"), closed.get("name")
        if not tk or not nm:
            return {"moved": 0.0, "skip": "재진입 종목 미상 (청산 기록 부재) — 수동 진입 필요"}
        from api.vams.engine import enter_fx_hedge  # 지연 import — 순환 방지
        res = enter_fx_hedge(
            {"vams": v}, krw_amount=amount, usdkrw=fx, ticker=str(tk), name=str(nm),
            reason=f"레짐 ON 목표 미달 보충 ({PREREG})")
        return {"moved": (round(amount, 2) if res.get("ok") else 0.0)}
    r["usd_value"] = float(r["usd_value"]) + amount / fx
    r["krw_invested"] = round(float(r["krw_invested"]) + amount, 2)
    r["current_krw"] = round(float(r.get("current_krw") or 0) + amount, 2)
    r["pnl_krw"] = round(r["current_krw"] - r["krw_invested"], 2)
    v["cash"] = cash - amount
    return {"moved": round(amount, 2)}


def run(portfolio: Dict[str, Any], fx: float) -> Dict[str, Any]:
    """레짐 판정 + 트리거 시 목표 재산출·조정. 사이클마다 호출되며 조정은 트리거에서만."""
    v = portfolio.get("vams") or {}
    if fx <= 0:
        return {"status": "skip", "reason": f"fx {fx} 비정상"}

    st = v.setdefault("fx_hedge_regime", {
        "state": INITIAL_STATE, "band": [BAND_LO, BAND_HI], "target_ratio": TARGET_RATIO,
        "prereg": PREREG, "ops": [], "last": {},
    })
    prev = str(st.get("state") or INITIAL_STATE)
    state = "OFF" if fx < BAND_LO else ("ON" if fx >= BAND_HI else prev)

    now = now_kst()
    month = now.strftime("%Y-%m")
    usd_set = _usd_ticker_set(v)
    last = st.get("last") or {}
    op_ids = {o.get("id") for o in (st.get("ops") or [])}

    triggers = []
    if state != prev:
        triggers.append(f"regime_{prev}→{state}")
    if usd_set != (last.get("usd_set") or []):
        triggers.append("usd_holdings_change")
    if month != last.get("month"):
        triggers.append("month_end")
    if INITIAL_OP_ID not in op_ids:
        triggers.append("initial")

    st["state"] = state
    st["last"] = {"fx": round(fx, 2), "month": month, "usd_set": usd_set,
                  "at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00")}
    if not triggers:
        return {"status": "hold", "state": state, "fx": round(fx, 2)}

    total = float(v.get("total_asset") or 0)
    usd_val = _usd_stock_value(v)
    reserve = v.get("fx_hedge_reserve") or {}
    cur = float(reserve.get("current_krw") or 0)
    target = 0.0 if state == "OFF" else max(0.0, TARGET_RATIO * total - usd_val)

    action: Dict[str, Any] = {"moved": 0.0}
    kind = "none"
    if cur - target > 1:
        action = _reduce(v, cur - target, fx)
        kind = "reduce"
    elif target - cur > 1 and state == "ON":
        action = _increase(v, target - cur, fx)
        kind = "increase"

    op = {
        "id": (INITIAL_OP_ID if "initial" in triggers
               else f"fx_hedge_{now.strftime('%Y%m%d_%H%M%S')}"),
        "at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "triggers": triggers, "state": state, "fx": round(fx, 2),
        "total_asset": round(total), "usd_stock_krw": round(usd_val),
        "reserve_before": round(cur), "target": round(target),
        "kind": kind, **{k: vv for k, vv in action.items()},
    }
    st.setdefault("ops", []).append(op)

    if "initial" in triggers:
        _append_rule_log({
            "at": op["at"], "rule": "fx_hedge_regime",
            "from": "규칙 없음 (진입 사유에 해제조건 부재 · 달러 연동 42.7%)",
            "to": f"게이트 {BAND_LO:.0f}/{BAND_HI:.0f} + 달러 연동 상한 {TARGET_RATIO:.0%}",
            "prereg": PREREG, "initial_op": op,
        })
    return {"status": "adjusted" if action.get("moved") else "evaluated",
            "state": state, "op": op}
