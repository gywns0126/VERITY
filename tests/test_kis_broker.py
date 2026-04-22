"""KIS Broker 실자금 안전 경로 검증.

B4 (test_auto_trader_safety) 는 auto_trader 레벨 안전장치를 검증했다.
이 파일은 한 층 더 아래인 kis_broker 의 HTTP 호출 경로를 커버한다:

  · 토큰 발급/재사용/만료/daily lock
  · place_order 성공/실패/HTTP 에러/타임아웃/JSON 파싱 실패
  · get_balance 인증 전제

HTTP 호출은 전부 MockResponse + monkeypatch 로 대체. 네트워크 0.
"""
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
import requests


class _MockResponse:
    """requests.Response 흉내 — raise_for_status + json() 만 지원."""
    def __init__(self, status_code: int, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(
                f"HTTP {self.status_code}", response=self
            )

    def json(self):
        if self._json is None:
            raise ValueError("No JSON content")
        return self._json


def _fresh_broker(monkeypatch, **env):
    """깨끗한 KISBroker — env 설정 + 디스크 cache 격리.

    conftest 가 DATA_DIR 격리 → _daily_lock_path 자동 격리.
    KIS_TOKEN_CACHE_DIR 는 모듈 로드 시 ~/.cache 폴백이라 별도 tmp 주입해야
    cross-test 오염 방지.
    """
    import tempfile
    cache_dir = tempfile.mkdtemp(prefix="kis_test_cache_")
    defaults = {
        "KIS_APP_KEY": "test-app-key",
        "KIS_APP_SECRET": "test-app-secret",
        "KIS_ACCOUNT_NO": "12345678-01",
        "KIS_TOKEN_CACHE_DIR": cache_dir,
    }
    for k, v in {**defaults, **env}.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)

    # 모듈 재로드 → _TOKEN_CACHE_DIR/_TOKEN_CACHE_PATH 가 위 tmp 로 재계산
    import importlib
    import api.trading.kis_broker as mod
    importlib.reload(mod)
    return mod.KISBroker(), mod


def _ok_auth_response(token="tok-123"):
    """KIS /oauth2/tokenP 정상 응답."""
    future = (datetime.now() + timedelta(hours=20)).strftime("%Y-%m-%d %H:%M:%S")
    return _MockResponse(200, {
        "access_token": token,
        "access_token_token_expired": future,
    })


def _ok_order_response(odno="0001234"):
    """KIS /order-cash 정상 응답."""
    return _MockResponse(200, {
        "rt_cd": "0",
        "msg1": "정상처리 되었습니다.",
        "output": {"ODNO": odno, "KRX_FWDG_ORD_ORGNO": "00001"},
    })


# ═══════════════════════════════════════════════════
# authenticate — 토큰 발급
# ═══════════════════════════════════════════════════

class TestAuthenticate:
    def test_fresh_token_success(self, monkeypatch):
        broker, mod = _fresh_broker(monkeypatch)
        calls = []
        def fake_post(url, **kwargs):
            calls.append(url)
            return _ok_auth_response("tok-new")
        monkeypatch.setattr(mod.requests, "post", fake_post)

        token = broker.authenticate()
        assert token == "tok-new"
        assert len(calls) == 1
        assert "/oauth2/tokenP" in calls[0]
        assert broker._issued_date == datetime.now().strftime("%Y-%m-%d")

    def test_missing_api_key_raises(self, monkeypatch):
        broker, mod = _fresh_broker(monkeypatch, KIS_APP_KEY=None, KIS_APP_SECRET=None)
        monkeypatch.setattr(mod.requests, "post", MagicMock())
        with pytest.raises(RuntimeError, match="KIS_APP_KEY"):
            broker.authenticate()

    def test_http_error_propagates(self, monkeypatch):
        """KIS가 4xx/5xx 반환 시 requests.HTTPError 전파 (caller 가 catch)."""
        broker, mod = _fresh_broker(monkeypatch)
        def fake_post(url, **kwargs):
            return _MockResponse(500, text="Internal Server Error")
        monkeypatch.setattr(mod.requests, "post", fake_post)

        with pytest.raises(requests.exceptions.HTTPError):
            broker.authenticate()

    def test_daily_lock_reuses_cache_on_second_call(self, monkeypatch):
        """하루 1회 발급 정책 — cache 에 오늘 토큰 있으면 HTTP 재호출 안 함."""
        broker, mod = _fresh_broker(monkeypatch)
        call_count = {"n": 0}
        def fake_post(url, **kwargs):
            call_count["n"] += 1
            return _ok_auth_response("tok-once")
        monkeypatch.setattr(mod.requests, "post", fake_post)

        t1 = broker.authenticate()
        t2 = broker.authenticate()  # 두 번째 호출
        assert t1 == t2 == "tok-once"
        assert call_count["n"] == 1  # HTTP 는 1번만

    def test_daily_lock_blocks_same_day_refresh(self, monkeypatch):
        """cache 삭제했어도 오늘 이미 발급됐으면 재발급 불가 (.kis_issued_date.txt)."""
        broker, mod = _fresh_broker(monkeypatch)
        def fake_post(url, **kwargs):
            return _ok_auth_response("tok-first")
        monkeypatch.setattr(mod.requests, "post", fake_post)

        broker.authenticate()  # 첫 발급 → daily lock 파일 생성
        # 메모리 token 만 날리고 cache 도 삭제
        broker._token = None
        broker._token_expires = None
        import os as _os
        if _os.path.exists(mod._TOKEN_CACHE_PATH):
            _os.remove(mod._TOKEN_CACHE_PATH)

        # 두 번째 시도 — daily lock 이 잡고 있으므로 RuntimeError
        with pytest.raises(RuntimeError, match="오늘"):
            broker.authenticate()


