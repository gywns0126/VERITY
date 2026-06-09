"""
KOSPI/KOSDAQ 지수: pykrx(KRX) 우선, 실패 시 yfinance.
해외 지수(NDX, S&P500): yfinance.
"""
import time as _perf
from datetime import timedelta
from typing import Dict, Optional

import pandas as pd
import yfinance as yf

from api.config import now_kst

# pykrx KRX 지수 티커 (코스피·코스닥 종합)
_PYKRX_KOSPI = "1001"
_PYKRX_KOSDAQ = "2001"

KOSPI_MAJOR = {
    "005930.KS": "삼성전자",
    "000660.KS": "SK하이닉스",
    "373220.KS": "LG에너지솔루션",
    "207940.KS": "삼성바이오로직스",
    "005380.KS": "현대차",
    "000270.KS": "기아",
    "068270.KS": "셀트리온",
    "035420.KS": "NAVER",
    "035720.KS": "카카오",
    "051910.KS": "LG화학",
    "006400.KS": "삼성SDI",
    "055550.KS": "신한지주",
    "105560.KS": "KB금융",
    "003670.KS": "포스코퓨처엠",
    "012330.KS": "현대모비스",
    "066570.KS": "LG전자",
    "028260.KS": "삼성물산",
    "003550.KS": "LG",
    "096770.KS": "SK이노베이션",
    "034730.KS": "SK",
    "030200.KS": "KT",
    "032830.KS": "삼성생명",
    "086790.KS": "하나금융지주",
    "017670.KS": "SK텔레콤",
    "033780.KS": "KT&G",
    "009150.KS": "삼성전기",
    "034020.KS": "두산에너빌리티",
    "010130.KS": "고려아연",
    "003490.KS": "대한항공",
    "018260.KS": "삼성에스디에스",
}

KOSDAQ_MAJOR = {
    "247540.KQ": "에코프로비엠",
    "086520.KQ": "에코프로",
    "403870.KQ": "HPSP",
    "028300.KQ": "HLB",
    "067160.KQ": "아프리카TV",
    "277810.KQ": "레인보우로보틱스",
    "058470.KQ": "리노공업",
    "039030.KQ": "이오테크닉스",
    "035900.KQ": "JYP Ent.",
    "041510.KQ": "에스엠",
    "196170.KQ": "알테오젠",
    "348370.KQ": "엔켐",
    "257720.KQ": "실리콘투",
    "328130.KQ": "루닛",
    "145020.KQ": "휴젤",
}

US_MAJOR = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "META": "Meta Platforms",
    "TSLA": "Tesla",
    "AVGO": "Broadcom",
    "BRK-B": "Berkshire Hathaway",
    "JPM": "JPMorgan Chase",
    "LLY": "Eli Lilly",
    "V": "Visa",
    "UNH": "UnitedHealth",
    "MA": "Mastercard",
    "XOM": "ExxonMobil",
    "COST": "Costco",
    "HD": "Home Depot",
    "PG": "Procter & Gamble",
    "JNJ": "Johnson & Johnson",
    "NFLX": "Netflix",
    "ABBV": "AbbVie",
    "CRM": "Salesforce",
    "AMD": "AMD",
    "ADBE": "Adobe",
    "ORCL": "Oracle",
    "MRK": "Merck",
    "PEP": "PepsiCo",
    "KO": "Coca-Cola",
    "WMT": "Walmart",
    "BAC": "Bank of America",
    "TMO": "Thermo Fisher",
    "CSCO": "Cisco",
    "DIS": "Walt Disney",
    "INTC": "Intel",
    "QCOM": "Qualcomm",
    "PLTR": "Palantir",
    "COIN": "Coinbase",
    "SOFI": "SoFi Technologies",
    "ARM": "Arm Holdings",
    "SMCI": "Super Micro Computer",
}

_EXCHANGE_MAP = {
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ",
    "NYQ": "NYSE", "NYS": "NYSE",
    "ASE": "AMEX", "AMX": "AMEX",
    "PCX": "NYSE ARCA",
}

