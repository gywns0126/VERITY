"""
거래대금 상위 종목 스캐너
- 1순위: 네이버 증권 sise_quant (KOSPI/KOSDAQ 병합 후 거래대금 기준 정렬)
- 보조: pykrx (환경에 따라 KRX 응답이 동작할 때)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

NAVER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

NAVER_QUANT_URL = "https://finance.naver.com/sise/sise_quant.naver"

_ETF_HINTS = (
    "KODEX",
    "TIGER",
    "ARIRANG",
    "ACE ",
    "KBSTAR",
    "KOSEF",
    "HANARO",
    "KINDEX",
    "SOL ",
    "TIMEFOLIO",
    "KOACT",
    "TRUE ",
    "FOCUS ",
    "RISE ",
    "PLUS ",
    "KTOP",
    "TREX ",
    "WON ",
    "KTOP",
)


@dataclass
class ScannedStock:
    name: str
    ticker: str
    trademoney_million_krw: int


def _is_likely_etf_or_etn(name: str) -> bool:
    n = name.upper()
    return any(h in n for h in _ETF_HINTS)


def _parse_money_mil(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _fetch_naver_quant_rows(sosok: int) -> List[dict]:
    r = requests.get(
        NAVER_QUANT_URL,
        params={"sosok": sosok},
        headers=NAVER_HEADERS,
        timeout=20,
    )
    r.raise_for_status()
    r.encoding = "euc-kr"
    soup = BeautifulSoup(r.text, "html.parser")
    table = soup.select_one("table.type_2")
    if not table:
        return []

    rows: List[dict] = []
    for tr in table.select("tr"):
        tds = tr.select("td")
        if len(tds) < 8:
            continue
        link = tds[1].select_one("a[href*='code=']")
        if not link:
            continue
        href = link.get("href", "")
        m = re.search(r"code=(\d{6})", href)
        if not m:
            continue
        name = link.get_text(strip=True)
        trademoney = _parse_money_mil(tds[6].get_text(strip=True))
        rows.append(
            {
                "name": name,
                "ticker": m.group(1),
                "trademoney_million_krw": trademoney,
            }
        )
    return rows


def scan_top_trading_value_naver(top_n: int = 30, exclude_etfs: bool = True) -> List[ScannedStock]:
    """네이버 거래상위 테이블에서 KOSPI·KOSDAQ을 합쳐 거래대금 기준 상위 종목."""
    merged: dict[str, dict] = {}
    for sosok in (0, 1):
        for row in _fetch_naver_quant_rows(sosok):
            tid = row["ticker"]
            if tid not in merged or row["trademoney_million_krw"] > merged[tid]["trademoney_million_krw"]:
                merged[tid] = row

    ranked = sorted(
        merged.values(),
        key=lambda x: x["trademoney_million_krw"],
        reverse=True,
    )

    out: List[ScannedStock] = []
    for row in ranked:
        if exclude_etfs and _is_likely_etf_or_etn(row["name"]):
            continue
        out.append(
            ScannedStock(
                name=row["name"],
                ticker=row["ticker"],
                trademoney_million_krw=row["trademoney_million_krw"],
            )
        )
        if len(out) >= top_n:
            break

    return out


def scan_top_trading_value_pykrx(top_n: int = 30, exclude_etfs: bool = True) -> Optional[List[ScannedStock]]:
    """pykrx로 최근 영업일 기준 거래대금 상위 (동작하는 환경에서만)."""
    try:
        from datetime import datetime, timedelta

        from pykrx import stock
    except Exception:
        return None

    for i in range(1, 20):
        d = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        try:
            df_k = stock.get_market_ohlcv_by_ticker(d, market="KOSPI")
            df_q = stock.get_market_ohlcv_by_ticker(d, market="KOSDAQ")
            if df_k is None or df_q is None or len(df_k) == 0:
                continue
            if "거래대금" not in df_k.columns:
                continue
            df = __import__("pandas").concat([df_k, df_q])
            df = df.sort_values("거래대금", ascending=False)
            out: List[ScannedStock] = []
            for ticker, row in df.iterrows():
                name = stock.get_market_ticker_name(ticker)
                if exclude_etfs and _is_likely_etf_or_etn(name):
                    continue
                code = str(ticker).replace(".KS", "").replace(".KQ", "").zfill(6)
                tv = int(row["거래대금"])
                out.append(
                    ScannedStock(
                        name=name,
                        ticker=code,
                        trademoney_million_krw=tv,
                    )
                )
                if len(out) >= top_n:
                    return out
            if out:
                return out
        except Exception:
            continue
    return None


def scan_top_trading_value_krx(top_n: int = 30, exclude_etfs: bool = True) -> Optional[List[ScannedStock]]:
    """KRX OpenAPI(stk_bydd_trd + ksq_bydd_trd). Actions 등에서 네이버 차단 시 보조."""
    from api.collectors.krx_openapi import krx_stk_ksq_rows_sorted_by_trading_value
    from api.config import KRX_API_KEY

    if not (KRX_API_KEY or "").strip():
        return None

    used_dd, rows = krx_stk_ksq_rows_sorted_by_trading_value()
    if not rows:
        return None
    print(f"[Scanner] KRX 일자 basDd={used_dd}", flush=True)

    def _acc(row: dict) -> int:
        raw = row.get("ACC_TRDVAL") or row.get("ACC_TRDVALU") or 0
        s = str(raw or "").strip().replace(",", "")
        try:
            return int(float(s)) if s else 0
        except ValueError:
            return 0

    out: List[ScannedStock] = []
    for row in rows:
        name = (row.get("ISU_NM") or "").strip()
        code_raw = str(row.get("ISU_SRT_CD") or row.get("ISU_CD") or "")
        digits = "".join(c for c in code_raw if c.isdigit())
        if len(digits) < 6:
            continue
        ticker = digits[-6:].zfill(6)
        krw = _acc(row)
        mil = max(0, krw // 1_000_000)
        if mil <= 0:
            continue
        if exclude_etfs and _is_likely_etf_or_etn(name):
            continue
        out.append(
            ScannedStock(
                name=name or ticker,
                ticker=ticker,
                trademoney_million_krw=mil,
            )
        )
        if len(out) >= top_n:
            break

    return out if out else None


def scan_top_trading_value(top_n: int = 30, exclude_etfs: bool = True) -> List[ScannedStock]:
    """네이버 우선, 실패 시 pykrx, 그다음 KRX OpenAPI."""
    try:
        nv = scan_top_trading_value_naver(top_n=top_n, exclude_etfs=exclude_etfs)
        if nv:
            return nv
    except Exception as e:
        print(f"[Scanner] 네이버 스캔 실패: {e}")

    pk = scan_top_trading_value_pykrx(top_n=top_n, exclude_etfs=exclude_etfs)
    if pk:
        print("[Scanner] pykrx 백업 소스 사용")
        return pk

    kx = scan_top_trading_value_krx(top_n=top_n, exclude_etfs=exclude_etfs)
    if kx:
        print("[Scanner] KRX OpenAPI 백업 소스 사용")
        return kx

    raise RuntimeError("거래대금 상위 스캔 실패 (네이버·pykrx·KRX 모두 불가)")
