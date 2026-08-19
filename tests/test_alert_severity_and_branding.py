"""알림 등급 판정 + 텔레그램 브랜드 표기 두 건을 고정한다 (2026-08-19).

## ① 등급 — 비핵심 소스가 🔴 를 내면 안 된다

PM 이 받은 알림: `🔴 데이터 소스 장애: public_data · core_sources_ok: True`.
**핵심 소스는 다 살아 있는데 최고 등급**이 나갔다. 원인 = `alert_dispatcher` 가
`core_sources_ok` 를 details 에만 싣고 판정에 쓰지 않았다. `overall_status` 는 전 소스의
최악값(`data_health.py:270 worst_status`)이라 비핵심 1건이 전체를 critical 로 만든다.

실측 — latency **17,572ms** = `_TIMEOUT_DEFAULT 8s × 2회 + sleep 1s` 에 정확히 일치 =
양쪽 시도 모두 응답 드롭(느려진 게 아니다). 같은 시각 로컬 한국 IP 프로브 **2,566ms 정상**.
앞뒤 실행도 정상(8/17 1,044ms · 8/19 1,205ms) = 지속 장애 아닌 러너 IP 단발 드롭.
즉 소스가 아니라 **등급**이 결함이었다.

🚨 삼키지는 않는다 — 🟡 로 내리되 계속 신고한다. 빈도가 사라지면 진짜 열화를 못 본다.

## ② 브랜드 — 텔레그램 발송 문자열에 브랜드명 0

PM 지시 "텔레그램에 배리티라고 나오는거 전부 없애버려".
🚨 알파네스트로 바꾸지 않는다 — 텔레그램은 PM 1인 비공개 채널이고
`AlphaNest = 공개 터미널 / VERITY = 비공개 백엔드` 라 방향이 거꾸로다.
알림 내용이 brain_score·funnel·VAMS 같은 비공개 자산이라 공개 브랜드를 달면 그 자산이
공개 것으로 보인다 — 4회 재발한 혼동이다([[feedback_verity_vs_alphanest_identity]]).
"""
from __future__ import annotations

import ast
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parent.parent

_TELEGRAM_MODULES = (
    "api/notifications/telegram.py",
    "api/notifications/telegram_bot.py",
    "api/observability/alert_dispatcher.py",
)


def _emitted_strings(path: pathlib.Path):
    """AST 로 **문자열 리터럴만** — 주석·docstring 은 이력 설명이라 허용."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            d = ast.get_docstring(n, clean=False)
            if d:
                docs.add(d)
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value not in docs:
            yield n.lineno, n.value


def test_no_brand_in_telegram_output():
    hits = []
    for rel in _TELEGRAM_MODULES:
        p = _ROOT / rel
        for lineno, val in _emitted_strings(p):
            if "VERITY_TELEGRAM" in val:      # env 변수명은 대상 아님
                continue
            for brand in ("VERITY", "배리티", "AlphaNest", "알파네스트"):
                if brand in val:
                    hits.append(f"{rel}:{lineno} — {brand!r} in {val[:60]!r}")
    assert not hits, "텔레그램 발송 문자열에 브랜드명이 있다:\n  " + "\n  ".join(hits)


def test_dead_admin_link_not_sent():
    """폐기된 구 프레이머 admin 링크를 알림마다 보내지 않는다."""
    for rel in _TELEGRAM_MODULES:
        for lineno, val in _emitted_strings(_ROOT / rel):
            assert "brain-monitor" not in val, f"{rel}:{lineno} 폐기 링크 — {val[:60]!r}"


def _health(**status):
    src = {k: {"status": v} for k, v in status.items()}
    core = {"yfinance", "fred", "kis", "dart"}
    core_ok = not any(s == "critical" for k, s in status.items() if k in core)
    worst = "critical" if "critical" in status.values() else (
        "warning" if "warning" in status.values() else "ok")
    src["_meta"] = {"overall_status": worst, "core_sources_ok": core_ok}
    return src


def _msgs(health):
    """`_build_messages(health, drift, trust, state)` 직접 호출 — 동적 탐색 금지.

    🚨 최초 판본은 `dir()` 로 "alerts 로 끝나는 함수" 를 찾았다. 그런 함수가 없어
    엉뚱한 것을 잡고 빈 리스트를 받았다 — 테스트가 실패 이유를 코드가 아니라 자기
    탐색 로직에서 만들어냈다. 시그니처를 확인하고 고정한다.
    """
    from api.observability.alert_dispatcher import _build_messages
    return _build_messages(health, {}, {}, {})


def test_noncore_only_failure_is_warning_not_critical():
    """🚨 핵심 4종이 살아 있으면 비핵심 장애는 🟡 — PM 이 받은 그 알림 케이스."""
    alerts = _msgs(_health(public_data="critical", yfinance="ok", fred="ok",
                           kis="ok", dart="ok"))
    dh = [a for a in alerts if a.get("topic") == "data_health"]
    assert dh, f"data_health 알림이 없다: {alerts}"
    assert dh[0]["level"] == "warning", f"비핵심 단독 장애가 {dh[0]['level']} 로 나갔다"
    assert "비핵심" in dh[0]["message"]
    assert dh[0]["details"]["core_bad"] == []
    # 🚨 삼키지 않는다 — 어느 소스였는지 계속 신고한다
    assert "public_data" in dh[0]["details"]["bad_sources"]


def test_core_failure_stays_critical():
    """핵심 소스가 죽으면 🔴 를 유지한다 — 등급을 내리는 게 목적이 아니다."""
    alerts = _msgs(_health(dart="critical", yfinance="ok", fred="ok", kis="ok"))
    dh = [a for a in alerts if a.get("topic") == "data_health"]
    assert dh and dh[0]["level"] == "critical", f"핵심 장애가 강등됐다: {dh}"
    assert "dart" in dh[0]["details"]["core_bad"]


def test_mixed_failure_is_critical():
    """핵심 + 비핵심 동시 = 🔴. 비핵심이 섞였다고 강등되면 안 된다."""
    alerts = _msgs(_health(dart="critical", public_data="critical",
                           yfinance="ok", fred="ok", kis="ok"))
    dh = [a for a in alerts if a.get("topic") == "data_health"]
    assert dh and dh[0]["level"] == "critical"
    assert set(dh[0]["details"]["bad_sources"]) >= {"dart", "public_data"}
