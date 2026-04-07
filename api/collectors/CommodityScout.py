"""
VERITY 원자재 스카우트 — yfinance 기반 상관·스프레드·마진 방어력.

- 추적 종목(후보+보유)의 섹터별 핵심 원자재만 조회(쿼터 절약).
- Gemini로 섹터→티커 매핑 보강(일 1회 캐시, 실패 시 정적 폴백).
- 결과: data/commodity_impact.json + 종목별 safety_adjustment / margin_safety_score.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from api.config import (
    COMMODITY_IMPACT_PATH,
    COMMODITY_MAP_CACHE_PATH,
    GEMINI_API_KEY,
    GEMINI_MODEL,
)

LOOKBACK_DAYS = 90
CORR_WINDOW = 60
SHOCK_PCT = 10.0
MOM_ALERT_PCT = float(os.environ.get("COMMODITY_MOM_ALERT_PCT", "10"))

# Yahoo Finance 섹터(영문) → 대표 원자재 티커 (Gemini 실패 시)
SECTOR_COMMODITY_FALLBACK: Dict[str, List[str]] = {
    "Energy": ["CL=F", "BZ=F"],
    "Oil & Gas": ["CL=F"],
    "Basic Materials": ["HG=F", "GC=F"],
    "Materials": ["HG=F", "GC=F"],
    "Utilities": ["NG=F"],
    "Consumer Defensive": ["ZC=F", "ZW=F"],
    "Consumer Staples": ["ZC=F"],
    "Consumer Cyclical": ["CL=F", "HG=F"],
    "Industrials": ["HG=F", "CL=F"],
    "Real Estate": ["CL=F"],
    "Financial Services": ["CL=F"],
    "Financials": ["CL=F"],
    "Healthcare": ["CL=F"],
    "Technology": ["LIT", "SMH"],
    "Communication Services": ["CL=F"],
    "Unknown": ["CL=F"],
}


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return float(obj) if isinstance(obj, np.floating) else int(obj)
    return obj


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _fetch_close_series(ticker: str) -> Optional[pd.Series]:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=f"{LOOKBACK_DAYS}d", auto_adjust=True)
        if hist is None or hist.empty or "Close" not in hist.columns:
            return None
        s = hist["Close"].dropna()
        return s if len(s) >= 20 else None
    except Exception:
        return None


def _daily_returns(close: pd.Series) -> pd.Series:
    return close.pct_change().dropna()


def _pearson_r(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    if len(a) < 10 or len(b) < 10:
        return None
    if len(a) != len(b):
        m = min(len(a), len(b))
        a, b = a[-m:], b[-m:]
    if np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def _aligned_returns(stock_close: pd.Series, comm_close: pd.Series) -> Tuple[np.ndarray, np.ndarray]:
    df = pd.DataFrame({"s": stock_close, "c": comm_close}).dropna()
    if len(df) < CORR_WINDOW + 5:
        return np.array([]), np.array([])
    rs = _daily_returns(df["s"]).iloc[-CORR_WINDOW:]
    rc = _daily_returns(df["c"]).iloc[-CORR_WINDOW:]
    joined = pd.DataFrame({"rs": rs, "rc": rc}).dropna()
    if len(joined) < 20:
        return np.array([]), np.array([])
    return joined["rs"].values, joined["rc"].values


def _rolling_window_return(close: pd.Series, window: int) -> float:
    if len(close) < window + 1:
        return 0.0
    a = float(close.iloc[-window - 1])
    b = float(close.iloc[-1])
    if a <= 0:
        return 0.0
    return (b / a - 1.0) * 100.0


def _commodity_volatility_score(comm_close: pd.Series) -> float:
    r = _daily_returns(comm_close)
    if len(r) < 20:
        return 50.0
    ann = float(r.std() * np.sqrt(252) * 100.0)
    return float(_clip(ann / 40.0 * 100.0, 0.0, 100.0))


def _pricing_power_score(stock: Dict[str, Any], consensus_block: Optional[Dict[str, Any]] = None) -> float:
    op = float(stock.get("operating_margin") or 0)
    margin_part = _clip(op / 22.0 * 100.0, 0.0, 100.0)
    cons = consensus_block or stock.get("consensus") or {}
    cs = cons.get("consensus_score")
    try:
        c = float(cs) if cs is not None else 50.0
    except (TypeError, ValueError):
        c = 50.0
    return float(_clip(0.55 * margin_part + 0.45 * c, 0.0, 100.0))


def _spread_regime(c20: float, s20: float) -> Tuple[str, int]:
    """20거래일 원자재/주가 변화율로 마진 스프레드 국면 분류 → 안심 점수 가감."""
    if c20 <= -3 and s20 >= 3:
        return "마진 스프레드 확대", 25
    if c20 >= 3 and s20 >= 0:
        return "동반 상승", 10
    if c20 >= 3 and s20 < 0:
        if c20 >= 5 and s20 <= -5:
            return "최악의 상황", -50
        return "비용 압박", -20
    if c20 <= -3 and s20 < -3:
        return "동반 약세", -5
    return "중립", 0


def _margin_safety_formula(pricing_power: float, raw_vol: float) -> float:
    return float(pricing_power * 0.6 - raw_vol * 0.4)


def _stock_sector(ticker_yf: str) -> str:
    try:
        info = yf.Ticker(ticker_yf).info or {}
        sec = info.get("sector") or info.get("category") or ""
        if isinstance(sec, str) and sec.strip():
            return sec.strip()
    except Exception:
        pass
    return "Unknown"


def _tickers_for_sector(sector: str, gemini_map: Dict[str, List[str]]) -> List[str]:
    if sector in gemini_map and gemini_map[sector]:
        return gemini_map[sector][:2]
    fb = SECTOR_COMMODITY_FALLBACK.get(sector) or SECTOR_COMMODITY_FALLBACK["Unknown"]
    return fb[:2]


def _parse_gemini_json(text: str) -> Dict[str, List[str]]:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        t = t.rsplit("```", 1)[0]
    data = json.loads(t)
    out: Dict[str, List[str]] = {}
    raw = data.get("mappings") or data
    if not isinstance(raw, dict):
        return out
    for k, v in raw.items():
        tickers: List[str] = []
        if isinstance(v, list):
            for item in v:
                if isinstance(item, str):
                    tickers.append(item.strip())
                elif isinstance(item, dict) and item.get("ticker"):
                    tickers.append(str(item["ticker"]).strip())
        elif isinstance(v, str):
            tickers.append(v.strip())
        tickers = [x for x in tickers if re.match(r"^[A-Z0-9=\-\.]+$", x, re.I)]
        if tickers:
            out[str(k)] = tickers[:3]
    return out


def build_sector_commodity_map_gemini(sectors: List[str]) -> Dict[str, List[str]]:
    """섹터 문자열 목록 → Yahoo 티커 (Gemini 1회)."""
    if not GEMINI_API_KEY or not sectors:
        return {}
    try:
        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)
        uniq = sorted(set(sectors))
        body = json.dumps(uniq, ensure_ascii=False)
        prompt = f"""한국 상장주의 Yahoo Finance `sector` 문자열 목록이다: {body}

