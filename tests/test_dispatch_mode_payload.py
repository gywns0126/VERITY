"""Vercel dispatch 가 워크플로 모드를 실어 보내는지 고정한다 (2026-08-20).

## 왜

`daily_analysis_full` 의 모드 분기는 `github.event.schedule` **문자열 매칭**이다.
그런데 실제 트리거는 GH schedule 이 아니라 **Vercel `repository_dispatch`** 다
(schedule silent miss 회피용 fallback 이 사실상 주 경로가 됐다).

dispatch 경로에서는 `github.event.schedule` 이 **빈 문자열**이므로 모든 `elif` 가
불일치하고 `else → mode=full` 로 흐른다. KST 06:30(UTC 21:30) 슬롯은 `full_us`
(미장 전체)여야 하는데 매번 `full`(미장 **상위 10개**)로 돌았다.

🚨 실측 2026-08-20 06:30 run(32304227272):
    ANALYSIS_MODE: full
    [5.71] 미장 데이터 수집 — 상위 10개 (10종목, Finnhub/SEC/yfinance)
Finnhub 커버가 US 29/49 로 보이던 원인이 이것이다. mock 도 rate limit 도 아니었다
(같은 run 의 MOCK CENSUS = finnhub 0건 · rate_limit=0).

워크플로 주석이 이미 경고했다 — *"cron 문자열 매칭이라 스케줄을 옮기면 else 로 흘러간다"*.
dispatch 는 schedule 이 아니므로 그 매칭이 **구조적으로** 성립하지 않는다.
"""
from __future__ import annotations

import importlib.util
import pathlib
from datetime import datetime, timezone

import yaml

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _dp():
    spec = importlib.util.spec_from_file_location(
        "dp", _ROOT / "vercel-api" / "api" / "cron" / "dispatch_pulse.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _full_events(dt):
    out = []
    for e in _dp()._resolve_events(dt):
        name = e[0] if isinstance(e, tuple) else e
        if name == "daily_analysis_full":
            out.append(e)
    return out


def test_us_close_slot_carries_full_us_mode():
    """🚨 KST 06:30 슬롯은 full_us 를 payload 로 실어야 한다."""
    ev = _full_events(datetime(2026, 8, 19, 21, 30, tzinfo=timezone.utc))  # UTC 수 21:30
    assert ev, "US 마감 슬롯에서 daily_analysis_full 이 발화하지 않는다"
    assert isinstance(ev[0], tuple), f"payload 없이 보낸다: {ev[0]!r} — full 로 흘러간다"
    assert ev[0][1].get("mode") == "full_us", ev[0]


def test_kr_close_slot_stays_default():
    """KST 16:50 슬롯은 full(KR) — payload 없이 보내 기본값을 쓴다."""
    ev = _full_events(datetime(2026, 8, 20, 7, 50, tzinfo=timezone.utc))  # UTC 목 07:50
    assert ev and not isinstance(ev[0], tuple), f"KR 슬롯에 모드가 붙었다: {ev}"


def test_workflow_reads_client_payload_before_cron():
    """워크플로가 client_payload.mode 를 CRON 매칭보다 **먼저** 본다."""
    src = (_ROOT / ".github" / "workflows" / "daily_analysis_full.yml").read_text(encoding="utf-8")
    assert "github.event.client_payload.mode" in src, "payload 를 읽지 않는다"
    i_pay = src.index("DISPATCH_MODE")
    i_cron = src.index('elif [ "$CRON" =')
    assert i_pay < i_cron, "CRON 분기가 payload 보다 먼저다 — dispatch 모드가 무시된다"
    yaml.safe_load(src)


def test_dispatch_sends_client_payload_field():
    """`_dispatch` 가 payload 를 GitHub 규격 필드명으로 싣는다."""
    src = (_ROOT / "vercel-api" / "api" / "cron" / "dispatch_pulse.py").read_text(encoding="utf-8")
    assert '"client_payload"' in src, "client_payload 키가 없다 — GitHub 이 모드를 못 받는다"
