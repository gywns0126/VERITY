"""🚨 RULE 1 — 공유 store 앱키 지문 충돌 시 발급 fail-closed (2026-08-09 신설).

발견 경위:
  오퍼레이터 챗에 US 실시간 시세를 붙이려고 로컬에서 KIS 해외 API 를 부르려다,
  **로컬 `.env` 앱키 지문(c72f47d5d28e) ≠ 공유 store 토큰 앱키(728e2190409c)** 를 실측했다.
  락 파일이 `data/.kis_issued_date.txt` 하나뿐이라 GH 는 앱키 1개만 쓴다 = 로컬 키는
  stale 이거나 같은 계좌의 두 번째 등록 앱이다.

잠재 구멍:
  `_kis_load_shared_token` 은 지문 불일치를 **"행 없음" 과 똑같이 None** 으로 돌려준다.
  호출부가 둘을 구분하지 못해 발급 경로로 흘러가고, 그걸 막는 건 파일 락 하나뿐이다.
  락은 커밋 전파에 의존한다 — 2026-08-09 에 `git add A B*` 글롭 미매칭으로 이틀 동결돼
  24h 가드가 항상 통과한 전례가 있다(CLAUDE.md RULE 1 사고 8-09). 락이 굳는 순간
  "같은 계좌 두 번째 토큰" 이 조용히 나간다 — 알림·에러·워크플로 실패 전부 0 인 형태다.

정정:
  실제 발급 직전에 공유 store 를 다시 보고, **같은 slug 에 다른 앱키의 유효 토큰**이 있으면
  발급하지 않고 raise 한다. store 는 cross-runner 실시간 truth 라 락이 굳어도 살아 있다.
  fail-closed 가 정답 — 못 쓰는 토큰을 하나 더 받느니 멈추는 쪽이 싸다.

  다중 계좌(0928af2) 설계와 충돌하지 않는다: 계좌가 다르면 slug 가 달라 store 행이 갈리고,
  이 검사는 **같은 slug 안에서만** 지문을 대조한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from api.trading import kis_broker as kb

KST = timezone(timedelta(hours=9))


class _Resp:
    def __init__(self, rows):
        self._rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


def _store(fp, expires_in_h=8):
    exp = (datetime.now(KST) + timedelta(hours=expires_in_h)).isoformat()
    return _Resp([{"app_key_fp": fp, "expires_at": exp}])


@pytest.fixture
def shared_env(monkeypatch):
    monkeypatch.setenv("KIS_SHARED_TOKEN", "1")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc")


def test_다른_앱키_유효토큰이_있으면_충돌로_본다(shared_env):
    with mock.patch.object(kb.requests, "get", return_value=_store("deadbeef1234")):
        assert kb._kis_shared_fp_conflict("my-key") == "deadbeef1234"


def test_같은_앱키면_충돌_아니다(shared_env):
    fp = kb._kis_app_key_fp("my-key")
    with mock.patch.object(kb.requests, "get", return_value=_store(fp)):
        assert kb._kis_shared_fp_conflict("my-key") is None


def test_만료된_토큰은_충돌_아니다(shared_env):
    """만료분까지 충돌로 보면 정상 갱신을 영구히 막는다."""
    with mock.patch.object(kb.requests, "get", return_value=_store("deadbeef1234", -1)):
        assert kb._kis_shared_fp_conflict("my-key") is None


def test_store_미도달은_발급을_막지_않는다(shared_env):
    """가용성 — Supabase 장애가 발급원을 세우면 안 된다. 락·interval 가드가 남는다."""
    with mock.patch.object(kb.requests, "get", side_effect=RuntimeError("net")):
        assert kb._kis_shared_fp_conflict("my-key") is None


def test_지문_충돌이면_HTTP_발급을_하지_않는다(tmp_path, shared_env, monkeypatch):
    """🚨 본 가드의 존재 이유 — 락이 stale 해도 두 번째 토큰이 못 나간다."""
    b = kb.KISBroker()
    b.app_key = "local-stale-key"
    b.app_secret = "secret"
    # 락을 **일부러 굳힌다**(25h 전) — 8/9 동결 사고 재현. 락만 믿으면 여기서 발급된다.
    lock = tmp_path / ".kis_issued_date.txt"
    lock.write_text((datetime.now(KST) - timedelta(hours=25)).isoformat())
    b._daily_lock_path = lambda: str(lock)  # type: ignore
    b._token = None
    b._token_expires = None
    b._issued_date = None

    with mock.patch.object(b, "_load_cached_token"), \
         mock.patch.object(b, "_apply_shared_token", return_value=False), \
         mock.patch.object(kb, "_kis_load_shared_token", return_value=None), \
         mock.patch.object(kb, "_kis_shared_fp_conflict", return_value="728e2190409c"), \
         mock.patch.object(kb.requests, "post") as mpost:
        with pytest.raises(RuntimeError, match="RULE 1"):
            b.authenticate(force_refresh=True)
    mpost.assert_not_called()   # 🚨 두 번째 토큰 HTTP 발급 없음
