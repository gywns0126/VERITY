"""LANDEX timeseries API 핸들러 단위 테스트.

검증 범위:
  - validation: gu / metric / 빈/잘못된 파라미터 → 400
  - upstream 실패 (rone 어댑터 None) → 503
  - 빈 시계열 (series=[]) → 404
  - 정상 응답 (price_index / unsold) → 200 + 표준 포맷

vercel-api 패키지가 sys.path 에 없으므로 importlib 로 직접 로드.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import types
from unittest.mock import MagicMock

import pytest


def _load_module(monkeypatch):
    """landex_timeseries.py 격리 로드. api.landex._sources.rone 도 stub 으로 주입."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # api / api.landex / api.landex._sources 패키지 stub
    for pkg in ("api", "api.landex", "api.landex._sources"):
        if pkg not in sys.modules:
            mod = types.ModuleType(pkg)
            mod.__path__ = []  # 패키지로 인식
            monkeypatch.setitem(sys.modules, pkg, mod)

    # rone stub — 테스트마다 set_attr 로 fetch 함수 주입
    rone_stub = types.ModuleType("api.landex._sources.rone")
    rone_stub.fetch_weekly_index = MagicMock(return_value=None)
    rone_stub.fetch_monthly_unsold = MagicMock(return_value=None)
    monkeypatch.setitem(sys.modules, "api.landex._sources.rone", rone_stub)
    monkeypatch.setattr(sys.modules["api.landex._sources"], "rone", rone_stub, raising=False)

    ts_path = os.path.join(
        repo_root, "vercel-api", "api", "landex_timeseries.py"
    )
    spec = importlib.util.spec_from_file_location("landex_timeseries_test", ts_path)
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "landex_timeseries_test", mod)
    spec.loader.exec_module(mod)
    return mod, rone_stub


# ─────────────────────────────────────────
# fetch_timeseries (라이브러리 함수)
# ─────────────────────────────────────────

def test_fetch_price_index_success(monkeypatch):
    mod, rone = _load_module(monkeypatch)
    rone.fetch_weekly_index.return_value = {
        "gu": "강남구",
        "series": [
            {"week": "202613", "index": 100.0, "date": "2026-03-23"},
            {"week": "202614", "index": 100.7, "date": "2026-03-30"},
        ],
        "as_of": "2026-03-30",
        "as_of_week": "202614",
        "collected_at": "2026-04-30T20:30:00+09:00",
        "source": "rone_weekly",
        "stat_id": "T244183132827305",
    }
    out = mod.fetch_timeseries("강남구", "price_index", weeks=52)
    assert out is not None
    assert out["gu"] == "강남구"
    assert out["metric"] == "price_index"
    assert out["series"] == [
        {"x": "202613", "y": 100.0, "date": "2026-03-23"},
        {"x": "202614", "y": 100.7, "date": "2026-03-30"},
    ]
    assert out["as_of"] == "2026-03-30"
    assert out["source"] == "rone_weekly"


def test_fetch_unsold_success(monkeypatch):
    mod, rone = _load_module(monkeypatch)
    rone.fetch_monthly_unsold.return_value = {
        "gu": "강남구",
        "series": [
            {"month": "202602", "unsold": 0, "date": "2026년 02월"},
            {"month": "202603", "unsold": 5, "date": "2026년 03월"},
        ],
        "as_of": "2026년 03월",
        "as_of_month": "202603",
        "collected_at": "2026-04-30T20:30:00+09:00",
        "source": "rone_unsold",
        "stat_id": "T237973129847263",
    }
    out = mod.fetch_timeseries("강남구", "unsold", months=24)
    assert out is not None
    assert out["metric"] == "unsold"
    assert out["series"] == [
        {"x": "202602", "y": 0, "date": "2026년 02월"},
        {"x": "202603", "y": 5, "date": "2026년 03월"},
    ]
    assert out["as_of_period"] == "202603"


def test_fetch_returns_none_on_upstream_failure(monkeypatch):
    mod, rone = _load_module(monkeypatch)
    rone.fetch_weekly_index.return_value = None
    assert mod.fetch_timeseries("강남구", "price_index", weeks=52) is None


def test_fetch_invalid_metric_returns_none(monkeypatch):
    mod, _ = _load_module(monkeypatch)
    assert mod.fetch_timeseries("강남구", "garbage") is None


