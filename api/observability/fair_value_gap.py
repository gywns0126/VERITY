"""
fair_value_gap — 내재가치 괴리 관측 (RIM V/P + reverse-DCF implied-g). 관측 ONLY, 점수 wire 0.

2026-06-17 사전등록(PM 발의, 세무서 친구 "재무숫자로 향후 주가" 아이디어를 규율 흡수).
SoT = memory project_observation_scoring_prereg_queue (C-fv). RULE 7 — 점수화는 검증(~2028-29,
지평 2-3년 forward IC) 통과 후 PM 승인+단일조정. 지금은 관측 누적만.

신호1 = RIM V/P (Frankel-Lee 1998, 문헌상 유일 검증된 fair-value factor):
    V = BV + RI·ω/(1+r_e−ω),  RI = NI − r_e·BV  (Ohlson 지속성 ω=0.62, Dechow-Hutton-Sloan)
    V/P = V / 시총.  >1 저평가, <1 고평가.  ROE<r_e ⇒ V<BV ⇒ value_trap 후보(저PBR≠쌈).
신호2 = implied-g (reverse DCF, Mauboussin "기대 관측"=목표주가 아님): fcf_yield 있을 때만.

🚨 정합성 가드: stale ratio 필드(pbr/per) 신뢰 불가(클래시스 pbr 1.0 vs 역산 5.2) →
   raw 대차대조표(total_assets·debt_ratio[=D/E]·net_income·market_cap)에서 self-consistent 산출.
🚨 한계(자료 Q4): 1-stage RIM 은 고성장 기업 저평가(터미널 성장 미반영) → is_high_growth 플래그.
   재평가잉여금 BV 과대 가능(K-IFRS) — v0 미보정, 로그에 명시. 지주사는 group_structure SOTP 가 적합.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

OBS_DIR = os.path.join(DATA_DIR, "observations")
FVG_PATH = os.path.join(OBS_DIR, "fair_value_gap.jsonl")

# 자기자본비용 r_e — KR hurdle (rf ~3.2% + ERP ~5.3%). v0 상수, β·CAPM 정밀화는 검증 단계.
R_E_DEFAULT = 0.085
# Ohlson 잔여이익 지속성 ω (Dechow-Hutton-Sloan 1999 실증 ~0.62). 1년 RI 가 ω 비율로 감쇠.
OMEGA = 0.62


def rim_value(bv: float, earnings: float, r_e: float = R_E_DEFAULT, omega: float = OMEGA) -> float:
    """1-stage 잔여이익모형(RIM, Frankel-Lee 1998) 내재가치. 산식 단일 출처.

    V = BV + RI·ω/(1+r_e−ω),  RI = earnings − r_e·BV.
    **scale-invariant** — 총액(equity, NI) 또는 주당(BVPS, EPS) 어느 입력이든 동일 결과
    → KR(총액, fair_value_gap) 와 US(주당, fair_value_gap_us) 가 이 함수를 공유(drift 0).
    denom≤0(r_e≤ω−1, 비현실) 시 BV 로 폴백.
    """
    ri = earnings - r_e * bv
    denom = 1.0 + r_e - omega
    return bv + ri * (omega / denom) if denom > 0 else bv


def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
        return x if x == x else None  # NaN 제거
    except (TypeError, ValueError):
        return None


def _compute_one(stock: Dict[str, Any], r_e: float = R_E_DEFAULT) -> Optional[Dict[str, Any]]:
    """단일 종목 RIM V/P + implied-g + 가드. 입력 부족/비정합 시 None."""
    ta = _f(stock.get("total_assets"))
    mc = _f(stock.get("market_cap"))
    ni = _f(stock.get("net_income"))
    de_pct = _f(stock.get("debt_ratio"))  # D/E (%) — 한국 관례
    if not ta or ta <= 0 or not mc or mc <= 0 or ni is None or de_pct is None:
        return None

    # self-consistent equity = TA/(1+D/E). stale pbr/roe 필드 미사용.
    equity = ta / (1 + de_pct / 100.0)
    if equity <= 0:
        return None
    roe_frac = ni / equity  # raw 기반 ROE (스냅샷 stale roe 대신)

    # RIM V = BV + RI·ω/denom (공용 rim_value, scale-invariant). 로컬명 rim_v = 헬퍼와 구분.
    rim_v = rim_value(equity, ni, r_e)
    v_over_p = rim_v / mc

    # 신호2: implied perpetual FCF 성장 (fcf_yield 있을 때만). g=(r_e−fy)/(1+fy).
    fy = _f(stock.get("fcf_yield"))
    if fy is None:
        fcf = _f(stock.get("fcf"))
        fy = (fcf / mc) if (fcf is not None and mc > 0) else None
    implied_g = ((r_e - fy) / (1 + fy)) if fy is not None else None

    gs = stock.get("group_structure")
    is_holdco = bool(gs and (gs.get("subsidiaries") or gs.get("nav_analysis", {}).get("sum_of_parts_억")))
    qf = (stock.get("multi_factor") or {}).get("quant_factors") or {}

    return {
        "ticker": str(stock.get("ticker", "")),
        "name": stock.get("name", ""),
        "equity": round(equity, 0),
        "market_cap": round(mc, 0),
        "roe_frac": round(roe_frac, 4),
        "r_e": r_e,
        "rim_v_over_p": round(v_over_p, 3),           # >1 저평가, <1 고평가
        "pbr_derived": round(mc / equity, 2),         # stale 필드 대신 역산
        "implied_g": round(implied_g, 4) if implied_g is not None else None,
        "value_trap_candidate": roe_frac < r_e,       # ROE<r_e ⇒ V<BV (저PBR≠쌈)
        "is_high_growth": roe_frac > 0.20,            # 1-stage RIM 저평가 가능(터미널 미반영)
        "is_holdco": is_holdco,                       # RIM 부적합·SOTP 적합 플래그
        "f_score": _f(qf.get("fscore") or qf.get("f_score")),  # joint value-trap 필터용(검증 단계)
    }


def _append(rec: Dict[str, Any], target: str) -> bool:
    """1일 1스냅샷 append (date dedupe)."""
    os.makedirs(os.path.dirname(target), exist_ok=True)
    try:
        with open(target, encoding="utf-8") as fh:
            seen = {json.loads(line).get("date") for line in fh if line.strip()}
        if rec["date"] in seen:
            return False
    except OSError:
        pass
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return True


def run_fair_value_gap_observation(
    candidates: List[Dict[str, Any]],
    r_e: float = R_E_DEFAULT,
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """후보 종목 RIM V/P + implied-g 1스냅샷 관측 append. 점수 wire 0. graceful."""
    target = path or FVG_PATH
    now = now_kst()
    per: Dict[str, Dict[str, Any]] = {}
    for stk in (candidates or []):
        try:
            rec = _compute_one(stk, r_e)
        except Exception as e:  # noqa: BLE001
            logger.warning("fair_value_gap %s 실패: %s", stk.get("ticker"), e)
            rec = None
        if rec and rec["ticker"]:
            per[rec["ticker"]] = rec

    if not per:
        return {"tickers": 0, "logged": False}

    n_under = sum(1 for v in per.values() if v["rim_v_over_p"] > 1)
    n_trap = sum(1 for v in per.values() if v["value_trap_candidate"])
    snapshot = {
        "observed_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "date": now.strftime("%Y-%m-%d"),
        "n_tickers": len(per),
        "n_undervalued_vp_gt_1": n_under,
        "n_value_trap_candidate": n_trap,
        "r_e": r_e,
        "per_ticker": per,
        "spec": "fair_value_gap_v0_observation",
        "_note": ("관측 only, 점수 wire 0. RIM V/P(Frankel-Lee)+implied-g(Mauboussin). "
                  "검증 = 1/2/3년 forward IC(2-3년 핵심), 생존편향 없는 universe, ~2028-29. "
                  "raw 대차대조표 self-consistent 산출(stale pbr/per 미사용). RULE 7 — 점수화는 "
                  "검증 후 사전등록+PM승인+단일조정."),
    }
    logged = _append(snapshot, target)
    return {
        "tickers": len(per),
        "undervalued": n_under,
        "value_trap_candidate": n_trap,
        "logged": logged,
    }