ALL_STOCKS = {**KOSPI_MAJOR, **KOSDAQ_MAJOR}
ALL_STOCKS_WITH_US = {**KOSPI_MAJOR, **KOSDAQ_MAJOR, **US_MAJOR}

_YF_INDEX_TICKERS = [
    ("^KS11", "kospi"),
    ("^KQ11", "kosdaq"),
    ("^NDX", "ndx"),
    ("^GSPC", "sp500"),
]


def _fi_scalar(fi, *keys):
    """yfinance fast_info에서 첫 유효 숫자 값."""
    if fi is None:
        return None
    for k in keys:
        try:
            v = fi[k]
        except Exception:
            continue
        if v is None:
            continue
        try:
            f = float(v)
            if pd.notna(f):
                return f
        except (TypeError, ValueError):
            continue
    return None


_SECTOR_KO = {
    "Technology": "IT/기술",
    "Communication Services": "통신/미디어",
    "Consumer Cyclical": "소비재",
    "Consumer Defensive": "필수소비재",
    "Financial Services": "금융",
    "Healthcare": "헬스케어",
    "Industrials": "산업재",
    "Basic Materials": "소재/화학",
    "Energy": "에너지",
    "Real Estate": "부동산",
    "Utilities": "유틸리티",
}

_INDUSTRY_KO_KEYWORDS = {
    "Semiconductor": "반도체",
    "Auto": "자동차",
    "Internet": "인터넷",
    "Software": "소프트웨어",
    "Bank": "은행",
    "Insurance": "보험",
    "Biotech": "바이오",
    "Pharma": "제약",
    "Construction": "건설",
    "Steel": "철강",
    "Chemical": "화학",
    "Telecom": "통신",
    "Entertainment": "엔터",
    "Retail": "유통",
    "Aerospace": "항공우주",
    "Ship": "조선",
    "Food": "식품",
    "Electric": "전기/전자",
    "Battery": "배터리",
    "Oil": "석유",
    "Gas": "가스",
    "Mining": "광업",
    "Defense": "방산",
    "Luxury": "럭셔리",
    "Gaming": "게임",
    "Packaging": "포장",
    "REIT": "리츠",
    "Solar": "태양광",
    "Wind": "풍력",
    "EV": "전기차",
    "Renewable": "신재생에너지",
}


def _resolve_company_type(sector: str, industry: str) -> str:
    """yfinance sector/industry → 간결한 한글 업종 라벨."""
    if not sector and not industry:
        return ""
    for kw, label in _INDUSTRY_KO_KEYWORDS.items():
        if kw.lower() in (industry or "").lower():
            return label
    return _SECTOR_KO.get(sector, "")


def _yf_index_snapshot(idx_ticker: str) -> dict:
    """
    단일 지수 스냅샷 + 1Y 기간별 추이.
    가능하면 fast_info(시장 개장 중 지연 시세), 없으면 최근 일봉 종가.
    """
    from api.collectors.yfinance_safe import safe_yf_call

    bad: dict = {"value": 0.0, "change_pct": 0.0}
    try:
        t = yf.Ticker(idx_ticker)
        last = None
        prev = None
        try:
            fi = safe_yf_call(lambda: t.fast_info, label=f"{idx_ticker}.fast_info")
            if fi is not None:
                last = _fi_scalar(fi, "last_price", "regular_market_price")
                prev = _fi_scalar(fi, "previous_close", "regular_market_previous_close")
        except Exception:
            pass

        base: dict = {}
        if last is not None and prev is not None and prev > 0:
            base = {
                "value": round(last, 2),
                "change_pct": round((last - prev) / prev * 100, 2),
            }
        else:
            hist_short = safe_yf_call(
                lambda: t.history(period="5d"),
                label=f"{idx_ticker}.history(5d)",
            )
            if hist_short is None:
                return bad
            hist_short = hist_short.dropna(subset=["Close"])
            if len(hist_short) >= 2:
                today_close = float(hist_short["Close"].iloc[-1])
                prev_close = float(hist_short["Close"].iloc[-2])
                if pd.notna(today_close) and pd.notna(prev_close) and prev_close > 0:
                    base = {"value": round(today_close, 2), "change_pct": round((today_close - prev_close) / prev_close * 100, 2)}
                else:
                    return bad
            elif len(hist_short) == 1:
                val = float(hist_short["Close"].iloc[-1])
                base = {"value": round(val, 2) if pd.notna(val) else 0.0, "change_pct": 0.0}
            else:
                return bad

        try:
            hist_1y = safe_yf_call(
                lambda: t.history(period="1y"),
                label=f"{idx_ticker}.history(1y)",
            )
            if hist_1y is not None:
                hist_1y = hist_1y.dropna(subset=["Close"])
                current = base["value"]
                if not hist_1y.empty and current > 0:
                    base["trend"] = _compute_period_trends(hist_1y, current, 2)
                    base["sparkline_weekly"] = _compute_weekly_sparkline(hist_1y, 2)
        except Exception:
            pass

        return base
    except Exception:
        return bad


