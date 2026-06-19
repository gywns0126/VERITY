"""
flow_observation_logger.py — KR 외국인/기관 일별 순매매 관측 트레일 (KR 홈그라운드 crowding v0).

2026-06-15 신설. US CoMOM(간접 잔차상관 proxy) 대비 KR-native *직접* crowding 신호 =
종목별 외국인/기관 일별 순매매. 🚨 무료 프로그램 소스 검증(2026-06-15, 실호출): pykrx 투자자
엔드포인트 死 / KRX bld 死(검증큐) → 현재 유일 생존 = 네이버 frgn 페이지. historical 백필 불가,
*forward 누적*만 가능(단 1회 fetch=최근 ~20거래일 → 즉시 20일 시드).

🚨 관측/측정 only (RULE 7) — 점수/brain wire 0. 별 trail(US crowding v0 와 동급 관측 누적).
🚨 N<252 = 수년 누적형. near-term 승부 아님. 스코프 유니버스(top-N by 거래대금)로 anti-bot 회피.

데이터 행 구조(2026-06-15 실검증, class="tah" 셀):
  [날짜, 종가, 전일비, 등락률, 거래량, 기관순매매(idx5), 외국인순매매(idx6), 외국인보유주수]
저장: ~/VERITY_data_lake/kr_flow_observations.parquet (append+(date,ticker) dedup).
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from typing import Dict, List, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

LAKE = os.path.expanduser("~/VERITY_data_lake")
OUT_PARQUET = os.path.join(LAKE, "kr_flow_observations.parquet")
KR_PRICES_DB = os.path.join(LAKE, "kr_prices.duckdb")
NAVER_URL = "https://finance.naver.com/item/frgn.naver?code={code}"
NAVER_TREND_URL = "https://m.stock.naver.com/api/stock/{code}/trend"  # 모바일 JSON: 개인까지 + 더 견고(2026-06-19)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://finance.naver.com/",
}
_TAH = re.compile(r'<(?:td|span)[^>]*class="tah[^"]*"[^>]*>(.*?)</(?:td|span)>', re.S)
_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_DATE = re.compile(r"\d{4}\.\d{2}\.\d{2}")


def _num(s: str) -> Optional[float]:
    s = re.sub(r"<[^>]+>", "", s).strip().replace(",", "").replace("+", "").replace("%", "")
    if not s or s in ("-",):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def fetch_flow_panel(code: str, session: Optional[requests.Session] = None) -> List[Dict]:
    """네이버 frgn 페이지 → 최근 ~20거래일 [{date, ticker, close, volume, inst_net, foreign_net}]."""
    sess = session or requests.Session()
    r = sess.get(NAVER_URL.format(code=code), headers=_HEADERS, timeout=20)
    r.encoding = "euc-kr"
    rows: List[Dict] = []
    for tr in _TR.findall(r.text):
        if not _DATE.search(tr):
            continue
        cells = [re.sub(r"<[^>]+>", "", c).strip().replace(",", "") for c in _TAH.findall(tr)]
        cells = [c for c in cells if c]
        if len(cells) < 7 or not _DATE.fullmatch(cells[0]):
            continue
        rows.append({
            "date": cells[0].replace(".", "-"),
            "ticker": code,
            "close": _num(cells[1]),
            "volume": _num(cells[4]),
            "inst_net": _num(cells[5]),       # 기관 순매매량(주)
            "foreign_net": _num(cells[6]),    # 외국인 순매매량(주)
        })
    return rows


def fetch_trend_mobile(code: str, session: Optional[requests.Session] = None) -> List[Dict]:
    """네이버 모바일 trend JSON → 최근 ~60거래일 [{date,ticker,close,volume,inst_net,foreign_net,individual_net}].

    frgn HTML(외인/기관만) 대비 개인(individualPureBuyQuant)까지 포함 + Referer/UA 게이트 낮아 더 견고.
    🚨 개인 순매매 = 외인/기관의 거의 거울상(zero-sum) — 독립 정보가치 낮음. 관측-only 누적(점수 wire 0).
    """
    sess = session or requests.Session()
    try:
        r = sess.get(NAVER_TREND_URL.format(code=code), params={"pageSize": 60, "page": 1},
                     headers=_HEADERS, timeout=20)
        arr = r.json()
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(arr, list):
        return []
    rows: List[Dict] = []
    for it in arr:
        bd = str(it.get("bizdate") or "")
        if len(bd) != 8:
            continue
        rows.append({
            "date": f"{bd[:4]}-{bd[4:6]}-{bd[6:8]}",
            "ticker": code,
            "close": _num(it.get("closePrice")),
            "volume": _num(it.get("accumulatedTradingVolume")),
            "inst_net": _num(it.get("organPureBuyQuant")),
            "foreign_net": _num(it.get("foreignerPureBuyQuant")),
            "individual_net": _num(it.get("individualPureBuyQuant")),
        })
    return rows


def liquid_universe(top_n: int) -> List[str]:
    """kr_prices 레이크에서 최근 거래일 거래대금 상위 top_n 티커 (anti-bot 위해 스코프)."""
    import duckdb
    con = duckdb.connect(KR_PRICES_DB, read_only=True)
    try:
        # value(거래대금) = 레이크 전부 null → close*volume 근사 랭킹
        df = con.execute("""
            WITH last AS (SELECT MAX(date) d FROM ohlcv)
            SELECT ticker FROM ohlcv, last
            WHERE date = last.d AND close IS NOT NULL AND volume IS NOT NULL
            ORDER BY close * volume DESC LIMIT ?
        """, [top_n]).fetchdf()
        return df["ticker"].astype(str).str.zfill(6).tolist()
    finally:
        con.close()


def run(top_n: int = 200, delay: float = 0.4, max_tickers: Optional[int] = None,
        out_path: str = OUT_PARQUET) -> Dict[str, object]:
    universe = liquid_universe(top_n)
    if max_tickers:
        universe = universe[:max_tickers]
    sess = requests.Session()
    all_rows: List[Dict] = []
    ok, fail = 0, 0
    for i, code in enumerate(universe):
        try:
            rows = fetch_trend_mobile(code, sess) or fetch_flow_panel(code, sess)  # 모바일(개인 포함) 우선, frgn 폴백
            if rows:
                all_rows.extend(rows)
                ok += 1
            else:
                fail += 1
        except Exception as e:  # noqa: BLE001
            fail += 1
            logger.warning("%s fetch 실패: %s", code, e)
        if delay:
            time.sleep(delay)
        if (i + 1) % 50 == 0:
            logger.info("진행 %d/%d (ok=%d fail=%d, rows=%d)", i + 1, len(universe), ok, fail, len(all_rows))

    if not all_rows:
        return {"tickers": len(universe), "ok": ok, "fail": fail, "new_rows": 0, "note": "수집 0 — 소스 점검"}

    new = pd.DataFrame(all_rows)
    if os.path.exists(out_path):
        old = pd.read_parquet(out_path)
        merged = pd.concat([old, new], ignore_index=True)
    else:
        merged = new
    merged = merged.drop_duplicates(subset=["date", "ticker"], keep="last").sort_values(["ticker", "date"])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    merged.to_parquet(out_path)
    return {
        "tickers": len(universe), "ok": ok, "fail": fail,
        "new_rows": len(new), "total_rows": len(merged),
        "date_range": (merged["date"].min(), merged["date"].max()),
        "out": out_path,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-n", type=int, default=200, help="거래대금 상위 N 종목(스코프)")
    ap.add_argument("--delay", type=float, default=0.4, help="요청 간 지연(초, anti-bot)")
    ap.add_argument("--max", type=int, default=None, help="테스트용 상한")
    ap.add_argument("--out", default=OUT_PARQUET)
    args = ap.parse_args()
    try:
        res = run(top_n=args.top_n, delay=args.delay, max_tickers=args.max, out_path=args.out)
        print("[flow_observation_logger] KR flow 관측 트레일:")
        for k, v in res.items():
            print(f"  {k}: {v}")
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[flow_observation_logger] 실패: {type(e).__name__}: {e}\n")
        raise
