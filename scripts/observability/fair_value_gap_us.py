"""fair_value_gap_us — US(Sharadar) RIM V/P fair-value 관측. KR fair_value_gap 의 US 커버리지 확장.

기존 사전등록(2026-06-17, C-fv, memory project_observation_scoring_prereg_queue)의 **US 확장**.
동일 산식(RIM V/P, Frankel-Lee 1998)을 Sharadar SF1(ART, PIT)에 적용 — 새 산식 아님.
공용 `rim_value()`(api.observability.fair_value_gap) 를 그대로 import → KR/US 산식 단일 출처(drift 0).

🚨 관측 ONLY, 점수 wire 0. 검증 = 1/2/3년 forward IC(2-3년 핵심) 통과 후 PM 승인+단일조정(RULE 7).
🚨 컴플라이언스: Sharadar 라이선스 = own-use. 산출 jsonl = 내부 관측 trail. 공개 표면/재배포 금지.
🚨 PIT(look-ahead 0): 재무 = 종목별 최신 ART row(datekey), 가격 = 그 이후 실제 시장가(SEP 최신 종가).
🚨 가격 앵커 = SEP 최신 종가(px_date 기록), **SF1.price 아님** — SF1.price 는 filing 시점 고정값(현재가 아님,
   실측 4~9% 괴리). forward-IC 검증이 px_date 기준 전방수익률을 붙일 수 있게 px_date 를 per-ticker 기록.

파라미터(1회 등록·무튜닝, RULE 7):
  R_E_US = 0.088  — 미 10y rf ~4.2% + ERP ~4.6% (KR 0.085 와 동일 구조, 시장 hurdle 차이만).
  OMEGA  = 0.62   — KR 과 동일(Dechow-Hutton-Sloan 1999). 공용 상수 재사용.
  universe = SF1 ART 최신 PIT · marketcap 상위 UNIV_CAP(=3000). small-cap 확장 = v1(문서화된 cap, silent 아님).
  주당 기반 = BVPS/EPS + SEP 종가 (SF1 stale ratio·stale price 미사용 = KR self-consistent 철학 정합).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

import duckdb

# repo root 를 path 에 추가 → api.* import (산식 단일 출처)
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)
from api.config import DATA_DIR, now_kst  # noqa: E402
from api.observability.fair_value_gap import OMEGA, _append, rim_value  # noqa: E402

DB = os.path.expanduser("~/VERITY_data_lake/sharadar.duckdb")
OUT = os.path.join(DATA_DIR, "observations", "fair_value_gap_us.jsonl")

R_E_US = 0.088          # 미 자기자본비용 (rf ~4.2% + ERP ~4.6%). 1회 등록·무튜닝.
UNIV_CAP = 3000         # marketcap 상위 N (문서화된 bound, small-cap 확장=v1).


def _latest_snapshot(con, cap: int):
    """종목별 최신 ART(PIT) 재무 + 최신 SEP 종가(현재 시장가) 조인. marketcap 상위 cap.
    가격 = SF1.price(filing 고정) 아님, 레이크 최신 SEP 종가(px_date). SEP 는 max(date)-14d 로 bound(고속)."""
    return con.execute(
        """
        WITH px AS (
            SELECT ticker, close AS price, date AS px_date FROM (
                SELECT ticker, close, date,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) rn
                FROM SEP WHERE date >= (SELECT max(date) FROM SEP) - INTERVAL 14 DAY
            ) WHERE rn=1
        ),
        fund AS (
            SELECT ticker, datekey, bvps, eps, fcfps, marketcap FROM (
                SELECT ticker, datekey, bvps, eps, fcfps, marketcap,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY datekey DESC) rn
                FROM SF1 WHERE dimension='ART' AND datekey IS NOT NULL
            ) WHERE rn=1 AND bvps>0 AND eps IS NOT NULL AND marketcap>0
        )
        SELECT f.ticker, f.datekey, f.bvps, f.eps, f.fcfps, p.price, p.px_date
        FROM fund f JOIN px p USING(ticker)
        WHERE p.price > 0
        ORDER BY f.marketcap DESC LIMIT ?
        """,
        [cap],
    ).fetchdf()


def _compute_one(row, r_e: float = R_E_US) -> dict:
    """단일 종목 RIM V/P. 가격=SEP 최신 종가(현재가). roe_frac=EPS/BVPS(raw, stale roe 미사용)."""
    bvps = float(row.bvps)
    eps = float(row.eps)
    price = float(row.price)                    # SEP 최신 종가 (현재 시장가, SF1.price 아님)
    rim_v = rim_value(bvps, eps, r_e)          # 공용 헬퍼 (KR 과 동일 산식)
    v_over_p = rim_v / price                    # V_ps / 현재가 = V/시총 (scale-invariant)
    roe_frac = eps / bvps                        # book 대비 이익 = ROE (self-consistent)

    fcfps = row.fcfps
    fy = (float(fcfps) / price) if (fcfps is not None and fcfps == fcfps and float(fcfps) > 0) else None
    implied_g = ((r_e - fy) / (1 + fy)) if fy is not None else None

    return {
        "ticker": str(row.ticker),
        "roe_frac": round(roe_frac, 4),
        "r_e": r_e,
        "rim_v_over_p": round(v_over_p, 3),          # >1 저평가, <1 고평가
        "pbr_derived": round(price / bvps, 2),        # = PB(현재가 기준), stale 필드 대신 역산
        "implied_g": round(implied_g, 4) if implied_g is not None else None,
        "value_trap_candidate": roe_frac < r_e,       # ROE<r_e ⇒ V<BV (저PBR≠쌈)
        "is_high_growth": roe_frac > 0.20,            # 1-stage RIM 저평가 가능(터미널 미반영)
        "px_date": str(row.px_date)[:10],             # 가격 앵커일 (forward-IC 전방수익률 기준)
    }


def run(cap: int = UNIV_CAP, r_e: float = R_E_US, path: str | None = None, dry: bool = False) -> dict:
    target = path or OUT
    con = duckdb.connect(DB, read_only=True)
    try:
        df = _latest_snapshot(con, cap)
    finally:
        con.close()

    per: dict = {}
    for row in df.itertuples(index=False):
        try:
            rec = _compute_one(row, r_e)
        except Exception as e:  # noqa: BLE001
            print(f"[fvg_us] {getattr(row, 'ticker', '?')} 실패: {e}")
            continue
        if rec["ticker"]:
            per[rec["ticker"]] = rec

    if not per:
        return {"tickers": 0, "logged": False}

    now = now_kst()
    n_under = sum(1 for v in per.values() if v["rim_v_over_p"] > 1)
    n_trap = sum(1 for v in per.values() if v["value_trap_candidate"])
    n_hg = sum(1 for v in per.values() if v["is_high_growth"])
    price_asof = max(v["px_date"] for v in per.values())   # 레이크 가격 앵커일 (forward-IC 기준)
    snapshot = {
        "observed_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "date": now.strftime("%Y-%m-%d"),
        "price_asof": price_asof,          # 🚨 전방수익률 앵커 = 이 날짜(레이크 최신 SEP), observed_at 아님
        "market": "us",
        "n_tickers": len(per),
        "n_undervalued_vp_gt_1": n_under,
        "n_value_trap_candidate": n_trap,
        "n_high_growth": n_hg,
        "r_e": r_e,
        "univ_cap": cap,
        "per_ticker": per,
        "spec": "fair_value_gap_us_v0_observation",
        "_note": ("US 확장 관측 only, 점수 wire 0. RIM V/P(Frankel-Lee) 공용산식(KR 과 동일 rim_value). "
                  "재무=SF1 ART PIT(datekey), 가격=SEP 최신 종가(price_asof, SF1.price 고정값 아님). "
                  "검증 = px_date 기준 1/2/3년 forward IC(2-3년 핵심), ~2028-29. Sharadar own-use — 내부 관측 "
                  "trail, 공개/재배포 금지. RULE 7 — 점수화는 검증 후 사전등록+PM승인+단일조정."),
    }
    if dry:
        return {"tickers": len(per), "undervalued": n_under, "value_trap": n_trap,
                "high_growth": n_hg, "logged": False, "dry": True}
    logged = _append(snapshot, target)
    return {"tickers": len(per), "undervalued": n_under, "value_trap": n_trap,
            "high_growth": n_hg, "logged": logged}


def _commit_private(push: bool = True) -> None:
    """관측 jsonl 을 .git-private(비공개 repo)에 커밋. 🚨 Sharadar own-use →
    공개 main 차단(.gitignore) + private 만 -f 추적 (smallcap_corner_ic_history 패턴 정합).
    KR fair_value_gap.jsonl(DART 공개데이터)은 public, US(Sharadar)는 private — 트랙 분리."""
    gd = os.path.join(REPO, ".git-private")
    rel = os.path.relpath(OUT, REPO)
    base = ["git", f"--git-dir={gd}", f"--work-tree={REPO}"]
    subprocess.call(base + ["add", "-f", rel], cwd=REPO)
    if subprocess.call(base + ["diff", "--cached", "--quiet", "--", rel], cwd=REPO) == 0:
        print("[fvg_us] 변경 없음 — commit skip")
        return
    subprocess.call(base + ["commit", "-m",
                    "data(fvg_us): US RIM V/P 관측 append (비공개·own-use·점수 held ~2028)"], cwd=REPO)
    if push:
        subprocess.call(base + ["push"], cwd=REPO)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="US Sharadar RIM V/P fair-value 관측 스냅샷")
    ap.add_argument("--cap", type=int, default=UNIV_CAP, help="marketcap 상위 N")
    ap.add_argument("--dry-run", action="store_true", help="append 안 함(집계만)")
    ap.add_argument("--no-push", action="store_true", help="private 커밋 후 push 생략")
    ap.add_argument("--no-commit", action="store_true", help="private repo 커밋 생략(로컬 append 만)")
    args = ap.parse_args()
    res = run(cap=args.cap, dry=args.dry_run)
    print(f"[fvg_us] {res}")
    if not args.dry_run and not args.no_commit and res.get("logged"):
        _commit_private(push=not args.no_push)
