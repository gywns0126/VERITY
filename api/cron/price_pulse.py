"""
가격 펄스 — 1~2분 cron 으로 KOSPI/KOSDAQ/NDX/SPX + 보유 + 추천 종목 가격만 갱신.

설계 의도 (2026-05-11 사용자 결정):
- main.py 의 무거운 import (4m50s) + STEP 0 자가진단 (3m41s) 회피
- 핵심 가격만 ~30초 안에 fetch + 저장
- output = data/price_pulse.json (portfolio.json 과 별도 파일, race 없음)
- Vercel API 가 portfolio + price_pulse merge 해서 사이트 노출

light import 만 — yfinance / pandas / pykrx 의도적으로 import 안 함 (각 1~5초 startup).
사용:
- KIS 정규장 분봉 / Yahoo chart metadata (KR 종목)
- yfinance (US 종목 + 지수)
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any
from http.client import HTTPException
from urllib.request import Request, urlopen

KST = timezone(timedelta(hours=9))

# 프로젝트 root 경로 — repo root 에서 실행 가정
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from api.utils.kr_pulse_quote import aware_time, expected_session, valid_kr_quote

_DATA = os.path.join(_ROOT, "data")
_PORTFOLIO = os.path.join(_DATA, "portfolio.json")
_RECS = os.path.join(_DATA, "recommendations.json")
_OUT = os.path.join(_DATA, "price_pulse.json")

# 지수 yahoo 심볼
_INDEX_SYMBOLS = {
    "kospi": "^KS11",
    "kosdaq": "^KQ11",
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
    "dow": "^DJI",
    "vix": "^VIX",
    "usdkrw": "KRW=X",
}


def _now_iso() -> str:
    return datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def fetch_yahoo_quotes(symbols: list[str]) -> dict:
    """yfinance.Tickers batch fetch — yahoo raw API 가 401 인증 요구라 yfinance 경유.

    반환: {symbol: {price, change_pct}}
    """
    if not symbols:
        return {}
    try:
        import yfinance as yf  # ~2~3s startup, lazy
    except Exception as e:
        print(f"[pulse] yfinance import 실패: {e}")
        return {}

    out: dict = {}
    try:
        tk = yf.Tickers(" ".join(symbols))
        for sym in symbols:
            try:
                info = tk.tickers[sym].fast_info
                price = info.get("last_price") or info.get("lastPrice")
                prev = info.get("previous_close") or info.get("previousClose")
                if price is None:
                    continue
                change_pct = None
                if prev and prev > 0:
                    change_pct = round((price - prev) / prev * 100, 2)
                out[sym] = {"price": float(price), "change_pct": change_pct}
            except Exception:
                continue
    except Exception as e:
        print(f"[pulse] yfinance batch 실패: {e}")
    return out


def _yahoo_kr_quote(symbol: str) -> dict:
    """Use Yahoo's regular price and trade time from one chart response."""
    code, market = symbol.split(".")
    exchange = {"KS": "KSC", "KQ": "KOE"}[market]
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{code}.{market}?range=1d&interval=1d"
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=4) as response:
            chart = json.load(response)["chart"]
        if chart.get("error") or len(chart["result"]) != 1:
            return {}
        meta = chart["result"][0]["meta"]
        if (meta.get("symbol") != symbol or meta.get("exchangeName") != exchange
                or meta.get("currency") != "KRW" or meta.get("exchangeTimezoneName") != "Asia/Seoul"):
            return {}
        observed = datetime.fromtimestamp(meta["regularMarketTime"], tz=KST)
        return {"source": "yahoo", "symbol": symbol, "observed_at": observed.isoformat(),
                "price": meta["regularMarketPrice"]}
    except (OSError, HTTPException, KeyError, ValueError, TypeError, OverflowError, AttributeError):
        return {}


