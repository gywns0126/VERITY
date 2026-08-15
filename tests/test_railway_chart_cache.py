"""Railway /chart 응답 캐시 회귀 테스트 (네트워크 0 · KIS 호출 0).

2026-08-15 신설. 이 라우트만 KIS REST 를 **요청마다 직접** 호출했다 — 토큰만 캐시하고
응답은 안 했다. 증폭이 크다: 기본값 `type=all` 은 한 요청에 KIS 5콜
(daily·minute·price·orderbook·trades)이다.

위험 경로: 엔드포인트가 무인증이고 URL 이 public repo 에 그대로 있다
(framer-components/public-probe/RealtimeChartProbe.tsx · api/intelligence/ticker_facts.py).
제3자 트래픽이 오퍼레이터 계정의 KIS 쿼터를 먹고, 유량 초과 재시도·백오프 코드가 없어
**오퍼레이터 본인 조회가 먼저 죽는다.** CORS 를 닫아도(2026-08-15) 이 벡터는 안 막힌다 —
CORS 는 브라우저 정책이라 curl 은 통과한다(실측).

대조 (건드리지 않은 것):
  · /quotes·/us_quotes = 이미 per-IP 레이트리밋 60초 30회
  · /snapshot·/candles = WS 메모리 상태 읽기라 KIS 무접촉
  · /api/order        = fail-closed 인증 (실측 401)

레이트리밋 대신 캐시를 택한 이유: IP 기준 제한은 Vercel 공용 egress 를 함께 막을 위험이
있는데, 캐시는 트래픽 출처와 무관하게 KIS 호출 상한을 만들고 오퍼레이터 응답도 빨라진다.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import server.main as m  # noqa: E402


@pytest.fixture(autouse=True)
def _clean():
    m._chart_cache.clear()
    m._chart_locks.clear()
    yield
    m._chart_cache.clear()
    m._chart_locks.clear()


def _counting(box, value=None, delay=0.0):
    def _f(tk):
        box["n"] += 1
        if delay:
            time.sleep(delay)
        return value if value is not None else {"price": 274500}
    return _f


def test_repeat_requests_hit_cache(monkeypatch):
    """순차 반복 요청이 KIS 를 한 번만 친다."""
    box = {"n": 0}
    monkeypatch.setattr(m, "fetch_price", _counting(box))
    async def go():
        for _ in range(20):
            await m.chart("005930", type="price")
    asyncio.run(go())
    assert box["n"] == 1, f"KIS 호출 {box['n']}회 — 캐시 미작동"


def test_concurrent_stampede_is_joined(monkeypatch):
    """캐시 미스 순간의 동시 요청이 KIS 로 그대로 나가면 안 된다 (공격 시나리오)."""
    box = {"n": 0}
    monkeypatch.setattr(m, "fetch_price", _counting(box, delay=0.02))
    async def go():
        await asyncio.gather(*[m.chart("000660", type="price") for _ in range(50)])
    asyncio.run(go())
    assert box["n"] == 1, f"KIS 호출 {box['n']}회 — stampede 합류 미작동"


def test_ttl_expiry_refetches(monkeypatch):
    """TTL 이 지나면 다시 조회한다 — 영구 캐시가 되면 시세가 굳는다."""
    box = {"n": 0}
    monkeypatch.setattr(m, "fetch_price", _counting(box))
    async def go():
        await m.chart("005930", type="price")
        k = "005930:price"
        _, payload = m._chart_cache[k]
        m._chart_cache[k] = (0.0, payload)      # 강제 만료
        await m.chart("005930", type="price")
    asyncio.run(go())
    assert box["n"] == 2


def test_realtime_ttl_stays_short():
    """실시간성 축은 짧게 — 5초는 체감 0이면서 초당 KIS 콜을 1로 묶는다."""
    for k in ("price", "all", "minute"):
        assert m._CHART_TTL[k] <= 10, (k, m._CHART_TTL[k])
    # 느린 축은 길게 둬도 된다
    assert m._CHART_TTL["monthly"] >= 60


def test_partial_failure_is_not_cached(monkeypatch):
    """type=all 일부 축이 실패하면 캐시하지 않는다 — TTL 동안 degrade 응답 고정 방지."""
    box = {"n": 0}
    def boom(tk):
        box["n"] += 1
        raise RuntimeError("KIS 유량 초과")
    monkeypatch.setattr(m, "fetch_daily", _counting({"n": 0}, value=[]))
    monkeypatch.setattr(m, "fetch_minute", _counting({"n": 0}, value=[]))
    monkeypatch.setattr(m, "fetch_price", _counting({"n": 0}, value={}))
    monkeypatch.setattr(m, "fetch_orderbook", _counting({"n": 0}, value={}))
    monkeypatch.setattr(m, "fetch_trades", boom)
    async def go():
        await m.chart("005930", type="all")
        await m.chart("005930", type="all")
    asyncio.run(go())
    assert "005930:all" not in m._chart_cache, "부분 실패가 캐시됐다"
    assert box["n"] == 2, "캐시되어 재조회가 막혔다"


def test_cache_is_bounded():
    """무한 증가 방지 — 상주 서버라 누수가 곧 장애다."""
    for i in range(m._CHART_CACHE_MAX + 200):
        m._chart_cache_put(f"k{i}", {"x": i}, 300)
    assert len(m._chart_cache) <= m._CHART_CACHE_MAX


def test_cache_key_separates_ticker_and_type(monkeypatch):
    """종목·타입이 섞이면 남의 시세가 나간다 — 가장 위험한 회귀."""
    box = {"n": 0}
    monkeypatch.setattr(m, "fetch_price", lambda tk: {"price": int(tk)})
    async def go():
        a = await m.chart("005930", type="price")
        b = await m.chart("000660", type="price")
        return a, b
    a, b = asyncio.run(go())
    assert a["price"]["price"] == 5930 and b["price"]["price"] == 660


def test_other_routes_untouched():
    """🚨 이미 방어된 라우트·주문 인증은 건드리지 않았다."""
    with open(os.path.join(_ROOT, "server", "main.py"), encoding="utf-8") as f:
        src = f.read()
    assert src.count("_quote_rate_ok(ip)") >= 2, "/quotes 레이트리밋이 사라졌다"
    assert src.count("_order_auth_fail_response(request)") >= 2, "주문 인증이 사라졌다"
    assert "ws_client.get_snapshot(tk)" in src and "ws_client.get_candles(tk)" in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