def _pykrx_index_snapshot(pykrx_ticker: str) -> Optional[Dict[str, float]]:
    """
    KRX 일봉 기준 최신 종가·전일 대비(%). 장중이면 당일 봉이 채워질 때까지 전일 대비로 근사.
    KRX/네트워크 실패 시 None.
    """
    try:
        from pykrx import stock
    except ImportError:
        return None
    bad = None
    try:
        end = now_kst().date()
        start = end - timedelta(days=14)
        from_s = start.strftime("%Y%m%d")
        to_s = end.strftime("%Y%m%d")
        df = stock.get_index_ohlcv_by_date(from_s, to_s, pykrx_ticker)
        if df is None or df.empty:
            return bad
        close_col = "종가"
        if close_col not in df.columns:
            return bad
        closes = df[close_col].dropna()
        if len(closes) < 1:
            return bad
        last = float(closes.iloc[-1])
        if len(closes) >= 2:
            prev = float(closes.iloc[-2])
            pct = round((last - prev) / prev * 100, 2) if prev > 0 else 0.0
        else:
            pct = 0.0
        return {"value": round(last, 2), "change_pct": pct}
    except Exception:
        return bad


def _pykrx_equity_last_close(ticker_6: str) -> Optional[float]:
    """KRX 상장 종 최근 거래일 종가(당일 봉 반영). 네트워크/모듈 실패 시 None."""
    try:
        from pykrx import stock as pykrx_stock
    except ImportError:
        return None
    try:
        code = str(ticker_6).zfill(6)
        end = now_kst().date()
        start = end - timedelta(days=14)
        df = pykrx_stock.get_market_ohlcv_by_date(
            start.strftime("%Y%m%d"),
            end.strftime("%Y%m%d"),
            code,
        )
        if df is None or df.empty or "종가" not in df.columns:
            return None
        closes = df["종가"].dropna()
        if len(closes) < 1:
            return None
        v = float(closes.iloc[-1])
        return v if v > 0 else None
    except Exception:
        return None


