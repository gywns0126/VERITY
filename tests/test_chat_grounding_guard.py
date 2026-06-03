"""
챗 환각 가드 회귀 테스트 (2026-06-03 삼성전자 65,000원 환각 사고).

근본원인: 유니버스 밖 종목(삼성전자) 질의 → brain 컨텍스트 비고 + portfolio_only
분류로 외부 grounding 하드 차단 → 합성 LLM 이 학습 기억(옛 가격)으로 환각.

정공법 가드 2축:
  1) response_synthesizer: 시세 미확인 종목에 '수치 생성 금지' 하드 마커 + system prompt 규칙
  2) orchestrator: ungrounded 티커 감지 시 web grounding 강제 (여기선 1축만 단위검증)
"""
from api.chat_hybrid.response_synthesizer import _build_context_message, _SYSTEM_PROMPT


def test_system_prompt_has_hard_numeric_guard():
    # 모든 시장 수치는 컨텍스트 출처가 있을 때만 — 학습 기억 가격 금지
    assert "수치 grounding" in _SYSTEM_PROMPT
    assert "실시간 시세는 확인되지 않음" in _SYSTEM_PROMPT
    assert "학습" in _SYSTEM_PROMPT  # 학습 시점 가격 신뢰 불가 경고


def test_ungrounded_ticker_emits_no_price_marker():
    # 유니버스 밖 + grounding 전무 → '시세 미확인 — 수치 생성 금지' 블록
    msg = _build_context_message(
        query="삼성전자 어때?",
        brain_ctx={"ok": False},
        ungrounded_tickers=["005930", "삼성전자"],
    )
    assert "시세 미확인" in msg
    assert "005930" in msg
    assert "추정하거나 학습 기억으로 생성하지 말" in msg


def test_grounded_price_suppresses_marker():
    # grounding 이 실제 가격을 가져오면 경고 억제 + 실가격이 컨텍스트에 주입
    grounding = {
        "ok": True,
        "text": "삼성전자(005930) 현재가 365,000원, 전일 종가 349,000원",
        "citations": [],
    }
    msg = _build_context_message(
        query="삼성전자 어때?",
        brain_ctx={"ok": False},
        grounding_result=grounding,
        ungrounded_tickers=["005930"],
    )
    assert "시세 미확인" not in msg
    assert "365,000" in msg


def test_no_ungrounded_no_marker():
    # ungrounded 없음 (유니버스 내 종목 등) → 경고 블록 미노출
    msg = _build_context_message(
        query="내 포지션 어때?",
        brain_ctx={"ok": True, "text": "보유 종목 요약..."},
        ungrounded_tickers=[],
    )
    assert "시세 미확인" not in msg


# ── 갈래 A: price_pulse 5분-fresh KIS 시세 overlay (2026-06-03) ──
from api.chat_hybrid.search import brain_client as _bc


def test_pulse_price_map_parses_prices():
    pulse = {"prices": {"005930": 365000.0, "009540": "383500", "bad": None}}
    m = _bc._pulse_price_map(pulse)
    assert m["005930"] == 365000.0
    assert m["009540"] == 383500.0
    assert "BAD" not in m  # None 값은 제외


def test_ticker_block_prefers_fresh_kis_price():
    # portfolio 가격(111) 대신 price_pulse fresh(365000) 우선 + 'KIS 실시간' 라벨
    fresh = {"005930": 365000.0}
    blk = _bc._format_ticker_block(
        {"name": "삼성전자", "ticker": "005930", "current_price": 111}, fresh_prices=fresh
    )
    assert "365,000" in blk
    assert "KIS 실시간" in blk
    assert "현재가: 111 " not in blk  # 옛 가격이 노출되지 않음


def test_ticker_block_no_fresh_falls_back():
    # fresh 맵에 없는 종목 → portfolio 가격 유지, 라벨 없음 (회귀 방지)
    blk = _bc._format_ticker_block(
        {"name": "x", "ticker": "999999", "current_price": 111}, fresh_prices={"005930": 365000.0}
    )
    assert "KIS 실시간" not in blk
    assert "111" in blk


