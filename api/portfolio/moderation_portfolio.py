"""중용(中庸) 포트폴리오 빌더 — 구성 척추 (#4).

사전등록 = docs/PREREG_MODERATION_PORTFOLIO_2026_08_01.md (private repo · 등록본이 권위).
PM 승인: 방향 2026-08-01 · 상수 2026-08-02. RULE 7: 상수 동결 — 조정 = 신규 사전등록.

🚨 2026-08-02 자기 정정: 최초 구현이 메모리 재구성 E-룰(낙폭·과열·규모)을 사용 — 등록본과 상이
(특히 "낙폭 최심 배제"는 등록본의 "하위 극단 배제 금지" 원칙과 충돌). 본 판 = 등록본 E1~E4 그대로.

등록 3층:
  Layer1 극단 배제 — 당일 후보 풀 내 상대 10분위, 비대칭(근거 있는 쪽만):
    E1 = PBR 하위 분위 AND (F-Score<=2 OR ROE<0)      — Piotroski 2000 (밸류트랩)
    E2 = 6M 수익률 상위 분위 AND 시장 패닉 상태          — Daniel-Moskowitz 2016 (승자 크래시)
    E3 = volatility_60d 상위 분위                        — Ang et al. 2006 · Frazzini-Pedersen 2014
    E4 = debt_ratio 상위 분위                            — 재무 곤경 (E1 과 직교)
    잔여 < 8 → insufficient_breadth 정직 중단(억지 구성 금지).
  Layer2 = sklearn LedoitWolf 수축 공분산 → SLSQP 최소분산(롱온리·상한) ⊕ 1/N (λ=0.5 LOCKED).
  Layer3 = E = min(0.12/σ_p, 0.25·0.04/σ_p², 1.0) · 잔여 현금 · 무레버리지.
  brain_score = 어느 층에도 미투입(자기참조 차단).

구현 노트(등록 공백/데이터 갭 — 산식 변경 아님, 상태 플래그로 정직 노출):
  · 수익률 입력 = kr_chart_daily 일봉(등록 시점 sparkline_weekly 는 정렬 결함 확인 → 일봉 재배선).
    σ 연율화 = sqrt(252).
  · F-Score 정수 필드 부재 → E1 은 가용 leg(ROE<0)만 + flag. (필드 적재 시 자동 완전체.)
  · 패닉 판정(24개월 지수 누적<0 AND 63일 변동성>3년 중앙값) = 지수 시계열 756일 필요.
    현 kr_index_daily keep 120일 → 판정 불가 시 panic=False + flag (E2 휴면, 백필 큐).
  · SLSQP 상한 0.10 은 N<10 에서 수학 불능 → 상한 = 1/N 로 완화 + flag (feasibility 보정).
산출/트레일 = 태생 봉인(.gitignore + private bucket + authed).
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
KST = timezone(timedelta(hours=9))

# ── 사전등록 상수 (LOCKED) ──
DECILE = 0.10
BLEND_LAMBDA = 0.5
MAX_POS = 0.10                 # SLSQP 상한 (N<10 → 1/N 완화 + flag)
TARGET_VOL = 0.12
KELLY_PHI = 0.25
ERP = 0.04
MIN_BREADTH = 8                # 잔여 하한 — 미만이면 구성 중단
RET6M_DAYS = 126
VOL_DAYS = 60
PANIC_NEED_DAYS = 756          # 3년 (지수 시계열 요구)
TRADING_DAYS = 252


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and np.isfinite(v) else None


def _decile_flags(vals: List[Optional[float]], top: bool) -> List[bool]:
    """상/하위 10분위 플래그. 결측=False. 유효표본 <5 = 룰 미적용(분위 퇴화)."""
    idx = [i for i, v in enumerate(vals) if v is not None]
    out = [False] * len(vals)
    if len(idx) < 5:
        return out
    arr = np.array([vals[i] for i in idx], dtype=float)
    if np.isclose(arr.max(), arr.min()):     # 분산 0(전원 동일) = 극단 부재 → 룰 미적용
        return out
    q = float(np.quantile(arr, 1 - DECILE if top else DECILE))
    for i in idx:
        v = vals[i]
        if (top and v >= q) or (not top and v <= q):
            out[i] = True
    return out


# ── 지수 패닉 상태 (등록 정의 · 데이터 부족 시 휴면) ──

def panic_state(index_closes: Optional[List[float]]) -> Tuple[bool, str]:
    """등록: 24개월 누적수익 < 0 AND 63일 실현변동성 > 3년 중앙값. 756일 미만 = 판정 불가."""
    if not index_closes or len(index_closes) < PANIC_NEED_DAYS:
        n = len(index_closes or [])
        return False, f"panic_series_insufficient({n}d<{PANIC_NEED_DAYS}d)"
    px = np.array(index_closes, dtype=float)
    ret24 = px[-1] / px[-504] - 1.0                       # 24개월 ≈ 504거래일
    rets = px[1:] / px[:-1] - 1.0
    win = 63
    vols = np.array([rets[i - win:i].std() for i in range(win, len(rets) + 1)])
    cur_vol = float(vols[-1])
    med3y = float(np.median(vols[-PANIC_NEED_DAYS:]))
    active = bool(ret24 < 0 and cur_vol > med3y)
    return active, ""


# ── Layer 1 — 등록 E1~E4 (비대칭 · 상대 분위 · brain 미사용) ──

def layer1_exclude(
    recs: List[Dict[str, Any]],
    feats: Dict[str, Dict[str, Optional[float]]],
    panic_active: bool,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]], List[str]]:
    """recs + 계산 피처(ret_6m·vol_60d) → (생존, 배제, flags)."""
    flags: List[str] = []
    pbr = [_num(r.get("pbr")) for r in recs]
    roe = [_num(r.get("roe")) or _num((r.get("kis_financial_ratio") or {}).get("roe")) for r in recs]
    fsc = [_num(r.get("f_score")) for r in recs]
    debt = [_num(r.get("debt_ratio")) or _num((r.get("kis_financial_ratio") or {}).get("debt_ratio")) for r in recs]
    r6 = [feats.get(str(r.get("ticker")), {}).get("ret_6m") for r in recs]
    v60 = [feats.get(str(r.get("ticker")), {}).get("vol_60d") for r in recs]

    if all(v is None for v in fsc):
        flags.append("f_score_unavailable(E1=ROE<0 leg only)")

    pbr_low = _decile_flags(pbr, top=False)
    r6_top = _decile_flags(r6, top=True)
    v60_top = _decile_flags(v60, top=True)
    debt_top = _decile_flags(debt, top=True)
    if not panic_active:
        flags.append("E2_dormant(panic=False)")

    keep, excluded = [], []
    for i, r in enumerate(recs):
        tk = str(r.get("ticker"))
        reasons = []
        quality_bad = (fsc[i] is not None and fsc[i] <= 2) or (roe[i] is not None and roe[i] < 0)
        if pbr_low[i] and quality_bad:
            reasons.append("E1 밸류트랩(PBR하위+저품질)")
        if panic_active and r6_top[i]:
            reasons.append("E2 패닉장 승자(모멘텀 크래시 존)")
        if v60_top[i]:
            reasons.append("E3 고변동 극단")
        if debt_top[i]:
            reasons.append("E4 고부채 극단")
        if reasons:
            excluded.append({"ticker": tk, "name": r.get("name") or tk, "reason": " · ".join(reasons)})
        else:
            keep.append(r)
    return keep, excluded, flags


# ── Layer 2 — sklearn LedoitWolf + SLSQP 최소분산 ⊕ 1/N ──

def layer2_sleeve(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """(T,d) 일수익률 → (슬리브 합1, Σ(일간), meta)."""
    from sklearn.covariance import LedoitWolf
    from scipy.optimize import minimize

    T, d = X.shape
    ew = np.full(d, 1.0 / d)
    if d == 1:
        return np.array([1.0]), np.atleast_2d(np.var(X[:, 0]) if T > 1 else 1e-4), {"method": "single"}
    lw = LedoitWolf().fit(X)
    sigma = lw.covariance_
    cap = MAX_POS
    meta: Dict[str, Any] = {"method": "LW-minvar(SLSQP)⊕1/N", "lw_shrinkage": round(float(lw.shrinkage_), 4)}
    if d < int(round(1 / MAX_POS)):
        cap = 1.0 / d
        meta["cap_relaxed"] = f"N={d}<10 → cap=1/N(feasibility)"
    res = minimize(
        lambda w: float(w @ sigma @ w),
        ew, method="SLSQP",
        bounds=[(0.0, cap)] * d,
        constraints=[{"type": "eq", "fun": lambda w: float(w.sum() - 1.0)}],
        options={"maxiter": 300, "ftol": 1e-12},
    )
    if res.success and np.isfinite(res.x).all():
        mv = np.clip(res.x, 0, cap)
        mv = mv / mv.sum()
    else:
        mv = ew
        meta["minvar_fallback"] = "SLSQP 실패 → 1/N"
    w = BLEND_LAMBDA * mv + (1 - BLEND_LAMBDA) * ew
    return w / w.sum(), sigma, meta


# ── Layer 3 — 노출 (목표변동성 ∧ quarter-Kelly ∧ 무레버리지) ──

def layer3_exposure(w: np.ndarray, sigma_daily: np.ndarray) -> Dict[str, Any]:
    var_d = float(w @ sigma_daily @ w)
    vol = float(np.sqrt(max(var_d, 1e-12) * TRADING_DAYS))
    k_vol = TARGET_VOL / vol if vol > 0 else 1.0
    k_kelly = KELLY_PHI * ERP / (vol ** 2) if vol > 0 else 1.0
    e = float(min(k_vol, k_kelly, 1.0))
    bind = "vol_target" if k_vol <= min(k_kelly, 1.0) else ("quarter_kelly" if k_kelly <= 1.0 else "no_leverage")
    return {"portfolio_vol_annual": round(vol, 4), "k_vol": round(k_vol, 4),
            "k_kelly": round(k_kelly, 4), "exposure": round(e, 4), "cash": round(1 - e, 4), "bind": bind}


# ── 데이터 적재 ──

def _load_closes(tickers: List[str]) -> Dict[str, Dict[int, float]]:
    closes: Dict[str, Dict[int, float]] = {}
    for path in sorted(glob.glob(os.path.join(_ROOT, "data", "kr_chart_daily", "chunk_*.json"))):
        try:
            stocks = (json.load(open(path, encoding="utf-8")) or {}).get("stocks") or {}
        except (OSError, ValueError):
            continue
        for tk in tickers:
            if tk in stocks and tk not in closes:
                closes[tk] = {int(row[0]): float(row[4]) for row in (stocks[tk].get("c") or [])
                              if isinstance(row, list) and len(row) >= 5 and row[4]}
    return closes


def _features(closes: Dict[str, Dict[int, float]]) -> Dict[str, Dict[str, Optional[float]]]:
    """티커별 ret_6m(126d)·vol_60d — Layer1 입력."""
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for tk, cd in closes.items():
        px = np.array([cd[k] for k in sorted(cd)], dtype=float)
        ret6 = float(px[-1] / px[-(RET6M_DAYS + 1)] - 1.0) if len(px) > RET6M_DAYS else None
        if len(px) > VOL_DAYS:
            r = px[-(VOL_DAYS + 1):]
            vol = float((r[1:] / r[:-1] - 1.0).std())
        else:
            vol = None
        out[tk] = {"ret_6m": ret6, "vol_60d": vol}
    return out


def _load_index_closes() -> Optional[List[float]]:
    try:
        d = json.load(open(os.path.join(_ROOT, "data", "kr_index_daily.json"), encoding="utf-8"))
        ser = ((d.get("indices") or {}).get("코스피") or {}).get("c") or []
        return [float(r[1]) for r in ser if isinstance(r, list) and len(r) >= 2]
    except (OSError, ValueError, KeyError):
        return None


def _aligned_returns(closes: Dict[str, Dict[int, float]], tickers: List[str]) -> Tuple[np.ndarray, List[str], int]:
    have = [tk for tk in tickers if closes.get(tk)]
    if not have:
        return np.zeros((0, 0)), [], 0
    common = set.intersection(*(set(closes[tk]) for tk in have))
    days = sorted(common)
    if len(days) < 2:
        return np.zeros((0, 0)), have, 0
    P = np.array([[closes[tk][d] for tk in have] for d in days], dtype=float)
    return P[1:] / P[:-1] - 1.0, have, len(days)


# ── 빌드 + 트레일 ──

def build(portfolio_doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if portfolio_doc is None:
        portfolio_doc = json.load(open(os.path.join(_ROOT, "data", "portfolio.json"), encoding="utf-8"))
    recs = portfolio_doc.get("recommendations") or []
    kr = [r for r in recs if r.get("currency") == "KRW"]
    us = [str(r.get("ticker")) for r in recs if r.get("currency") == "USD"]

    tickers = [str(r.get("ticker")) for r in kr]
    closes = _load_closes(tickers)
    feats = _features(closes)
    panic, panic_flag = panic_state(_load_index_closes())
    keep, excluded, flags = layer1_exclude(kr, feats, panic)
    if panic_flag:
        flags.append(panic_flag)

    base = {
        "as_of": datetime.now(KST).strftime("%Y-%m-%d"),
        "method": "중용 3층 v0 (PREREG_MODERATION_PORTFOLIO_2026_08_01 등록본 · 상수 승인 2026-08-02)",
        "layer1": {"universe_kr": len(kr), "excluded": excluded, "survivors": len(keep),
                   "panic_active": panic, "flags": flags},
        "us_pending": us,
        "disclosure": {"rule7": "가설 · 라이브 검증 N=0 (게이트 N>=252, ~2027) · 매수/매도 지시 아님",
                       "brain_used_in_sizing": False,
                       "citations": "Piotroski2000·Daniel-Moskowitz2016·Ang2006·Frazzini-Pedersen2014·"
                                    "Ledoit-Wolf2004·DeMiguel2009·Harvey2018·MacLean-Thorp-Ziemba2011"},
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
    }

    if len(keep) < MIN_BREADTH:
        base["status"] = "insufficient_breadth"
        base["layer1"]["note"] = f"생존 {len(keep)} < {MIN_BREADTH} — 억지 구성 금지(등록 §2)"
        base["weights"] = {}
        return base

    X, aligned, n_days = _aligned_returns(closes, [str(r.get("ticker")) for r in keep])
    w_sleeve, sigma, meta2 = layer2_sleeve(X)
    l3 = layer3_exposure(w_sleeve, sigma)
    w_final = w_sleeve * l3["exposure"]
    name_of = {str(r.get("ticker")): (r.get("name") or r.get("ticker")) for r in kr}

    base.update({
        "status": "ok",
        "layer2": {**meta2, "common_days": n_days, "aligned": len(aligned),
                   "blend_lambda": BLEND_LAMBDA, "max_pos_sleeve": MAX_POS},
        "layer3": {**l3, "target_vol": TARGET_VOL, "kelly_phi": KELLY_PHI, "erp_prior": ERP, "leverage_cap": 1.0},
        "weights": {tk: round(float(wi), 4) for tk, wi in zip(aligned, w_final) if wi > 1e-6},
        "names": {tk: name_of.get(tk, tk) for tk in aligned},
    })
    return base


def _append_trail(doc: Dict[str, Any]) -> None:
    """등록 §5 trail — 사후 편집 금지 append. 파일도 봉인 대상(gitignore)."""
    path = os.path.join(_ROOT, "data", "moderation_portfolio_trail.jsonl")
    row = {
        "ts": doc.get("generated_at"),
        "status": doc.get("status"),
        "universe_kr": doc["layer1"]["universe_kr"],
        "cuts": {}, "survivors": doc["layer1"]["survivors"],
        "weights": doc.get("weights") or {},
        "sigma_p": (doc.get("layer3") or {}).get("portfolio_vol_annual"),
        "k_vol": (doc.get("layer3") or {}).get("k_vol"),
        "k_kelly": (doc.get("layer3") or {}).get("k_kelly"),
        "exposure": (doc.get("layer3") or {}).get("exposure"),
        "flags": doc["layer1"].get("flags"),
    }
    for e in doc["layer1"]["excluded"]:
        for part in str(e.get("reason", "")).split(" · "):
            key = part.split(" ")[0]
            row["cuts"][key] = row["cuts"].get(key, 0) + 1
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    doc = build()
    out = os.path.join(_ROOT, "data", "moderation_portfolio.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    _append_trail(doc)
    l3 = doc.get("layer3") or {}
    print(f"[moderation] {doc.get('status')} · 생존 {doc['layer1']['survivors']}/{doc['layer1']['universe_kr']}"
          f" · E {l3.get('exposure')} ({l3.get('bind')}) · vol {l3.get('portfolio_vol_annual')} → {out}",
          file=sys.stderr)


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    main()