def get_equity_last_price(ticker_yf: str) -> Optional[float]:
    """
    개별 종목 최신가.
    KOSPI/KOSDAQ: pykrx(거래소 일봉) 우선 → yfinance fast_info → 최근 일봉.
    US: yfinance fast_info → 최근 일봉.
    """
    if not ticker_yf:
        return None
    ticker_yf = str(ticker_yf).strip()
    has_dot = "." in ticker_yf
    if has_dot:
        parts = ticker_yf.split(".")
        code = parts[0].zfill(6)
        suf = parts[-1].upper()
    else:
        code = ticker_yf
        suf = ""
    if suf in ("KS", "KQ"):
        pk = _pykrx_equity_last_close(code)
        if pk is not None:
            return pk
    from api.collectors.yfinance_safe import safe_yf_call, yf_ticker
    try:
        # 2026-06-09: plain yf.Ticker → yf_ticker (curl_cffi session, anti-bot + 연결 안정).
        #   socket-level hang 방어 (6/9 realtime watchdog SIGTERM 사고 — fast_info/history
        #   소켓 무한 대기로 10분 watchdog 도달). per-ticker thread cap 은 build_price_map 의
        #   safe_collect 래핑이 담당 (이중 방어).
        t = yf_ticker(ticker_yf)
        try:
            fi = safe_yf_call(lambda: t.fast_info, label=f"{ticker_yf}.fast_info")
            if fi is not None:
                last = _fi_scalar(fi, "last_price", "regular_market_price")
                if last is not None and last > 0:
                    return float(last)
        except Exception:
            pass
        hist = safe_yf_call(
            lambda: t.history(period="5d", timeout=8),
            label=f"{ticker_yf}.history(5d)",
        )
        if hist is None:
            return None
        hist = hist.dropna(subset=["Close"])
        if len(hist) >= 1:
            v = float(hist["Close"].iloc[-1])
            if pd.notna(v) and v > 0:
                return v
    except Exception:
        pass
    return None


def get_market_index() -> dict:
    """KOSPI, KOSDAQ, 나스닥100(^NDX), S&P500(^GSPC) 지수 조회"""
    out: Dict[str, Dict[str, float]] = {}
    kospi_pk = _pykrx_index_snapshot(_PYKRX_KOSPI)
    kosdaq_pk = _pykrx_index_snapshot(_PYKRX_KOSDAQ)
    out["kospi"] = kospi_pk if kospi_pk else _yf_index_snapshot("^KS11")
    out["kosdaq"] = kosdaq_pk if kosdaq_pk else _yf_index_snapshot("^KQ11")
    for tick, name in _YF_INDEX_TICKERS:
        if name in ("kospi", "kosdaq"):
            continue
        out[name] = _yf_index_snapshot(tick)
    return out


_PERIOD_TRADING_DAYS = {"1m": 22, "3m": 66, "6m": 132, "1y": 252}


def _compute_period_trends(hist: pd.DataFrame, current_price: float, rnd: int = 2) -> dict:
    """1Y 일봉에서 1M/3M/6M/1Y 수익률·고가·저가·평균거래량 계산."""
    trends = {}
    for label, days in _PERIOD_TRADING_DAYS.items():
        subset = hist.tail(days)
        if subset.empty:
            trends[label] = None
            continue
        first_close = float(subset.iloc[0]["Close"])
        change_pct = ((current_price - first_close) / first_close * 100) if first_close else 0
        avg_vol = int(subset["Volume"].mean()) if "Volume" in subset.columns else 0
        trends[label] = {
            "change_pct": round(change_pct, 2),
            "high": round(float(subset["High"].max()), rnd),
            "low": round(float(subset["Low"].min()), rnd),
            "avg_volume": avg_vol,
        }
    return trends


def _compute_weekly_sparkline(hist: pd.DataFrame, rnd: int = 2) -> list:
    """1Y 일봉을 주봉 종가로 리샘플 (~52pt)."""
    if hist.empty:
        return []
    weekly = hist["Close"].resample("W-FRI").last().dropna()
    return [round(float(v), rnd) for v in weekly.values]


def _market_cap_or_fallback(market_cap, shares_outstanding, price) -> int:
    """yfinance marketCap 누락(0/None) 시 sharesOutstanding × price fallback.
    2026-06-07 action_queue aed82498 — TMO/SOFI 등 US 종목 시총 결손 → Ackman/원본 Altman 복구."""
    if not market_cap and shares_outstanding and price and price > 0:
        try:
            return int(float(shares_outstanding) * float(price))
        except (ValueError, TypeError):
            return 0
    return int(market_cap) if market_cap else 0


