# -*- coding: utf-8 -*-
"""Module 1 — 횡단면 팩터 엔진 v1 (2026-08-16 wire).

계약 = `docs/FACTOR_ENGINE_DESIGN_2026_08_16.md` (시행과 동시 등록 — 결과 확인 전 고정).
§7-3(8)·§4 이행: 월말 횡단면 Spearman IC · N_t≥100 · PIT(+45일 규칙) · frozen OOS(2024-08~) ·
비겹침 df=k−1 evidence_class · BH-FDR(시도 40).

🚨 측정 인프라다 — 산식·가중·운영 경로 무변경. 산출물은 연구 전용이며 `_meta` 가 자기신고한다.

실행:
    python3 -m api.intelligence.factor            # IS 구간 측정 + 산출물 기록
    python3 -m api.intelligence.factor --dry-run  # 기록 없이 표만

구 stub(2026-05-28, "8월 wire 전제")를 본 구현이 대체한다. 학술 참조는 계약 문서와
`learning_materials/perplexity_ic_validation_answers_2026_08_15.md`(방법론) 참조.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from api.config import DATA_DIR, now_kst
from api.quant.alpha.alpha_scanner import _t_crit

VAL_PATH = os.path.join(DATA_DIR, "metadata", "kr_valuation_panel.jsonl")
FUND_PATH = os.path.join(DATA_DIR, "metadata", "kr_fundamental_panel.jsonl")
OUT_PATH = os.path.join(DATA_DIR, "analysis", "factor_engine_kr_v1.json")
REG_PATH = os.path.join(DATA_DIR, "analysis", "experiment_registry.jsonl")

# ── 계약 상수 (변경 = 재등록) ─────────────────────────────────
MIN_N_T = 100                     # 월별 최소 횡단면 크기
FUND_LAG_DAYS = 45                # 분기 재무 가용 규칙: quarter_end + 45일 ≤ 월말
OOS_FROM = 20240801               # 🚨 frozen OOS — 이 날짜 이후 월말은 v1 에서 잠금
# ── v1.1 restatement (2026-08-16, PM "확실해?" 재검증에서 적발) ────────────────
# 패널 close = 🚨 무수정 종가 실증: 카카오 035720 5:1 분할(2021-04) 498,000→113,500
# = 가짜 −77% 수익률 (실제 시총 +14%). 오염 관측 1,784/202,953 (0.88%, 극단 680).
# 스크린 = 수익률 창에서 |Δln close − Δln mktcap| > CA_SCREEN 이면 그 관측 제외
# (분할·감자·대량증자로 주당 수익률을 신뢰할 수 없음 — 정당한 유증도 걸리지만 보수·정직 방향).
# Q4 채택 규칙 정합: 성과를 바꾸는 bug fix = restatement + 기존 결과 정정 공지.
CA_SCREEN = 0.25
HORIZONS_M = [1, 3, 6, 12]        # forward 지평 (개월)
FACTORS = ["ep", "bp", "dy", "roa", "gross_margin", "cfoa",
           "asset_turnover", "current_ratio", "accrual_inv", "debt_inv"]
N_TRIALS = len(FACTORS) * len(HORIZONS_M)   # 다중검정 N = 40


def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _ymd_to_date(d: int) -> date:
    s = str(d)
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def load_valuation() -> Dict[int, Dict[str, dict]]:
    """{월말 YYYYMMDD: {ticker: row}} — kr_safety_score_full.load_valuation 과 동일 계약."""
    out: Dict[int, Dict[str, dict]] = {}
    with open(VAL_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            out.setdefault(int(r["d"]), {})[str(r["t"])] = r
    return out


def load_fundamental_pit() -> Dict[str, List[Tuple[date, dict]]]:
    """{ticker: [(가용일 = quarter_end+45d, row)] 오름차순} — PIT 매핑용."""
    out: Dict[str, List[Tuple[date, dict]]] = defaultdict(list)
    with open(FUND_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            qe = r.get("quarter_end")
            try:
                y, m, dd = str(qe)[:10].split("-")
                avail = date(int(y), int(m), int(dd)) + timedelta(days=FUND_LAG_DAYS)
            except (ValueError, AttributeError):
                continue
            out[str(r.get("ticker"))].append((avail, r))
    for t in out:
        out[t].sort(key=lambda x: x[0])
    return out


def latest_fund(fund: Dict[str, List[Tuple[date, dict]]], ticker: str, asof: date) -> Optional[dict]:
    """asof 시점에 '가용'한 최신 분기 행 (없으면 None). 선형 탐색 — 분기 수 소(≤46)."""
    rows = fund.get(ticker)
    if not rows:
        return None
    best = None
    for avail, r in rows:
        if avail <= asof:
            best = r
        else:
            break
    return best


def factor_values(vrow: dict, frow: Optional[dict]) -> Dict[str, Optional[float]]:
    """계약의 10팩터 — 패널 필드 그대로, 파생 신설 없음. 방향 = 높을수록 좋게 통일."""
    per = _f(vrow.get("per"))
    pbr = _f(vrow.get("pbr"))
    out: Dict[str, Optional[float]] = {
        "ep": (1.0 / per) if per and per > 0 else None,
        "bp": (1.0 / pbr) if pbr and pbr > 0 else None,
        "dy": _f(vrow.get("div_yield")),
        "roa": None, "gross_margin": None, "cfoa": None,
        "asset_turnover": None, "current_ratio": None,
        "accrual_inv": None, "debt_inv": None,
    }
    if frow:
        out["roa"] = _f(frow.get("roa"))
        out["gross_margin"] = _f(frow.get("gross_margin"))
        ocf, assets = _f(frow.get("operating_cashflow")), _f(frow.get("assets"))
        out["cfoa"] = (ocf / assets) if (ocf is not None and assets and assets > 0) else None
        out["asset_turnover"] = _f(frow.get("asset_turnover"))
        out["current_ratio"] = _f(frow.get("current_ratio"))
        acc = _f(frow.get("accrual_ratio"))
        out["accrual_inv"] = (-acc) if acc is not None else None
        debt = _f(frow.get("debt_ratio"))
        out["debt_inv"] = (-debt) if debt is not None else None
    return out


def spearman(x: List[float], y: List[float]) -> Optional[float]:
    """동순위 평균 랭크 Spearman — scipy 없이. n<30 이면 None (월별 최소선과 별개 안전선)."""
    n = len(x)
    if n < 30:
        return None

    def avg_rank(a: List[float]) -> List[float]:
        idx = sorted(range(n), key=lambda i: a[i])
        rk = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and a[idx[j + 1]] == a[idx[i]]:
                j += 1
            r = (i + j) / 2.0 + 1.0
            for k2 in range(i, j + 1):
                rk[idx[k2]] = r
            i = j + 1
        return rk

    rx, ry = avg_rank(x), avg_rank(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    den = math.sqrt(sum((v - mx) ** 2 for v in rx) * sum((v - my) ** 2 for v in ry))
    return (num / den) if den > 1e-12 else None


def nonoverlap_judge(ic: List[float], step: int) -> Dict[str, Any]:
    """fwd step 개월 IC 시계열(월별) 판정 — alpha_scanner 규약과 동일 (df=k−1·전 오프셋)."""
    n = len(ic)
    if n < 5:
        return {"n": n, "verdict": "표본부족"}
    mu = statistics.mean(ic)
    sd = statistics.stdev(ic)
    t_raw = mu / (sd / math.sqrt(n)) if sd > 1e-9 else 0.0
    k = n // step
    row: Dict[str, Any] = {"ic_mean": round(mu, 5), "n_months": n, "k_independent": k,
                           "t_raw": round(t_raw, 2)}
    if step == 1:
        crit = _t_crit(n - 1)
        # NW(lag=3) 보조 — 월별 IC 시계열 자기상관 대비 (분류는 계약대로 raw, 병기 의무)
        mu2 = mu
        e = [v - mu2 for v in ic]
        s0 = sum(v * v for v in e) / n
        for L in range(1, min(3, n - 1) + 1):
            g = sum(e[t] * e[t - L] for t in range(L, n)) / n
            s0 += 2 * (1 - L / 4) * g
        se_nw = math.sqrt(max(s0, 1e-12) / n)
        t_nw = mu2 / se_nw if se_nw > 0 else 0.0
        ac1 = 0.0
        if n > 2 and statistics.stdev(ic) > 1e-12:
            m0 = statistics.mean(ic)
            num = sum((ic[t] - m0) * (ic[t - 1] - m0) for t in range(1, n))
            den = sum((v - m0) ** 2 for v in ic)
            ac1 = num / den if den > 1e-12 else 0.0
        row.update({"t_nonoverlap": round(t_raw, 2), "t_crit_df": round(crit, 3),
                    "estimable": True, "t_nw_lag3": round(t_nw, 2), "ic_autocorr1": round(ac1, 2),
                    "evidence_class": ("confirmatory" if (abs(t_raw) >= crit and n >= 10)
                                       else "exploratory"),
                    "nw_also_passes": bool(abs(t_nw) >= crit)})
        return row
    if k < 3:
        row.update({"estimable": False, "t_nonoverlap": None, "evidence_class": "unestimable"})
        return row
    ts = []
    for off in range(step):
        sub = ic[off::step]
        if len(sub) >= 3 and statistics.stdev(sub) > 1e-9:
            ts.append(statistics.mean(sub) / (statistics.stdev(sub) / math.sqrt(len(sub))))
    if not ts:
        row.update({"estimable": False, "t_nonoverlap": None, "evidence_class": "unestimable"})
        return row
    t_med = statistics.median(ts)
    crit = _t_crit(k - 1)
    row.update({"t_nonoverlap": round(t_med, 2), "t_crit_df": round(crit, 3), "estimable": True,
                "positive_offset_ratio": round(sum(1 for t in ts if t > 0) / len(ts), 2),
                "evidence_class": ("confirmatory" if (abs(t_med) >= crit and k >= 10)
                                   else "exploratory")})
    return row


def bh_fdr(pairs: List[Tuple[str, float]], q: float = 0.10) -> Dict[str, bool]:
    """Benjamini-Hochberg — (이름, |t|→양측 p 근사) 목록에 대해 통과 여부. 정규 근사."""
    def p_of(t: float) -> float:
        # 양측 정규 근사 (t 분포 대비 관대하지 않게 |t| 큰 쪽만 통과되는 용도)
        z = abs(t)
        return 2.0 * (1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))
    items = sorted(((nm, p_of(t)) for nm, t in pairs), key=lambda x: x[1])
    m = len(items)
    passed_upto = -1
    for i, (_, p) in enumerate(items):
        if p <= q * (i + 1) / m:
            passed_upto = i
    ok = {nm for nm, _ in items[:passed_upto + 1]}
    return {nm: (nm in ok) for nm, _ in pairs}


def run(dry: bool = False) -> Dict[str, Any]:
    val = load_valuation()
    fund = load_fundamental_pit()
    months = sorted(val)
    is_months = [m for m in months if m < OOS_FROM]
    oos_locked = [m for m in months if m >= OOS_FROM]

    # 월별 팩터·수익률 준비
    month_dates = {m: _ymd_to_date(m) for m in months}
    skipped_thin: List[int] = []
    # forward 매핑: months 리스트 인덱스 기준 step 개월 뒤 월말
    idx_of = {m: i for i, m in enumerate(months)}

    ic_series: Dict[Tuple[str, int], List[float]] = defaultdict(list)
    excluded_delist = 0
    excluded_ca = 0
    used_pairs = 0

    for m in is_months:
        rows = val[m]
        if len(rows) < MIN_N_T:
            skipped_thin.append(m)
            continue
        asof = month_dates[m]
        # 팩터 값
        fvals: Dict[str, Dict[str, float]] = {}
        for t, vr in rows.items():
            fr = latest_fund(fund, t, asof)
            fvals[t] = factor_values(vr, fr)
        for step in HORIZONS_M:
            j = idx_of[m] + step
            if j >= len(months):
                continue
            m2 = months[j]
            # 🚨 IS 팩터 → OOS 구간 수익률 참조 금지: 수익률 종료 월말이 OOS 면 제외
            if m2 >= OOS_FROM:
                continue
            fut = val[m2]
            for fac in FACTORS:
                xs, ys = [], []
                for t, vr in rows.items():
                    fv = fvals[t].get(fac)
                    if fv is None:
                        continue
                    c0 = _f(vr.get("close"))
                    r2 = fut.get(t)
                    if r2 is None:
                        excluded_delist += 1
                        continue
                    c1 = _f(r2.get("close"))
                    if not c0 or not c1 or c0 <= 0 or c1 <= 0:
                        continue
                    # v1.1 기업행동 스크린 — 무수정 종가의 가짜 수익률 차단
                    k0, k1 = _f(vr.get("mktcap")), _f(r2.get("mktcap"))
                    if k0 and k1 and k0 > 0 and k1 > 0:
                        if abs(math.log(c1 / c0) - math.log(k1 / k0)) > CA_SCREEN:
                            excluded_ca += 1
                            continue
                    else:
                        excluded_ca += 1   # 시총 결측 = 검증 불가 → 제외 (보수)
                        continue
                    xs.append(fv)
                    ys.append((c1 - c0) / c0)
                ic = spearman(xs, ys)
                if ic is not None:
                    ic_series[(fac, step)].append(ic)
                    used_pairs += len(xs)

    # 판정
    results: Dict[str, Dict[str, Any]] = {f: {} for f in FACTORS}
    t_for_fdr: List[Tuple[str, float]] = []
    for (fac, step), ser in ic_series.items():
        r = nonoverlap_judge(ser, step)
        results[fac][f"fwd{step}m"] = r
        if r.get("estimable") and r.get("t_nonoverlap") is not None:
            t_for_fdr.append((f"{fac}|{step}", r["t_nonoverlap"]))
    fdr = bh_fdr(t_for_fdr, q=0.10)
    for (fac, step), _ in ic_series.items():
        key = f"{fac}|{step}"
        if key in fdr:
            results[fac][f"fwd{step}m"]["bh_fdr_pass_q10"] = fdr[key]

    n_is = len([m for m in is_months if len(val[m]) >= MIN_N_T])
    payload = {
        "_meta": {
            "artifact": "factor_engine_kr_v1.1",
            "generated_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "contract": "docs/FACTOR_ENGINE_DESIGN_2026_08_16.md",
            "score_system": {"name": "factor_engine_kr_v1", "is_operational": False,
                             "note": "연구 전용 — 운영 가중·게이트에 미연결. 반영은 별도 사전등록"},
            "universe": f"kr_valuation_panel 월말 전량 (N_t≥{MIN_N_T}, 유동성 필터 없음 — microcap 포함 한계)",
            "pit": f"밸류=패널 내장 stale_days · 재무=quarter_end+{FUND_LAG_DAYS}d 가용 규칙",
            "frozen_oos": {"locked_from": OOS_FROM, "locked_months": len(oos_locked),
                           "note": "개봉 = 합침/폐기 결정 시 1회 (§7-3b)"},
            "known_limitations": [
                f"상폐 실현손실 미반영 — 소멸 종목은 지평 제외 (제외 관측 {excluded_delist:,}건). quality/value IC 과대 위험",
                f"🚨 v1.1 restatement: 패널 close = 무수정 종가 (카카오 5:1 실증) — 기업행동 스크린 |dln c − dln mc|>{CA_SCREEN} 로 {excluded_ca:,}관측 제외. v1.0 결과는 이 오염 포함이라 폐기",
                "유동성/거래대금 필터 없음 — microcap 비중 미통제",
                "fwd12m 은 IS 내 k≈4 — 설계상 exploratory 고정",
            ],
            "n_trials": N_TRIALS,
            "min_detectable_note": f"fwd1m IS T={n_is - 1}개월급 — |t|=2 검출하한 IC ≈ 2σ_IC/√T",
            "thin_months_skipped": skipped_thin,
        },
        "is_months_used": n_is,
        "is_range": [is_months[0] if is_months else None,
                     max(m for m in is_months if m < OOS_FROM) if is_months else None],
        "observations_used": used_pairs,
        "factors": results,
    }

    # 출력 표
    print(f"IS 월말 {n_is} ({payload['is_range'][0]}~{payload['is_range'][1]}) · "
          f"OOS 잠금 {len(oos_locked)}개월 · 시도 {N_TRIALS} · 관측 {used_pairs:,}")
    print(f"\n{'팩터':16}" + "".join(f"{'fwd'+str(h)+'m':>24}" for h in HORIZONS_M))
    print(f"{'':16}" + "".join(f"{'IC t_no k cls FDR':>24}" for _ in HORIZONS_M))
    print("-" * 114)
    for fac in FACTORS:
        line = f"{fac:16}"
        for h in HORIZONS_M:
            r = results[fac].get(f"fwd{h}m")
            if not r or r.get("verdict") == "표본부족":
                line += f"{'—':>24}"
                continue
            cls = {"confirmatory": "C", "exploratory": "E", "unestimable": "U"}.get(
                r.get("evidence_class", "?"), "?")
            fd = "F" if r.get("bh_fdr_pass_q10") else "·"
            tn = r.get("t_nonoverlap")
            line += (f"{r['ic_mean']:+7.3f}{(tn if tn is not None else 0):+7.2f}"
                     f"{r['k_independent']:>4}{cls:>3}{fd:>2}")
        print(line)

    conf = [(f, h) for f in FACTORS for h in HORIZONS_M
            if results[f].get(f"fwd{h}m", {}).get("evidence_class") == "confirmatory"]
    conf_fdr = [(f, h) for f, h in conf if results[f][f"fwd{h}m"].get("bh_fdr_pass_q10")]
    print(f"\nconfirmatory {len(conf)}/{N_TRIALS} · 그중 BH-FDR(q=0.10) 통과 {len(conf_fdr)}")
    for f, h in conf_fdr:
        r = results[f][f"fwd{h}m"]
        print(f"  ✅ {f:16} fwd{h}m  IC {r['ic_mean']:+.3f}  t {r['t_nonoverlap']:+.2f} "
              f"(임계 {r['t_crit_df']})  k={r['k_independent']}")

    if not dry:
        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        json.dump(payload, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        # experiment registry (append-only)
        try:
            commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                             text=True).strip()
        except Exception:
            commit = "unknown"
        reg = {"ts_kst": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
               "run": "factor_engine_kr_v1", "commit": commit,
               "params": {"factors": FACTORS, "horizons_m": HORIZONS_M, "min_nt": MIN_N_T,
                          "fund_lag_days": FUND_LAG_DAYS, "oos_from": OOS_FROM},
               "n_trials": N_TRIALS, "is_months": n_is,
               "confirmatory": len(conf), "fdr_pass": len(conf_fdr)}
        with open(REG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        print(f"\n기록 → {OUT_PATH} · registry append → {REG_PATH}")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    run(dry=a.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
