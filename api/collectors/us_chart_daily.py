"""US 정렬 일봉 수집 — 중용 포트폴리오 공분산 전제조건 (#8, 2026-08-02).

산출 = data/us_chart_daily.json (kr_chart_daily chunk 과 동일 shape:
  {as_of, stocks: {ticker: {n, m, c: [[yyyymmdd, open, high, low, close, vol], ...]}}, ...}).
KR(kr_chart_daily)+US(us_chart_daily) 를 공분산 빌더가 균일 소비 → 공통일 inner-join 정렬.

🚨 소스 = yfinance (2026-08-08 전환). 이전 = KIS 해외 dailyprice(HHDFS76240000).

**왜 바꿨나**: KIS 경로가 조용히 전량 실패하고 있었다 — 실측 산출물
  {"count":0, "missing":[47종목 전부], "updated_at":"2026-08-03"}.
매일 워크플로가 성공으로 끝나고 파일 mtime 도 갱신돼 신선도 보드에는 "0일 경과" 로 잡히는데
내용은 비어 있었다. **가장 나쁜 실패 형태** — 없는 것보다 나쁘다(있다고 착각하게 만든다).
원인 = cache_only 브로커가 공유 토큰을 못 얻으면 조용히 skip 하도록 설계된 경로가
그대로 "정상 종료" 로 흘렀다.

부가 이득 = **KIS 의존이 사라진다**. RULE 1(1일 1토큰)에서 US 일봉은 애초에 KIS 를 쓸
이유가 없다 — 가장 제약이 큰 자원을 가장 대량인 작업에 붙였던 것이다.

대안 실호출 검증(2026-08-08): Polygon 무료=과거 403·분당 2콜 429 / FMP 403 /
Alpha Vantage 프리미엄 전환 / Finnhub 403 / Stooq HTML 차단. yfinance 만 통과
(TSLA 4,052봉 2010~, TSLL 1,003봉). 이미 `analyze_technical` 이 운영에서 쓰는 경로다.

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
WORKERS = 8                # yfinance 병렬 (Yahoo 유량 가드 — 과하면 429)
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


def _fetch_one(ticker: str, want: int = KEEP_DAYS) -> list:
    """yfinance 일봉 → [[yyyymmdd, o, h, l, c, v], ...] 최근 want 봉. 실패/무데이터면 [].

    🚨 수정주가(분할·배당 반영) 기준이다 — 원본 KIS MODP=1 과 같은 성격.
       공분산 소비자가 수익률을 쓰므로 미수정 가격이 섞이면 분할일에 가짜 폭락이 생긴다.
    """
    try:
        from api.collectors.yfinance_safe import yf_ticker
        hist = yf_ticker(ticker).history(period="2y", auto_adjust=True)
    except Exception:  # noqa: BLE001 — 개별 실패는 caller 가 missing 으로 집계
        return []
    if hist is None or len(hist) < 20:
        return []
    out = []
    for ts, row in hist.tail(want).iterrows():
        try:
            c = float(row["Close"])
            if c <= 0:
                continue
            out.append([int(ts.strftime("%Y%m%d")),
                        float(row["Open"]), float(row["High"]),
                        float(row["Low"]), c, float(row["Volume"] or 0)])
        except (TypeError, ValueError, KeyError):
            continue
    return out


def collect() -> dict:
    """공분산 대상 US 티커의 정렬 일봉. 스키마는 이전(KIS)과 **동일** — 소비자 무영향."""
    import concurrent.futures as cf

    universe = _us_universe()
    if not universe:
        print("[us_chart_daily] US 추천 유니버스 0 — skip (portfolio.json 확인)", file=sys.stderr)
        return {}

    stocks: dict = {}
    miss: list = []
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for (tk, name), arr in zip(universe, ex.map(lambda x: _fetch_one(x[0]), universe)):
            if arr:
                stocks[tk] = {"n": name, "m": "US", "c": arr}
            else:
                miss.append(tk)

    doc = {
        "as_of": _now_kst().strftime("%Y%m%d"),
        "stocks": stocks,
        "count": len(stocks),
        "keep_days": KEEP_DAYS,
        "source": "yfinance daily (auto_adjust=True 수정주가)",
        "updated_at": _now_kst().isoformat(timespec="seconds"),
        "missing": miss,
    }
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUT_PATH)
    print(f"[us_chart_daily] {len(stocks)}/{len(universe)} 종목 · 결측 {len(miss)} → {OUT_PATH}",
          file=sys.stderr)
    # 🚨 전량 실패를 '성공' 으로 끝내지 않는다 — 이전 결함(count 0 인데 정상 종료)의 재발 방지.
    if universe and not stocks:
        print("[us_chart_daily] 🚨 전량 실패 — 산출물 신뢰 불가", file=sys.stderr)
        raise SystemExit(1)
    return doc


if __name__ == "__main__":
    sys.path.insert(0, os.getcwd())
    collect()