def get_stock_data(
    ticker_yf: str,
    period: str = "1y",
    name_hint: Optional[str] = None,
    _metrics: Optional[Dict] = None,
) -> dict:
    """
    yfinance로 종목 데이터 수집 (KR + US 공용)
    반환: {name, ticker, market, currency, price, volume, trading_value, high_52w, ...}

    name 해석 우선순위: name_hint (KRX ISU_NM 등) > 정적 화이트리스트 > yfinance longName/shortName > ticker_yf

    _metrics: 호출자가 dict 를 넘기면 yf_rate_limited 누적 (yfinance_safe wrapper 정합).
    """
    from api.collectors.yfinance_safe import safe_yf_call

    _all = {**ALL_STOCKS, **US_MAJOR}
    name = name_hint or _all.get(ticker_yf, ticker_yf)
    _name_is_fallback = (name_hint is None) and (name == ticker_yf)

    is_kr = ticker_yf.endswith(".KS") or ticker_yf.endswith(".KQ")
    if is_kr:
        market = "KOSPI" if ticker_yf.endswith(".KS") else "KOSDAQ"
        ticker_short = ticker_yf.split(".")[0]
        currency = "KRW"
    else:
        market = None
        ticker_short = ticker_yf
        currency = "USD"

    try:
        t = yf.Ticker(ticker_yf)
        # rate limit 대응 wrapper — 429 retry + cooler pause + metric 적재
        hist = safe_yf_call(
            lambda: t.history(period=period),
            label=f"{ticker_yf}.history",
            metrics=_metrics,
        )
        if hist is None or hist.empty:
            return None

        hist = hist.dropna(subset=["Close"])
        if hist.empty:
            return None
        latest = hist.iloc[-1]
        price = float(latest["Close"])
        if pd.isna(price):
            return None
        volume = int(latest["Volume"]) if pd.notna(latest["Volume"]) else 0
        trading_value = int(price * volume)

        high_52w = float(hist["High"].max())
        drop_from_high = ((price - high_52w) / high_52w * 100) if high_52w > 0 else 0

        info = safe_yf_call(
            lambda: t.info or {},
            label=f"{ticker_yf}.info",
            metrics=_metrics,
        ) or {}

        # name 보강: 정적 맵에도 없고 hint 도 없으면 yfinance 메타에서 보강 (Phase 2-A 확장 유니버스 케이스)
        if _name_is_fallback:
            yf_name = info.get("longName") or info.get("shortName")
            if yf_name:
                name = str(yf_name).strip() or name

        if not is_kr and market is None:
            exchange = (info.get("exchange") or "").upper()
            market = _EXCHANGE_MAP.get(exchange, exchange or "US")
            currency = info.get("currency", "USD")

        per = info.get("trailingPE", info.get("forwardPE", 0)) or 0
        pbr = info.get("priceToBook", 0) or 0
        div_yield = 0
        _raw_yield = info.get("dividendYield", 0) or 0
        _div_rate = info.get("dividendRate") or info.get("trailingAnnualDividendRate") or 0
        if _div_rate and float(_div_rate) > 0 and price > 0:
            div_yield = (float(_div_rate) / price) * 100
        elif 0 < _raw_yield < 1.0:
            div_yield = _raw_yield * 100
        if div_yield > 20:
            div_yield = 0
        market_cap = info.get("marketCap", 0) or 0
        eps = info.get("trailingEps", 0) or 0

        debt_ratio = info.get("debtToEquity", 0) or 0
        operating_margin = (info.get("operatingMargins", 0) or 0) * 100
        profit_margin = (info.get("profitMargins", 0) or 0) * 100
        revenue_growth = (info.get("revenueGrowth", 0) or 0) * 100
        roe = (info.get("returnOnEquity", 0) or 0) * 100
        current_ratio = info.get("currentRatio", 0) or 0

        # ── Phase 2-B 보강 (2026-05-10) — yfinance info 이미-fetched 미사용 필드 추출 ──
        # API 호출 0 추가. 텐버거 leading 정량 지표 (F-Score / GP/A / CANSLIM C / Buffett FCF) 정확도 향상.
        gross_margins = info.get("grossMargins")
        roa = info.get("returnOnAssets")
        eps_quarterly_growth = info.get("earningsQuarterlyGrowth")
        free_cashflow = info.get("freeCashflow")
        operating_cashflow = info.get("operatingCashflow")
        shares_outstanding = info.get("sharesOutstanding")
        held_pct_insiders = info.get("heldPercentInsiders")
        held_pct_institutions = info.get("heldPercentInstitutions")

        # market_cap fallback (2026-06-07 action_queue aed82498) — yfinance marketCap
        # 간헐 누락(TMO/SOFI 등) 시 sharesOutstanding × price 로 산출 → Ackman/원본 Altman 평가 복구.
        market_cap = _market_cap_or_fallback(market_cap, shares_outstanding, price)

        company_type = _resolve_company_type(info.get("sector", ""), info.get("industry", ""))

        spark = []
        recent = hist.tail(20)
        for _, row in recent.iterrows():
            c = float(row["Close"])
            if pd.notna(c):
                spark.append(round(c, 2) if currency == "USD" else round(c, 0))

        rnd = 2 if currency == "USD" else 0
        trends = _compute_period_trends(hist, price, rnd)
        sparkline_weekly = _compute_weekly_sparkline(hist, rnd)

        result = {
            "ticker": ticker_short,
            "ticker_yf": ticker_yf,
            "name": name,
            "market": market,
            "currency": currency,
            "price": price,
            "volume": volume,
            "trading_value": trading_value,
            "market_cap": market_cap,
            "high_52w": high_52w,
            "drop_from_high_pct": round(drop_from_high, 2),
            "per": round(per, 2) if per else 0,
            "pbr": round(pbr, 2) if pbr else 0,
            "eps": round(eps, 2) if eps else 0,
            "div_yield": round(div_yield, 2) if div_yield else 0,
            "debt_ratio": round(debt_ratio, 1),
            "operating_margin": round(operating_margin, 1),
            "profit_margin": round(profit_margin, 1),
            "revenue_growth": round(revenue_growth, 1),
            "roe": round(roe, 1),
            "current_ratio": round(current_ratio, 2),
            "sparkline": spark,
            "trends": trends,
            "sparkline_weekly": sparkline_weekly,
        }
        # Phase 2-B 보강 — None 일 수 있으므로 optional 키 (downstream None handling 의무)
        if gross_margins is not None:
            result["gross_margins"] = round(float(gross_margins) * 100, 2)
        if roa is not None:
            result["roa"] = round(float(roa) * 100, 2)
        if eps_quarterly_growth is not None:
            result["eps_quarterly_growth"] = round(float(eps_quarterly_growth) * 100, 2)
        if free_cashflow is not None:
            result["free_cashflow"] = int(free_cashflow)
        if operating_cashflow is not None:
            result["operating_cashflow"] = int(operating_cashflow)
        if shares_outstanding is not None:
            result["shares_outstanding"] = int(shares_outstanding)
        if held_pct_insiders is not None:
            result["held_pct_insiders"] = round(float(held_pct_insiders) * 100, 2)
        if held_pct_institutions is not None:
            result["held_pct_institutions"] = round(float(held_pct_institutions) * 100, 2)
        if company_type:
            result["company_type"] = company_type
        # funnel sprint Step 4 (2026-05-17): Sector Diversified — raw sector / industry
        # 추가하여 wide_scan 의 sector 분산 알고리즘 사용. yfinance .info 'sector' 가 GICS sector.
        raw_sector = info.get("sector") or ""
        raw_industry = info.get("industry") or ""
        if raw_sector:
            result["sector"] = raw_sector
        if raw_industry:
            result["industry"] = raw_industry
        return result
    except Exception as e:
        print(f"  [수집 실패] {name}: {e}")
        return None