def _latest_kis_quote(rows: list[dict], symbol: str) -> dict:
    # KIS output2 carries business date, exchange time, price and volume in each bar.
    # Bars without a trade must not advance a frozen price's observation time.
    latest = {}
    for row in rows:
        try:
            timestamp = row["stck_bsop_date"] + row["stck_cntg_hour"]
            if len(timestamp) != 14 or int(row["cntg_vol"]) <= 0:
                continue
            observed = datetime.strptime(timestamp, "%Y%m%d%H%M%S").replace(tzinfo=KST)
            price = int(row["stck_prpr"])
            if price > 0 and (not latest or observed.isoformat() > latest["observed_at"]):
                latest = {"source": "kis", "symbol": symbol, "observed_at": observed.isoformat(),
                          "price": price}
        except (KeyError, ValueError, TypeError):
            continue
    return latest


def fetch_kis_prices(symbols: dict[str, str]) -> dict:
    """Read one timestamped KRX minute-chart response per listed ticker."""
    now = datetime.now(KST)
    session = expected_session(now) if symbols else None
    if session is None:
        return {}
    opening, closing = session
    end_time = (now if opening <= now <= closing else closing).strftime("%H%M%S")
    try:
        from api.trading.kis_broker import KISBroker
    except Exception as e:
        print(f"[pulse] KIS broker import 실패: {e}")
        return {}
    try:
        # 🚨 cache_only=True — 신규 토큰 발급 절대 금지 (5/16 5분 폭주 사고 후).
        # 정상 source: kis_token_refresh (KST 23:45 일 1회) / daily_realtime backup.
        broker = KISBroker(cache_only=True)
        if not getattr(broker, "is_configured", False):
            print("[pulse] KIS 미설정 — KR 가격 skip (env KIS_APP_KEY/KIS_APP_SECRET 확인)")
            return {}
        broker.authenticate(force_refresh=False)
    except Exception as exc:
        print(f"[pulse] KIS 캐시 인증 실패 ({type(exc).__name__}) — 공개 시세 대체 조회")
        return {}

    out: dict = {}
    fail_count = 0
    for ticker, symbol in symbols.items():
        try:
            rows = broker.get_minute_chart(ticker, time_from=end_time, include_prev="Y")
            quote = _latest_kis_quote(rows, symbol)
            if quote:
                out[ticker] = quote
            else:
                fail_count += 1
        except Exception:
            fail_count += 1
    if fail_count:
        print(f"[pulse] KIS 분봉 누락 {fail_count}/{len(symbols)}")
    return out


def collect_kr_quotes(tickers: set[str], listed: dict) -> dict:
    """Keep verified KIS records; only request Yahoo for the missing listed names."""
    if not tickers or expected_session(datetime.now(KST)) is None:
        return {}
    symbols = {}
    for ticker in sorted(tickers):
        listing = listed.get(ticker)
        market = listing.get("market") if isinstance(listing, dict) else None
        if (len(ticker) == 6 and ticker.isascii() and ticker.isalnum()
                and ticker[0].isdigit() and ticker == ticker.upper() and market in ("KS", "KQ")):
            symbols[ticker] = f"{ticker}.{market}"
    kis = fetch_kis_prices(symbols)
    accepted = {}
    for ticker, symbol in symbols.items():
        quote = kis.get(ticker, {})
        if valid_kr_quote(ticker, quote.get("price"), quote, listed, datetime.now(KST)):
            accepted[ticker] = quote
            continue
        quote = _yahoo_kr_quote(symbol)
        if valid_kr_quote(ticker, quote.get("price"), quote, listed, datetime.now(KST)):
            accepted[ticker] = quote
    return accepted


