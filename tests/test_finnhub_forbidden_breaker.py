"""finnhub_client — 403 엔드포인트 프로세스 차단기 회귀 테스트 (네트워크 0).

2026-08-13 신설. 고정하려는 사고:

  full run 이 자체 예산 110분을 소진해 Gemini 배치 16/50 에서 종료됐다(run 31745952833).
  그 로그에서 `stock/price-target` 와 `institutional/ownership` 이 **10/10 전부 403** 이었고
  성공 run(31679449048)에서도 동일했다 — 즉 플랜 미포함이라 절대 성공하지 않는데 종목마다
  호출해 스로틀 1s + 왕복을 태우고 있었다. 헛돈 시간이 그대로 결손으로 이어진 형태다.

  고칠 때 지우지 않고 차단기를 택한 이유 = 호출을 영영 지우면 플랜을 올려도 조용히 빈 채로
  남는다. 프로세스마다 1콜로 권한을 재확인하고 열리면 자동 복귀해야 한다.

따라서 이 파일이 지키는 계약은 셋이다.
  ① 403 은 **한 번만** 때린다 — 같은 엔드포인트 재호출은 네트워크에 나가지 않는다
  ② 차단은 **엔드포인트 단위** — 403 하나가 멀쩡한 다른 엔드포인트를 막지 않는다
  ③ 429 는 차단 대상이 아니다 — 일시적 신호라 기존 재시도 경로를 유지한다
"""
from __future__ import annotations

import pytest

from api.collectors import finnhub_client as fc


class _Resp:
    def __init__(self, status: int, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    """차단 집합은 모듈 전역 — 테스트 간 누수 방지. 스로틀 sleep 도 제거(테스트 속도)."""
    fc._FORBIDDEN_ENDPOINTS.clear()
    monkeypatch.setattr(fc.time, "sleep", lambda *_a, **_k: None)
    fc._LAST_CALL = 0.0
    yield
    fc._FORBIDDEN_ENDPOINTS.clear()


def test_403_endpoint_is_called_once_then_skipped(monkeypatch):
    """① 403 확인 1회 후 같은 엔드포인트는 네트워크에 안 나간다."""
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return _Resp(403)

    monkeypatch.setattr(fc._SESSION, "get", fake_get)

    for _ in range(5):
        assert fc._get("stock/price-target", {"symbol": "AAPL"}, "k") is None

    assert len(calls) == 1, f"403 인데 {len(calls)}회 호출 — 차단기가 안 걸렸다"
    assert "stock/price-target" in fc._FORBIDDEN_ENDPOINTS


def test_forbidden_is_per_endpoint(monkeypatch):
    """② 403 한 건이 멀쩡한 엔드포인트를 막지 않는다."""
    seen = []

    def fake_get(url, params=None, timeout=None):
        seen.append(url)
        if "institutional/ownership" in url:
            return _Resp(403)
        return _Resp(200, {"ok": True})

    monkeypatch.setattr(fc._SESSION, "get", fake_get)

    assert fc._get("institutional/ownership", {"symbol": "AAPL"}, "k") is None
    assert fc._get("institutional/ownership", {"symbol": "MSFT"}, "k") is None
    # 다른 엔드포인트는 매번 정상 통과
    for t in ("AAPL", "MSFT", "NVDA"):
        assert fc._get("stock/recommendation", {"symbol": t}, "k") == {"ok": True}

    assert sum(1 for u in seen if "institutional/ownership" in u) == 1
    assert sum(1 for u in seen if "stock/recommendation" in u) == 3
    assert "stock/recommendation" not in fc._FORBIDDEN_ENDPOINTS


def test_429_is_not_forbidden_and_retries(monkeypatch):
    """③ 429 는 일시적 — 차단하지 않고 기존 재시도 경로를 유지한다."""
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return _Resp(429) if len(calls) == 1 else _Resp(200, {"v": 1})

    monkeypatch.setattr(fc._SESSION, "get", fake_get)

    assert fc._get("stock/recommendation", {"symbol": "AAPL"}, "k") == {"v": 1}
    assert len(calls) == 2, "429 재시도가 사라졌다"
    assert not fc._FORBIDDEN_ENDPOINTS


def test_consumer_contract_survives_403(monkeypatch):
    """소비처 계약 유지 — 403 이어도 호출부는 같은 shape 를 받는다.

    get_analyst_consensus 는 stock/recommendation(정상) + stock/price-target(403) 을 함께 쓴다.
    차단기가 목표가만 비우고 의견 분포는 그대로 채워야 한다 — 여기가 깨지면 Gemini 프롬프트가
    KeyError 로 죽는다.
    """
    def fake_get(url, params=None, timeout=None):
        if "price-target" in url:
            return _Resp(403)
        if "recommendation" in url:
            return _Resp(200, [{"buy": 3, "strongBuy": 2, "hold": 1, "sell": 0, "strongSell": 0}])
        return _Resp(200, {})

    monkeypatch.setattr(fc._SESSION, "get", fake_get)

    out = fc.get_analyst_consensus.__wrapped__("AAPL", "k") if hasattr(
        fc.get_analyst_consensus, "__wrapped__"
    ) else fc.get_analyst_consensus("AAPL", "k")

    for k in ("buy", "hold", "sell", "target_mean", "target_high", "target_low", "upside_pct"):
        assert k in out, f"소비처가 읽는 키 {k} 가 사라졌다"
    assert out["buy"] == 5 and out["hold"] == 1
    assert out["target_mean"] == 0 and out["upside_pct"] == 0
