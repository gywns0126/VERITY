"""US 정렬 일봉 수집 — 중용 포트폴리오 공분산 전제조건 (#8, 2026-08-02).

산출 = data/us_chart_daily.json (kr_chart_daily chunk 과 동일 shape:
  {as_of, stocks: {ticker: {n, m, c: [[yyyymmdd, open, high, low, close, vol], ...]}}, ...}).
KR(kr_chart_daily)+US(us_chart_daily) 를 공분산 빌더가 균일 소비 → 공통일 inner-join 정렬.

🚨 RULE 1: KISBroker(cache_only=True) — 토큰 발급 절대 안 함. KIS_SHARED_TOKEN 공유 토큰 read 만.
  워크플로는 KIS_SHARED_TOKEN=1 + (안전상) KIS_CACHE_ONLY=1 로 실행. 공유 토큰 부재 시 조용히 skip.
🚨 소스 = KIS 해외 dailyprice(HHDFS76240000), MODP='1'=수정주가(분할·병합 반영). FHKST03030100 은
  지수 전용이라 개별주 불가 (2026-08-02 확인). 1회 ~100건 → BYMD 페이지네이션.

US 개별주는 무료 실시간(NASD/NYSE/AMEX). 미장 실시간 표시는 별도(전일종가/TradingView, 차트 이원화 정책);
본 수집기는 '공분산용 정렬 일봉' 목적의 백엔드 데이터로, 차트 표시 소스와 직교.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta

try:
    from api.config import DATA_DIR
    _DATA = DATA_DIR
except Exception:
    _DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")

KST_OFFSET = timedelta(hours=9)
KEEP_DAYS = 250
MAX_TICKERS = 60           # 추천 US 유니버스 상한 (공분산 대상)
EXCD_TRY = ("NAS", "NYS", "AMS")   # NASDAQ / NYSE / AMEX 순 폴백
SLEEP_S = 0.12             # 유량 가드 (~20/s 한도, 넉넉히)
OUT_PATH = os.path.join(_DATA, "us_chart_daily.json")
PORTFOLIO_PATH = os.path.join(_DATA, "portfolio.json")


def _now_kst() -> datetime:
    return datetime.utcnow() + KST_OFFSET


def _us_universe() -> list:
    """공분산 대상 US 티커 = 추천(currency==USD). (ticker, name) 목록, 상한 MAX_TICKERS."""
    try:
        with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
            recs = (json.load(f) or {}).get("recommendations") or []
    except (FileNotFoundError, ValueError):
        return []
    out, seen = [], set()
    for r in recs:
        if str(r.get("currency")) != "USD":
            continue
        tk = str(r.get("ticker") or "").strip().upper()
        if not tk or tk in seen:
            continue
        seen.add(tk)
        out.append((tk, r.get("name") or tk))
        if len(out) >= MAX_TICKERS:
            break
    return out


def _fetch_one(broker, excd: str, ticker: str, want: int = KEEP_DAYS) -> list:
    """단일 (excd, ticker) 수정주가 일봉 → [[yyyymmdd, o, h, l, c, v], ...] (과거→현재).
    BYMD 페이지네이션으로 want 일 이상 확보. 빈 응답이면 [] (다른 EXCD 폴백 신호)."""
    rows: dict = {}
    bymd = ""
    for _ in range(4):  # 최대 ~400일
        try:
            out = broker.overseas_daily_price(excd, ticker, bymd=bymd, modp="1")
        except Exception:
            break
        if not out:
            break
        oldest = None
        for r in out:
            try:
                dt = int(str(r.get("xymd")).strip())
                o = float(r.get("open") or 0)
                h = float(r.get("high") or 0)
                lo = float(r.get("low") or 0)
                c = float(r.get("clos") or 0)
                v = float(r.get("tvol") or 0)
            except (TypeError, ValueError):
                continue
            if dt <= 0 or c <= 0:
                continue
            rows[dt] = [dt, o, h, lo, c, v]
            if oldest is None or dt < oldest:
                oldest = dt
        if len(rows) >= want or oldest is None:
            break
        try:
            prev = datetime.strptime(str(oldest), "%Y%m%d") - timedelta(days=1)
        except ValueError:
            break
        bymd = prev.strftime("%Y%m%d")
        time.sleep(SLEEP_S)
    return [rows[k] for k in sorted(rows)][-want:]


def collect() -> dict:
    from api.trading.kis_broker import KISBroker

    broker = KISBroker(cache_only=True)   # 🚨 RULE 1 — 발급 금지, 공유 토큰 read 전용
    if not broker.is_configured:
        print("[us_chart_daily] KIS 미설정 — skip", file=sys.stderr)
        return {}

    universe = _us_universe()
    if not universe:
        print("[us_chart_daily] US 추천 유니버스 0 — skip (portfolio.json 확인)", file=sys.stderr)
        return {}

    stocks: dict = {}
    ok, miss = 0, []
    for tk, name in universe:
        arr, used_excd = [], None
        for excd in EXCD_TRY:
            arr = _fetch_one(broker, excd, tk)
            if arr:
                used_excd = excd
                break
            time.sleep(SLEEP_S)
        if arr:
            stocks[tk] = {"n": name, "m": "US", "excd": used_excd, "c": arr}
            ok += 1
        else:
            miss.append(tk)
        time.sleep(SLEEP_S)

    doc = {
        "as_of": _now_kst().strftime("%Y%m%d"),
        "stocks": stocks,
        "count": len(stocks),
        "keep_days": KEEP_DAYS,
        "source": "KIS overseas dailyprice HHDFS76240000 (MODP=1 수정주가)",
        "updated_at": _now_kst().isoformat(timespec="seconds"),
        "missing": miss,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"[us_chart_daily] {ok}/{len(universe)} 종목 · 결측 {len(miss)} → {OUT_PATH}", file=sys.stderr)
    return doc


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    collect()
