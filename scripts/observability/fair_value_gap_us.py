"""fair_value_gap_us — US RIM V/P fair-value 관측. KR fair_value_gap 의 US 확장. **무료 소스 전용**.

기존 사전등록(2026-06-17, C-fv, memory project_observation_scoring_prereg_queue)의 US 확장.
동일 산식(RIM V/P, Frankel-Lee 1998)을 **무료 소스**에 적용 — 새 산식 아님.
공용 `rim_value()`(api.observability.fair_value_gap) 를 import → KR/US 산식 단일 출처(drift 0).

🚨 데이터 소스 = 전부 무료·기존 파이프라인 (Sharadar $79/월 구독 **불요**, 2026-07-08 전환):
  재무 = SEC EDGAR (public domain) `data/us_financials/<ticker>.json` (stockholders_equity/net_income/
         diluted_shares/derived.fcf_usd). 밸런스=최신(연·분기), 플로우(NI)=연간 스케일.
  가격 = `~/VERITY_data_lake/us_prices.duckdb` ohlcv (무료 레이크, SP1500, Sharadar 6/12보다 신선).
  universe = us_prices ∩ EDGAR (SP1500 ~1500).

🚨 관측 ONLY, 점수 wire 0. 검증 = px_date 기준 1/2/3년 forward IC(2-3년 핵심) 통과 후 PM 승인+단일조정(RULE 7).
🚨 PIT: 재무=필링 종료일(bv_asof) 기준 최신, 가격=us_prices 최신 종가(px_date). forward-IC 는 px_date 앵커.
🚨 지속: EDGAR own-source·public domain. 관측 trail 은 held-2028(RULE 7) 라 .git-private 유지(보수적).

파라미터(1회 등록·무튜닝, RULE 7):
  R_E_US = 0.088  — 미 10y rf ~4.2% + ERP ~4.6% (KR 0.085 와 동일 구조). OMEGA=0.62 (KR 공용).
  RIM V/P = rim_value(stockholders_equity, net_income) / (diluted_shares × 종가). roe=NI/equity(self-consistent).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Optional, Tuple

import duckdb

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)
from api.config import DATA_DIR, now_kst  # noqa: E402
from api.observability.fair_value_gap import OMEGA, _append, rim_value  # noqa: E402

EDGAR_DIR = os.path.join(DATA_DIR, "us_financials")
US_PRICES_DB = os.path.expanduser("~/VERITY_data_lake/us_prices.duckdb")
OUT = os.path.join(DATA_DIR, "observations", "fair_value_gap_us.jsonl")

R_E_US = 0.088          # 미 자기자본비용 (rf ~4.2% + ERP ~4.6%). 1회 등록·무튜닝.


def _latest(series_a: dict, series_q: dict, tag: str, annual: bool = False) -> Tuple[Optional[float], Optional[str]]:
    """태그의 최신값(end 기준). annual=True 면 연간(FY)만 — 플로우(NI/OCF)는 연간 스케일 필수."""
    recs = list(series_a.get(tag, []))
    if not annual:
        recs = recs + list(series_q.get(tag, []))
    recs = [r for r in recs if r.get("val") is not None and r.get("end")]
    if not recs:
        return None, None
    r = max(recs, key=lambda x: x["end"])
    return float(r["val"]), r["end"]


def _latest_prices(con) -> dict:
    """us_prices 최신 종가 per ticker (max(date)-10d bound). {ticker: (close, date)}."""
    rows = con.execute(
        """
        SELECT ticker, close, date FROM (
            SELECT ticker, close, date, ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY date DESC) rn
            FROM ohlcv WHERE date >= (SELECT max(date) FROM ohlcv) - INTERVAL 10 DAY
        ) WHERE rn=1 AND close > 0
        """
    ).fetchall()
    return {str(r[0]): (float(r[1]), str(r[2])[:10]) for r in rows}


def _compute_one(ticker: str, ej: dict, price: float, px_date: str, r_e: float = R_E_US) -> Optional[dict]:
    """RIM V/P = rim_value(equity, NI) / (shares × 종가). 밸런스=최신, NI=연간, roe=NI/equity(self-consistent)."""
    a = ej.get("series_annual", {}) or {}
    q = ej.get("series_quarterly", {}) or {}
    equity, eq_end = _latest(a, q, "stockholders_equity")     # 최신 밸런스(연·분기 중 최신)
    shares, _ = _latest(a, q, "diluted_shares")
    ni, _ = _latest(a, q, "net_income", annual=True)          # 연간 스케일(분기 단일값 금지)
    if equity is None or shares is None or ni is None:
        return None
    if equity <= 0 or shares <= 0 or price <= 0:
        return None

    mktcap = shares * price
    rim_v = rim_value(equity, ni, r_e)          # 공용 헬퍼 (KR 과 동일 산식)
    v_over_p = rim_v / mktcap                    # V / 시총
    roe_frac = ni / equity                        # NI/BV = ROE (self-consistent)

    fcf = ej.get("derived", {}).get("fcf_usd")
    fy = (float(fcf) / mktcap) if (fcf is not None and mktcap > 0) else None
    implied_g = ((r_e - fy) / (1 + fy)) if fy is not None else None

    return {
        "ticker": ticker,
        "roe_frac": round(roe_frac, 4),
        "r_e": r_e,
        "rim_v_over_p": round(v_over_p, 3),          # >1 저평가, <1 고평가
        "pbr_derived": round(mktcap / equity, 2),     # = PB(현재가 기준)
        "implied_g": round(implied_g, 4) if implied_g is not None else None,
        "value_trap_candidate": roe_frac < r_e,       # ROE<r_e ⇒ V<BV (저PBR≠쌈)
        "is_high_growth": roe_frac > 0.20,            # 1-stage RIM 저평가 가능(터미널 미반영)
        "is_financial": bool(ej.get("meta", {}).get("is_financial")),  # 은행/보험=RIM 부적합 플래그
        "bv_asof": eq_end,                            # 밸런스 필링 종료일 (PIT)
        "px_date": px_date,                           # 가격 앵커일 (forward-IC 기준)
    }


def run(r_e: float = R_E_US, path: Optional[str] = None, dry: bool = False) -> dict:
    target = path or OUT
    con = duckdb.connect(US_PRICES_DB, read_only=True)
    try:
        prices = _latest_prices(con)
    finally:
        con.close()

    per: dict = {}
    n_no_edgar = 0
    for ticker, (price, px_date) in prices.items():
        ef = os.path.join(EDGAR_DIR, f"{ticker}.json")
        if not os.path.exists(ef):
            n_no_edgar += 1
            continue
        try:
            with open(ef, encoding="utf-8") as fh:
                ej = json.load(fh)
            rec = _compute_one(ticker, ej, price, px_date, r_e)
        except Exception as e:  # noqa: BLE001
            print(f"[fvg_us] {ticker} 실패: {e}")
            continue
        if rec:
            per[ticker] = rec

    if not per:
        return {"tickers": 0, "logged": False, "no_edgar": n_no_edgar}

    now = now_kst()
    n_under = sum(1 for v in per.values() if v["rim_v_over_p"] > 1)
    n_trap = sum(1 for v in per.values() if v["value_trap_candidate"])
    n_hg = sum(1 for v in per.values() if v["is_high_growth"])
    price_asof = max(v["px_date"] for v in per.values())    # 레이크 가격 앵커일
    snapshot = {
        "observed_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "date": now.strftime("%Y-%m-%d"),
        "price_asof": price_asof,          # 🚨 forward-IC 앵커 = 이 날짜(us_prices 최신), observed_at 아님
        "market": "us",
        "source": "edgar+us_prices",       # 무료 소스 (Sharadar 아님)
        "n_tickers": len(per),
        "n_undervalued_vp_gt_1": n_under,
        "n_value_trap_candidate": n_trap,
        "n_high_growth": n_hg,
        "r_e": r_e,
        "per_ticker": per,
        "spec": "fair_value_gap_us_v0_observation",
        "_note": ("US 확장 관측 only, 점수 wire 0. RIM V/P(Frankel-Lee) 공용산식(KR 과 동일 rim_value). "
                  "재무=SEC EDGAR(밸런스 최신·NI 연간), 가격=us_prices 최신 종가(price_asof). 둘 다 무료 소스"
                  "(Sharadar 구독 불요). 검증 = px_date 기준 1/2/3년 forward IC(2-3년 핵심), ~2028-29. "
                  "관측 trail held-2028(.git-private). RULE 7 — 점수화는 검증 후 사전등록+PM승인+단일조정."),
    }
    if dry:
        return {"tickers": len(per), "undervalued": n_under, "value_trap": n_trap,
                "high_growth": n_hg, "no_edgar": n_no_edgar, "logged": False, "dry": True}
    logged = _append(snapshot, target)
    return {"tickers": len(per), "undervalued": n_under, "value_trap": n_trap,
            "high_growth": n_hg, "no_edgar": n_no_edgar, "logged": logged}


def _commit_private(push: bool = True) -> None:
    """관측 jsonl 을 .git-private(비공개 repo)에 커밋. held-2028(RULE 7) 관측 trail →
    공개 main 차단(.gitignore) + private 만 -f 추적 (smallcap_corner_ic_history 패턴 정합).
    소스는 무료(EDGAR public domain)이나 미검증 관측이라 보수적으로 비공개 유지."""
    gd = os.path.join(REPO, ".git-private")
    rel = os.path.relpath(OUT, REPO)
    base = ["git", f"--git-dir={gd}", f"--work-tree={REPO}"]
    subprocess.call(base + ["add", "-f", rel], cwd=REPO)
    if subprocess.call(base + ["diff", "--cached", "--quiet", "--", rel], cwd=REPO) == 0:
        print("[fvg_us] 변경 없음 — commit skip")
        return
    subprocess.call(base + ["commit", "-m",
                    "data(fvg_us): US RIM V/P 관측 append (EDGAR+us_prices, 비공개·held ~2028)"], cwd=REPO)
    if push:
        subprocess.call(base + ["push"], cwd=REPO)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="US EDGAR+us_prices RIM V/P fair-value 관측 스냅샷")
    ap.add_argument("--dry-run", action="store_true", help="append 안 함(집계만)")
    ap.add_argument("--no-push", action="store_true", help="private 커밋 후 push 생략")
    ap.add_argument("--no-commit", action="store_true", help="private repo 커밋 생략(로컬 append 만)")
    args = ap.parse_args()
    res = run(dry=args.dry_run)
    print(f"[fvg_us] {res}")
    if not args.dry_run and not args.no_commit and res.get("logged"):
        _commit_private(push=not args.no_push)
