"""
dividend_us — US 배당 수집기 (yfinance Ticker.dividends).

KR dividend_kr.py 패턴 정합:
  - ex_date 기준 기록 (지급일 X). 권리 확정 시점이 경제적 실체.
  - amount_per_share_usd 저장 (KRW 환산은 engine.py cycle 에서 fx_rate 적용).
  - yfinance = 실제 지급된 배당. is_confirmed=True 고정 (역사 확정 + 권리 확정).

SOURCE: yfinance Ticker.dividends → pd.Series of (ex_date → amount USD)

산출: data/dividends_us.json
  {
    "AAPL": [
      {
        "ex_date": "2026-02-07",
        "amount_per_share_usd": 0.24,
        "is_confirmed": true,
        "dividend_type": "regular",     # regular | special
        "source": "yfinance",
        "updated_at": "2026-05-17T..."
      }
    ]
  }

wiring: 현재 dead code (cron 미등록, US 매수 trigger 전). dividend_us cron 신설 시 활성.
VAMS 연동: api/vams/engine.py run_vams_cycle 내부 KR 배당 누적 다음에 US 분기 추가.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from api.config import DATA_DIR, now_kst

_DIVIDENDS_DB_PATH = os.path.join(DATA_DIR, "dividends_us.json")


# ──────────────────────────────────────────────────────────────
# yfinance fetch (Tier 0 — 유일 source. SEC/Finnhub 추가는 후속)
# ──────────────────────────────────────────────────────────────

def fetch_dividends_yfinance(ticker: str, lookback_years: int = 2) -> List[dict]:
    """yfinance Ticker.dividends → 최근 lookback_years 의 배당 list."""
    try:
        import yfinance as yf
    except ImportError:
        print(f"[dividend_us] yfinance import 실패")
        return []

    try:
        # 2026-05-18 fix — yfinance Yahoo anti-bot [[yfinance_safe.yf_ticker]]
        from api.collectors.yfinance_safe import yf_ticker
        yt = yf_ticker(ticker)
        divs = yt.dividends  # pd.Series of ex_date → amount_usd
        if divs is None or len(divs) == 0:
            return []
    except Exception as e:
        print(f"[dividend_us] {ticker} yfinance fetch 실패: {e}")
        return []

    cutoff = datetime.now() - timedelta(days=365 * lookback_years)
    out: List[dict] = []
    for ex_date_ts, amount_usd in divs.items():
        try:
            # yfinance DatetimeIndex 는 tz-aware 일 수 있음 → naive 로 변환
            ts = ex_date_ts.to_pydatetime() if hasattr(ex_date_ts, 'to_pydatetime') else ex_date_ts
            if hasattr(ts, 'tzinfo') and ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)
            if ts < cutoff:
                continue
            amt = float(amount_usd)
            if amt <= 0:
                continue
            out.append({
                "ex_date": ts.strftime("%Y-%m-%d"),
                "amount_per_share_usd": amt,
                "is_confirmed": True,
                "dividend_type": "regular",  # yfinance 는 type 구분 X — 후속 sweep 에서 special 식별
                "source": "yfinance",
                "updated_at": now_kst().isoformat(timespec="seconds"),
            })
        except Exception as e:
            print(f"[dividend_us] {ticker} record 변환 실패: {e}")
            continue
    return out


# ──────────────────────────────────────────────────────────────
# DB I/O (KR 패턴 정합)
# ──────────────────────────────────────────────────────────────

def load_dividends_db() -> Dict[str, List[dict]]:
    if not os.path.exists(_DIVIDENDS_DB_PATH):
        return {}
    try:
        with open(_DIVIDENDS_DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[dividend_us] load 실패 (빈 DB 반환): {e}")
        return {}


def save_dividends_db(db: Dict[str, List[dict]]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = _DIVIDENDS_DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2, allow_nan=False)
    os.replace(tmp, _DIVIDENDS_DB_PATH)


def _upsert(db: Dict[str, List[dict]], ticker: str, record: dict) -> str:
    """ticker × ex_date 기준 upsert. 반환: 'insert' | 'update' | 'skip'."""
    arr = db.setdefault(ticker, [])
    ex = record.get("ex_date")
    if not ex:
        return "skip"
    for i, existing in enumerate(arr):
        if existing.get("ex_date") == ex:
            # yfinance 가 유일 source — 동일 ex_date 면 최신값으로 update
            merged = {**existing, **record}
            arr[i] = merged
            return "update"
    arr.append(record)
    arr.sort(key=lambda r: r.get("ex_date", ""))
    return "insert"


# ──────────────────────────────────────────────────────────────
# Sweep (cron 호출용)
# ──────────────────────────────────────────────────────────────

def update_dividends_for_tickers(tickers: List[str], lookback_years: int = 2) -> Dict[str, str]:
    """tickers 의 yfinance 배당 데이터 → DB upsert. 결과 = {ticker: 'insert'|'update'|'skip'}."""
    db = load_dividends_db()
    results: Dict[str, str] = {}
    for tk in tickers:
        recs = fetch_dividends_yfinance(tk, lookback_years)
        if not recs:
            results[tk] = "no_data"
            continue
        statuses = [_upsert(db, tk, r) for r in recs]
        results[tk] = ",".join(set(statuses))
    save_dividends_db(db)
    return results


# ──────────────────────────────────────────────────────────────
# VAMS 헬퍼 (engine.py run_vams_cycle 호출)
# ──────────────────────────────────────────────────────────────

def get_ex_dates_today(tickers: List[str], today: Optional[str] = None) -> List[dict]:
    """오늘이 ex_date 인 US 보유 종목의 배당 레코드 반환.
    VAMS run_vams_cycle 이 호출해서 dividend_received_us 를 누적.
    KR pattern 정합 (api/collectors/dividend_kr.py:366).
    """
    if today is None:
        today = now_kst().strftime("%Y-%m-%d")
    db = load_dividends_db()
    out = []
    for tk in tickers:
        for rec in db.get(tk, []):
            if rec.get("_meta"):
                continue
            if rec.get("ex_date") == today:
                out.append({"ticker": tk, **rec})
    return out
