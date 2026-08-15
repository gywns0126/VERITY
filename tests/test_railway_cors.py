"""Railway 시세 서버 CORS 회귀 테스트 (네트워크 0).

2026-08-15 신설. 배포본이 `access-control-allow-origin: *` 였다(실측: 임의 Origin
`evil.example.com` 으로 /chart/005930 호출 → HTTP 200 + ACAO `*`).

이 서버의 시세 라우트(/chart /quotes /snapshot /candles /stream)는 인증이 없고
KIS 실시간 현재가를 그대로 반환한다. 이 프로젝트의 자체 규율은
"KIS raw 시세 = 제3자 재배포 불가, 본인 이용은 합법"이다
(api/collectors/fsc_daily_prices.py 상단, docs/MIGRATION_KRX_QUOTE_REDISTRIBUTION_2026_07.md).

⚠️ 범위 — CORS 는 브라우저 정책일 뿐이다. curl·서버 호출은 이걸로 막히지 않는다(실측).
   서버 대 서버 소비자(ticker_facts·kis_quote)는 영향 없다.
   여기서 닫는 것은 "제3자 웹사이트가 브라우저 JS 로 시세를 읽어가는" 벡터뿐이고,
   인증·rate limit 은 별건으로 남아 있다.

🚨 주문 라우트는 이미 fail-closed 다 (/api/order → 401 실측). 그 가드는 건드리지 않는다.
"""
from __future__ import annotations

import os
import re
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)


def _load(monkeypatch, env=None):
    """server.config 를 원하는 env 로 재로드."""
    for k in ("ALLOWED_ORIGINS", "ALLOWED_ORIGIN_REGEX"):
        monkeypatch.delenv(k, raising=False)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    for m in [m for m in list(sys.modules) if m.startswith("server.config")]:
        del sys.modules[m]
    import server.config as cfg
    return cfg


def _allowed(cfg, origin: str) -> bool:
    return origin in cfg.ALLOWED_ORIGINS or bool(re.match(cfg.ALLOWED_ORIGIN_REGEX, origin))


def test_no_wildcard_by_default(monkeypatch):
    """env 미설정에서도 '*' 가 나오면 안 된다 — 배포본이 정확히 그 상태였다."""
    cfg = _load(monkeypatch)
    assert "*" not in cfg.ALLOWED_ORIGINS
    assert cfg.ALLOWED_ORIGINS, "빈 목록이면 공개 사이트가 죽는다"


def test_env_wildcard_is_stripped(monkeypatch):
    """env 에 '*' 를 넣어도 무시한다 (cors_helper 정합)."""
    cfg = _load(monkeypatch, {"ALLOWED_ORIGINS": "*,https://www.alphanest.kr"})
    assert "*" not in cfg.ALLOWED_ORIGINS
    assert "https://www.alphanest.kr" in cfg.ALLOWED_ORIGINS


def test_production_origins_survive_env_absence(monkeypatch):
    """env 누락·오설정에도 공개 사이트 origin 은 코드 기본으로 남는다."""
    cfg = _load(monkeypatch)
    for o in ("https://www.alphanest.kr", "https://alphanest.kr"):
        assert _allowed(cfg, o), o


def test_framer_preview_domains_allowed(monkeypatch):
    """공개 컴포넌트(RealtimeChartProbe)가 EventSource 로 /stream 에 붙는다.

    프리뷰 도메인을 빠뜨리면 라이브 차트가 죽는다 — 이 테스트가 그 회귀를 막는다.
    """
    cfg = _load(monkeypatch)
    for o in ("https://verity.framer.website", "https://a-b.framer.app",
              "https://x.y.framer.website"):
        assert _allowed(cfg, o), o


def test_third_party_origin_blocked(monkeypatch):
    """제3자 사이트는 차단 — 이 변경의 목적."""
    cfg = _load(monkeypatch)
    for o in ("https://evil.example.com", "https://alphanest.kr.evil.com",
              "https://framer.app.evil.com", "http://alphanest.kr"):
        assert not _allowed(cfg, o), o


def test_env_can_add_origins(monkeypatch):
    """운영 중 origin 추가는 코드 배포 없이 env 로 가능해야 한다."""
    cfg = _load(monkeypatch, {"ALLOWED_ORIGINS": "https://new.example.com"})
    assert _allowed(cfg, "https://new.example.com")
    assert _allowed(cfg, "https://www.alphanest.kr"), "기본 origin 이 사라지면 안 된다"


def test_middleware_wires_regex():
    """config 의 regex 가 실제로 CORSMiddleware 에 전달돼야 한다."""
    with open(os.path.join(_ROOT, "server", "main.py"), encoding="utf-8") as f:
        src = f.read()
    assert "allow_origin_regex=ALLOWED_ORIGIN_REGEX" in src
    # 주석 안의 설명 문자열(옛 설정 인용)은 제외하고 실제 코드만 본다
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert 'allow_origins=["*"]' not in code


def test_order_route_auth_untouched():
    """🚨 /api/order 는 fail-closed 인증 유지 (실측 401). 이 가드 제거 금지."""
    with open(os.path.join(_ROOT, "server", "main.py"), encoding="utf-8") as f:
        src = f.read()
    assert src.count("_order_auth_fail_response(request)") >= 2, (
        "주문 GET/POST 양쪽의 인증 호출이 있어야 한다")
    assert "RAILWAY_SHARED_SECRET" in src


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
