"""
Phase 0.5 — Universe Load Measurement (관측 전용, IP 차단 방지 우선)

측정 케이스 (8개 트랙):
  U1: yf.Ticker(t).info 단건 순차 (현재 운영 패턴, fundamentals 병목 후보)
  U2: yf.download(batch) — 가격 1Y OHLCV
  U3: yf.Ticker(t).history 단건 순차 (가격 단건)
  K1: KRX OpenAPI 일별매매 일괄 (universe 추출 + 거래대금 정렬)
  K2: pykrx.get_market_ohlcv(start,end,ticker) 단건 순차
  K3: pykrx fundamental 단건 (PER/PBR/ROE)
  P1: U1 순차 baseline (= U1 동일)
  P2: U1 ThreadPoolExecutor max_workers=20
  P3: U1 ThreadPoolExecutor max_workers=50
  P4: U2 yf.download chunked batch
  B1: Finnhub /stock/metric (백업, 60req/min)
  B2: Polygon (백업, free 5req/min)
  B3: SEC EDGAR companyfacts (백업)
  FUND-CHANGE: portfolio.json 의 historical fundamentals 변화율

설계 원칙:
  - 100 → 500 → 1,000 단계별 측정 (선형성 검증)
  - 단계 간 30s 휴지
  - 첫 실패 시 즉시 중단
  - raw 결과는 data/metadata/universe_load_measurement.jsonl 에 append

stock_filter.py / main.py 등 운영 코드 미터치. 본 파일은 관측 전용.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

LOG_PATH = Path("data/metadata/universe_load_measurement.jsonl")


def _now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat()


def _log(rec: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    rec.setdefault("at", _now_iso())
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _fmt_min(sec: float) -> str:
    return f"{sec:.1f}s ({sec/60:.2f}min)"


# ────────────────────────────────────────────────
# Universe pools
# ────────────────────────────────────────────────

_US_POOL_CACHE: list[str] | None = None


def _us_universe(n: int) -> list[str]:
    """S&P 100 + 시총 상위 확장. 정적 화이트리스트 (IP 부담 회피)."""
    global _US_POOL_CACHE
    if _US_POOL_CACHE is None:
        sp100 = [
            "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","BRK-B","AVGO","JPM",
            "WMT","LLY","V","UNH","XOM","MA","ORCL","COST","HD","PG",
            "BAC","JNJ","NFLX","ABBV","CRM","CVX","KO","TMUS","MRK","WFC",
            "CSCO","AMD","ACN","PEP","ADBE","LIN","NOW","DIS","ABT","MCD",
            "TXN","INTU","CAT","GE","IBM","AXP","VZ","DHR","T","PM",
            "PFE","UNP","COP","NEE","BX","RTX","BKNG","C","LOW","SPGI",
            "GS","HON","AMGN","NKE","SYK","UPS","TJX","BLK","BA","SCHW",
            "ISRG","DE","ELV","MS","ADI","BSX","ETN","MMC","GILD","VRTX",
            "MDLZ","ANET","REGN","LMT","PLD","SBUX","BMY","ADP","CB","FI",
            "AMT","MO","CI","ZTS","SO","DUK","TMO","KKR","SHW","CMG",
        ]
        ext_400 = [
            "EQT","CLX","HUBS","DECK","ROKU","WBD","PINS","SNAP","UBER","LYFT",
            "ABNB","SHOP","PYPL","COIN","RBLX","DASH","ZM","DOCU","CRWD","PANW",
            "SNOW","DDOG","NET","ZS","OKTA","TEAM","MDB","CFLT","ASAN","SMCI",
            "ARM","PLTR","RIVN","LCID","NIO","BABA","JD","PDD","SE","TSM",
            "ASML","NTES","INTC","MU","ON","MRVL","KLAC","AMAT","LRCX","WDAY",
            "ADSK","CDNS","SNPS","FTNT","TTD","RDDT","DDS","ANF","GAP","M",
            "KSS","JWN","DKS","FL","SHOO","TPR","CPRI","RH","WSM","BBY",
            "CCL","RCL","NCLH","LVS","MGM","WYNN","CMCSA","CHTR","FOX","FOXA",
            "PARA","NWSA","NWS","SIRI","HAS","MAT","FUN","SIX","AMC","CNK",
            "IMAX","GME","F","GM","STLA","HMC","TM","RACE","XPEV","LI",
        ]
        ext_500 = [
            "EOG","SLB","HAL","BKR","DVN","FANG","PXD","OXY","KMI","ET",
            "MPC","PSX","VLO","HES","APA","MRO","CTRA","TRGP","WMB","ENB",
            "TRP","BTU","CNX","LNG","CHK","RRC","SWN","AR","SM","MTDR",
            "NOG","CIVI","CPE","CRC","PR","MGY","CRGY","SD","REI","CNX",
            "DKL","PARR","DK","CVI","HFC","TS","TX","GTLS","FTI","SLCA",
            "NOV","WHD","WTTR","NFE","KOS","TALO","OII","ARLP","NRP","HCC",
            "ARCH","METC","WIRE","ATKR","HRMY","TGNA","SCHL","TRIP","CARS","AUTO",
            "LAD","KMX","SAH","GPI","ABG","PAG","RUSHB","RUSHA","ALSN","CMI",
            "PCAR","NAV","NGVT","JKHY","BR","ACIW","ALEX","AVB","EQR","ESS",
            "MAA","CPT","UDR","INVH","AMH","BRX","CPRT","PLD","DLR","O",
        ]
        # cap at 800 unique tickers
        seen, pool = set(), []
        for t in sp100 + ext_400 + ext_500:
            if t not in seen:
                seen.add(t)
                pool.append(t)
        _US_POOL_CACHE = pool
    if n > len(_US_POOL_CACHE):
        # pad with duplicates strategy NOT used — just return what we have
        return _US_POOL_CACHE[:]
    return _US_POOL_CACHE[:n]


def _kr_universe_via_krx_openapi(n: int) -> tuple[str, list[str], float]:
    """KRX OpenAPI 일별매매 일괄 (universe + 거래대금 정렬). Returns (bas_dd, tickers, elapsed_s)."""
    sys.path.insert(0, ".")
    from api.collectors.krx_openapi import krx_stk_ksq_rows_sorted_by_trading_value
    t0 = time.time()
    bas_dd, rows = krx_stk_ksq_rows_sorted_by_trading_value()
    elapsed = time.time() - t0
    if not bas_dd or not rows:
        raise RuntimeError("KRX OpenAPI: empty result (KRX_API_KEY 미설정 or KRX 응답 부재)")
    tickers = []
    for r in rows:
        c = str(r.get("ISU_SRT_CD") or r.get("ISU_CD") or "")
        digits = "".join(ch for ch in c if ch.isdigit())
        if len(digits) >= 6:
            tickers.append(digits[-6:].zfill(6))
        if len(tickers) >= n:
            break
    return bas_dd, tickers, elapsed


# ────────────────────────────────────────────────
# Track measurements
# ────────────────────────────────────────────────

def measure_u1_yf_info_seq(tickers: list[str]) -> dict:
    """U1: yf.Ticker(t).info 단건 순차"""
    import yfinance as yf
    t0 = time.time()
    ok = fail = has_pe = 0
    for tk in tickers:
        try:
            info = yf.Ticker(tk).info or {}
            if info.get("trailingPE") is not None or info.get("forwardPE") is not None:
                has_pe += 1
            ok += 1
        except Exception:
            fail += 1
    elapsed = time.time() - t0
    return {
        "track": "U1", "method": "yf.Ticker(t).info seq",
        "n": len(tickers), "elapsed_s": round(elapsed, 2),
        "ok": True, "success": ok, "fail": fail, "has_fundamentals": has_pe,
        "per_ticker_s": round(elapsed/len(tickers), 4) if tickers else 0,
    }


def measure_u2_yf_download(tickers: list[str], chunk: int = 0) -> dict:
    """U2/P4: yf.download batch. chunk=0 → single call, else chunked."""
    import yfinance as yf
    t0 = time.time()
    chunks = [tickers] if chunk <= 0 else [tickers[i:i+chunk] for i in range(0, len(tickers), chunk)]
    ok_count = fail_count = 0
    fail_tickers = []
    try:
        for ch in chunks:
            df = yf.download(
                tickers=" ".join(ch),
                period="1y",
                group_by="ticker",
                threads=True,
                progress=False,
                auto_adjust=False,
            )
            for tk in ch:
                try:
                    sub = df[tk] if len(ch) > 1 else df
                    if sub is None or len(sub.dropna(how="all")) < 50:
                        fail_count += 1
                        fail_tickers.append(tk)
                    else:
                        ok_count += 1
                except Exception:
                    fail_count += 1
                    fail_tickers.append(tk)
    except Exception as e:
        return {"track": "U2/P4", "n": len(tickers), "ok": False, "error": str(e)}
    elapsed = time.time() - t0
    return {
        "track": "U2/P4" if chunk > 0 else "U2",
        "method": f"yf.download(batch chunk={chunk or 'all'})",
        "n": len(tickers), "elapsed_s": round(elapsed, 2),
        "ok": True, "success": ok_count, "fail": fail_count,
        "fail_sample": fail_tickers[:10],
        "per_ticker_s": round(elapsed/len(tickers), 4) if tickers else 0,
    }


def measure_u3_yf_history_seq(tickers: list[str]) -> dict:
    """U3: yf.Ticker(t).history 단건 순차"""
    import yfinance as yf
    t0 = time.time()
    ok = fail = 0
    for tk in tickers:
        try:
            h = yf.Ticker(tk).history(period="1y")
            if h is not None and len(h) > 50:
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
    elapsed = time.time() - t0
    return {
        "track": "U3", "method": "yf.Ticker(t).history seq",
        "n": len(tickers), "elapsed_s": round(elapsed, 2),
        "ok": True, "success": ok, "fail": fail,
        "per_ticker_s": round(elapsed/len(tickers), 4) if tickers else 0,
    }


def measure_p_pool(tickers: list[str], workers: int) -> dict:
    """P2/P3: yf.Ticker.info via ThreadPoolExecutor"""
    import yfinance as yf
    def _one(tk: str) -> tuple[bool, bool]:
        try:
            info = yf.Ticker(tk).info or {}
            return (True, info.get("trailingPE") is not None or info.get("forwardPE") is not None)
        except Exception:
            return (False, False)
    t0 = time.time()
    ok = fail = has_pe = 0
    rate_limit_429 = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_one, tk) for tk in tickers]
        for fu in as_completed(futures):
            try:
                done, has = fu.result()
                if done:
                    ok += 1
                    if has:
                        has_pe += 1
                else:
                    fail += 1
            except Exception:
                fail += 1
    elapsed = time.time() - t0
    return {
        "track": f"P{2 if workers==20 else 3 if workers==50 else 'X'}",
        "method": f"yf.Ticker.info ThreadPoolExecutor(max_workers={workers})",
        "n": len(tickers), "elapsed_s": round(elapsed, 2),
        "workers": workers, "ok": True, "success": ok, "fail": fail,
        "has_fundamentals": has_pe,
        "rate_limit_429_estimated": rate_limit_429,
        "per_ticker_s": round(elapsed/len(tickers), 4) if tickers else 0,
    }


def measure_k1_krx_openapi(n: int = 1500) -> dict:
    """K1: KRX OpenAPI 일별매매 일괄 호출 (1 call = 전체 KOSPI+KOSDAQ)"""
    try:
        bas_dd, tickers, elapsed = _kr_universe_via_krx_openapi(n)
    except Exception as e:
        return {"track": "K1", "ok": False, "error": str(e)}
    return {
        "track": "K1", "method": "KRX OpenAPI stk_bydd_trd+ksq_bydd_trd (1 call)",
        "elapsed_s": round(elapsed, 2),
        "ok": True, "rows_returned": len(tickers), "as_of": bas_dd,
        "note": "1 API call로 KOSPI+KOSDAQ 전체 종목 + 거래대금 정렬 결과",
    }


def measure_k2_pykrx_ohlcv_seq(tickers: list[str]) -> dict:
    """K2: pykrx.get_market_ohlcv 단건 순차"""
    from pykrx import stock
    today = datetime.now(ZoneInfo("Asia/Seoul"))
    end = today.strftime("%Y%m%d")
    start = (today - timedelta(days=370)).strftime("%Y%m%d")
    t0 = time.time()
    ok = fail = 0
    for tk in tickers:
        try:
            df = stock.get_market_ohlcv(start, end, tk)
            if df is not None and len(df) > 50:
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
    elapsed = time.time() - t0
    return {
        "track": "K2", "method": "pykrx.get_market_ohlcv (per-ticker seq)",
        "n": len(tickers), "elapsed_s": round(elapsed, 2),
        "ok": True, "success": ok, "fail": fail,
        "per_ticker_s": round(elapsed/len(tickers), 4) if tickers else 0,
    }


def measure_k2_pool(tickers: list[str], workers: int) -> dict:
    """K2-P10/P20/P30/P50: pykrx.get_market_ohlcv via ThreadPoolExecutor.

    pykrx 는 종목당 KRX 백엔드에 ~3-5 HTTP 호출. concurrent N → KRX 동시 N×3~5.
    rate limit 는 pykrx 가 4xx/5xx 시 대부분 빈 DataFrame 반환 → fail count 로 검출.
    """
    from pykrx import stock
    today = datetime.now(ZoneInfo("Asia/Seoul"))
    end = today.strftime("%Y%m%d")
    start = (today - timedelta(days=370)).strftime("%Y%m%d")

    def _one(tk: str) -> bool:
        try:
            df = stock.get_market_ohlcv(start, end, tk)
            return df is not None and len(df) > 50
        except Exception:
            return False

    t0 = time.time()
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_one, tk) for tk in tickers]
        for fu in as_completed(futures):
            try:
                if fu.result():
                    ok += 1
                else:
                    fail += 1
            except Exception:
                fail += 1
    elapsed = time.time() - t0
    fail_rate = round(fail/len(tickers)*100, 2) if tickers else 0
    return {
        "track": f"K2-P{workers}",
        "method": f"pykrx.get_market_ohlcv ThreadPoolExecutor(max_workers={workers})",
        "n": len(tickers), "elapsed_s": round(elapsed, 2),
        "workers": workers, "ok": True, "success": ok, "fail": fail,
        "fail_rate_pct": fail_rate,
        "rate_limit_suspected": fail_rate > 5.0,
        "per_ticker_s": round(elapsed/len(tickers), 4) if tickers else 0,
        "speedup_vs_seq_estimate": round(0.547/(elapsed/len(tickers)), 2) if tickers and elapsed > 0 else 0,
    }


def measure_k3_pykrx_fundamental_seq(tickers: list[str]) -> dict:
    """K3: pykrx.get_market_fundamental_by_date 단건"""
    from pykrx import stock
    today = datetime.now(ZoneInfo("Asia/Seoul"))
    end = today.strftime("%Y%m%d")
    start = (today - timedelta(days=10)).strftime("%Y%m%d")
    t0 = time.time()
    ok = fail = 0
    for tk in tickers:
        try:
            df = stock.get_market_fundamental_by_date(start, end, tk)
            if df is not None and len(df) > 0:
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
    elapsed = time.time() - t0
    return {
        "track": "K3", "method": "pykrx.get_market_fundamental_by_date (per-ticker)",
        "n": len(tickers), "elapsed_s": round(elapsed, 2),
        "ok": True, "success": ok, "fail": fail,
        "per_ticker_s": round(elapsed/len(tickers), 4) if tickers else 0,
    }


def measure_b1_finnhub(tickers: list[str], api_key: str) -> dict:
    """B1: Finnhub /stock/metric (60req/min)"""
    import requests
    t0 = time.time()
    ok = fail = 0
    rate_429 = False
    minute_start = time.time()
    calls = 0
    for tk in tickers:
        if calls >= 55:
            sleep_for = 60 - (time.time() - minute_start)
            if sleep_for > 0:
                time.sleep(sleep_for + 1)
            minute_start = time.time()
            calls = 0
        try:
            r = requests.get("https://finnhub.io/api/v1/stock/metric",
                             params={"symbol": tk, "metric": "all", "token": api_key},
                             timeout=10)
            calls += 1
            if r.status_code == 429:
                rate_429 = True
                fail += 1
                break
            if r.status_code == 200 and r.json().get("metric"):
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
    elapsed = time.time() - t0
    return {
        "track": "B1", "method": "Finnhub /stock/metric",
        "n": len(tickers), "elapsed_s": round(elapsed, 2),
        "ok": not rate_429, "success": ok, "fail": fail,
        "rate_limit_429": rate_429,
        "per_ticker_s": round(elapsed/len(tickers), 4) if tickers else 0,
    }


def measure_b3_sec_edgar(tickers: list[str], user_agent: str) -> dict:
    """B3: SEC EDGAR companyfacts XBRL"""
    import requests
    headers = {"User-Agent": user_agent}
    try:
        r = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers=headers, timeout=10)
        cik_map = r.json()
        ticker_to_cik = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in cik_map.values()}
    except Exception as e:
        return {"track": "B3", "ok": False, "error": f"cik fetch fail: {e}"}
    t0 = time.time()
    ok = fail = 0
    rate_429 = False
    for tk in tickers:
        cik = ticker_to_cik.get(tk.upper())
        if not cik:
            fail += 1
            continue
        try:
            r = requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                             headers=headers, timeout=15)
            if r.status_code == 429:
                rate_429 = True
                fail += 1
                break
            if r.status_code == 200 and r.json().get("facts"):
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
        time.sleep(0.11)
    elapsed = time.time() - t0
    return {
        "track": "B3", "method": "SEC EDGAR companyfacts XBRL",
        "n": len(tickers), "elapsed_s": round(elapsed, 2),
        "ok": not rate_429, "success": ok, "fail": fail,
        "rate_limit_429": rate_429,
        "per_ticker_s": round(elapsed/len(tickers), 4) if tickers else 0,
    }


def measure_fund_change() -> dict:
    """FUND-CHANGE: portfolio.json 의 최근 7일 PER/PBR/ROE 변화율 (data/history/) 측정"""
    rows = []
    dates = ['2026-04-23','2026-04-24','2026-04-25','2026-04-27','2026-04-28','2026-04-29','2026-04-30','2026-05-01']
    snap = {}
    for d in dates:
        p = Path(f"data/history/{d}.json")
        if not p.exists():
            continue
        try:
            j = json.loads(p.read_text())
            for r in j.get("recommendations", []):
                tk = r.get("ticker")
                if not tk:
                    continue
                snap.setdefault(tk, []).append({
                    "date": d,
                    "per": r.get("per"),
                    "pbr": r.get("pbr"),
                    "roe": r.get("roe"),
                    "debt_ratio": r.get("debt_ratio"),
                    "operating_margin": r.get("operating_margin"),
                })
        except Exception:
            continue

    # change rates
    changes = {"per": [], "pbr": [], "roe": [], "debt_ratio": [], "operating_margin": []}
    for tk, hist in snap.items():
        if len(hist) < 2:
            continue
        first, last = hist[0], hist[-1]
        for k in changes:
            f, l = first.get(k), last.get(k)
            if f is None or l is None or f == 0:
                continue
            try:
                pct = abs((l - f) / f * 100)
                changes[k].append(pct)
            except Exception:
                continue

    summary = {}
    for k, vals in changes.items():
        if vals:
            summary[k] = {
                "n_tickers": len(vals),
                "avg_change_pct": round(sum(vals)/len(vals), 2),
                "max_change_pct": round(max(vals), 2),
                "min_change_pct": round(min(vals), 2),
                "median_change_pct": round(sorted(vals)[len(vals)//2], 2),
            }
    return {
        "track": "FUND-CHANGE",
        "method": "data/history/*.json 8일 분포 비교",
        "ok": True,
        "tickers_with_history": len(snap),
        "change_summary_pct": summary,
        "interpretation": "변화율이 < 5%이면 매일 갱신은 낭비, 주 1회 갱신 권고. trailingPE 는 분기 보고서에 의존.",
    }


# ────────────────────────────────────────────────
# Runner
# ────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", type=int, default=100)
    ap.add_argument("--tracks", default="u2,k1,k2,u3,u1,p2,p3,fund_change")
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    n = 10 if args.quick else args.tier
    tracks = [t.strip().lower() for t in args.tracks.split(",") if t.strip()]

    print(f"[Phase 0.5] tier={n}  tracks={tracks}  at={_now_iso()}")
    print(f"[Phase 0.5] LOG_PATH={LOG_PATH}")

    session_id = datetime.now().strftime("%Y%m%dT%H%M%S")
    _log({"event": "session_start", "session_id": session_id, "tier": n, "tracks": tracks})

    us_pool_full = _us_universe(n)
    print(f"[US universe] resolved {len(us_pool_full)} tickers (requested {n})")

    kr_pool_full: list[str] = []
    if any(x in tracks for x in ("k1", "k2", "k3", "k2_p10", "k2_p20", "k2_p30", "k2_p50")):
        try:
            bas_dd, kr_pool_full, _kr_el = _kr_universe_via_krx_openapi(n)
            print(f"[KR universe via KRX OpenAPI] resolved {len(kr_pool_full)} tickers (as_of {bas_dd}, {_kr_el:.2f}s)")
        except Exception as e:
            print(f"[KR universe] FAILED: {e}")
            _log({"event": "kr_universe_fail", "session_id": session_id, "error": str(e)})

    runners: list[tuple[str, Callable[[], dict]]] = []

    # 가벼운 것부터 (실패 격리)
    if "k1" in tracks:
        runners.append(("K1", lambda: measure_k1_krx_openapi(n)))
    if "u2" in tracks:
        runners.append(("U2", lambda: measure_u2_yf_download(us_pool_full)))
    if "p4" in tracks:
        runners.append(("P4", lambda: measure_u2_yf_download(us_pool_full, chunk=100)))
    if "u3" in tracks:
        runners.append(("U3", lambda: measure_u3_yf_history_seq(us_pool_full)))
    if "u1" in tracks:
        runners.append(("U1", lambda: measure_u1_yf_info_seq(us_pool_full)))
    if "p2" in tracks:
        runners.append(("P2", lambda: measure_p_pool(us_pool_full, workers=20)))
    if "p3" in tracks:
        runners.append(("P3", lambda: measure_p_pool(us_pool_full, workers=50)))
    if "k2" in tracks and kr_pool_full:
        runners.append(("K2", lambda: measure_k2_pykrx_ohlcv_seq(kr_pool_full)))
    if "k2_p10" in tracks and kr_pool_full:
        runners.append(("K2-P10", lambda: measure_k2_pool(kr_pool_full, workers=10)))
    if "k2_p20" in tracks and kr_pool_full:
        runners.append(("K2-P20", lambda: measure_k2_pool(kr_pool_full, workers=20)))
    if "k2_p30" in tracks and kr_pool_full:
        runners.append(("K2-P30", lambda: measure_k2_pool(kr_pool_full, workers=30)))
    if "k2_p50" in tracks and kr_pool_full:
        runners.append(("K2-P50", lambda: measure_k2_pool(kr_pool_full, workers=50)))
    if "k3" in tracks and kr_pool_full:
        runners.append(("K3", lambda: measure_k3_pykrx_fundamental_seq(kr_pool_full[:30])))
    if "b1" in tracks:
        key = os.environ.get("FINNHUB_API_KEY")
        if key:
            runners.append(("B1", lambda: measure_b1_finnhub(us_pool_full[:60], key)))
        else:
            print("[B1] skipped: FINNHUB_API_KEY missing")
    if "b3" in tracks:
        ua = os.environ.get("SEC_EDGAR_USER_AGENT")
        if ua:
            runners.append(("B3", lambda: measure_b3_sec_edgar(us_pool_full[:30], ua)))
        else:
            print("[B3] skipped: SEC_EDGAR_USER_AGENT missing")
    if "fund_change" in tracks:
        runners.append(("FUND-CHANGE", measure_fund_change))

    for label, fn in runners:
        print(f"\n[{label}] starting at {_now_iso()}...")
        t_start = time.time()
        try:
            r = fn()
        except Exception as e:
            print(f"[{label}] EXCEPTION: {e}")
            _log({"event": "track_exception", "session_id": session_id, "track": label, "error": str(e)})
            print(f"[{label}] 즉시 중단 (선결조건: 첫 실패 시 stop)")
            break
        r["session_id"] = session_id
        r["wall_s"] = round(time.time() - t_start, 2)
        _log(r)
        print(f"[{label}] {r.get('method', '')}")
        print(f"[{label}] done: {_fmt_min(r.get('elapsed_s', 0))}  "
              f"ok={r.get('success', '-')}  fail={r.get('fail', '-')}")
        if not r.get("ok", True):
            print(f"[{label}] FAILED — 즉시 중단")
            break
        time.sleep(2)

    print(f"\n[Phase 0.5] session_end at={_now_iso()}")
    _log({"event": "session_end", "session_id": session_id})


if __name__ == "__main__":
    main()
