"""
Framer StockDetailPanel용 종목 상세 JSON
GET /api/stock_detail?q=005930  (또는 ?symbol=005930)

기존 stock.py 수집 로직을 재사용해 동일 스키마(data/stock_detail_mock.json)로 변환.
배포 URL 예: https://<프로젝트>.vercel.app/api/stock_detail?q={symbol}
  → Framer analysisUrlTemplate 에 인코딩된 쿼리로 연결
"""
from http.server import BaseHTTPRequestHandler
import json
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

from stock import (
    _fetch_flow,
    _fetch_stock_data,
    _judge,
    _resolve_query,
    _safety_score,
    _sanitize,
)


def _fmt_trading_value_krw(n):
    n = float(n)
    if n >= 1e12:
        return "약 {:.1f}조원".format(n / 1e12)
    if n >= 1e8:
        return "약 {:.0f}억원".format(n / 1e8)
    return "약 {:,.0f}만원".format(n / 1e4)


def _fmt_flow_net(n):
    n = int(n)
    if n == 0:
        return "0"
    sign = "+" if n >= 0 else "-"
    a = abs(n)
    if a >= 10000:
        return "{}{}만".format(sign, round(a / 10000))
    return "{}{}".format(sign, a)


def _candles_from_sparkline(spark):
    if not spark or len(spark) < 2:
        return []
    out = []
    start = max(1, len(spark) - 3)
    for i in range(start, len(spark)):
        o = float(spark[i - 1])
        c = float(spark[i])
        h = max(o, c) * 1.003
        l = min(o, c) * 0.997
        out.append({"o": o, "h": h, "l": l, "c": c, "up": c >= o})
    return out


def _synthetic_order_book(price):
    step = max(1, int(round(float(price) * 0.0008)))
    rows = []
    for i in range(3, 0, -1):
        p = int(price + step * i)
        rows.append(
            {
                "price": p,
                "ask_vol": 4000 + i * 900,
                "bid_vol": None,
                "pct_label": "+{:.1f}%".format(i * 0.15),
            }
        )
    rows.append(
        {
            "price": int(price),
            "ask_vol": None,
            "bid_vol": None,
            "pct_label": "0.0%",
            "highlight": True,
        }
    )
    for i in range(1, 4):
        p = int(price - step * i)
        rows.append(
            {
                "price": p,
                "ask_vol": None,
                "bid_vol": 3500 + i * 700,
                "pct_label": "-{:.1f}%".format(i * 0.15),
            }
        )
    return {
        "current_price": int(price),
        "rows": rows,
        "footer": {
            "sell_wait_label": "판매 대기",
            "buy_wait_label": "구매 대기",
            "sell_wait": "합성 호가 (데모)",
            "buy_wait": "합성 호가 (데모)",
            "session_note": "VERITY API",
        },
    }


def _synthetic_trades(price):
    p = int(price)
    return [
        {"price": p, "qty": 100, "side": "buy"},
        {"price": p - 50, "qty": 30, "side": "sell"},
        {"price": p, "qty": 200, "side": "buy"},
    ]


