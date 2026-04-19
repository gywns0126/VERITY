"""
VERITY 종목 검색 자동완성 API
GET /api/search?q=삼성 → 매칭되는 종목 최대 10개 반환 (즉시 응답)
"""
from http.server import BaseHTTPRequestHandler
import json
import os
from urllib.parse import parse_qs, urlparse

STOCKS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "krx_stocks.json")
_cache = None


def _safe_int(raw, default: int, lo: int = 1, hi: int = 100) -> int:
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))

US_STOCKS = [
    {"ticker": "AAPL", "name": "Apple", "name_kr": "애플", "market": "NASDAQ", "yf": "AAPL"},
    {"ticker": "MSFT", "name": "Microsoft", "name_kr": "마이크로소프트", "market": "NASDAQ", "yf": "MSFT"},
    {"ticker": "NVDA", "name": "NVIDIA", "name_kr": "엔비디아", "market": "NASDAQ", "yf": "NVDA"},
    {"ticker": "AMZN", "name": "Amazon", "name_kr": "아마존", "market": "NASDAQ", "yf": "AMZN"},
    {"ticker": "GOOGL", "name": "Alphabet Class A", "name_kr": "알파벳(구글)", "market": "NASDAQ", "yf": "GOOGL"},
    {"ticker": "GOOG", "name": "Alphabet Class C", "name_kr": "알파벳C", "market": "NASDAQ", "yf": "GOOG"},
    {"ticker": "META", "name": "Meta Platforms", "name_kr": "메타", "market": "NASDAQ", "yf": "META"},
    {"ticker": "TSLA", "name": "Tesla", "name_kr": "테슬라", "market": "NASDAQ", "yf": "TSLA"},
    {"ticker": "NFLX", "name": "Netflix", "name_kr": "넷플릭스", "market": "NASDAQ", "yf": "NFLX"},
    {"ticker": "AMD", "name": "Advanced Micro Devices", "name_kr": "AMD", "market": "NASDAQ", "yf": "AMD"},
    {"ticker": "AVGO", "name": "Broadcom", "name_kr": "브로드컴", "market": "NASDAQ", "yf": "AVGO"},
    {"ticker": "QCOM", "name": "Qualcomm", "name_kr": "퀄컴", "market": "NASDAQ", "yf": "QCOM"},
    {"ticker": "INTC", "name": "Intel", "name_kr": "인텔", "market": "NASDAQ", "yf": "INTC"},
    {"ticker": "CRM", "name": "Salesforce", "name_kr": "세일즈포스", "market": "NYSE", "yf": "CRM"},
    {"ticker": "ORCL", "name": "Oracle", "name_kr": "오라클", "market": "NYSE", "yf": "ORCL"},
    {"ticker": "ADBE", "name": "Adobe", "name_kr": "어도비", "market": "NASDAQ", "yf": "ADBE"},
    {"ticker": "PYPL", "name": "PayPal", "name_kr": "페이팔", "market": "NASDAQ", "yf": "PYPL"},
    {"ticker": "UBER", "name": "Uber Technologies", "name_kr": "우버", "market": "NYSE", "yf": "UBER"},
    {"ticker": "JPM", "name": "JPMorgan Chase", "name_kr": "JP모건", "market": "NYSE", "yf": "JPM"},
    {"ticker": "BAC", "name": "Bank of America", "name_kr": "뱅크오브아메리카", "market": "NYSE", "yf": "BAC"},
    {"ticker": "GS", "name": "Goldman Sachs", "name_kr": "골드만삭스", "market": "NYSE", "yf": "GS"},
    {"ticker": "V", "name": "Visa", "name_kr": "비자", "market": "NYSE", "yf": "V"},
    {"ticker": "MA", "name": "Mastercard", "name_kr": "마스터카드", "market": "NYSE", "yf": "MA"},
    {"ticker": "BRK-B", "name": "Berkshire Hathaway B", "name_kr": "버크셔해서웨이", "market": "NYSE", "yf": "BRK-B"},
    {"ticker": "UNH", "name": "UnitedHealth Group", "name_kr": "유나이티드헬스", "market": "NYSE", "yf": "UNH"},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "name_kr": "존슨앤존슨", "market": "NYSE", "yf": "JNJ"},
    {"ticker": "PFE", "name": "Pfizer", "name_kr": "화이자", "market": "NYSE", "yf": "PFE"},
    {"ticker": "LLY", "name": "Eli Lilly", "name_kr": "일라이릴리", "market": "NYSE", "yf": "LLY"},
    {"ticker": "MRK", "name": "Merck", "name_kr": "머크", "market": "NYSE", "yf": "MRK"},
    {"ticker": "ABBV", "name": "AbbVie", "name_kr": "애브비", "market": "NYSE", "yf": "ABBV"},
    {"ticker": "XOM", "name": "Exxon Mobil", "name_kr": "엑슨모빌", "market": "NYSE", "yf": "XOM"},
    {"ticker": "CVX", "name": "Chevron", "name_kr": "셰브론", "market": "NYSE", "yf": "CVX"},
    {"ticker": "CAT", "name": "Caterpillar", "name_kr": "캐터필러", "market": "NYSE", "yf": "CAT"},
    {"ticker": "GE", "name": "GE Aerospace", "name_kr": "GE에어로스페이스", "market": "NYSE", "yf": "GE"},
    {"ticker": "BA", "name": "Boeing", "name_kr": "보잉", "market": "NYSE", "yf": "BA"},
    {"ticker": "DIS", "name": "Walt Disney", "name_kr": "디즈니", "market": "NYSE", "yf": "DIS"},
    {"ticker": "WMT", "name": "Walmart", "name_kr": "월마트", "market": "NYSE", "yf": "WMT"},
    {"ticker": "COST", "name": "Costco", "name_kr": "코스트코", "market": "NASDAQ", "yf": "COST"},
    {"ticker": "COIN", "name": "Coinbase", "name_kr": "코인베이스", "market": "NASDAQ", "yf": "COIN"},
    {"ticker": "SQ", "name": "Block (Square)", "name_kr": "블록(스퀘어)", "market": "NYSE", "yf": "SQ"},
    {"ticker": "SNOW", "name": "Snowflake", "name_kr": "스노우플레이크", "market": "NYSE", "yf": "SNOW"},
    {"ticker": "PLTR", "name": "Palantir", "name_kr": "팔란티어", "market": "NYSE", "yf": "PLTR"},
    {"ticker": "SOFI", "name": "SoFi Technologies", "name_kr": "소파이", "market": "NASDAQ", "yf": "SOFI"},
    {"ticker": "SHOP", "name": "Shopify", "name_kr": "쇼피파이", "market": "NYSE", "yf": "SHOP"},
    {"ticker": "ARM", "name": "ARM Holdings", "name_kr": "ARM", "market": "NASDAQ", "yf": "ARM"},
    {"ticker": "TSM", "name": "TSMC", "name_kr": "TSMC(대만반도체)", "market": "NYSE", "yf": "TSM"},
    {"ticker": "ASML", "name": "ASML Holding", "name_kr": "ASML", "market": "NASDAQ", "yf": "ASML"},
    {"ticker": "MU", "name": "Micron Technology", "name_kr": "마이크론", "market": "NASDAQ", "yf": "MU"},
    {"ticker": "MRVL", "name": "Marvell Technology", "name_kr": "마벨", "market": "NASDAQ", "yf": "MRVL"},
    {"ticker": "PANW", "name": "Palo Alto Networks", "name_kr": "팔로알토", "market": "NASDAQ", "yf": "PANW"},
    {"ticker": "CRWD", "name": "CrowdStrike", "name_kr": "크라우드스트라이크", "market": "NASDAQ", "yf": "CRWD"},
    {"ticker": "NOW", "name": "ServiceNow", "name_kr": "서비스나우", "market": "NYSE", "yf": "NOW"},
    {"ticker": "ABNB", "name": "Airbnb", "name_kr": "에어비앤비", "market": "NASDAQ", "yf": "ABNB"},
    {"ticker": "RIVN", "name": "Rivian", "name_kr": "리비안", "market": "NASDAQ", "yf": "RIVN"},
    {"ticker": "NIO", "name": "NIO", "name_kr": "니오", "market": "NYSE", "yf": "NIO"},
    {"ticker": "BABA", "name": "Alibaba", "name_kr": "알리바바", "market": "NYSE", "yf": "BABA"},
    {"ticker": "PDD", "name": "PDD Holdings", "name_kr": "핀둬둬", "market": "NASDAQ", "yf": "PDD"},
    {"ticker": "SPOT", "name": "Spotify", "name_kr": "스포티파이", "market": "NYSE", "yf": "SPOT"},
    {"ticker": "NET", "name": "Cloudflare", "name_kr": "클라우드플레어", "market": "NYSE", "yf": "NET"},
    {"ticker": "DDOG", "name": "Datadog", "name_kr": "데이터독", "market": "NASDAQ", "yf": "DDOG"},
    {"ticker": "ZS", "name": "Zscaler", "name_kr": "지스케일러", "market": "NASDAQ", "yf": "ZS"},
    {"ticker": "MSTR", "name": "MicroStrategy", "name_kr": "마이크로스트래티지", "market": "NASDAQ", "yf": "MSTR"},
    {"ticker": "HD", "name": "Home Depot", "name_kr": "홈디포", "market": "NYSE", "yf": "HD"},
    {"ticker": "NKE", "name": "Nike", "name_kr": "나이키", "market": "NYSE", "yf": "NKE"},
    {"ticker": "SBUX", "name": "Starbucks", "name_kr": "스타벅스", "market": "NASDAQ", "yf": "SBUX"},
    {"ticker": "MCD", "name": "McDonald's", "name_kr": "맥도날드", "market": "NYSE", "yf": "MCD"},
    {"ticker": "KO", "name": "Coca-Cola", "name_kr": "코카콜라", "market": "NYSE", "yf": "KO"},
    {"ticker": "PEP", "name": "PepsiCo", "name_kr": "펩시", "market": "NASDAQ", "yf": "PEP"},
    {"ticker": "PG", "name": "Procter & Gamble", "name_kr": "P&G", "market": "NYSE", "yf": "PG"},
    {"ticker": "T", "name": "AT&T", "name_kr": "AT&T", "market": "NYSE", "yf": "T"},
    {"ticker": "VZ", "name": "Verizon", "name_kr": "버라이즌", "market": "NYSE", "yf": "VZ"},
]