def test_fetch_clamps_weeks_to_max(monkeypatch):
    mod, rone = _load_module(monkeypatch)
    rone.fetch_weekly_index.return_value = {"series": [], "source": "rone_weekly"}
    mod.fetch_timeseries("강남구", "price_index", weeks=99999)
    # weeks 인자가 MAX_WEEKS 로 클램프됐는지 확인
    args, kwargs = rone.fetch_weekly_index.call_args
    assert kwargs["weeks"] == mod.MAX_WEEKS


# ─────────────────────────────────────────
# handler — HTTP 인터페이스
# ─────────────────────────────────────────

class _FakeRequest:
    """BaseHTTPRequestHandler 테스트용 최소 stub."""
    def __init__(self, path: str):
        self._path = path
    def makefile(self, *a, **kw):
        return io.BytesIO(b"")


def _invoke_get(mod, path: str):
    """handler.do_GET 만 호출. send_* 부분은 stub 으로 캡처."""
    h = mod.handler.__new__(mod.handler)
    h.path = path
    h.wfile = io.BytesIO()
    captured = {"status": None, "headers": []}
    def _send_response(status):
        captured["status"] = status
    def _send_header(k, v):
        captured["headers"].append((k, v))
    def _end_headers():
        pass
    h.send_response = _send_response
    h.send_header = _send_header
    h.end_headers = _end_headers
    h.do_GET()
    body_bytes = h.wfile.getvalue()
    body = json.loads(body_bytes.decode("utf-8")) if body_bytes else None
    return captured["status"], captured["headers"], body


def test_handler_invalid_gu_returns_400(monkeypatch):
    mod, _ = _load_module(monkeypatch)
    status, _hdr, body = _invoke_get(mod, "/api/landex/timeseries?gu=Gangnam&metric=price_index")
    assert status == 400
    assert body["error"] == "invalid_gu"


def test_handler_invalid_metric_returns_400(monkeypatch):
    mod, _ = _load_module(monkeypatch)
    status, _hdr, body = _invoke_get(mod, "/api/landex/timeseries?gu=강남구&metric=garbage")
    assert status == 400
    assert body["error"] == "invalid_metric"


def test_handler_upstream_failure_returns_503(monkeypatch):
    mod, rone = _load_module(monkeypatch)
    rone.fetch_weekly_index.return_value = None
    status, _hdr, body = _invoke_get(
        mod, "/api/landex/timeseries?gu=강남구&metric=price_index&weeks=52"
    )
    assert status == 503
    assert body["error"] == "upstream_unavailable"


def test_handler_empty_series_returns_404(monkeypatch):
    mod, rone = _load_module(monkeypatch)
    rone.fetch_weekly_index.return_value = {
        "series": [], "source": "rone_weekly",
        "as_of": None, "as_of_week": None, "collected_at": "x", "stat_id": "y",
    }
    status, _hdr, body = _invoke_get(
        mod, "/api/landex/timeseries?gu=강남구&metric=price_index&weeks=52"
    )
    assert status == 404
    assert body["error"] == "no_data"


def test_handler_success_200_with_cache_header(monkeypatch):
    mod, rone = _load_module(monkeypatch)
    rone.fetch_weekly_index.return_value = {
        "gu": "강남구",
        "series": [
            {"week": "202614", "index": 100.7, "date": "2026-03-30"},
            {"week": "202615", "index": 101.5, "date": "2026-04-06"},
        ],
        "as_of": "2026-04-06",
        "as_of_week": "202615",
        "collected_at": "2026-04-30T20:30:00+09:00",
        "source": "rone_weekly",
        "stat_id": "T244183132827305",
    }
    status, hdr, body = _invoke_get(
        mod, "/api/landex/timeseries?gu=강남구&metric=price_index&weeks=52"
    )
    assert status == 200
    assert body["gu"] == "강남구"
    assert body["metric"] == "price_index"
    assert body["count"] == 2
    assert body["series"][0] == {"x": "202614", "y": 100.7, "date": "2026-03-30"}
    # 캐시 헤더 확인
    cache_headers = [v for k, v in hdr if k == "Cache-Control"]
    assert any("max-age=3600" in v for v in cache_headers)