각 섹터마다 해당 업종 원가에 가장 민감한 글로벌 원자재/에너지/농산물 Yahoo Finance 티커를 1~2개만 제시하라.
반드시 실제 거래되는 티커만 (예: CL=F WTI, BZ=F 브렌트, HG=F 구리, GC=F 금, SI=F 은, NG=F 천연가스, ZC=F 옥수수, ZW=F 밀, LIT 리튬 ETF, COPX 구리 ETF).

JSON만 출력:
{{"mappings": {{"Technology": ["LIT", "HG=F"], "Energy": ["CL=F"]}}}}
키는 입력 섹터 문자열과 정확히 동일하게."""
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        return _parse_gemini_json(response.text or "{}")
    except Exception:
        return {}


def load_or_build_sector_map(sectors: List[str]) -> Dict[str, List[str]]:
    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(os.path.dirname(COMMODITY_MAP_CACHE_PATH), exist_ok=True)
    if os.path.isfile(COMMODITY_MAP_CACHE_PATH):
        try:
            with open(COMMODITY_MAP_CACHE_PATH, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("date") == today and isinstance(cached.get("mappings"), dict):
                return {str(k): list(v) for k, v in cached["mappings"].items()}
        except (json.JSONDecodeError, OSError):
            pass

    gmap = build_sector_commodity_map_gemini(list(set(sectors)))
    merged: Dict[str, List[str]] = {}
    for s in set(sectors):
        if gmap.get(s):
            merged[s] = gmap[s][:3]
        else:
            fb = SECTOR_COMMODITY_FALLBACK.get(s) or SECTOR_COMMODITY_FALLBACK["Unknown"]
            merged[s] = fb[:2]

    try:
        with open(COMMODITY_MAP_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_sanitize({"date": today, "mappings": merged}), f, ensure_ascii=False, indent=2)
    except OSError:
        pass
    return merged


def _shock_history_note(
    stock_close: pd.Series,
    comm_close: pd.Series,
    shock_pct: float = SHOCK_PCT,
) -> Dict[str, Any]:
    """원자재 rolling N일 +10% 구간에서 주가 평균 수익률 요약."""
    df = pd.DataFrame({"s": stock_close, "c": comm_close}).dropna()
    if len(df) < 30:
        return {"windows": 0, "avg_stock_when_commodity_shock_pct": None}
    windows = 0
    stock_rets: List[float] = []
    for win in (10, 15, 20):
        if len(df) < win + 1:
            continue
        cr = df["c"].pct_change(win) * 100.0
        sr = df["s"].pct_change(win) * 100.0
        mask = cr >= shock_pct
        w = int(mask.sum())
        if w > 0:
            windows += w
            stock_rets.extend(sr[mask].dropna().tolist())
    if not stock_rets:
        return {"windows": 0, "avg_stock_when_commodity_shock_pct": None}
    return {
        "windows": windows,
        "avg_stock_when_commodity_shock_pct": round(float(np.mean(stock_rets)), 2),
    }


def _prior_month_vs_spot_pct(comm_close: pd.Series) -> Optional[float]:
    """직전 달력월 평균 종가 대비 최근 종가 변화율(%)."""
    if comm_close.empty:
        return None
    last_dt = comm_close.index[-1]
    if hasattr(last_dt, "to_pydatetime"):
        last_dt = last_dt.to_pydatetime()
    first_this = datetime(last_dt.year, last_dt.month, 1)
    prev_end = first_this - timedelta(days=1)
    prev_start = datetime(prev_end.year, prev_end.month, 1)
    m = comm_close.to_frame("c")
    m = m.reset_index()
    col = m.columns[0]
    mask = (m[col] >= pd.Timestamp(prev_start)) & (m[col] <= pd.Timestamp(prev_end))
    prev = m.loc[mask, "c"]
    if prev.empty or float(prev.mean()) <= 0:
        return None
    spot = float(comm_close.iloc[-1])
    return round((spot / float(prev.mean()) - 1.0) * 100.0, 2)


def analyze_one_stock(
    stock: Dict[str, Any],
    sector_map: Dict[str, List[str]],
    sector: Optional[str] = None,
    close_cache: Optional[Dict[str, Optional[pd.Series]]] = None,
) -> Dict[str, Any]:
    ticker_yf = stock.get("ticker_yf") or f"{stock.get('ticker', '')}.KS"
    sector = sector if sector is not None else _stock_sector(ticker_yf)
    comm_tickers = _tickers_for_sector(sector, sector_map)

    def _close(sym: str) -> Optional[pd.Series]:
        if close_cache is not None:
            if sym not in close_cache:
                close_cache[sym] = _fetch_close_series(sym)
            return close_cache[sym]
        return _fetch_close_series(sym)

    stock_close = _close(ticker_yf)
    if stock_close is None:
        return {
            "sector": sector,
            "commodity_tickers": comm_tickers,
            "error": "stock_history_empty",
        }

    best: Optional[Dict[str, Any]] = None
    best_abs_r = -1.0

    for ct in comm_tickers:
        cclose = _close(ct)
        if cclose is None:
            continue
        rs, rc = _aligned_returns(stock_close, cclose)
        r60 = _pearson_r(rs, rc) if len(rs) >= 20 else None
        c20 = _rolling_window_return(cclose, 20)
        s20 = _rolling_window_return(stock_close, 20)
        regime, adj = _spread_regime(c20, s20)
        vol_s = _commodity_volatility_score(cclose)
        pp = _pricing_power_score(stock, stock.get("consensus"))
        margin_safety = _margin_safety_formula(pp, vol_s)
        shock = _shock_history_note(stock_close, cclose)
        mom_spike = _prior_month_vs_spot_pct(cclose)

        row = {
            "commodity_ticker": ct,
            "correlation_60d": round(r60, 4) if r60 is not None else None,
            "commodity_20d_pct": round(c20, 2),
            "stock_20d_pct": round(s20, 2),
            "spread_regime": regime,
            "safety_adjustment": adj,
            "pricing_power": round(pp, 1),
            "raw_material_volatility_score": round(vol_s, 1),
            "margin_safety_score": round(margin_safety, 2),
            "shock_analysis": shock,
            "vs_prior_month_avg_pct": mom_spike,
        }
        ar = abs(r60) if r60 is not None else 0.0
        if ar >= best_abs_r:
            best_abs_r = ar
            best = row

    if best is None:
        return {
            "sector": sector,
            "commodity_tickers": comm_tickers,
            "error": "commodity_history_empty",
        }

    out = {
        "sector": sector,
        "commodity_tickers": comm_tickers,
        "primary": best,
    }
    return out


def collect_commodity_mom_alerts(
    all_commodity_tickers: List[str],
    close_cache: Optional[Dict[str, Optional[pd.Series]]] = None,
) -> List[Dict[str, Any]]:
    """전월 평균 대비 |변화| >= MOM_ALERT_PCT 인 원자재만 긴급 후보."""

    def _close(sym: str) -> Optional[pd.Series]:
        if close_cache is not None:
            if sym not in close_cache:
                close_cache[sym] = _fetch_close_series(sym)
            return close_cache[sym]
        return _fetch_close_series(sym)

    alerts: List[Dict[str, Any]] = []
    seen = set()
    for ct in all_commodity_tickers:
        if ct in seen:
            continue
        seen.add(ct)
        s = _close(ct)
        if s is None:
            continue
        pct = _prior_month_vs_spot_pct(s)
        if pct is None:
            continue
        if abs(pct) < MOM_ALERT_PCT:
            continue
        alerts.append(
            {
                "commodity_ticker": ct,
                "vs_prior_month_avg_pct": pct,
                "last_close": round(float(s.iloc[-1]), 4),
            }
        )
    alerts.sort(key=lambda x: abs(x["vs_prior_month_avg_pct"]), reverse=True)
    return alerts


def run_commodity_scout(
    candidates: List[Dict[str, Any]],
    holdings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    후보+보유 종목에 대해 원자재 상관·스프레드 분석.
    yfinance 호출: 종목당 섹터 조회 + 공통 원자재 시계열은 티커당 1회 캐시.
    """
    holdings = holdings or []
    universe: Dict[str, Dict[str, Any]] = {}
    for s in candidates:
        t = str(s.get("ticker", "")).zfill(6)
        universe[t] = s
    for h in holdings:
        t = str(h.get("ticker", "")).zfill(6)
        if t not in universe:
            universe[t] = {
                "ticker": h.get("ticker"),
                "ticker_yf": h.get("ticker_yf") or f"{t}.KS",
                "name": h.get("name", t),
                "operating_margin": h.get("operating_margin", 0),
                "consensus": {},
            }

    stocks_list = list(universe.values())
    close_cache: Dict[str, Optional[pd.Series]] = {}
    sector_by_yf: Dict[str, str] = {}
    sectors: List[str] = []
    for st in stocks_list:
        ty = st.get("ticker_yf") or f"{st.get('ticker', '')}.KS"
        if ty not in sector_by_yf:
            sector_by_yf[ty] = _stock_sector(ty)
        sectors.append(sector_by_yf[ty])

    sector_map = load_or_build_sector_map(sectors)

    all_comm: List[str] = []
    for st in stocks_list:
        ty = st.get("ticker_yf") or f"{st.get('ticker', '')}.KS"
        sec = sector_by_yf[ty]
        all_comm.extend(_tickers_for_sector(sec, sector_map))
    all_comm = list(dict.fromkeys(all_comm))

    by_ticker: Dict[str, Any] = {}
    high_corr: List[Dict[str, Any]] = []

    for st in stocks_list:
        t = str(st.get("ticker", "")).zfill(6)
        ty = st.get("ticker_yf") or f"{st.get('ticker', '')}.KS"
        sec = sector_by_yf[ty]
        one = analyze_one_stock(st, sector_map, sector=sec, close_cache=close_cache)
        by_ticker[t] = one
        pr = one.get("primary") or {}
        r = pr.get("correlation_60d")
        if r is not None and abs(r) >= 0.45:
            high_corr.append(
                {
                    "ticker": t,
                    "name": st.get("name", t),
                    "commodity": pr.get("commodity_ticker"),
                    "correlation_60d": r,
                    "regime": pr.get("spread_regime"),
                }
            )

    mom_alerts = collect_commodity_mom_alerts(all_comm, close_cache=close_cache)

    payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "mom_alert_threshold_pct": MOM_ALERT_PCT,
        "commodity_mom_alerts": mom_alerts,
        "high_correlation": sorted(high_corr, key=lambda x: abs(x["correlation_60d"]), reverse=True),
        "by_ticker": by_ticker,
    }
    payload = _sanitize(payload)
    save_commodity_impact(payload)
    return payload


