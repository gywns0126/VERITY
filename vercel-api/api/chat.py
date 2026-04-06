"""
VERITY AI 채팅 API
POST /api/chat  { "question": "삼성전자 지금 사도 될까?" }
→ { "answer": "...", "ok": true }
Rate limit: IP당 분당 5회.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import time
from collections import defaultdict

from google import genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
PORTFOLIO_URL = os.environ.get(
    "PORTFOLIO_URL",
    "https://kim-hyojun.github.io/stock-analysis/data/portfolio.json",
)

_rate_limit: dict = defaultdict(list)
_RATE_WINDOW = 60
_RATE_MAX = 5

_portfolio_cache: dict = {}
_portfolio_ts: float = 0
_CACHE_TTL = 300

SYSTEM_PROMPT = """너는 VERITY — AI 자산 보안 비서다.
사용자의 투자 관련 질문에 한국어로 간결하게 답한다.
데이터 기반으로 답하고, 확실하지 않으면 솔직히 말한다.
리스크가 있으면 먼저 언급한다. 3~5문장 이내.
특정 가격/날짜 예측이나 단정적 매수/매도 지시는 하지 않는다.
최종 투자 결정은 본인 책임임을 상기시킨다."""


def _check_rate(ip: str) -> bool:
    now = time.time()
    _rate_limit[ip] = [t for t in _rate_limit[ip] if now - t < _RATE_WINDOW]
    if len(_rate_limit[ip]) >= _RATE_MAX:
        return False
    _rate_limit[ip].append(now)
    return True


def _fetch_portfolio() -> dict:
    global _portfolio_cache, _portfolio_ts
    if time.time() - _portfolio_ts < _CACHE_TTL and _portfolio_cache:
        return _portfolio_cache
    try:
        import urllib.request
        req = urllib.request.Request(PORTFOLIO_URL, headers={"User-Agent": "VERITY-Chat/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            txt = resp.read().decode("utf-8")
            txt = txt.replace("NaN", "null").replace("Infinity", "null").replace("-Infinity", "null")
            _portfolio_cache = json.loads(txt)
            _portfolio_ts = time.time()
    except Exception:
        pass
    return _portfolio_cache


def _build_context(data: dict) -> str:
    parts = []
    parts.append(f"데이터 갱신: {data.get('updated_at', '?')}")
    macro = data.get("macro", {})
    mood = macro.get("market_mood", {})
    parts.append(f"시장무드: {mood.get('score', '?')}점 ({mood.get('label', '?')})")
    cf = macro.get("capital_flow", {})
    if cf.get("interpretation"):
        parts.append(f"자금흐름: {cf['interpretation']}")
    recs = data.get("recommendations", [])[:5]
    if recs:
        lines = [f"  {r.get('name','?')}: {r.get('recommendation','?')} (브레인 {r.get('brain_score','?')})" for r in recs]
        parts.append("추천 TOP5:\n" + "\n".join(lines))
    briefing = data.get("briefing", {})
    if briefing.get("headline"):
        parts.append(f"브리핑: {briefing['headline']}")
    return "\n".join(parts)


def _ask_gemini(question: str, context: str) -> str:
    if not GEMINI_API_KEY:
        return "Gemini API 키가 설정되지 않았습니다."
    client = genai.Client(api_key=GEMINI_API_KEY)
    full_system = f"{SYSTEM_PROMPT}\n\n─── 최신 데이터 ───\n{context}"
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=question,
        config={
            "system_instruction": full_system,
            "temperature": 0.3,
            "max_output_tokens": 500,
        },
    )
    return (response.text or "").strip() or "답변을 생성하지 못했습니다."


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        ip = self.client_address[0] if self.client_address else "unknown"
        if not _check_rate(ip):
            self._json_response(429, {"ok": False, "error": "요청 한도 초과. 1분 후 다시 시도하세요."})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
        except Exception:
            self._json_response(400, {"ok": False, "error": "잘못된 요청"})
            return

        question = (body.get("question") or "").strip()
        if not question:
            self._json_response(400, {"ok": False, "error": "question 필드가 필요합니다."})
            return
        if len(question) > 500:
            self._json_response(400, {"ok": False, "error": "질문이 너무 깁니다 (500자 이내)."})
            return

        try:
            data = _fetch_portfolio()
            context = _build_context(data) if data else "데이터 없음"
            answer = _ask_gemini(question, context)
            self._json_response(200, {"ok": True, "answer": answer})
        except Exception as e:
            self._json_response(500, {"ok": False, "error": str(e)})

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, code: int, data: dict):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