# ═══════════════════════════════════════════════════
# _ensure_token — 토큰 재사용
# ═══════════════════════════════════════════════════

class TestEnsureToken:
    def test_valid_cached_token_skips_api(self, monkeypatch):
        broker, mod = _fresh_broker(monkeypatch)
        broker._token = "cached-tok"
        broker._token_expires = datetime.now(mod.KST) + timedelta(hours=5)

        spy = MagicMock()
        monkeypatch.setattr(mod.requests, "post", spy)

        tok = broker._ensure_token()
        assert tok == "cached-tok"
        spy.assert_not_called()

    def test_expired_token_triggers_authenticate(self, monkeypatch):
        broker, mod = _fresh_broker(monkeypatch)
        # 과거로 만료
        broker._token = "expired"
        broker._token_expires = datetime.now(mod.KST) - timedelta(hours=1)

        calls = []
        def fake_post(url, **kwargs):
            calls.append(url)
            return _ok_auth_response("tok-new")
        monkeypatch.setattr(mod.requests, "post", fake_post)

        tok = broker._ensure_token()
        assert tok == "tok-new"
        assert len(calls) == 1


# ═══════════════════════════════════════════════════
# place_order — 주문 실행
# ═══════════════════════════════════════════════════

class TestPlaceOrder:
    def _authed_broker(self, monkeypatch):
        broker, mod = _fresh_broker(monkeypatch)
        broker._token = "tok-prefilled"
        broker._token_expires = datetime.now(mod.KST) + timedelta(hours=10)
        return broker, mod

    def test_no_account_returns_failure_no_api_call(self, monkeypatch):
        broker, mod = _fresh_broker(monkeypatch, KIS_ACCOUNT_NO=None)
        spy = MagicMock()
        monkeypatch.setattr(mod.requests, "post", spy)

        result = broker.place_order("005930", mod.OrderSide.BUY, qty=1, price=70000)
        assert result.success is False
        assert "KIS_ACCOUNT_NO" in result.message
        spy.assert_not_called()

    def test_successful_buy_order(self, monkeypatch):
        broker, mod = _fresh_broker(monkeypatch)
        broker._token = "tok"
        broker._token_expires = datetime.now(mod.KST) + timedelta(hours=10)

        captured = {}
        def fake_post(url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs.get("headers", {})
            return _ok_order_response(odno="ABC123")
        monkeypatch.setattr(mod.requests, "post", fake_post)

        result = broker.place_order("005930", mod.OrderSide.BUY, qty=10, price=70000)
        assert result.success is True
        assert result.order_id == "ABC123"
        assert "/order-cash" in captured["url"]
        assert captured["headers"]["tr_id"] == "TTTC0802U"  # 실전 매수

    def test_successful_sell_uses_sell_tr_id(self, monkeypatch):
        broker, mod = self._authed_broker(monkeypatch)
        captured = {}
        def fake_post(url, **kwargs):
            captured["headers"] = kwargs.get("headers", {})
            return _ok_order_response()
        monkeypatch.setattr(mod.requests, "post", fake_post)

        broker.place_order("005930", mod.OrderSide.SELL, qty=5, price=80000)
        assert captured["headers"]["tr_id"] == "TTTC0801U"

    def test_rt_cd_nonzero_returns_failure(self, monkeypatch):
        broker, mod = self._authed_broker(monkeypatch)
        def fake_post(url, **kwargs):
            return _MockResponse(200, {
                "rt_cd": "1",
                "msg1": "잔고 부족",
                "output": {},
            })
        monkeypatch.setattr(mod.requests, "post", fake_post)

        result = broker.place_order("005930", mod.OrderSide.BUY, qty=100, price=70000)
        assert result.success is False
        assert "잔고 부족" in result.message

    def test_http_429_rate_limit_returns_failure(self, monkeypatch):
        """KIS rate limit (초당 20req) — 현재는 재시도 없음. success=False 확인."""
        broker, mod = self._authed_broker(monkeypatch)
        def fake_post(url, **kwargs):
            return _MockResponse(429, text="Too Many Requests")
        monkeypatch.setattr(mod.requests, "post", fake_post)

        result = broker.place_order("005930", mod.OrderSide.BUY, qty=1, price=70000)
        assert result.success is False
        assert "429" in result.message or "HTTP" in result.message

    def test_http_500_returns_failure(self, monkeypatch):
        broker, mod = self._authed_broker(monkeypatch)
        def fake_post(url, **kwargs):
            return _MockResponse(500, text="upstream failure")
        monkeypatch.setattr(mod.requests, "post", fake_post)

        result = broker.place_order("005930", mod.OrderSide.BUY, qty=1, price=70000)
        assert result.success is False

    def test_request_timeout_returns_failure(self, monkeypatch):
        broker, mod = self._authed_broker(monkeypatch)
        def fake_post(url, **kwargs):
            raise requests.exceptions.Timeout("connect timeout")
        monkeypatch.setattr(mod.requests, "post", fake_post)

        result = broker.place_order("005930", mod.OrderSide.BUY, qty=1, price=70000)
        assert result.success is False
        assert "timeout" in result.message.lower() or "Timeout" in result.message

    def test_json_parse_fail_returns_failure(self, monkeypatch):
        """KIS 가 HTML 에러 페이지 반환 시 json() 이 ValueError → success=False."""
        broker, mod = self._authed_broker(monkeypatch)
        def fake_post(url, **kwargs):
            return _MockResponse(200, json_data=None, text="<html>error</html>")
        monkeypatch.setattr(mod.requests, "post", fake_post)

        result = broker.place_order("005930", mod.OrderSide.BUY, qty=1, price=70000)
        assert result.success is False


# ═══════════════════════════════════════════════════
# get_balance — 계좌 잔고
# ═══════════════════════════════════════════════════

class TestGetBalance:
    def test_no_account_raises(self, monkeypatch):
        broker, mod = _fresh_broker(monkeypatch, KIS_ACCOUNT_NO=None)
        with pytest.raises(RuntimeError, match="KIS_ACCOUNT_NO"):
            broker.get_balance()

    def test_successful_balance(self, monkeypatch):
        broker, mod = _fresh_broker(monkeypatch)
        broker._token = "tok"
        broker._token_expires = datetime.now(mod.KST) + timedelta(hours=10)

        def fake_get(url, **kwargs):
            return _MockResponse(200, {
                "rt_cd": "0",
                "output1": [{"pdno": "005930", "hldg_qty": "10"}],
                "output2": [{"tot_evlu_amt": "700000"}],
            })
        monkeypatch.setattr(mod.requests, "get", fake_get)

        result = broker.get_balance()
        assert isinstance(result, dict)
        assert len(result["holdings"]) == 1
        assert result["summary"]["tot_evlu_amt"] == "700000"

    def test_balance_rt_cd_failure_raises(self, monkeypatch):
        broker, mod = _fresh_broker(monkeypatch)
        broker._token = "tok"
        broker._token_expires = datetime.now(mod.KST) + timedelta(hours=10)

        def fake_get(url, **kwargs):
            return _MockResponse(200, {
                "rt_cd": "1",
                "msg1": "계좌 조회 실패",
                "output1": [],
                "output2": [],
            })
        monkeypatch.setattr(mod.requests, "get", fake_get)

        with pytest.raises(RuntimeError, match="계좌 조회 실패"):
            broker.get_balance()