def build_stock_detail_payload(stock_data):
    """recommendation 형태 dict → StockDetailPanel JSON"""
    tech = stock_data.get("technical") or {}
    flow = stock_data.get("flow") or {}
    ticker = str(stock_data.get("ticker", ""))
    name = str(stock_data.get("name", ""))
    price = float(stock_data.get("price", 0))
    vol = int(stock_data.get("volume", 0) or 0)
    tv = float(stock_data.get("trading_value", 0) or 0)
    high_52w = float(stock_data.get("high_52w", price) or price)
    spark = stock_data.get("sparkline") or [price]

    pct = float(tech.get("price_change_pct", 0) or 0)
    if pct != -100:
        prev = price / (1 + pct / 100.0)
    else:
        prev = price
    change_amount = price - prev

    fn = int(flow.get("foreign_net", 0) or 0)
    inst = int(flow.get("institution_net", 0) or 0)
    indiv_est = -(fn + inst)

    investors = [
        {"label": "개인", "net_display": _fmt_flow_net(indiv_est), "side": "sell" if indiv_est < 0 else "buy"},
        {"label": "외국인", "net_display": _fmt_flow_net(fn), "side": "sell" if fn < 0 else "buy"},
        {"label": "기관", "net_display": _fmt_flow_net(inst), "side": "sell" if inst < 0 else "buy"},
    ]

    tail = spark[-20:] if len(spark) > 20 else spark
    lo_d = min(tail)
    hi_d = max(tail)

    insights = []
    rec = stock_data.get("recommendation", "")
    grade = (stock_data.get("multi_factor") or {}).get("grade", "")
    if grade or rec:
        insights.append(
            {
                "tag": "호재" if rec == "BUY" else "소식",
                "text": "종합 {} — {}".format(grade or "-", rec or "-"),
                "ago": "VERITY 분석",
            }
        )
    for s in (tech.get("signals") or [])[:4]:
        tag = "호재" if any(k in s for k in ("매수", "상승", "저점", "과매도")) else "소식"
        insights.append({"tag": tag, "text": s, "ago": "기술적"})
    for s in (flow.get("flow_signals") or [])[:3]:
        insights.append({"tag": "소식", "text": s, "ago": "수급"})

    upper = int(round(price * 1.3))
    lower = int(round(price * 0.7))

    return {
        "symbol": ticker,
        "name": name,
        "price": int(round(price)),
        "change_amount": int(round(change_amount)),
        "change_pct": round(pct, 2),
        "compare_label": "전일대비",
        "chart": {
            "timeframes": ["1일", "1주", "3달", "1년", "5년", "전체"],
            "active_timeframe": "1주",
            "line": [float(x) for x in spark],
            "annotations": {
                "high": {"price": int(round(hi_d)), "label": "구간 고점 {:,}원".format(int(round(hi_d)))},
                "low": {"price": int(round(lo_d)), "label": "구간 저점 {:,}원".format(int(round(lo_d)))},
            },
            "candles": _candles_from_sparkline(spark),
        },
        "ranges": [
            {"id": "1d", "label": "1일(근사)", "low": int(round(lo_d)), "high": int(round(hi_d))},
            {"id": "1y", "label": "1년", "low": int(round(min(lo_d, price * 0.85))), "high": int(round(max(high_52w, price)))},
        ],
        "session": {
            "open": int(round(price - change_amount * 0.3)),
            "close": int(round(price)),
            "volume": vol,
            "trading_value_label": _fmt_trading_value_krw(tv),
        },
        "investors": investors,
        "order_book": _synthetic_order_book(price),
        "execution": {
            "strength_pct": 120.0,
            "trades": _synthetic_trades(price),
        },
        "limits": {
            "upper": "{:,}".format(upper),
            "lower": "{:,}".format(lower),
            "vi": "—",
        },
        "insights": insights[:8] if insights else [{"tag": "소식", "text": "분석 요약 없음", "ago": "-"}],
        "_meta": {"source": "vercel_api/stock_detail", "version": 1},
    }


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        q = (params.get("q", [""])[0] or params.get("symbol", [""])[0] or "").strip()

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=60, stale-while-revalidate=300")
        self.end_headers()

        if not q:
            self.wfile.write(
                json.dumps(
                    {"error": "q 또는 symbol 파라미터 필요 (종목코드·이름). 예: ?q=005930"},
                    ensure_ascii=False,
                ).encode()
            )
            return

        ticker, ticker_yf, name, market = _resolve_query(q)
        if not ticker:
            self.wfile.write(json.dumps({"error": "'{}' 종목을 찾을 수 없습니다".format(q)}, ensure_ascii=False).encode())
            return

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                fut_s = pool.submit(_fetch_stock_data, ticker_yf, name, market)
                fut_f = pool.submit(_fetch_flow, ticker)
                stock_data = fut_s.result(timeout=8)
                flow_data = fut_f.result(timeout=8)

            if not stock_data:
                self.wfile.write(json.dumps({"error": "'{}' 데이터 수집 실패".format(name)}, ensure_ascii=False).encode())
                return

            stock_data["flow"] = flow_data
            stock_data["safety_score"] = _safety_score(stock_data)
            judgment = _judge(stock_data)
            stock_data["multi_factor"] = {"multi_score": judgment["multi_score"], "grade": judgment["grade"]}
            stock_data["recommendation"] = judgment["recommendation"]

            panel = build_stock_detail_payload(stock_data)
            self.wfile.write(json.dumps(_sanitize(panel), ensure_ascii=False).encode())
        except Exception as e:
            self.wfile.write(json.dumps({"error": str(e)[:200]}, ensure_ascii=False).encode())