def save_commodity_impact(payload: Dict[str, Any]) -> None:
    """commodity_impact.json 저장 (서술 보강 후 재저장용)."""
    payload = _sanitize(payload)
    os.makedirs(os.path.dirname(COMMODITY_IMPACT_PATH), exist_ok=True)
    try:
        with open(COMMODITY_IMPACT_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def apply_commodity_adjustment_to_fundamental(fundamental_score: int, commodity_block: Optional[Dict[str, Any]]) -> int:
    """멀티팩터용 펀더멘털에 원자재 스프레드 가감 반영."""
    if not commodity_block:
        return int(fundamental_score)
    pr = commodity_block.get("primary")
    if not isinstance(pr, dict):
        return int(fundamental_score)
    adj = pr.get("safety_adjustment")
    try:
        a = int(adj)
    except (TypeError, ValueError):
        return int(fundamental_score)
    return int(_clip(float(fundamental_score) + float(a), 0.0, 100.0))


def attach_commodity_to_stocks(stocks: List[Dict[str, Any]], scout: Dict[str, Any]) -> None:
    """scout.by_ticker를 각 종목 dict에 commodity_margin으로 부착."""
    by_t = scout.get("by_ticker") or {}
    for s in stocks:
        t = str(s.get("ticker", "")).zfill(6)
        s["commodity_margin"] = by_t.get(t, {})
