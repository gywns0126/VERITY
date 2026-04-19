"""
DART KR Fundamental Backfill — 한국 종목 펀더멘털 historical IC 측정.

목적
----
VERITY Brain 의 한국 종목 검증 사각지대 해소.
- US 종목: yfinance + backfill_replay 로 IC 측정 완료
- KR 종목: 기존 검증 0% → DART 공시 데이터로 historical 펀더멘털 재구성

스코프 (Phase 1)
--------------
- ticker universe: 기존 portfolio 의 KR 30 large-cap (KOSPI/KOSDAQ)
- 기간: 2015~2024 (10년, 연간 사업보고서)
- 데이터: DART fnlttSinglAcnt.json → BS/IS/CF 핵심 계정
- 후속 수익률: yfinance .KS/.KQ 공시시점(결산+90일) +30d forward
- Factor IC: debt_ratio / roe / operating_margin / revenue_growth

Phase 2 (미래)
-------------
- 분기보고서 (11012/11013/11014) 추가
- FCF, dividend, 내부자 거래 등 factor 확장
- historical_replay.py KR 통합

사용
----
  python scripts/dart_kr_backfill.py             # smoke (3종목 × 3년)
  python scripts/dart_kr_backfill.py --full      # 30종목 × 10년 (~5분)
  python scripts/dart_kr_backfill.py --tickers 005930,000660 --years 2020,2021

캐싱
----
  data/dart_kr_cache/{corp_code}_{year}.json — DART 응답 raw
  → 재실행 시 API 호출 생략 (DART 쿼터 보호)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# 프로젝트 루트 추가
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from api.config import DART_API_KEY, DATA_DIR
from api.collectors.dart_corp_code import get_corp_code
from api.collectors.DartScout import _call as _dart_call

# yfinance 는 optional — 없으면 IC 계산 생략
try:
    import yfinance as yf
    _HAS_YF = True
except ImportError:
    _HAS_YF = False


CACHE_DIR = os.path.join(DATA_DIR, "dart_kr_cache")
OUT_BACKFILL = os.path.join(DATA_DIR, "dart_kr_backfill_result.json")
OUT_IC = os.path.join(DATA_DIR, "dart_kr_ic_result.json")

DEFAULT_SMOKE_TICKERS = ["005930", "000660", "035420"]  # 삼성, 하이닉스, NAVER
DEFAULT_FULL_TICKERS_PATH = "/tmp/kr_tickers.json"  # 30 KR from portfolio

DEFAULT_START_YEAR = 2015
DEFAULT_END_YEAR = 2024

FORWARD_HOLD_DAYS = 30
DISCLOSURE_LAG_DAYS = 90  # 사업연도 종료 후 공시 마감 (실제 시장 반응 시점 proxy)

IC_NOISE_THRESHOLD = 0.03

os.makedirs(CACHE_DIR, exist_ok=True)


# ─── DART fetch + cache ────────────────────────────────────


def _cache_path(corp_code: str, year: str) -> str:
    return os.path.join(CACHE_DIR, f"{corp_code}_{year}.json")


def fetch_dart_financials(corp_code: str, year: str) -> Optional[Dict[str, Any]]:
    """DART 연간 재무 원본. 캐시 우선."""
    cp = _cache_path(corp_code, year)
    if os.path.exists(cp):
        try:
            with open(cp, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    try:
        data = _dart_call("fnlttSinglAcnt.json", {
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": "11011",  # 사업보고서
        })
    except Exception as e:
        print(f"    [WARN] DART call failed {corp_code} {year}: {e}", file=sys.stderr)
        return None
    # 캐시 저장
    try:
        with open(cp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass
    return data


def _parse_int_safe(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    s = str(v).replace(",", "").replace(" ", "").strip()
    if not s or s in ("-", "N/A"):
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def extract_fundamentals(dart_data: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """DART 응답 → {revenue, operating_profit, net_income, total_assets, total_liab, equity}."""
    if not dart_data or dart_data.get("status") not in ("000", None):
        # status 013 = 조회된 데이타 없음, 020 = 사용한도 초과 등
        return {}

    result: Dict[str, Optional[float]] = {
        "revenue": None,           # 매출액
        "operating_profit": None,  # 영업이익
        "net_income": None,        # 당기순이익
        "total_assets": None,      # 자산총계
        "total_liab": None,        # 부채총계
        "equity": None,            # 자본총계
    }

    # 계정명 매핑 (DART 표기 다양성 대응 — 연결/별도 모두 수용)
    acct_map = {
        "매출액": "revenue",
        "수익(매출액)": "revenue",
        "영업수익": "revenue",
        "영업이익": "operating_profit",
        "영업이익(손실)": "operating_profit",
        "당기순이익": "net_income",
        "당기순이익(손실)": "net_income",
        "자산총계": "total_assets",
        "부채총계": "total_liab",
        "자본총계": "equity",
    }

    # CFS(연결) 우선, OFS(별도) fallback
    items_cfs = [i for i in dart_data.get("list", []) if i.get("fs_div") == "CFS"]
    items_ofs = [i for i in dart_data.get("list", []) if i.get("fs_div") == "OFS"]
    items = items_cfs if items_cfs else items_ofs

    for item in items:
        acct = item.get("account_nm", "").strip()
        key = acct_map.get(acct)
        if key and result[key] is None:  # 첫 매치만 (중복 계정 방지)
            result[key] = _parse_int_safe(item.get("thstrm_amount"))

    return result


def compute_factors(current: Dict[str, Optional[float]],
                    previous: Optional[Dict[str, Optional[float]]]) -> Dict[str, Optional[float]]:
    """재무 raw → 4 factor (debt_ratio, roe, op_margin, rev_growth)."""
    out: Dict[str, Optional[float]] = {
        "debt_ratio_pct": None,
        "roe_pct": None,
        "operating_margin_pct": None,
        "revenue_growth_pct": None,
    }
    ta = current.get("total_assets")
    tl = current.get("total_liab")
    eq = current.get("equity")
    ni = current.get("net_income")
    rv = current.get("revenue")
    op = current.get("operating_profit")

    if tl is not None and eq is not None and eq > 0:
        out["debt_ratio_pct"] = round(tl / eq * 100, 2)
    if ni is not None and eq is not None and eq > 0:
        out["roe_pct"] = round(ni / eq * 100, 2)
    if op is not None and rv is not None and rv > 0:
        out["operating_margin_pct"] = round(op / rv * 100, 2)
    if previous and rv is not None:
        prv = previous.get("revenue")
        if prv is not None and prv > 0:
            out["revenue_growth_pct"] = round((rv - prv) / prv * 100, 2)
    return out


# ─── 후속 수익률 (yfinance .KS) ──────────────────────────────


_YF_CACHE: Dict[str, Optional[pd.DataFrame]] = {}


def _yf_ticker(kr_code: str) -> str:
    """6자리 코드 → yfinance ticker. KOSDAQ/KOSPI 구분 없이 .KS 우선, .KQ fallback."""
    return f"{kr_code}.KS"


def fetch_price_history_yf(kr_code: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """yfinance .KS/.KQ 가격 history (캐시 메모리)."""
    if not _HAS_YF:
        return None
    key = f"{kr_code}_{start}_{end}"
    if key in _YF_CACHE:
        return _YF_CACHE[key]
    for suffix in (".KS", ".KQ"):
        try:
            t = yf.Ticker(f"{kr_code}{suffix}")
            df = t.history(start=start, end=end, auto_adjust=True)
            if df is not None and not df.empty and len(df) >= 10:
                df.index = pd.to_datetime(df.index).tz_localize(None)
                _YF_CACHE[key] = df
                return df
        except Exception:
            continue
    _YF_CACHE[key] = None
    return None


def forward_return_at_disclosure(df: pd.DataFrame, fiscal_year: int) -> Optional[float]:
    """사업연도 결산일(12/31) + DISCLOSURE_LAG_DAYS 시점부터 FORWARD_HOLD_DAYS 후 수익률."""
    if df is None or df.empty:
        return None
    # 결산일 + 공시lag = 실제 시장 반응 시점
    base_date = datetime(fiscal_year, 12, 31) + timedelta(days=DISCLOSURE_LAG_DAYS)
    # base_date 이후 첫 거래일 (asof)
    try:
        idx_series = pd.Series(df.index, index=df.index)
        ge = idx_series[idx_series >= base_date]
        if ge.empty:
            return None
        base_ts = ge.iloc[0]
        exit_date = base_ts + timedelta(days=FORWARD_HOLD_DAYS)
        ge_exit = idx_series[idx_series >= exit_date]
        if ge_exit.empty:
            return None
        exit_ts = ge_exit.iloc[0]
        base_p = float(df.loc[base_ts, "Close"])
        exit_p = float(df.loc[exit_ts, "Close"])
        if base_p <= 0:
            return None
        return (exit_p - base_p) / base_p * 100
    except Exception:
        return None


# ─── 메인 backfill 루프 ─────────────────────────────────────


def backfill_ticker(ticker: str, name: str,
                    start_year: int, end_year: int) -> List[Dict[str, Any]]:
    """단일 ticker × 연도 범위 → (factor, forward_return) 레코드."""
    corp_code = get_corp_code(ticker)
    if not corp_code:
        print(f"    [SKIP] {ticker} {name}: corp_code 미매핑")
        return []

    # 가격 history 한번에 fetch (start_year-1 부터 end_year+2)
    px_start = f"{start_year - 1}-01-01"
    px_end = f"{end_year + 2}-01-01"
    px_df = fetch_price_history_yf(ticker, px_start, px_end)

    rows: List[Dict[str, Any]] = []
    prev_fund: Optional[Dict[str, Optional[float]]] = None
    for year in range(start_year, end_year + 1):
        raw = fetch_dart_financials(corp_code, str(year))
        if not raw or raw.get("status") not in ("000", None):
            prev_fund = None
            continue
        fund = extract_fundamentals(raw)
        if not any(v is not None for v in fund.values()):
            prev_fund = None
            continue
        factors = compute_factors(fund, prev_fund)

        fwd = forward_return_at_disclosure(px_df, year) if px_df is not None else None

        rows.append({
            "ticker": ticker, "name": name, "corp_code": corp_code,
            "fiscal_year": year,
            "fundamentals": fund,
            "factors": factors,
            "forward_30d_return_pct": round(fwd, 3) if fwd is not None else None,
        })
        prev_fund = fund

    return rows


def compute_factor_ic(all_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """4 factor × forward_30d return IC (Pearson + Spearman)."""
    factor_keys = ["debt_ratio_pct", "roe_pct", "operating_margin_pct", "revenue_growth_pct"]
    usable = [
        r for r in all_rows
        if r.get("forward_30d_return_pct") is not None
        and any(r["factors"].get(k) is not None for k in factor_keys)
    ]
    if len(usable) < 20:
        return {"status": "insufficient_data", "n": len(usable)}

    df = pd.DataFrame([
        {"forward_ret": r["forward_30d_return_pct"], **r["factors"]}
        for r in usable
    ])
    out: Dict[str, Any] = {"status": "ok", "n": len(df), "components": {}}
    for k in factor_keys:
        x = df[k].astype(float)
        y = df["forward_ret"].astype(float)
        mask = x.notna() & y.notna()
        if mask.sum() < 10:
            out["components"][k] = {"pearson": None, "spearman": None,
                                     "n": int(mask.sum()), "is_noise": True}
            continue
        try:
            p = float(x[mask].corr(y[mask], method="pearson"))
            s = float(x[mask].corr(y[mask], method="spearman"))
        except Exception:
            p, s = None, None
        is_noise = (
            (p is None or abs(p) < IC_NOISE_THRESHOLD) and
            (s is None or abs(s) < IC_NOISE_THRESHOLD)
        )
        out["components"][k] = {
            "pearson": round(p, 4) if p is not None else None,
            "spearman": round(s, 4) if s is not None else None,
            "n": int(mask.sum()),
            "is_noise": is_noise,
        }
    out["noise_candidates"] = [k for k, v in out["components"].items() if v["is_noise"]]
    return out


# ─── 메인 ──────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="VERITY DART KR fundamental backfill")
    parser.add_argument("--smoke", action="store_true", help="3종목 × 3년 (smoke)")
    parser.add_argument("--full", action="store_true", help="30종목 × 10년 (풀)")
    parser.add_argument("--tickers", type=str, help="콤마 구분 KR code")
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    args = parser.parse_args()

    # Ticker universe
    if args.tickers:
        ticker_pairs = [(t.strip(), t.strip()) for t in args.tickers.split(",") if t.strip()]
        start_y, end_y = args.start_year, args.end_year
    elif args.full:
        if not os.path.exists(DEFAULT_FULL_TICKERS_PATH):
            print(f"❌ {DEFAULT_FULL_TICKERS_PATH} 미존재 — 30종목 리스트 먼저 생성 필요")
            return 1
        ticker_pairs = json.load(open(DEFAULT_FULL_TICKERS_PATH))
        start_y, end_y = DEFAULT_START_YEAR, DEFAULT_END_YEAR
    else:
        ticker_pairs = [(t, t) for t in DEFAULT_SMOKE_TICKERS]
        start_y, end_y = 2020, 2023

    print("=" * 72)
    print(f"DART KR Fundamental Backfill  [{len(ticker_pairs)} 종목 × {start_y}~{end_y}]")
    print("=" * 72)
    if not DART_API_KEY:
        print("❌ DART_API_KEY 미설정 — .env 확인")
        return 1
    print(f"DART_API_KEY: 설정됨 ({DART_API_KEY[:4]}...{DART_API_KEY[-4:]})")
    print(f"yfinance: {'✓' if _HAS_YF else '❌ (수익률 IC 계산 생략됨)'}")
    print()

    all_rows: List[Dict[str, Any]] = []
    t0 = time.time()
    for i, (ticker, name) in enumerate(ticker_pairs, 1):
        print(f"  [{i}/{len(ticker_pairs)}] {ticker} {name} ...", end=" ", flush=True)
        rows = backfill_ticker(ticker, name, start_y, end_y)
        if rows:
            n_fwd = sum(1 for r in rows if r["forward_30d_return_pct"] is not None)
            print(f"OK ({len(rows)} 연도, fwd {n_fwd})")
            all_rows.extend(rows)
        else:
            print("SKIP")

    elapsed = time.time() - t0
    print(f"\n총 {len(all_rows)} 연도-종목 레코드 (elapsed {elapsed:.1f}s)")

    # 저장 raw
    with open(OUT_BACKFILL, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "config": {"tickers": [t for t, _ in ticker_pairs],
                       "start_year": start_y, "end_year": end_y,
                       "forward_hold_days": FORWARD_HOLD_DAYS,
                       "disclosure_lag_days": DISCLOSURE_LAG_DAYS},
            "n_records": len(all_rows),
            "rows": all_rows,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n저장: {OUT_BACKFILL}")

    # IC
    ic = compute_factor_ic(all_rows)
    with open(OUT_IC, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now().isoformat(), **ic},
                  f, ensure_ascii=False, indent=2)
    print(f"저장: {OUT_IC}")

    # 리포트
    print()
    print("=" * 72)
    print("Factor IC (forward 30d 수익률 상관)")
    print("=" * 72)
    if ic.get("status") == "ok":
        print(f"{'factor':<26} {'pearson':>10} {'spearman':>10}  {'n':>5}")
        print("-" * 60)
        for k, v in ic["components"].items():
            p = f"{v['pearson']:+.4f}" if v["pearson"] is not None else "     -"
            s = f"{v['spearman']:+.4f}" if v["spearman"] is not None else "     -"
            mark = " ⚠NOISE" if v["is_noise"] else ""
            print(f"{k:<26} {p:>10} {s:>10}  {v['n']:>5}{mark}")
        noise = ic.get("noise_candidates", [])
        if noise:
            print(f"\n제거 후보 (|IC| < {IC_NOISE_THRESHOLD}): {', '.join(noise)}")
        else:
            print(f"\n✓ 모든 factor |IC| ≥ {IC_NOISE_THRESHOLD}")
    else:
        print(f"insufficient_data (n={ic.get('n', 0)})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