def _load():
    global _cache
    if _cache is None:
        with open(STOCKS_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


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
        q = params.get("q", [""])[0].strip()
        limit = _safe_int(params.get("limit", ["10"])[0], 10, 1, 100)
        market = params.get("market", ["all"])[0].strip().lower()
        if market not in ("all", "kr", "us"):
            market = "all"

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=3600, stale-while-revalidate=86400")
        self.end_headers()

        if not q or len(q) < 1:
            self.wfile.write(json.dumps([], ensure_ascii=False).encode())
            return

        kr_stocks = _load()
        if market == "us":
            stocks = US_STOCKS
        elif market == "kr":
            stocks = kr_stocks
        else:
            stocks = kr_stocks + US_STOCKS
        q_lower = q.lower()
        q_upper = q.upper()
        results = []

        def _name_kr(s):
            return (s.get("name_kr") or "").lower()

        exact_name = [s for s in stocks if s["name"].lower() == q_lower or _name_kr(s) == q_lower]
        exact_ticker = [s for s in stocks if s["ticker"] == q or s["ticker"] == q_upper]

        starts_name = [s for s in stocks
                       if (s["name"].lower().startswith(q_lower) or _name_kr(s).startswith(q_lower))
                       and s not in exact_name]
        starts_ticker = [s for s in stocks if s["ticker"].startswith(q_upper) and s not in exact_ticker]

        contains_name = [s for s in stocks
                         if (q_lower in s["name"].lower() or q_lower in _name_kr(s))
                         and s not in exact_name and s not in starts_name]

        for group in [exact_name, exact_ticker, starts_name, starts_ticker, contains_name]:
            for s in group:
                if s not in results:
                    results.append(s)
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break

        self.wfile.write(json.dumps(results[:limit], ensure_ascii=False).encode())