def get_all_stock_data(
    market_scope: str = "all",
    custom_universe: Optional[Dict[str, str]] = None,
    _metrics: Optional[Dict] = None,
) -> list:
    """전체 종목 데이터 수집. market_scope: 'kr' | 'us' | 'all'.

    custom_universe (Phase 2-A): {ticker_yf: name} dict 가 주어지면 정적 화이트리스트 대신 사용.
      - market_scope 는 무시되고 custom_universe 만 처리.
      - is_us 판정은 ticker_yf 의 .KS/.KQ 미부착 여부로 판단.

    _metrics: 호출자가 dict 를 넘기면 yf_attempted / yf_failed / yf_rate_limited 를 채움.
      ramp_up_monitor silent skip 차단 의무 (memory feedback_data_collection_verification_mandatory).
    """
    if custom_universe is not None:
        universe = custom_universe
    elif market_scope == "kr":
        universe = {**KOSPI_MAJOR, **KOSDAQ_MAJOR}
    elif market_scope == "us":
        universe = US_MAJOR
    else:
        universe = ALL_STOCKS_WITH_US

    results = []
    total = len(universe)
    failed = 0
    # _metrics 가 None 이면 local dict 만들어서 yf_rate_limited 누적 (wrapper 가 in-place 갱신)
    rl_metrics: Dict = _metrics if _metrics is not None else {}
    rl_metrics.setdefault("yf_rate_limited", 0)
    # W3 wiring (2026-05-21) — 첫 KR fetch latency 측정 (runtime_load_log.kr_first_call_duration_ms).
    # 첫 .KS/.KQ 종목 1건만 측정 (cold call 대표값). 이후 종목은 미측정.
    kr_first_call_ms = None
    for i, (ticker_yf, name) in enumerate(universe.items(), 1):
        # custom_universe 일 때는 .KS/.KQ suffix 부재 = US 추정
        is_us = (ticker_yf in US_MAJOR) or not (
            ticker_yf.endswith(".KS") or ticker_yf.endswith(".KQ")
        )
        label = "$" if is_us else "원"
        print(f"  [{i}/{total}] {name} 수집 중...", end="")
        # custom_universe 의 name (예: KRX ISU_NM) 을 hint 로 전달 — 정적 맵 미수록 종목 (Phase 2-A) 도 한국 종목명 보존
        _kr_t0 = _perf.perf_counter() if (not is_us and kr_first_call_ms is None) else None
        data = get_stock_data(
            ticker_yf,
            period="1y",
            name_hint=name if custom_universe is not None else None,
            _metrics=rl_metrics,
        )
        if _kr_t0 is not None:
            kr_first_call_ms = int((_perf.perf_counter() - _kr_t0) * 1000)
        if data:
            results.append(data)
            if is_us:
                print(f" ✓ ${data['price']:,.2f}")
            else:
                print(f" ✓ {data['price']:,.0f}원")
        else:
            failed += 1
            print(" ✗ 실패")
    if _metrics is not None:
        _metrics["yf_attempted"] = total
        _metrics["yf_succeeded"] = len(results)
        _metrics["yf_failed"] = failed
        _metrics["yf_failure_rate"] = (failed / total) if total else 0.0
        # yf_rate_limited 는 wrapper 가 이미 갱신함 (rl_metrics == _metrics)
        # W3 wiring (2026-05-21) — runtime_load_log 인자 통합용 노출.
        if kr_first_call_ms is not None:
            _metrics["kr_first_call_ms"] = kr_first_call_ms
    return results


