"""중용(中庸) 포트폴리오 빌더 — 구성 척추 (#4).

사전등록 = docs/PREREG_MODERATION_PORTFOLIO_2026_08_01.md (private repo).
PM 승인: 방향(3층 결합) 2026-08-01 · 상수 그대로 2026-08-02 ("이어서 고고").
RULE 7: 산출 = 가설(검증 N<252) · brain_score 는 어느 층에도 미투입(자기참조 차단 —
검증 전 산식이 사이징을 오염시키지 않게). Layer1 은 사실(팩트 필드)만 사용.

3층 (각 층 학술 근거 ≥2):
  Layer1 극단 배제 — 유니버스 내 상대 분위(decile), 비대칭(근거 있는 쪽 꼬리만).
    E1 재무 극단: 부채비율 상위 분위 AND 유동비율 하위 분위 (동시) 또는 DART 심각도 >=3
       (Piotroski 2000 — 재무건전성 하위 꼬리의 systematic 저성과)
    E2 낙폭 극단: 고점대비 낙폭 최심 분위 (Daniel & Moskowitz 2016 — momentum crash 꼬리)
    E3 과열 극단: PER 상위 분위 AND PBR 상위 분위 (동시) (Harvey et al. 2018 — 팩터 극단 꼬리)
    E4 규모 극단: 시총 하위 분위 — 정수주/체결 실행 불능 프록시
    결측 필드 = 해당 룰 그 종목 미적용(배제 아님 — 결측을 벌하지 않는다).
  Layer2 슬리브 가중 — Ledoit-Wolf(2004) 상수상관 수축 공분산의 최소분산(롱온리 클립)
    ⊕ 1/N (λ=0.5, DeMiguel 2009 — 추정오차 하 1/N 견고성).
  Layer3 스케일 — gross = min( 목표변동성 12%/σ_p , quarter-Kelly 0.25·(ERP 0.04/σ_p²) , 1.0 ).
    잔여 = 현금. 무레버리지 절대 (MacLean·Thorp·Ziemba 2011 — 과베팅 비대칭 파산).
  종목 10% 상한 = **총자산 대비, gross 적용 후** — 초과분은 현금으로(재배분 안 함, 보수 방향).
    (N<10 소규모 유니버스에서도 수학적으로 성립하는 유일한 해석.)

US 추천 = v1 제외 목록 표기(us_chart_daily 공분산 소스 주간 적재 후 편입 예정).
산출 data/moderation_portfolio.json = 오퍼레이터 자산 — .gitignore + private bucket 만(공개 발행 금지).
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

# ── 사전등록 상수 (PM 승인 2026-08-02 — 조정 = 신규 사전등록 필수) ──
DECILE = 0.10            # 극단 = 상/하위 10분위
BLEND_LAMBDA = 0.5       # Layer2: w = λ·minvar ⊕ (1−λ)·1/N
MAX_POS = 0.10           # 종목 상한 (총자산 대비, gross 후)
TARGET_VOL = 0.12        # 연 목표변동성
KELLY_PHI = 0.25         # quarter-Kelly
ERP = 0.04               # 기대 초과수익 보수 prior (스케일 앵커 — 예측 아님)
MIN_COMMON_DAYS = 60     # 공분산 최소 공통 거래일 (미만 = 1/N 폴백)
TRADING_DAYS = 252


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and np.isfinite(v) else None


# ── Layer 1 — 극단 배제 (비대칭 · 상대 분위 · 사실만) ──

def _decile_flags(vals: List[Optional[float]], top: bool) -> List[bool]:
    """상위(top=True)/하위 10분위 플래그. 결측 = False. 유효표본 <5 = 룰 전체 미적용."""
    idx = [i for i, v in enumerate(vals) if v is not None]
    out = [False] * len(vals)
    if len(idx) < 5:
        return out
    arr = np.array([vals[i] for i in idx], dtype=float)
    q = float(np.quantile(arr, 1 - DECILE if top else DECILE))
    for i in idx:
        v = vals[i]
        if (top and v >= q) or (not top and v <= q):
            out[i] = True
    return out


def exclude_extremes(recs: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """KR 추천 → (생존, 배제[{ticker,name,reason}]). 비대칭 — 근거 있는 쪽 꼬리만."""
    debt = [_num(r.get("debt_ratio")) for r in recs]
    curr = [_num(r.get("current_ratio")) for r in recs]
    drop = [_num(r.get("drop_from_high_pct")) for r in recs]
    per = [_num(r.get("per")) for r in recs]
    pbr = [_num(r.get("pbr")) for r in recs]
    mcap = [_num(r.get("market_cap")) for r in recs]

    e1a = _decile_flags(debt, top=True)
    e1b = _decile_flags(curr, top=False)
    e2 = _decile_flags(drop, top=False)      # drop 은 음수 — 하위 분위 = 최심 낙폭
    e3a = _decile_flags(per, top=True)
    e3b = _decile_flags(pbr, top=True)
    e4 = _decile_flags(mcap, top=False)

    keep, excluded = [], []
    for i, r in enumerate(recs):
        tk = str(r.get("ticker"))
        sev = _num((r.get("dart_disclosure_events") or {}).get("severity"))
        reasons = []
        if (e1a[i] and e1b[i]) or (sev is not None and sev >= 3):
            reasons.append("E1 재무 극단" + (" (DART sev>=3)" if sev is not None and sev >= 3 else ""))
        if e2[i]:
            reasons.append("E2 낙폭 극단")
        if e3a[i] and e3b[i]:
            reasons.append("E3 과열 극단")
        if e4[i]:
            reasons.append("E4 규모 극단")
        if reasons:
            excluded.append({"ticker": tk, "name": r.get("name") or tk, "reason": " · ".join(reasons)})
        else:
            keep.append(r)
    return keep, excluded


# ── Layer 2 — Ledoit-Wolf(2004) 상수상관 수축 → 최소분산⊕1/N 슬리브 ──

def ledoit_wolf_cc(X: np.ndarray) -> Tuple[np.ndarray, float]:
    """상수상관 타깃 LW 수축 공분산 (Ledoit & Wolf 2004). X=(T,d) 일수익률 → (Σ*, δ)."""
    T, d = X.shape
    Xc = X - X.mean(axis=0, keepdims=True)
    S = (Xc.T @ Xc) / T
    s = np.sqrt(np.clip(np.diag(S), 1e-18, None))
    R = S / np.outer(s, s)
    off = ~np.eye(d, dtype=bool)
    r_bar = float(R[off].mean()) if d > 1 else 0.0
    F = r_bar * np.outer(s, s)
    np.fill_diagonal(F, np.diag(S))

    W = np.einsum("ti,tj->tij", Xc, Xc) - S[None, :, :]      # (T,d,d)
    pi_mat = (W ** 2).mean(axis=0)
    pi_hat = float(pi_mat.sum())
    theta = np.einsum("ti,tij->ij", Xc ** 2, W) / T          # ϑ_ii,ij
    rho_hat = float(np.trace(pi_mat))
    if d > 1:
        sr = np.sqrt(np.outer(np.diag(S), 1.0 / np.clip(np.diag(S), 1e-18, None)))  # √(s_ii/s_jj)
        term = sr.T * theta + sr * theta.T
        rho_hat += float((r_bar / 2.0) * term[off].sum())
    gamma_hat = float(((F - S) ** 2).sum())
    delta = 0.0 if gamma_hat <= 0 else max(0.0, min(1.0, (pi_hat - rho_hat) / gamma_hat / T))
    return delta * F + (1 - delta) * S, delta


def layer2_sleeve(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """(T,d) → (슬리브 가중 합1, 공분산 Σ, meta). T 부족/퇴화 = 1/N 폴백."""
    T, d = X.shape
    ew = np.full(d, 1.0 / d)
    if d == 1:
        sigma = np.atleast_2d(np.var(X[:, 0])) if T > 1 else np.array([[0.0]])
        return np.array([1.0]), sigma, {"method": "single", "lw_delta": None}
    if T < MIN_COMMON_DAYS:
        sigma = np.cov(X.T) if T > 1 else np.eye(d) * 1e-4
        return ew, np.atleast_2d(sigma), {"method": f"1/N-fallback(T<{MIN_COMMON_DAYS})", "lw_delta": None}
    sigma, delta = ledoit_wolf_cc(X)
    try:
        mv = np.linalg.pinv(sigma) @ np.ones(d)
        mv = np.clip(mv, 0, None)            # 롱온리 클립 휴리스틱
        mv = mv / mv.sum() if mv.sum() > 0 else ew
    except np.linalg.LinAlgError:
        mv = ew
    w = BLEND_LAMBDA * mv + (1 - BLEND_LAMBDA) * ew
    return w / w.sum(), sigma, {"method": "LW-minvar⊕1/N", "lw_delta": round(delta, 4)}


# ── Layer 3 — 스케일 + 총자산 10% 상한 ──

def layer3_scale(w_sleeve: np.ndarray, sigma_daily: np.ndarray) -> Dict[str, Any]:
    var_d = float(w_sleeve @ sigma_daily @ w_sleeve)
    vol_ann = float(np.sqrt(max(var_d, 1e-12) * TRADING_DAYS))
    g_vol = TARGET_VOL / vol_ann if vol_ann > 0 else 1.0
    g_kelly = KELLY_PHI * (ERP / (vol_ann ** 2)) if vol_ann > 0 else 1.0
    gross = float(min(g_vol, g_kelly, 1.0))
    bind = "vol_target" if g_vol <= min(g_kelly, 1.0) else ("quarter_kelly" if g_kelly <= 1.0 else "no_leverage")
    return {"portfolio_vol_annual": round(vol_ann, 4), "gross_pre_cap": round(gross, 4), "bind": bind}


def final_weights(w_sleeve: np.ndarray, gross: float) -> np.ndarray:
    """최종 비중 = min(슬리브×gross, MAX_POS). 초과분 = 현금(재배분 없음 — 보수)."""
    return np.minimum(w_sleeve * gross, MAX_POS)


# ── 데이터 적재 + 빌드 ──

def _load_kr_returns(tickers: List[str]) -> Tuple[np.ndarray, List[str], int]:
    """kr_chart_daily 청크 → 공통일 inner-join 일수익률. (X(T,d), 정렬티커, 공통일수)."""
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
    have = [tk for tk in tickers if closes.get(tk)]
    if not have:
        return np.zeros((0, 0)), [], 0
    common = set.intersection(*(set(closes[tk]) for tk in have))
    days = sorted(common)
    if len(days) < 2:
        return np.zeros((0, 0)), have, 0
    P = np.array([[closes[tk][d] for tk in have] for d in days], dtype=float)
    return P[1:] / P[:-1] - 1.0, have, len(days)


def build(portfolio_doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if portfolio_doc is None:
        portfolio_doc = json.load(open(os.path.join(_ROOT, "data", "portfolio.json"), encoding="utf-8"))
    recs = portfolio_doc.get("recommendations") or []
    kr = [r for r in recs if r.get("currency") == "KRW"]
    us = [str(r.get("ticker")) for r in recs if r.get("currency") == "USD"]

    keep, excluded = exclude_extremes(kr)
    tickers = [str(r.get("ticker")) for r in keep]
    X, aligned, n_days = _load_kr_returns(tickers)

    if X.size and aligned:
        w_sleeve, sigma, meta2 = layer2_sleeve(X)
        l3 = layer3_scale(w_sleeve, sigma)
        w_final = final_weights(w_sleeve, l3["gross_pre_cap"])
        gross_final = float(w_final.sum())
        weights = {tk: round(float(wi), 4) for tk, wi in zip(aligned, w_final) if wi > 1e-6}
    else:
        meta2 = {"method": "no_data", "lw_delta": None}
        l3 = {"portfolio_vol_annual": None, "gross_pre_cap": 0.0, "bind": "no_data"}
        gross_final, weights = 0.0, {}

    name_of = {str(r.get("ticker")): (r.get("name") or r.get("ticker")) for r in kr}
    return {
        "as_of": datetime.now(KST).strftime("%Y-%m-%d"),
        "method": "중용 3층 (PREREG_MODERATION_PORTFOLIO_2026_08_01 · 상수 승인 2026-08-02)",
        "layer1": {"universe_kr": len(kr), "excluded": excluded, "survivors": len(keep)},
        "layer2": {**meta2, "common_days": n_days, "aligned": len(aligned), "blend_lambda": BLEND_LAMBDA},
        "layer3": {**l3, "target_vol": TARGET_VOL, "kelly_phi": KELLY_PHI, "erp_prior": ERP,
                   "max_pos_total": MAX_POS, "leverage_cap": 1.0,
                   "gross_final": round(gross_final, 4), "cash": round(1 - gross_final, 4)},
        "weights": weights,                      # 최종 비중(총자산 대비) — 잔여 = 현금
        "names": {tk: name_of.get(tk, tk) for tk in weights},
        "us_pending": us,                        # us_chart_daily 공분산 적재 후 편입
        "disclosure": {"rule7": "가설 · 검증 N<252 (2027 게이트) · 매수/매도 지시 아님",
                       "brain_used_in_sizing": False},
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
    }


def main() -> None:
    doc = build()
    out = os.path.join(_ROOT, "data", "moderation_portfolio.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print(f"[moderation] 생존 {doc['layer1']['survivors']}/{doc['layer1']['universe_kr']} · "
          f"gross {doc['layer3']['gross_final']} ({doc['layer3']['bind']}) · "
          f"vol {doc['layer3']['portfolio_vol_annual']} → {out}", file=sys.stderr)


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    main()