def main() -> int:
    t0 = time.perf_counter()
    print(f"[pulse] 시작 {_now_iso()}")

    # 1) 입력 — portfolio + recommendations 에서 티커 추출
    portfolio = _load_json(_PORTFOLIO, {})
    recs_root = _load_json(_RECS, {})
    recs = recs_root.get("recommendations", []) if isinstance(recs_root, dict) else (recs_root or [])

    kr_tickers: set[str] = set()
    us_symbols: set[str] = set()

    for h in (portfolio.get("vams", {}) or {}).get("holdings", []) or []:
        tk = h.get("ticker")
        if not tk:
            continue
        if (h.get("currency") or "").upper() == "USD":
            us_symbols.add(str(tk))
        else:
            kr_tickers.add(str(tk).zfill(6))

    for r in recs:
        tk = r.get("ticker")
        if not tk:
            continue
        if (r.get("currency") or "").upper() == "USD":
            us_symbols.add(str(tk))
        else:
            kr_tickers.add(str(tk).zfill(6))

    print(f"[pulse] 대상 KR={len(kr_tickers)} US={len(us_symbols)}")

    # 2) 지수 + US 종목 batch fetch (yahoo)
    yahoo_batch = list(_INDEX_SYMBOLS.values()) + [
        s if "." in s or "^" in s else s for s in us_symbols
    ]
    t_y0 = time.perf_counter()
    yahoo = fetch_yahoo_quotes(yahoo_batch)
    t_y = time.perf_counter() - t_y0
    print(f"[pulse] yahoo {len(yahoo)}/{len(yahoo_batch)} ({t_y:.1f}s)")

    listed = _load_json(os.path.join(_DATA, "kr_listed.json"), {})
    kr_quotes = collect_kr_quotes(kr_tickers, listed if isinstance(listed, dict) else {})
    as_of = datetime.now(KST)
    kr_quotes = {
        ticker: quote for ticker, quote in kr_quotes.items()
        if valid_kr_quote(ticker, quote.get("price"), quote, listed, as_of)
    }
    # A newly fetched response can predate the last verified trade for this ticker.
    previous = _load_json(_OUT, {}) if kr_quotes else {}
    older_quotes = previous.get("kr_quotes") if isinstance(previous, dict) else None
    older_prices = previous.get("prices") if isinstance(previous, dict) else None
    if isinstance(older_quotes, dict) and isinstance(older_prices, dict):
        for ticker, quote in kr_quotes.items():
            old = older_quotes.get(ticker)
            if valid_kr_quote(ticker, older_prices.get(ticker), old, listed, as_of):
                if aware_time(old["observed_at"]) >= aware_time(quote["observed_at"]):
                    kr_quotes[ticker] = old
    print(f"[pulse] KR 검증 {len(kr_quotes)}/{len(kr_tickers)}")

    # 4) 결과 조립
    indices = {}
    for key, sym in _INDEX_SYMBOLS.items():
        q = yahoo.get(sym)
        if q and q.get("price") is not None:
            indices[key] = {
                "value": q["price"],
                "change_pct": q.get("change_pct"),
                "symbol": sym,
            }

    prices = {ticker: quote["price"] for ticker, quote in kr_quotes.items()}
    for sym in us_symbols:
        q = yahoo.get(sym)
        if q and q.get("price") is not None:
            prices[sym] = q["price"]

    result = {
        "updated_at": as_of.isoformat(timespec="seconds"),
        "elapsed_sec": round(time.perf_counter() - t0, 2),
        "indices": indices,
        "prices": prices,
        "kr_quotes": kr_quotes,
        "counts": {
            "indices": len(indices),
            "kr": len(kr_quotes),
            "us": sum(1 for s in us_symbols if s in prices),
            "kr_requested": len(kr_tickers),
            "us_requested": len(us_symbols),
        },
    }

    # 🚨 전량 실패 가드 (#46, 2026-08-09). price_pulse 는 P0 스트림이다.
    #   지수·KR·US 를 전부 못 받았는데 파일을 새로 쓰면 내용은 빈 채로 mtime 만
    #   갱신되어 신선도 보드가 "0분 경과" 로 통과시킨다 = 없는 것보다 나쁘다.
    #   한쪽 시장만 휴장인 경우는 정상이므로 **전량 0** 일 때만 실패로 본다.
    #   실패 시 파일을 건드리지 않는다 — 빈 새 파일보다 옛 값이 낫다.
    obtained = len(indices) + len(kr_quotes) + result["counts"]["us"]
    requested = len(_INDEX_SYMBOLS) + len(kr_tickers) + len(us_symbols)
    if requested and not obtained:
        print(
            f"[pulse] outcome=total_fail 요청 {requested}건 전부 실패 "
            f"(지수 0 / KR 0 / US 0) — 산출 미갱신·실패 종료",
            file=sys.stderr,
        )
        return 1

    os.makedirs(_DATA, exist_ok=True)
    with open(_OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[pulse] 완료 {result['elapsed_sec']}s — 지수 {len(indices)} KR {len(kr_quotes)} US {result['counts']['us']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