def get_short_interest_yf(ticker_yf: str) -> dict:
    """
    yfinance로 미국 주식 공매도 정보 수집 (무료 대체 소스).
    NYSE/NASDAQ 공시 기반 월 2회 업데이트 — 중장기 리스크 체크용으로 충분.
    Polygon Options Starter($29/월) 대체.
    """
    result = {
        "short_pct": None,
        "short_pct_prior": None,
        "days_to_cover": None,
        "shares_short": None,
        "shares_short_prior": None,
        "report_date": None,
        "trend": None,
    }
    try:
        import yfinance as yf
        from api.collectors.yfinance_safe import safe_yf_call
        info = safe_yf_call(
            lambda: yf.Ticker(ticker_yf).info or {},
            label=f"{ticker_yf}.short_info",
        ) or {}
    except Exception:
        return result

    try:
        pct = info.get("shortPercentOfFloat")
        if pct is not None:
            result["short_pct"] = round(float(pct) * 100, 2)
    except Exception:
        pass
    try:
        ratio = info.get("shortRatio")
        if ratio is not None:
            result["days_to_cover"] = round(float(ratio), 2)
    except Exception:
        pass
    try:
        s = info.get("sharesShort")
        if s is not None:
            result["shares_short"] = int(s)
    except Exception:
        pass
    try:
        sp = info.get("sharesShortPriorMonth")
        if sp is not None:
            result["shares_short_prior"] = int(sp)
    except Exception:
        pass
    try:
        ts = info.get("dateShortInterest")
        if ts:
            import datetime as _dt
            result["report_date"] = _dt.datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except Exception:
        pass

    ss = result["shares_short"] or 0
    sp = result["shares_short_prior"] or 0
    if ss and sp:
        delta = (ss - sp) / sp
        if delta > 0.15:
            result["trend"] = "surge"
        elif delta > 0.03:
            result["trend"] = "up"
        elif delta < -0.15:
            result["trend"] = "drop"
        elif delta < -0.03:
            result["trend"] = "down"
        else:
            result["trend"] = "flat"
        try:
            result["short_pct_prior"] = round(sp / (info.get("floatShares") or info.get("sharesOutstanding") or 1) * 100, 2)
        except Exception:
            pass

    return result