# ── 갈래 B: 유니버스 밖 KR on-demand 시세 (Railway read-only, RULE 1 안전) ──
from api.chat_hybrid.search import kis_quote as _kq


class _FakeResp:
    def __init__(self, payload):
        import json as _j
        self._b = _j.dumps(payload).encode()

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_kis_quote_rejects_non_kr(monkeypatch):
    # 미국 티커/종목명/빈값 → None (네트워크 호출 없이 즉시 거부)
    def _no_net(*a, **k):
        raise AssertionError("US 티커는 네트워크 호출하면 안 됨")
    monkeypatch.setattr(_kq.urllib.request, "urlopen", _no_net)
    assert _kq.fetch_kr_quote("NVDA") is None
    assert _kq.fetch_kr_quote("AAPL") is None
    assert _kq.fetch_kr_quote("") is None


def test_kis_quote_parses_railway(monkeypatch):
    monkeypatch.setattr(
        _kq.urllib.request, "urlopen",
        lambda req, timeout=0: _FakeResp({"price": {"price": 365000, "change_pct": 1.23}}),
    )
    q = _kq.fetch_kr_quote("005930")
    assert q == {"ticker": "005930", "price": 365000, "change_pct": 1.23}


def test_kis_quote_zero_price_returns_none(monkeypatch):
    # 가격 0/누락 → None (caller=web fallback)
    monkeypatch.setattr(
        _kq.urllib.request, "urlopen",
        lambda req, timeout=0: _FakeResp({"price": {"price": 0}}),
    )
    assert _kq.fetch_kr_quote("005930") is None


def test_kis_quote_failure_returns_none(monkeypatch):
    # Railway 호출 예외 → None (RULE 1: 발급 시도 없음, 조용히 web fallback)
    def _boom(req, timeout=0):
        raise OSError("railway down")
    monkeypatch.setattr(_kq.urllib.request, "urlopen", _boom)
    assert _kq.fetch_kr_quote("005930") is None


# ── L2: 결정적 종목명→코드 resolver (LLM 무관, 코드 환각 0) ──
from api.chat_hybrid.search import name_resolver as _nr

_STUB_NAMES = {  # {code: name}
    "005930": "삼성전자",
    "006400": "삼성SDI",
    "000660": "SK하이닉스",
    "017670": "SK텔레콤",
    "A": "에",  # 1글자 — 제외돼야 (오매칭 위험)
}


def _use_stub(monkeypatch):
    monkeypatch.setattr(_nr, "_load_raw", lambda: dict(_STUB_NAMES))
    _nr._cache["pairs"] = None  # 캐시 무효화
    _nr._cache["ts"] = 0.0


def test_resolver_name_to_code(monkeypatch):
    _use_stub(monkeypatch)
    assert _nr.resolve("삼성전자 어때?") == ["005930"]
    assert _nr.resolve("SK하이닉스 전망") == ["000660"]


def test_resolver_longest_first_no_substring_dup(monkeypatch):
    # '삼성전자' 매칭 후 '삼성SDI'(별개) 도 query 에 있으면 둘 다, 단 '삼성'이 내부 재매칭 X
    _use_stub(monkeypatch)
    codes = _nr.resolve("삼성전자랑 삼성SDI 비교")
    assert "005930" in codes and "006400" in codes


def test_resolver_excludes_universe(monkeypatch):
    # 이미 유니버스 매칭된 코드는 제외 (중복 grounding 방지)
    _use_stub(monkeypatch)
    assert _nr.resolve("삼성전자 어때?", exclude={"005930"}) == []


def test_resolver_limit_and_1char_filtered(monkeypatch):
    _use_stub(monkeypatch)
    # 1글자 이름('에')은 후보에서 제외 — 오매칭 위험
    pairs = _nr._sorted_pairs()
    assert all(len(n) >= 2 for n, _ in pairs)


def test_resolver_empty_map_noop(monkeypatch):
    # 맵 부재(파일 없음) → [] (web grounding 폴백, 무영향)
    monkeypatch.setattr(_nr, "_load_raw", lambda: {})
    _nr._cache["pairs"] = None
    _nr._cache["ts"] = 0.0
    assert _nr.resolve("삼성전자 어때?") == []
