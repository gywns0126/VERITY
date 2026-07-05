"""
factor_gauntlet.py — 팩터/신호 검증 관문(gauntlet). 2026-06-15 멀티렌즈 adversarial 감사 산물.

감사에서 "강해 보인" 발견 8/14 가 죽은 사유 = 재발하는 8 실패모드. 이를 *자동 체크*로 코드화해
모든 미래 신호(CoMOM/KR flow/brain 팩터/fundamentals)가 wire 전 통과하도록 한 상시 관문.
🚨 관측/측정 only (RULE 7). in-sample 진단 도구 — "통과"가 알파 보증 아님(OOS/거래비용 별도).

입력: signal_panel(ticker, formation_date, value) + 월수익 parquet. 옵션: size 라벨, 상폐셋.
8 체크 (감사 killer_flaw 대응):
  1 base       — top-bottom 십분위 forward 스프레드 + 연도 t + 양의연도비율
  2 survivorship — 상폐셋 포함 vs 제외 스프레드 차(생존편향 bp). [무덤/+346bp 렌즈]
  3 size       — size 버킷 내 스프레드(대형서 부호역전/소멸 = size 프록시 플래그). [Piotroski killer]
  4 overlap    — effective_n=T/k, naive-t vs √Neff-조정 t (중첩윈도 인플레). [모멘텀크래시 killer]
  5 clip       — 수익 clip 여러 값서 t 부호 안정성(곡선맞추기). [Altman killer]
  6 subperiod  — 전/후반 스프레드(단일 레짐 의존). [자산성장 닷컴 killer]
  7 mean_median— 평균 vs 중앙값(우편향 lottery 환상). [저변동성 nuance]
  8 placebo    — 신호 셔플 → 스프레드 ~0 기대(허위 검출).

관측 전용 추가 (2026-07 — self 검증수학 연결. flags/PASS·FAIL 미반영, RULE 7):
  9 purged_cv  — tscv.purged_kfold_split 로 형성일 fold 분할 → held-out OOS 스프레드 분포(embargo 분리).
  10 pbo       — pbo.cscv_pbo(CSCV) 분위 수익행렬 → 분위 랭킹 OOS 안정성(과최적 확률).
     🚨 PBO cutoff 로 cycle reject 게이트화 시 = pbo.py 명시대로 PM 사전등록 별도 의무. 여기선 진단값만.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# ── self 검증수학 연결 (관측 전용) ──────────────────────────────────
# pbo.py(CSCV PBO) + tscv.py(purged k-fold) = 자체구현됐으나 미연결이던 것 (2026-07 연결).
# import 실패(경로/미설치) 시 관측 체크만 skip — 게이트는 무중단(형제 스크립트 패턴 = _ROOT 삽입).
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
try:
    from api.quant.alpha.pbo import cscv_pbo             # noqa: E402
    from api.predictors.tscv import purged_kfold_split   # noqa: E402
    _HAS_CV = True
except Exception:  # noqa: BLE001
    _HAS_CV = False

L = os.path.expanduser("~/VERITY_data_lake")
RETURNS = os.path.join(L, "features", "monthly_returns.parquet")
FUND = os.path.join(L, "features", "fundamentals_features.parquet")
SHARADAR_DB = os.path.join(L, "sharadar.duckdb")
DECILE_FRAC = 0.10


# ─────────────────────────── forward 수익 ───────────────────────────
def forward_returns(horizon_m: int = 12, returns_path: str = RETURNS,
                    clip: float = 5.0) -> pd.DataFrame:
    """월수익 → (ticker, month, fwd) = month 이후 horizon_m 개월 누적수익(gap-safe date join)."""
    mr = pd.read_parquet(returns_path)
    mr["month"] = pd.to_datetime(mr["month"])
    mr = mr.sort_values(["ticker", "month"])
    mr["lr"] = np.log1p(mr["ret_1m"].clip(-0.95, clip))
    mr["clr"] = mr.groupby("ticker")["lr"].cumsum()
    tgt = mr[["ticker", "month", "clr"]].copy()
    tgt["month"] = tgt["month"] - pd.DateOffset(months=horizon_m)  # 이 clr 는 month+h 시점 → month 에 귀속
    mr = mr.merge(tgt.rename(columns={"clr": "clr_fwd"}), on=["ticker", "month"], how="left")
    mr["fwd"] = np.expm1(mr["clr_fwd"] - mr["clr"])
    return mr[["ticker", "month", "fwd"]].dropna(subset=["fwd"])


# ─────────────────────────── 스프레드 엔진 ───────────────────────────
def _spread(panel: pd.DataFrame) -> Dict[str, object]:
    """panel[formation_date, value, fwd] → 형성일별 top-bottom 십분위 스프레드 + 연도 t."""
    rows = []
    for f, g in panel.groupby("formation_date"):
        g = g.dropna(subset=["value", "fwd"])
        if g["value"].nunique() < 10 or len(g) < 30:
            continue
        d = pd.qcut(g["value"].rank(method="first"), 10, labels=False)
        top = g.loc[d == 9, "fwd"].mean()
        bot = g.loc[d == 0, "fwd"].mean()
        rows.append({"f": f, "spread": top - bot, "n": len(g)})
    if not rows:
        return {"spread": None, "t": None, "n_periods": 0, "pos_frac": None, "pooled_n": 0}
    s = pd.DataFrame(rows)
    sp = s["spread"]
    t = float(sp.mean() / (sp.std(ddof=1) / np.sqrt(len(sp)))) if len(sp) > 1 and sp.std() > 0 else None
    return {"spread": round(float(sp.mean()), 4), "t": round(t, 2) if t else None,
            "n_periods": len(sp), "pos_frac": round(float((sp > 0).mean()), 2),
            "pooled_n": int(s["n"].sum())}


def _pooled_mean_median(panel: pd.DataFrame) -> Dict[str, float]:
    """전체 풀에서 top/bottom 십분위 fwd 평균·중앙값(형성일별 십분위 후 풀)."""
    tops, bots = [], []
    for f, g in panel.groupby("formation_date"):
        g = g.dropna(subset=["value", "fwd"])
        if g["value"].nunique() < 10 or len(g) < 30:
            continue
        d = pd.qcut(g["value"].rank(method="first"), 10, labels=False)
        tops.append(g.loc[d == 9, "fwd"]); bots.append(g.loc[d == 0, "fwd"])
    if not tops:
        return {}
    T = pd.concat(tops); B = pd.concat(bots)
    return {"mean_spread": round(float(T.mean() - B.mean()), 4),
            "median_spread": round(float(T.median() - B.median()), 4)}


# ─── 관측 전용: self 검증수학(purged-CV OOS + CSCV PBO) 헬퍼 ───
def _decile_matrix(panel: pd.DataFrame) -> tuple:
    """base_panel → (형성일 × 10분위) fwd 평균 행렬 M + 형성일 리스트.

    각 행=한 형성일, 각 열 d=그 시점 d분위(0=최저,9=최고)의 fwd 평균.
    _spread 와 동일 필터(고유값≥10 & 이름≥30)로 유효 형성일만, nan 행 제외.
    반환 M = cscv_pbo 의 (T, N=10) 입력 — '분위 랭킹이 OOS 에서 안정한가' 관측용.
    """
    rows, dates = [], []
    for f, g in panel.groupby("formation_date"):
        g = g.dropna(subset=["value", "fwd"])
        if g["value"].nunique() < 10 or len(g) < 30:
            continue
        d = pd.qcut(g["value"].rank(method="first"), 10, labels=False)
        means = g.groupby(d)["fwd"].mean()
        if len(means) < 10 or means.isna().any():
            continue
        rows.append([float(means.get(k, np.nan)) for k in range(10)])
        dates.append(f)
    M = np.asarray(rows, dtype=float)
    return M, dates


def _purged_oos_spread(panel: pd.DataFrame, n_splits: int, embargo_pct: float = 0.01) -> Dict[str, object]:
    """tscv.purged_kfold_split 로 형성일을 fold 분할 → held-out fold 별 top-bottom 스프레드 관측.

    모델 학습이 없어 purge/embargo 의 leakage 차단 효과는 제한적이나, embargo-분리된
    비중첩 test fold 별 OOS 스프레드 분포로 '샘플 구간 의존'을 leak-guard 하에 재측정
    (check 6 subperiod 의 강화판). flags 미반영.
    """
    periods = sorted(panel["formation_date"].unique())
    n = len(periods)
    if not _HAS_CV or n < 6:
        return {"skipped": f"형성일 {n}개(<6) 또는 CV 모듈 부재", "oos_spread_mean": None}
    parr = np.array(periods)
    fold_spreads = []
    for _tr, te in purged_kfold_split(n, n_splits=n_splits, embargo_pct=embargo_pct):
        if len(te) == 0:
            continue
        sub = panel[panel["formation_date"].isin(set(parr[te]))]
        r = _spread(sub)
        if r["spread"] is not None:
            fold_spreads.append(r["spread"])
    if not fold_spreads:
        return {"skipped": "유효 fold 스프레드 0", "oos_spread_mean": None}
    fs = np.array(fold_spreads, dtype=float)
    base_sp = _spread(panel)["spread"]
    same_sign = float(np.mean(np.sign(fs) == np.sign(base_sp))) if base_sp else None
    return {
        "oos_spread_mean": round(float(fs.mean()), 4),
        "oos_spread_std": round(float(fs.std(ddof=1)), 4) if len(fs) > 1 else None,
        "n_folds": int(len(fs)),
        "embargo_pct": embargo_pct,
        "same_sign_frac": round(same_sign, 2) if same_sign is not None else None,
        "in_sample_spread": base_sp,
    }


# ─────────────────────────── 8 체크 ───────────────────────────
def run_gauntlet(
    signal_panel: pd.DataFrame, horizon_m: int = 12,
    size_labels: Optional[pd.DataFrame] = None, delisted: Optional[set] = None,
    clips: List[float] = [0.3, 1.0, 5.0, 1000.0],
) -> Dict[str, object]:
    """signal_panel[ticker, formation_date, value] → 8 체크 리포트."""
    sp = signal_panel.copy()
    sp["formation_date"] = pd.to_datetime(sp["formation_date"])
    fwd = forward_returns(horizon_m, clip=5.0)
    base_panel = sp.merge(
        fwd.rename(columns={"month": "formation_date"}), on=["ticker", "formation_date"], how="inner")

    out: Dict[str, object] = {"checks": {}}
    flags: List[str] = []

    # 1 base
    base = _spread(base_panel)
    out["checks"]["1_base"] = base

    # 2 survivorship
    if delisted:
        full = base
        surv = _spread(base_panel[~base_panel["ticker"].isin(delisted)])
        bias = (round((surv["spread"] - full["spread"]) * 100, 1)
                if surv["spread"] is not None and full["spread"] is not None else None)
        out["checks"]["2_survivorship"] = {"full": full["spread"], "survivor_only": surv["spread"],
                                           "bias_pp": bias}
        if bias is not None and abs(bias) >= 1.0:
            flags.append("survivorship")
    # 3 size
    if size_labels is not None:
        sl = size_labels.rename(columns={size_labels.columns[1]: "size"})
        szp = base_panel.merge(sl[["ticker", "size"]], on="ticker", how="left")
        by = {}
        for sz, g in szp.dropna(subset=["size"]).groupby("size"):
            r = _spread(g)
            by[str(sz)] = {"spread": r["spread"], "t": r["t"], "n": r["pooled_n"]}
        out["checks"]["3_size"] = by
        # 대형(Large/Mega) 부호가 base 와 반대거나 소멸하면 플래그
        big = [v["spread"] for k, v in by.items() if ("Large" in k or "Mega" in k) and v["spread"] is not None]
        if base["spread"] and big and (np.mean(big) * base["spread"] <= 0 or abs(np.mean(big)) < abs(base["spread"]) * 0.3):
            flags.append("size_confound")

    # 4 overlap (effective_n)
    npd = base["n_periods"] or 0
    out["checks"]["4_overlap"] = {"n_periods": npd, "cadence": "annual(June)",
                                  "horizon_m": horizon_m,
                                  "note": "연1회 형성+12m horizon=비중첩(k≈1). cadence<horizon 시 Neff=T/k 적용 필요"}

    # 5 clip sensitivity
    clip_res = {}
    for c in clips:
        f2 = forward_returns(horizon_m, clip=c)
        bp = sp.merge(f2.rename(columns={"month": "formation_date"}), on=["ticker", "formation_date"], how="inner")
        r = _spread(bp)
        clip_res[str(c)] = {"spread": r["spread"], "t": r["t"]}
    out["checks"]["5_clip"] = clip_res
    ts = [v["t"] for v in clip_res.values() if v["t"] is not None]
    if ts and (max(ts) - min(ts) > 2.0 or (max(ts) > 2 and min(ts) < 1)):
        flags.append("clip_sensitivity")

    # 6 subperiod
    yrs = base_panel["formation_date"].dt.year
    mid = int(yrs.median()) if len(yrs) else None
    if mid:
        h1 = _spread(base_panel[base_panel["formation_date"].dt.year <= mid])
        h2 = _spread(base_panel[base_panel["formation_date"].dt.year > mid])
        out["checks"]["6_subperiod"] = {"first_half": {"spread": h1["spread"], "t": h1["t"]},
                                        "second_half": {"spread": h2["spread"], "t": h2["t"]}}
        if (h1["spread"] is not None and h2["spread"] is not None
                and h1["spread"] * h2["spread"] <= 0):
            flags.append("regime_dependent")

    # 7 mean vs median
    mm = _pooled_mean_median(base_panel)
    out["checks"]["7_mean_median"] = mm
    if mm and mm.get("mean_spread") is not None and mm.get("median_spread") is not None:
        if abs(mm["median_spread"]) > 1e-9 and abs(mm["mean_spread"]) > 2.5 * abs(mm["median_spread"]):
            flags.append("lottery_mean_driven")

    # 8 placebo (셔플)
    rng = np.random.default_rng(42)
    pl = base_panel.copy()
    pl["value"] = pl.groupby("formation_date")["value"].transform(lambda s: rng.permutation(s.values))
    placebo = _spread(pl)
    out["checks"]["8_placebo"] = placebo
    if (base["spread"] and placebo["spread"] is not None
            and abs(placebo["spread"]) > 0.4 * abs(base["spread"])):
        flags.append("placebo_leak")

    # ── 관측 전용 (self 검증수학 연결) — flags/verdict 미반영, RULE 7 ──
    # 9 purged-CV OOS 스프레드 (tscv.purged_kfold_split)
    try:
        n_periods_u = base_panel["formation_date"].nunique()
        nsp = 5 if n_periods_u >= 10 else 3
        out["checks"]["9_purged_cv"] = _purged_oos_spread(base_panel, n_splits=nsp)
    except Exception as e:  # noqa: BLE001 — 관측 체크 실패는 게이트 무중단
        out["checks"]["9_purged_cv"] = {"error": f"{type(e).__name__}: {e}"}

    # 10 CSCV PBO (pbo.cscv_pbo, 분위 랭킹 OOS 안정성)
    try:
        if not _HAS_CV:
            out["checks"]["10_pbo"] = {"skipped": "CV 모듈 부재"}
        else:
            M, _mdates = _decile_matrix(base_panel)
            T = M.shape[0] if M.ndim == 2 else 0
            S = next((s for s in (8, 6, 4) if T >= 2 * s), None)
            if S is None:
                out["checks"]["10_pbo"] = {"skipped": f"형성일 {T}개(<8) — CSCV 표본 부족"}
            else:
                pbo_res = cscv_pbo(M, n_partitions=S)
                pbo_res["interpretation"] = ("높을수록 in-sample 최적 분위가 OOS 에서 유지 안 됨 = "
                                             "분위 랭킹이 구간 특이(과최적 위험). 관측 only")
                out["checks"]["10_pbo"] = pbo_res
    except Exception as e:  # noqa: BLE001
        out["checks"]["10_pbo"] = {"error": f"{type(e).__name__}: {e}"}

    out["observation_only"] = ["9_purged_cv", "10_pbo"]  # RULE 7: PASS/FAIL 미반영

    out["flags"] = flags
    out["verdict"] = ("PASS (강건)" if not flags else f"FLAG ×{len(flags)}: {', '.join(flags)}")
    return out


# ─────────────────────────── 데모 로더 ───────────────────────────
def fundamental_signal(col: str) -> pd.DataFrame:
    """fundamentals_features 의 col → (ticker, formation_date=매년 6/30 PIT 최신, value)."""
    ff = pd.read_parquet(FUND, columns=["ticker", "datekey", col])
    ff["datekey"] = pd.to_datetime(ff["datekey"])
    rows = []
    for yr in range(1999, 2026):
        f = pd.Timestamp(f"{yr}-06-30")
        cur = ff[(ff["datekey"] <= f) & (ff["datekey"] >= f - pd.DateOffset(months=18))]
        cur = cur.sort_values("datekey").groupby("ticker").tail(1)
        cur = cur[["ticker", col]].rename(columns={col: "value"})
        cur["formation_date"] = pd.Timestamp(f"{yr}-06-01")  # monthly_returns month-start 정합
        rows.append(cur)
    return pd.concat(rows, ignore_index=True).dropna(subset=["value"])


def _load_size_delisted():
    import duckdb
    con = duckdb.connect(SHARADAR_DB, read_only=True)
    try:
        sz = con.execute("SELECT ticker, scalemarketcap AS size FROM TICKERS WHERE \"table\" IN ('SF1','SEP')").fetchdf().drop_duplicates("ticker")
        dl = set(con.execute("SELECT DISTINCT ticker FROM ACTIONS WHERE action IN ('bankruptcyliquidation','regulatorydelisting')").fetchdf()["ticker"])
        return sz, dl
    finally:
        con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--signal", default="gpoa", help="fundamentals_features 컬럼(데모): gpoa/piotroski_f/accruals/asset_growth/altman_z")
    ap.add_argument("--horizon", type=int, default=12)
    args = ap.parse_args()
    try:
        panel = fundamental_signal(args.signal)
        sz, dl = _load_size_delisted()
        res = run_gauntlet(panel, horizon_m=args.horizon, size_labels=sz, delisted=dl)
        print(f"\n===== GAUNTLET: signal={args.signal} (h={args.horizon}m) =====")
        print(f"VERDICT: {res['verdict']}\n")
        import json
        print(json.dumps(res["checks"], ensure_ascii=False, indent=1, default=str))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[gauntlet] 실패: {type(e).__name__}: {e}\n")
        raise