def get_extended_financials(ticker_yf: str) -> dict:
    """yfinance 확장 재무 데이터: 분기 실적, 배당 이력, ESG."""
    result: dict = {
        "quarterly_earnings": [],
        "dividend_history": [],
        "sustainability": {},
    }
    try:
        import yfinance as yf
        from api.collectors.yfinance_safe import safe_yf_call
        t = yf.Ticker(ticker_yf)

        # 분기 실적
        try:
            qe = safe_yf_call(lambda: t.quarterly_earnings, label=f"{ticker_yf}.quarterly_earnings")
            if qe is not None and not qe.empty:
                for idx, row in qe.tail(4).iterrows():
                    result["quarterly_earnings"].append({
                        "quarter": str(idx),
                        "revenue": float(row.get("Revenue", 0)),
                        "earnings": float(row.get("Earnings", 0)),
                    })
        except Exception:
            pass

        # 배당 이력 (최근 8건)
        try:
            divs = safe_yf_call(lambda: t.dividends, label=f"{ticker_yf}.dividends")
            if divs is not None and len(divs) > 0:
                for dt, val in divs.tail(8).items():
                    result["dividend_history"].append({
                        "date": str(dt.date()) if hasattr(dt, "date") else str(dt)[:10],
                        "amount": round(float(val), 4),
                    })
        except Exception:
            pass

        # ESG 점수
        try:
            sus = safe_yf_call(lambda: t.sustainability, label=f"{ticker_yf}.sustainability")
            if sus is not None and not sus.empty:
                total = sus.loc["totalEsg"].values[0] if "totalEsg" in sus.index else None
                env = sus.loc["environmentScore"].values[0] if "environmentScore" in sus.index else None
                soc = sus.loc["socialScore"].values[0] if "socialScore" in sus.index else None
                gov = sus.loc["governanceScore"].values[0] if "governanceScore" in sus.index else None
                result["sustainability"] = {
                    "total": float(total) if total is not None else None,
                    "environment": float(env) if env is not None else None,
                    "social": float(soc) if soc is not None else None,
                    "governance": float(gov) if gov is not None else None,
                }
        except Exception:
            pass

    except Exception:
        pass
    return result
